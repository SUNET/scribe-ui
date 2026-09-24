# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Where a recording waits on this server between the browser and the backend.

A recording reaches the server in parts, while it is still being recorded,
rather than as one upload at the end: an hour-long lecture is tens of
megabytes, a single POST of that over lecture-hall wifi fails at 90% and
starts again from zero, and the professor is left holding a phone at the
front of an empty room waiting for it.  Parts are small and idempotent -- the
same part sent twice is the same file written twice -- so a part that never
got an answer is simply sent again.

Nothing here is the only copy.  The browser keeps every chunk in IndexedDB
until the backend has said it holds the finished file (see
static/recorder_engine.js), so staging may be lost at any moment -- a
container restart, the sweep, a full disk -- and the worst that costs is
sending those parts again.

Layout, one directory per recording::

    <root>/<owner>/<rid>/part-000000
                        /part-000001
                        /done.json      once the backend has taken it

`owner` is derived on the server from the signed-in user, never taken from
the request, so one user cannot name another's directory; `rid` and `seq`
are validated to a fixed shape before they ever reach a path.
"""

import json
import os
import re
import shutil
import tempfile
import time

from pathlib import Path

# 32 lower-case hex characters: crypto.randomUUID() without its dashes.
RID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
OWNER_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# A part is ~30 seconds of audio: about 240 KB at the 64 kbit/s the recorder
# asks for.  Some browsers ignore the bitrate they are asked for, so the
# limit leaves an order of magnitude of room rather than being tight.
MAX_PART_BYTES = 16 * 1024 * 1024

# 20000 parts of 30 seconds is over a week of audio; the limit exists so a
# part number cannot be used to make an arbitrarily long file name.
MAX_PARTS = 20000

# The same ceiling the upload dialog states for a file.
MAX_RECORDING_BYTES = 4 * 1024 * 1024 * 1024

PART_PREFIX = "part-"
DONE_FILE = "done.json"


class StagingError(Exception):
    """
    A request that can never succeed as sent -- a malformed id, a part too
    large.  Distinct from a missing part, which is answered by sending it.
    """


def default_root() -> Path:
    return Path(tempfile.gettempdir()) / "scribe-recordings"


class RecordingStaging:
    """
    The parts of recordings not yet handed to the backend.

    Every method is synchronous and touches the disk; the routes call them
    through asyncio.to_thread so a slow disk never stalls the event loop.
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else default_root()

    def _dir(self, owner: str, rid: str) -> Path:
        if not OWNER_PATTERN.match(owner or ""):
            raise StagingError("bad owner")

        if not RID_PATTERN.match(rid or ""):
            raise StagingError("bad recording id")

        return self.root / owner / rid

    @staticmethod
    def _part_name(seq: int) -> str:
        if not isinstance(seq, int) or seq < 0 or seq >= MAX_PARTS:
            raise StagingError("bad part number")

        return f"{PART_PREFIX}{seq:06d}"

    def write_part(self, owner: str, rid: str, seq: int, data: bytes) -> None:
        """
        Store one part.  Written to a temporary name and renamed into place,
        so a part is either whole or absent -- a crash half way through a
        write must never leave a short part that looks complete.
        """

        name = self._part_name(seq)

        if len(data) == 0:
            raise StagingError("empty part")

        if len(data) > MAX_PART_BYTES:
            raise StagingError("part too large")

        directory = self._dir(owner, rid)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".incoming-")

        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, directory / name)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

        # A recording still being added to is not stale, whatever its
        # creation time says -- the sweep goes by the directory's mtime.
        os.utime(directory)

    def parts(self, owner: str, rid: str) -> list[int]:
        """
        The part numbers held, in order.  Empty for a recording never seen,
        which is also what a recording lost to a restart looks like.
        """

        directory = self._dir(owner, rid)

        if not directory.is_dir():
            return []

        held = []

        for entry in directory.iterdir():
            if entry.name.startswith(PART_PREFIX):
                try:
                    held.append(int(entry.name[len(PART_PREFIX) :]))
                except ValueError:
                    continue

        return sorted(held)

    def missing(self, owner: str, rid: str, count: int) -> list[int]:
        if count < 1 or count > MAX_PARTS:
            raise StagingError("bad part count")

        held = set(self.parts(owner, rid))

        return [seq for seq in range(count) if seq not in held]

    def assemble(self, owner: str, rid: str, count: int) -> Path:
        """
        Join parts 0..count-1 into one file, in order, and return its path.

        Refuses when any part is missing; the caller asks for `missing()`
        first and tells the browser which to send.  Joining is plain
        concatenation: MediaRecorder's timesliced output is one stream cut
        into pieces, and the pieces put back together are that stream.
        """

        missing = self.missing(owner, rid, count)

        if missing:
            raise StagingError(f"{len(missing)} parts missing")

        directory = self._dir(owner, rid)
        total = sum(
            (directory / self._part_name(seq)).stat().st_size for seq in range(count)
        )

        if total > MAX_RECORDING_BYTES:
            raise StagingError("recording too large")

        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".assembled-")

        with os.fdopen(fd, "wb") as out:
            for seq in range(count):
                with open(directory / self._part_name(seq), "rb") as part:
                    shutil.copyfileobj(part, out, 1024 * 1024)

        return Path(tmp)

    def done(self, owner: str, rid: str) -> dict | None:
        """
        What the backend answered when it took this recording, or None.

        Kept after the parts are gone so that a finish retried after its
        answer was lost -- the connection dropped on the way back -- is told
        it already succeeded rather than creating the job a second time.
        """

        path = self._dir(owner, rid) / DONE_FILE

        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def mark_done(self, owner: str, rid: str, result: dict) -> None:
        """
        Record the backend's answer and drop the audio.  The audio is only
        ever held here on its way somewhere else, and once the backend has
        it there is no reason for a second copy to sit on this server.
        """

        directory = self._dir(owner, rid)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)

        tmp = directory / f".{DONE_FILE}.tmp"
        tmp.write_text(json.dumps(result))
        os.replace(tmp, directory / DONE_FILE)

        for entry in directory.iterdir():
            if entry.name != DONE_FILE:
                try:
                    entry.unlink()
                except (FileNotFoundError, IsADirectoryError):
                    pass

    def discard(self, owner: str, rid: str) -> None:
        shutil.rmtree(self._dir(owner, rid), ignore_errors=True)

    def sweep(self, max_age_seconds: float, now: float | None = None) -> int:
        """
        Remove recordings nobody has touched for `max_age_seconds`.

        Safe by construction: the browser still holds everything it has not
        been told the backend took, and sends it again if it is asked for.
        Returns how many recordings were removed.
        """

        now = time.time() if now is None else now
        removed = 0

        if not self.root.is_dir():
            return 0

        for owner_dir in self.root.iterdir():
            if not owner_dir.is_dir():
                continue

            for rec_dir in owner_dir.iterdir():
                try:
                    stale = now - rec_dir.stat().st_mtime > max_age_seconds
                except FileNotFoundError:
                    continue

                if stale and rec_dir.is_dir():
                    shutil.rmtree(rec_dir, ignore_errors=True)
                    removed += 1

            try:
                owner_dir.rmdir()
            except OSError:
                pass

        return removed

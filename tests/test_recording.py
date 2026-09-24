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
Recording: the server's half.

What the browser does to keep a recording -- IndexedDB, retrying, recovering
a crashed tab -- is tested in tests/js/recorder_engine.test.js, run from here
when node is available.  What is tested here is the staging a recording
passes through on this server, and the routes' answers, since the browser's
retry logic is built on exactly which status means what.
"""

import asyncio
import json
import os
import pathlib
import re
import shutil
import subprocess
import time

import httpx
import pytest

from fastapi import HTTPException
from starlette.requests import Request

from utils import recording_api
from utils.recording_staging import (
    MAX_PART_BYTES,
    MAX_PARTS,
    RecordingStaging,
    StagingError,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OWNER = "0" * 32
RID = "f" * 32


@pytest.fixture
def staging(tmp_path):
    return RecordingStaging(tmp_path)


# -- Staging ---------------------------------------------------------------


def test_parts_join_in_order_whatever_order_they_arrived(staging):
    staging.write_part(OWNER, RID, 2, b"cc")
    staging.write_part(OWNER, RID, 0, b"aa")
    staging.write_part(OWNER, RID, 1, b"bb")

    assert staging.parts(OWNER, RID) == [0, 1, 2]
    joined = staging.assemble(OWNER, RID, 3)
    assert joined.read_bytes() == b"aabbcc"


def test_a_part_sent_twice_is_the_same_part(staging):
    staging.write_part(OWNER, RID, 0, b"aa")
    staging.write_part(OWNER, RID, 0, b"aa")

    assert staging.parts(OWNER, RID) == [0]


def test_missing_parts_are_named_and_block_assembly(staging):
    staging.write_part(OWNER, RID, 0, b"aa")
    staging.write_part(OWNER, RID, 2, b"cc")

    assert staging.missing(OWNER, RID, 4) == [1, 3]
    with pytest.raises(StagingError):
        staging.assemble(OWNER, RID, 4)


def test_an_unknown_recording_holds_nothing(staging):
    assert staging.parts(OWNER, RID) == []
    assert staging.done(OWNER, RID) is None


@pytest.mark.parametrize(
    "owner, rid",
    [
        (OWNER, "../" + "f" * 29),
        (OWNER, "F" * 32),
        (OWNER, "f" * 31),
        ("../etc", RID),
        ("", RID),
    ],
)
def test_ids_that_could_reach_outside_staging_are_refused(staging, owner, rid):
    with pytest.raises(StagingError):
        staging.write_part(owner, rid, 0, b"x")


@pytest.mark.parametrize("seq", [-1, MAX_PARTS])
def test_part_numbers_out_of_range_are_refused(staging, seq):
    with pytest.raises(StagingError):
        staging.write_part(OWNER, RID, seq, b"x")


def test_empty_and_oversized_parts_are_refused(staging):
    with pytest.raises(StagingError):
        staging.write_part(OWNER, RID, 0, b"")
    with pytest.raises(StagingError):
        staging.write_part(OWNER, RID, 0, b"x" * (MAX_PART_BYTES + 1))


def test_no_half_written_part_is_ever_counted(staging, monkeypatch):
    # A crash mid-write must leave the part absent, not short.
    def explode(src, dst):
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", explode)
    with pytest.raises(OSError):
        staging.write_part(OWNER, RID, 0, b"aa")

    monkeypatch.undo()
    assert staging.parts(OWNER, RID) == []
    leftovers = list((staging.root / OWNER / RID).iterdir())
    assert leftovers == []


def test_done_drops_the_audio_and_remembers_the_answer(staging):
    staging.write_part(OWNER, RID, 0, b"aa")
    staging.mark_done(OWNER, RID, {"uuid": "job"})

    assert staging.done(OWNER, RID) == {"uuid": "job"}
    assert staging.parts(OWNER, RID) == []
    assert [p.name for p in (staging.root / OWNER / RID).iterdir()] == ["done.json"]


def test_sweep_removes_only_what_nobody_touched(staging):
    staging.write_part(OWNER, RID, 0, b"aa")
    fresh = "e" * 32
    staging.write_part(OWNER, fresh, 0, b"aa")

    old = time.time() - 10 * 3600
    os.utime(staging.root / OWNER / RID, (old, old))

    assert staging.sweep(3600) == 1
    assert staging.parts(OWNER, RID) == []
    assert staging.parts(OWNER, fresh) == [0]


def test_staging_directories_are_private(staging):
    staging.write_part(OWNER, RID, 0, b"aa")
    mode = (staging.root / OWNER / RID).stat().st_mode & 0o777
    assert mode & 0o077 == 0


# -- The routes -------------------------------------------------------------


def request(method="POST", body=b"", headers=None):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    sent = {"done": False}

    async def receive():
        if sent["done"]:
            return {"type": "http.disconnect"}
        sent["done"] = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {"type": "http", "method": method, "path": "/", "headers": raw, "query_string": b""},
        receive,
    )


@pytest.fixture
def api(tmp_path, monkeypatch):
    """
    The routes with a signed-in caller and a fake backend.
    """

    monkeypatch.setattr(recording_api, "staging", RecordingStaging(tmp_path))
    monkeypatch.setattr(recording_api, "_caller", lambda request: OWNER)
    monkeypatch.setattr(recording_api, "_finish_locks", {})

    backend = {"calls": 0, "status": 200, "raise": None, "bodies": []}

    async def post(path, filename, mime):
        backend["calls"] += 1
        backend["bodies"].append((pathlib.Path(path).read_bytes(), filename, mime))
        if backend["raise"]:
            raise backend["raise"]
        return httpx.Response(
            backend["status"],
            json={"result": {"uuid": f"job-{backend['calls']}"}},
        )

    monkeypatch.setattr(recording_api, "_post_to_backend", post)
    return backend


def finish(parts, name="Lecture", mime="audio/webm"):
    body = json.dumps({"parts": parts, "name": name, "mime": mime}).encode()
    return asyncio.run(recording_api.recording_finish(RID, request(body=body)))


def put(seq, data):
    return asyncio.run(
        recording_api.recording_part(RID, seq, request("PUT", data, {"content-length": str(len(data))}))
    )


def payload(response):
    return response.status_code, json.loads(response.body)


def test_finish_hands_the_joined_file_to_the_backend_once(api):
    put(0, b"aa")
    put(1, b"bb")

    status, body = payload(finish(2, name="Lecture: week 3"))
    assert status == 200
    assert body["done"]["uuid"] == "job-1"
    assert api["bodies"] == [(b"aabb", "Lecture_ week 3.webm", "audio/webm")]

    # The answer was lost and the browser asks again: the same job, not a
    # second one.
    status, body = payload(finish(2))
    assert body["done"]["uuid"] == "job-1"
    assert api["calls"] == 1


def test_finish_names_the_parts_it_still_needs(api):
    put(0, b"aa")

    status, body = payload(finish(3))
    assert status == 409
    assert body["missing"] == [1, 2]
    assert api["calls"] == 0


@pytest.mark.parametrize(
    "backend_status, answer",
    [(500, 503), (502, 503), (503, 503), (429, 503), (401, 401), (400, 422), (413, 422)],
)
def test_backend_answers_become_retry_or_give_up(api, backend_status, answer):
    put(0, b"aa")
    api["status"] = backend_status

    with pytest.raises(HTTPException) as caught:
        finish(1)

    assert caught.value.status_code == answer
    # Nothing is dropped on a failure: the next finish can still succeed.
    assert recording_api.staging.parts(OWNER, RID) == [0]


def test_an_unreachable_backend_is_try_again(api):
    put(0, b"aa")
    api["raise"] = httpx.ConnectError("down")

    with pytest.raises(HTTPException) as caught:
        finish(1)

    assert caught.value.status_code == 503
    api["raise"] = None
    status, _ = payload(finish(1))
    assert status == 200


def test_an_oversized_part_is_refused_before_it_is_read(api):
    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            recording_api.recording_part(
                RID, 0, request("PUT", b"", {"content-length": str(MAX_PART_BYTES + 1)})
            )
        )
    assert caught.value.status_code == 422


def test_only_audio_types_are_accepted(api):
    put(0, b"aa")
    with pytest.raises(HTTPException) as caught:
        finish(1, mime="text/html")
    assert caught.value.status_code == 422


def test_file_names_get_the_extension_their_audio_has():
    assert recording_api._file_name("Lecture", "audio/mp4") == "Lecture.m4a"
    assert recording_api._file_name("Lecture.webm", "audio/webm;codecs=opus") == "Lecture.webm"
    assert recording_api._file_name("", "audio/ogg") == "Recording.ogg"
    assert "/" not in recording_api._file_name("../../x", "audio/webm")


def test_every_route_wants_the_custom_header():
    # A cross-site page cannot set it without a preflight this app never
    # answers -- on top of the session cookie being SameSite=Lax.
    with pytest.raises(HTTPException) as caught:
        recording_api._caller(request())
    assert caught.value.status_code == 400


def test_the_owner_key_is_stable_and_says_nothing_about_who():
    key = recording_api.recording_owner("someone@example.org")
    assert key == recording_api.recording_owner("someone@example.org")
    assert key != recording_api.recording_owner("someone.else@example.org")
    assert re.fullmatch(r"[0-9a-f]{32}", key)
    assert "someone" not in key
    assert recording_api.recording_owner(None) is None


# -- The pages ---------------------------------------------------------------


def test_the_recorder_survives_a_long_loss_of_connection():
    # Past reconnect_timeout NiceGUI reloads the page, and a reload stops
    # the MediaRecorder. A lecture-hall wifi drop must not do that.
    from pages import record

    assert record.RECONNECT_TIMEOUT >= 2 * 3600
    assert "reconnect_timeout=RECONNECT_TIMEOUT" in (ROOT / "pages" / "record.py").read_text()


def test_the_recorder_is_not_logged_out_mid_recording():
    source = (ROOT / "pages" / "record.py").read_text()
    assert "on_session_end=" in source


def test_the_files_page_offers_recording_and_resumes_uploads():
    home = (ROOT / "pages" / "home.py").read_text()
    assert '"Record audio"' in home
    assert "RecorderReminder(" in home
    assert "engine_script()" in home


def test_no_blocking_http_in_the_recording_routes():
    from tests.test_event_loop_hygiene import parse, sync_httpx_calls

    assert sync_httpx_calls(parse("utils/recording_api.py")) == []


def test_the_browser_and_the_server_agree_on_where_the_routes_are():
    engine = (ROOT / "static" / "recorder_engine.js").read_text()
    assert f'const API = "{recording_api.API_PREFIX}";' in engine
    # /api/* is scribe-backend's behind the reverse proxy.
    assert not recording_api.API_PREFIX.startswith("/api")


def test_the_nicegui_reloads_the_recorder_guards_are_still_there():
    # utils/recorder.js replaces three of nicegui.js's own socket handlers
    # while recording, because each of them reloads the page, and a reload
    # stops the recording. If NiceGUI renames or moves them, the guard
    # silently stops guarding -- this is what says so.
    import nicegui

    client = next(pathlib.Path(nicegui.__file__).parent.glob("static/nicegui.js")).read_text()
    for needle in (
        'window.socket = io(',
        'connect_error: (err) => {',
        'err.message == "timeout"',
        "try_reconnect: async () => {",
        'window.socket.emit("handshake", options.query, finishHandshake);',
        "window.socket.on(event,",
    ):
        assert needle in client, needle

    guard = (ROOT / "utils" / "recorder.js").read_text()
    for event in ("connect", "connect_error", "try_reconnect"):
        assert f'"{event}"' in guard


# -- The browser half -------------------------------------------------------


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_recorder_engine():
    result = subprocess.run(
        ["node", "--test", str(ROOT / "tests" / "js")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr

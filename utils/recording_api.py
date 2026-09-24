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
The HTTP side of recording: parts in, a finished file out to the backend.

Plain FastAPI routes rather than NiceGUI events, on purpose.  A NiceGUI event
travels over the page's websocket, and the websocket is exactly the thing a
phone in a lecture hall loses -- past `reconnect_timeout` NiceGUI deletes the
page's state and the browser reloads it.  A `fetch()` needs nothing but the
session cookie, so the browser can keep sending parts through a reconnect, a
reload, or from a different page than the one that recorded them.

Every route is answered for the signed-in user only: the staging directory is
named from the session's own token (`recording_owner()`), never from anything
in the request.  Cross-site requests are refused twice over -- the session
cookie is SameSite=Lax, so a cross-site POST or PUT carries no session, and
every route also requires a custom header, which a cross-site page cannot
send without a CORS preflight this app never answers.

Answers are shaped for the browser's retry logic (static/recorder_engine.js):

- 2xx: done, move on.
- 401: the session is over.  Nothing is lost; the browser keeps the
  recording and tries again once the reader has signed in.
- 409: parts are missing (staging was swept or the server restarted); the
  body lists them and the browser sends them.
- 422: can never succeed as sent.  The browser stops and offers to save the
  recording to the device instead.
- 503: try again later -- the backend is down, slow or refusing for now.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import time

import httpx

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from nicegui import app

from utils.helpers import sanitize_filename
from utils.recording_staging import (
    MAX_PART_BYTES,
    MAX_PARTS,
    RecordingStaging,
    StagingError,
)
from utils.settings import get_settings
from utils.token import RefreshUnavailable, get_user_info, token_refresh

settings = get_settings()
log = logging.getLogger(__name__)

# Under /record, not /api: behind the reverse proxy /api/* belongs to
# scribe-backend, so routes of this app there were answered 404 by the
# backend and never reached. /record is the recorder page's own path, which
# has to reach this app for the page to load at all.
API_PREFIX = "/record/api"

# The header every route requires.  Its value is not a secret; what matters
# is that a cross-site page cannot set it without a preflight.
CSRF_HEADER = "x-scribe-recording"

# What a recording may be sent as, and the extension its file is given.  The
# backend decides what it can transcribe by content, but a file name with
# the right extension is what a person downloading it again expects.
MIME_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
}

# Generous: the backend encrypts the whole file as it arrives, and an hour
# of audio over a slow link to it is minutes, not seconds.
BACKEND_TIMEOUT = httpx.Timeout(900, connect=15)

staging = RecordingStaging(settings.RECORDING_STAGING_DIR or None)

# Two tabs finishing the same recording must not both create a job.
_finish_locks: dict[str, asyncio.Lock] = {}
_last_sweep = {"at": 0.0}


def recording_owner(username: str | None) -> str | None:
    """
    A stable, opaque key for a user: the same person gets the same key on
    every device and in every session, and the key says nothing about who
    they are.

    Also sent to the browser, which tags its local recordings with it so a
    shared computer does not show one user's recordings to the next.  That
    tag is a courtesy, not a control -- the server never trusts a key sent
    back to it and derives its own from the session every time.
    """

    if not username:
        return None

    return hmac.new(
        settings.STORAGE_SECRET.encode(),
        b"scribe-recording-owner:" + username.encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _caller(request: Request) -> str:
    """
    The owner key of whoever sent this request, or an HTTPException.
    """

    if request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status_code=400, detail="missing header")

    try:
        signed_in = "_scribe_bk" in app.storage.browser
        username, _ = get_user_info()
    except (RuntimeError, AssertionError):
        signed_in, username = False, None

    owner = recording_owner(username) if signed_in else None

    if not owner:
        raise HTTPException(status_code=401, detail="not signed in")

    return owner


def _staging_error(error: StagingError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(error))


async def _maybe_sweep() -> None:
    """
    Drop stale staging now and then.  Done on the back of real requests
    rather than a timer so that a server nobody is recording on does no
    work at all.
    """

    now = time.time()

    if now - _last_sweep["at"] < 3600:
        return

    _last_sweep["at"] = now
    max_age = settings.RECORDING_STAGING_MAX_AGE_HOURS * 3600

    try:
        removed = await asyncio.to_thread(staging.sweep, max_age)
        if removed:
            log.info("recording staging sweep removed %d recording(s)", removed)
    except OSError:
        log.exception("recording staging sweep failed")


async def _read_body(request: Request, limit: int) -> bytes:
    """
    The request body, refused as soon as it passes `limit` rather than after
    it has all been read into memory.
    """

    declared = request.headers.get("content-length")

    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(status_code=422, detail="part too large")

    received = bytearray()

    async for piece in request.stream():
        received.extend(piece)
        if len(received) > limit:
            raise HTTPException(status_code=422, detail="part too large")

    return bytes(received)


@app.get(API_PREFIX + "/{rid}")
async def recording_status(rid: str, request: Request) -> JSONResponse:
    """
    Which parts this server holds, and whether the backend already has the
    recording.  Asked before sending anything, so a browser that reloaded
    half way through sends only what is missing.
    """

    owner = _caller(request)

    try:
        parts = await asyncio.to_thread(staging.parts, owner, rid)
        done = await asyncio.to_thread(staging.done, owner, rid)
    except StagingError as error:
        raise _staging_error(error)

    return JSONResponse({"parts": parts, "done": done})


@app.put(API_PREFIX + "/{rid}/part/{seq}")
async def recording_part(rid: str, seq: int, request: Request) -> JSONResponse:
    owner = _caller(request)
    data = await _read_body(request, MAX_PART_BYTES)

    try:
        await asyncio.to_thread(staging.write_part, owner, rid, seq, data)
    except StagingError as error:
        raise _staging_error(error)
    except OSError:
        # A full or read-only disk.  Nothing the browser sent is wrong, and
        # it still holds the part, so this is "later", not "never".
        log.exception("could not stage a recording part")
        raise HTTPException(status_code=503, detail="staging unavailable")

    await _maybe_sweep()

    return JSONResponse({"ok": True})


@app.delete(API_PREFIX + "/{rid}")
async def recording_discard(rid: str, request: Request) -> JSONResponse:
    owner = _caller(request)

    try:
        await asyncio.to_thread(staging.discard, owner, rid)
    except StagingError as error:
        raise _staging_error(error)

    return JSONResponse({"ok": True})


async def _post_to_backend(path, filename: str, mime: str) -> httpx.Response:
    """
    Send the assembled file to the backend, the same endpoint the upload
    dialog uses.  One retry on 401 after refreshing: the reader may well
    have had no page open for the token timer to keep fresh.
    """

    for attempt in (1, 2):
        headers = {}
        token = app.storage.user.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        with open(path, "rb") as handle:
            async with httpx.AsyncClient(timeout=BACKEND_TIMEOUT) as client:
                response = await client.post(
                    f"{settings.API_URL}/api/v1/transcriber",
                    files={"file": (filename, handle, mime)},
                    headers=headers,
                )

        if response.status_code != 401 or attempt == 2:
            return response

        try:
            if not await token_refresh():
                return response
        except RefreshUnavailable:
            raise HTTPException(status_code=503, detail="sign-in service unavailable")

    return response


def _file_name(name: str, mime: str) -> str:
    base_mime = (mime or "").split(";")[0].strip().lower()
    extension = MIME_EXTENSIONS.get(base_mime)

    if not extension:
        raise HTTPException(status_code=422, detail="unsupported audio type")

    raw = str(name or "").strip()
    stem = sanitize_filename(raw).strip()[:120] if raw else "Recording"

    if stem.lower().endswith(extension):
        return stem

    return stem + extension


@app.post(API_PREFIX + "/{rid}/finish")
async def recording_finish(rid: str, request: Request) -> JSONResponse:
    """
    Hand a fully staged recording to the backend.

    Idempotent: a finish repeated after the backend took the file -- the
    answer was lost, a second tab asked too -- is answered with the job the
    first one made rather than making another.
    """

    owner = _caller(request)

    try:
        body = await request.json()
        count = int(body.get("parts"))
        mime = str(body.get("mime") or "")
        name = str(body.get("name") or "")
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail="bad request")

    if count < 1 or count > MAX_PARTS:
        raise HTTPException(status_code=422, detail="bad part count")

    filename = _file_name(name, mime)
    lock = _finish_locks.setdefault(f"{owner}/{rid}", asyncio.Lock())

    async with lock:
        try:
            done = await asyncio.to_thread(staging.done, owner, rid)
            if done:
                return JSONResponse({"done": done})

            missing = await asyncio.to_thread(staging.missing, owner, rid, count)
            if missing:
                return JSONResponse({"missing": missing}, status_code=409)

            assembled = await asyncio.to_thread(staging.assemble, owner, rid, count)
        except StagingError as error:
            raise _staging_error(error)
        except OSError:
            log.exception("could not assemble a recording")
            raise HTTPException(status_code=503, detail="staging unavailable")

        try:
            response = await _post_to_backend(
                assembled, filename, mime.split(";")[0].strip()
            )
        except httpx.HTTPError:
            log.warning("backend unreachable while finishing a recording")
            raise HTTPException(status_code=503, detail="backend unavailable")
        finally:
            try:
                os.unlink(assembled)
            except FileNotFoundError:
                pass

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="not signed in")

        if response.status_code >= 500 or response.status_code in (408, 429):
            raise HTTPException(status_code=503, detail="backend unavailable")

        if response.status_code >= 400:
            log.warning("backend refused a recording: %d", response.status_code)
            raise HTTPException(status_code=422, detail="backend refused the file")

        try:
            result = response.json().get("result") or {}
        except ValueError:
            result = {}

        done = {"uuid": result.get("uuid"), "filename": filename}
        await asyncio.to_thread(staging.mark_done, owner, rid, done)

    _finish_locks.pop(f"{owner}/{rid}", None)

    return JSONResponse({"done": done})

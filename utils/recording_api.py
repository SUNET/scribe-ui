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
The HTTP side of recording: a finished recording, from the browser to the
backend.

**Nothing is stored here.**  The upload is streamed through to the backend
as it arrives, piece by piece, and never written to this server's disk or
held whole in its memory -- so the only copy of a recording that exists
outside the reader's own browser is the backend's, which it encrypts as it
stores it.  The browser keeps its copy until the backend has answered (see
static/recorder_engine.js), which is what makes it safe for this route to
hold nothing: a failed upload is simply sent again.

It has to pass through this server at all only because the browser holds
no token the backend accepts; the session's token lives in this server's
user storage.

A plain FastAPI route rather than a NiceGUI event, on purpose.  A NiceGUI
event travels over the page's websocket, and the websocket is exactly the
thing a laptop that has slept or a phone in a lecture hall loses.  A
`fetch()` needs nothing but the session cookie, so an upload goes on through
a reconnect, a reload, or from a different page than the one that recorded.

The recording is answered for the signed-in user only, and cross-site
requests are refused twice over: the session cookie is SameSite=Lax, so a
cross-site POST carries no session, and the route requires a custom header,
which a cross-site page cannot send without a CORS preflight this app never
answers.

Answers are shaped for the browser's retry logic:

- 200: the backend has it.
- 401: the session is over.  Nothing is lost; the browser keeps the
  recording and tries again once the reader has signed in.
- 422: can never succeed as sent.  The browser stops and the recording can
  still be downloaded.
- 503: try again later -- the backend is down, slow or refusing for now.
"""

import hashlib
import hmac
import logging
import re
import secrets

from collections import OrderedDict
from urllib.parse import unquote

import httpx

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from nicegui import app
from starlette.requests import ClientDisconnect

from utils.helpers import sanitize_filename
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

# 32 lower-case hex characters: crypto.randomUUID() without its dashes.
RID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# The same ceiling the upload dialog states for a file.
MAX_RECORDING_BYTES = 4 * 1024 * 1024 * 1024

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

# Recordings the backend has taken, by owner and recording id, with its
# answer -- ids and names only, never audio.  An upload repeated after its
# answer was lost on the way back (the connection dropped, a second tab
# asked too) gets the job the first one made instead of making another.
# In memory, so a restart forgets it; the worst that costs is that rare
# duplicate job.
_uploaded: "OrderedDict[str, dict]" = OrderedDict()
UPLOADED_REMEMBERED = 4096


class _TooLarge(Exception):
    pass


def recording_owner(username: str | None) -> str | None:
    """
    A stable, opaque key for a user: the same person gets the same key on
    every device and in every session, and the key says nothing about who
    they are.

    Sent to the browser, which tags its local recordings with it so a shared
    computer does not show one user's recordings to the next.  That tag is a
    courtesy, not a control -- the server never trusts a key sent back to it
    and derives its own from the session every time.
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


def _disposition_name(filename: str) -> str:
    """
    A file name for a multipart header, escaped the way browsers (and
    httpx's own `files=`) do it.  sanitize_filename has already taken quotes
    and control characters out; this is what keeps a header from being
    broken open if that ever changes.
    """

    return (
        filename.replace("\\", "\\\\")
        .replace('"', "%22")
        .replace("\r", "%0D")
        .replace("\n", "%0A")
    )


def _multipart(filename: str, mime: str, request: Request):
    """
    The request body as a multipart/form-data body for the backend, built
    around the incoming stream rather than from it: the part header, then
    every piece as it arrives, then the closing boundary.
    """

    boundary = secrets.token_hex(16)
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; '
        f'filename="{_disposition_name(filename)}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode()

    async def body():
        yield head
        sent = 0
        async for piece in request.stream():
            sent += len(piece)
            if sent > MAX_RECORDING_BYTES:
                raise _TooLarge()
            yield piece
        yield tail

    return boundary, head, tail, body()


def _token() -> str | None:
    return app.storage.user.get("token")


async def _forward(filename: str, mime: str, request: Request) -> httpx.Response:
    """
    Stream the upload to the backend -- the same endpoint the upload dialog
    uses, so a recording and a dropped file are the same job to it.

    The token is refreshed first rather than retried on a 401: a stream can
    be sent only once, and the reader may well have had no page open for
    the token timer to keep fresh.
    """

    try:
        if not await token_refresh():
            raise HTTPException(status_code=401, detail="not signed in")
    except RefreshUnavailable:
        raise HTTPException(status_code=503, detail="sign-in service unavailable")

    boundary, head, tail, body = _multipart(filename, mime, request)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Known length when the browser sent one -- it does for a Blob -- so the
    # backend is not handed a chunked body it did not need.
    declared = request.headers.get("content-length", "")
    if declared.isdigit():
        headers["Content-Length"] = str(len(head) + int(declared) + len(tail))

    async with httpx.AsyncClient(timeout=BACKEND_TIMEOUT) as client:
        return await client.post(
            f"{settings.API_URL}/api/v1/transcriber",
            content=body,
            headers=headers,
        )


@app.post(API_PREFIX + "/{rid}/upload")
async def recording_upload(rid: str, request: Request) -> JSONResponse:
    """
    Hand a finished recording to the backend, without keeping any of it.
    """

    owner = _caller(request)

    if not RID_PATTERN.match(rid or ""):
        raise HTTPException(status_code=422, detail="bad recording id")

    key = f"{owner}/{rid}"
    if key in _uploaded:
        return JSONResponse({"done": _uploaded[key]})

    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_RECORDING_BYTES:
        raise HTTPException(status_code=422, detail="recording too large")
    if declared == "0":
        raise HTTPException(status_code=422, detail="empty recording")

    mime = (request.headers.get("content-type") or "").split(";")[0].strip()
    filename = _file_name(unquote(request.headers.get("x-recording-name", "")), mime)

    try:
        response = await _forward(filename, mime, request)
    except _TooLarge:
        raise HTTPException(status_code=422, detail="recording too large")
    except ClientDisconnect:
        # The browser went away half way. The backend was handed a body that
        # stops short, which it refuses rather than storing, and the browser
        # sends the whole recording again when it is back.
        raise HTTPException(status_code=503, detail="upload interrupted")
    except httpx.HTTPError:
        log.warning("backend unreachable while uploading a recording")
        raise HTTPException(status_code=503, detail="backend unavailable")

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
    _uploaded[key] = done
    while len(_uploaded) > UPLOADED_REMEMBERED:
        _uploaded.popitem(last=False)

    return JSONResponse({"done": done})

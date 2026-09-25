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
The HTTP side of recording: parts of a recording, from the browser through
to the backend while it is being recorded.

**Nothing is stored here.**  Each part is passed straight on to the
backend's `/recordings` routes, which encrypt it as it arrives; the browser
deletes a part once it has been confirmed, so a recording is in the browser
only for the few seconds before its part is sent, and in the backend,
encrypted, from then on.  The routes exist at all only because the browser
holds no token the backend accepts; the session's token lives in this
server's user storage.

Plain FastAPI routes rather than NiceGUI events, on purpose.  A NiceGUI
event travels over the page's websocket, and the websocket is exactly the
thing a laptop that has slept or a phone in a lecture hall loses.  A
`fetch()` needs nothing but the session cookie, so sending goes on through a
reconnect, a reload, or from a different page than the one that recorded.

Every route answers for the signed-in user only, and cross-site requests are
refused twice over: the session cookie is SameSite=Lax, so a cross-site
request carries no session, and the routes require a custom header, which a
cross-site page cannot send without a CORS preflight this app never answers.

Answers are shaped for the browser's retry logic:

- 2xx: done, move on.
- 401: the session is over.  Nothing is lost; the browser keeps what it has
  not had confirmed and tries again once the reader has signed in.
- 409: parts are missing; the body lists them.
- 422: can never succeed as sent.  The browser stops retrying.
- 503: try again later -- the backend is down, slow or busy with the same
  recording.
"""

import base64
import hashlib
import hmac
import logging
import re

from typing import Optional
from urllib.parse import quote

import httpx

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from nicegui import app
from starlette.requests import ClientDisconnect

from utils.crypto import decrypt_string, get_browser_id
from utils.helpers import recording_store_key
from utils.settings import get_settings
from utils.token import RefreshUnavailable, get_user_info, token_refresh

settings = get_settings()
log = logging.getLogger(__name__)

# Under /record, not /api: behind the reverse proxy /api/* belongs to
# scribe-backend, so routes of this app there were answered 404 by the
# backend and never reached. /record is the recorder page's own path, which
# has to reach this app for the page to load at all.
API_PREFIX = "/record/api"

# Where a recording's original is downloaded from.  A plain link, so the
# browser's own download handling -- progress, where to save -- applies.
ORIGINAL_PREFIX = "/record/original"

# The header every route requires.  Its value is not a secret; what matters
# is that a cross-site page cannot set it without a preflight.
CSRF_HEADER = "x-scribe-recording"

# 32 lower-case hex characters: crypto.randomUUID() without its dashes.
RID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
JOB_PATTERN = re.compile(r"^[0-9A-Za-z-]{1,64}$")

# A part is a few seconds of audio.  Held whole here (it is small) so a
# request refused for an expired token can be sent again after refreshing;
# the backend states the same limit and refuses beyond it.
MAX_PART_BYTES = 16 * 1024 * 1024

BACKEND_TIMEOUT = httpx.Timeout(120, connect=15)
# Finishing joins and encrypts an hour of audio twice on the backend.
FINISH_TIMEOUT = httpx.Timeout(900, connect=15)


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


def _signed_in_owner() -> Optional[str]:
    try:
        signed_in = "_scribe_bk" in app.storage.browser
        username, _ = get_user_info()
    except (RuntimeError, AssertionError, KeyError):
        return None

    return recording_owner(username) if signed_in else None


def _caller(request: Request) -> str:
    """
    The owner key of whoever sent this request, or an HTTPException.
    """

    if request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status_code=400, detail="missing header")

    owner = _signed_in_owner()

    if not owner:
        raise HTTPException(status_code=401, detail="not signed in")

    return owner


def _rid(rid: str) -> str:
    if not RID_PATTERN.match(rid or ""):
        raise HTTPException(status_code=422, detail="bad recording id")

    return rid


async def _backend(
    method: str,
    path: str,
    content: bytes | None = None,
    json: dict | None = None,
    timeout: httpx.Timeout = BACKEND_TIMEOUT,
) -> httpx.Response:
    """
    One request to the backend with the session's token, sent once more
    after refreshing if the token had expired -- the reader may well have
    had no page open for the token timer to keep fresh.  Nothing sent here
    is a stream, so sending it twice is possible.
    """

    for attempt in (1, 2):
        headers = {}
        token = app.storage.user.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    f"{settings.API_URL}/api/v1{path}",
                    content=content,
                    json=json,
                    headers=headers,
                )
        except httpx.HTTPError:
            log.warning("backend unreachable for a recording request")
            raise HTTPException(status_code=503, detail="backend unavailable")

        if response.status_code != 401 or attempt == 2:
            return response

        try:
            if not await token_refresh():
                return response
        except RefreshUnavailable:
            raise HTTPException(status_code=503, detail="sign-in service unavailable")

    return response


def _answer(response: httpx.Response) -> JSONResponse:
    """
    The backend's answer, in the terms the browser's retry logic reads.
    """

    status = response.status_code

    try:
        body = response.json()
    except ValueError:
        body = {}

    if status < 300 or status == 409:
        return JSONResponse(body, status_code=status)

    if status == 401:
        raise HTTPException(status_code=401, detail="not signed in")

    if status >= 500 or status in (404, 408, 429):
        # 404 too: a backend without the recording routes is one that has
        # not been upgraded yet, which is "later", not "never".
        raise HTTPException(status_code=503, detail="backend unavailable")

    log.warning("backend refused a recording request: %d", status)
    error = (body.get("result") or {}).get("error") if isinstance(body, dict) else None
    raise HTTPException(status_code=422, detail=error or "refused")


async def _read_part(request: Request) -> bytes:
    declared = request.headers.get("content-length", "")

    if declared.isdigit() and int(declared) > MAX_PART_BYTES:
        raise HTTPException(status_code=422, detail="part too large")

    received = bytearray()

    try:
        async for piece in request.stream():
            received.extend(piece)
            if len(received) > MAX_PART_BYTES:
                raise HTTPException(status_code=422, detail="part too large")
    except ClientDisconnect:
        raise HTTPException(status_code=503, detail="upload interrupted")

    if not received:
        raise HTTPException(status_code=422, detail="empty part")

    return bytes(received)


@app.get(API_PREFIX + "/key")
async def recording_key(request: Request) -> JSONResponse:
    """
    The key the page encrypts audio with before writing it to IndexedDB.
    Never stored by the page: it asks again after every reload.
    """

    owner = _caller(request)

    try:
        key = recording_store_key(owner)
    except (KeyError, RuntimeError):
        raise HTTPException(status_code=401, detail="not signed in")

    return JSONResponse(
        {"key": base64.b64encode(key).decode()},
        headers={"Cache-Control": "no-store"},
    )


@app.get(API_PREFIX + "/{rid}")
async def recording_status(rid: str, request: Request) -> JSONResponse:
    """
    Which parts the backend holds, and which job the recording became if it
    already has.  Asked before sending, so a reloaded page sends only what
    is missing.
    """

    _caller(request)

    return _answer(await _backend("GET", f"/recordings/{_rid(rid)}"))


@app.put(API_PREFIX + "/{rid}/part/{seq}")
async def recording_part(rid: str, seq: int, request: Request) -> JSONResponse:
    _caller(request)
    _rid(rid)

    if seq < 0:
        raise HTTPException(status_code=422, detail="bad part number")

    data = await _read_part(request)

    return _answer(await _backend("PUT", f"/recordings/{rid}/part/{seq}", content=data))


@app.post(API_PREFIX + "/{rid}/finish")
async def recording_finish(rid: str, request: Request) -> JSONResponse:
    """
    Ask the backend to make the recording a job.  Idempotent at the backend:
    a finish repeated after a lost answer gets the job the first one made.
    """

    _caller(request)
    _rid(rid)

    try:
        body = await request.json()
        payload = {
            "parts": int(body.get("parts")),
            "name": str(body.get("name") or "")[:500],
            "mime": str(body.get("mime") or "")[:100],
        }
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail="bad request")

    return _answer(
        await _backend(
            "POST", f"/recordings/{rid}/finish", json=payload, timeout=FINISH_TIMEOUT
        )
    )


@app.delete(API_PREFIX + "/{rid}")
async def recording_discard(rid: str, request: Request) -> JSONResponse:
    _caller(request)

    return _answer(await _backend("DELETE", f"/recordings/{_rid(rid)}"))


def _encryption_password() -> Optional[str]:
    """
    The session's encryption password, or None.  Not storage_decrypt(): that
    navigates the page on failure, and a download has no page to navigate.
    """

    encrypted = app.storage.user.get("encryption_password")

    if not encrypted:
        return None

    try:
        return decrypt_string(
            encrypted,
            app.storage.browser["_scribe_bk"] + settings.STORAGE_SECRET,
            get_browser_id().encode(),
            b"scribe-secret",
        )
    except Exception:
        return None


@app.get(ORIGINAL_PREFIX + "/{job_id}")
async def recording_original(job_id: str) -> Response:
    """
    Download the original of a recording, decrypted by the backend with the
    session's encryption password and streamed through without being kept.

    A GET, so it can be a plain link.  Nothing changes on a GET, and a
    cross-site link to it downloads the reader's own file to the reader's
    own device, which gives the linking site nothing.
    """

    if not _signed_in_owner():
        return Response("Not signed in", status_code=401)

    if not JOB_PATTERN.match(job_id or ""):
        return Response("Not found", status_code=404)

    password = _encryption_password()

    if not password:
        return Response("Not signed in", status_code=401)

    headers = {}
    token = app.storage.user.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15))

    try:
        request = client.build_request(
            "POST",
            f"{settings.API_URL}/api/v1/transcriber/{job_id}/original",
            json={"encryption_password": password},
            headers=headers,
        )
        response = await client.send(request, stream=True)
    except httpx.HTTPError:
        await client.aclose()
        return Response("Scribe is not answering right now.", status_code=503)

    if response.status_code != 200:
        status = response.status_code
        await response.aclose()
        await client.aclose()
        return Response(
            "The original is not available.",
            status_code=404 if status in (403, 404) else 503,
        )

    async def body():
        try:
            async for piece in response.aiter_bytes():
                yield piece
        finally:
            await response.aclose()
            await client.aclose()

    passed = {
        name: response.headers[name]
        for name in ("content-type", "content-length", "content-disposition")
        if name in response.headers
    }
    passed.setdefault(
        "content-disposition", f"attachment; filename*=UTF-8''{quote('Recording')}"
    )
    passed["cache-control"] = "no-store"

    return StreamingResponse(body(), headers=passed)

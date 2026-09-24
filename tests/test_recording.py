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
when node is available.  What is tested here is the one route a recording
passes through on this server: that it reaches the backend whole and is
never kept here, and which status it answers with, since the browser's retry
logic is built on exactly which status means what.
"""

import asyncio
import json
import pathlib
import re
import shutil
import subprocess

import httpx
import pytest

from fastapi import HTTPException
from starlette.requests import Request

from utils import recording_api

ROOT = pathlib.Path(__file__).resolve().parent.parent
OWNER = "0" * 32
RID = "f" * 32


# -- The route --------------------------------------------------------------


def request(body=b"", headers=None, pieces=None):
    """
    A request as the browser sends it, its body arriving in `pieces`.
    """

    chunks = list(pieces) if pieces is not None else [body]
    base = {
        "x-scribe-recording": "1",
        "content-type": "audio/webm",
        "x-recording-name": "Lecture%3A%20week%203",
        "content-length": str(sum(len(c) for c in chunks)),
    }
    base.update(headers or {})
    raw = [(k.encode(), v.encode()) for k, v in base.items() if v is not None]
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": raw, "query_string": b""},
        receive,
    )


@pytest.fixture
def backend(monkeypatch):
    """
    A signed-in caller and a backend that parses what it is sent the way
    FastAPI's UploadFile does.
    """

    got = {"calls": 0, "status": 200, "raise": None, "files": []}

    def handle(request: httpx.Request) -> httpx.Response:
        got["calls"] += 1
        got["headers"] = dict(request.headers)
        if got["raise"]:
            raise got["raise"]
        body = request.read()
        # Parse the multipart body as a real server would.
        boundary = request.headers["content-type"].split("boundary=")[1]
        part = body.split(b"--" + boundary.encode())[1]
        head, _, content = part.partition(b"\r\n\r\n")
        got["files"].append((head.decode("utf-8"), content[: -len(b"\r\n")]))
        got["length_ok"] = int(request.headers.get("content-length", len(body))) == len(body)
        return httpx.Response(got["status"], json={"result": {"uuid": f"job-{got['calls']}"}})

    transport = httpx.MockTransport(handle)
    real = httpx.AsyncClient
    monkeypatch.setattr(
        recording_api.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw)
    )
    monkeypatch.setattr(recording_api, "_caller", lambda request: OWNER)
    monkeypatch.setattr(recording_api, "_token", lambda: "token")

    async def refreshed():
        return True

    monkeypatch.setattr(recording_api, "token_refresh", refreshed)
    monkeypatch.setattr(recording_api, "_uploaded", recording_api.OrderedDict())
    return got


def upload(req, rid=RID):
    return asyncio.run(recording_api.recording_upload(rid, req))


def payload(response):
    return response.status_code, json.loads(response.body)


def test_the_recording_reaches_the_backend_whole_and_named(backend):
    status, body = payload(upload(request(pieces=[b"aa", b"bb", b"cc"])))

    assert status == 200
    assert body["done"] == {"uuid": "job-1", "filename": "Lecture_ week 3.webm"}
    head, content = backend["files"][0]
    assert content == b"aabbcc"
    assert 'name="file"; filename="Lecture_ week 3.webm"' in head
    assert "Content-Type: audio/webm" in head
    assert backend["headers"]["authorization"] == "Bearer token"
    assert backend["length_ok"], "the length given the backend is the length sent"


def test_nothing_is_written_to_this_servers_disk(backend, tmp_path, monkeypatch):
    # The route never opens a file: the only copy that is stored anywhere
    # but the browser is the backend's, encrypted.
    import builtins

    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda *a, **k: opened.append(a) or real_open(*a, **k))
    upload(request(pieces=[b"aa", b"bb"]))
    assert opened == []
    assert not hasattr(recording_api, "staging")


def test_a_name_in_any_language_survives(backend):
    req = request(b"aa", {"x-recording-name": "F%C3%B6rel%C3%A4sning%20%C3%85"})
    _, body = payload(upload(req))
    assert body["done"]["filename"] == "Föreläsning Å.webm"
    assert 'filename="Föreläsning Å.webm"' in backend["files"][0][0]


def test_an_upload_repeated_after_its_answer_was_lost_makes_no_second_job(backend):
    first = payload(upload(request(b"aa")))[1]
    again = payload(upload(request(b"aa")))[1]
    assert again == first
    assert backend["calls"] == 1


@pytest.mark.parametrize(
    "backend_status, answer",
    [(500, 503), (502, 503), (503, 503), (429, 503), (401, 401), (400, 422), (413, 422)],
)
def test_backend_answers_become_retry_or_give_up(backend, backend_status, answer):
    backend["status"] = backend_status

    with pytest.raises(HTTPException) as caught:
        upload(request(b"aa"))

    assert caught.value.status_code == answer
    # A failure is not remembered as done: the next try reaches the backend.
    backend["status"] = 200
    assert payload(upload(request(b"aa")))[0] == 200


def test_an_unreachable_backend_is_try_again(backend):
    backend["raise"] = httpx.ConnectError("down")

    with pytest.raises(HTTPException) as caught:
        upload(request(b"aa"))

    assert caught.value.status_code == 503


def test_a_session_that_cannot_be_refreshed_is_signed_out(backend, monkeypatch):
    async def refused():
        return False

    monkeypatch.setattr(recording_api, "token_refresh", refused)
    with pytest.raises(HTTPException) as caught:
        upload(request(b"aa"))
    assert caught.value.status_code == 401
    assert backend["calls"] == 0


def test_an_oversized_recording_is_refused_before_it_is_read(backend):
    big = str(recording_api.MAX_RECORDING_BYTES + 1)
    with pytest.raises(HTTPException) as caught:
        upload(request(b"", {"content-length": big}))
    assert caught.value.status_code == 422
    assert backend["calls"] == 0


def test_only_audio_types_are_accepted(backend):
    with pytest.raises(HTTPException) as caught:
        upload(request(b"aa", {"content-type": "text/html"}))
    assert caught.value.status_code == 422


def test_recording_ids_have_one_shape(backend):
    with pytest.raises(HTTPException) as caught:
        upload(request(b"aa"), rid="../" + "f" * 29)
    assert caught.value.status_code == 422


def test_file_names_get_the_extension_their_audio_has():
    assert recording_api._file_name("Lecture", "audio/mp4") == "Lecture.m4a"
    assert recording_api._file_name("Lecture.webm", "audio/webm;codecs=opus") == "Lecture.webm"
    assert recording_api._file_name("", "audio/ogg") == "Recording.ogg"
    assert "/" not in recording_api._file_name("../../x", "audio/webm")


def test_the_route_wants_the_custom_header():
    # A cross-site page cannot set it without a preflight this app never
    # answers -- on top of the session cookie being SameSite=Lax.
    with pytest.raises(HTTPException) as caught:
        recording_api._caller(request(headers={"x-scribe-recording": None}))
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


def test_the_recorder_page_is_for_signed_in_users_only():
    # page_init's own gate is its token refresh navigating to the logout
    # route; this page asks it not to (to keep a recording running), so it
    # has to turn away a visitor who is not signed in itself -- before the
    # recorder, which works entirely in the browser, is drawn.
    source = (ROOT / "pages" / "record.py").read_text()
    gate = source.index("if not owner:")
    assert source.index("owner = current_owner()") < gate
    assert 'ui.navigate.to("/")' in source[gate : gate + 80]
    assert gate < source.index("Recorder(owner=owner")


def test_a_session_ending_without_a_recording_logs_out_as_usual():
    source = (ROOT / "pages" / "record.py").read_text()
    assert "end_session(settings.OIDC_APP_LOGOUT_ROUTE)" in source
    component = (ROOT / "utils" / "recorder.js").read_text()
    assert "leaveIfSignedOut()" in component
    assert "window.location.href = this.logoutUrl" in component


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

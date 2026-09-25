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

What the browser does to keep a recording -- IndexedDB, encryption, retrying,
recovering a crashed tab -- is tested in tests/js/recorder_engine.test.js,
run from here when node is available.  What is tested here is the routes a
recording passes through on this server: that each part reaches the backend
as sent and is never kept here, and which status each answers with, since
the browser's retry logic is built on exactly which status means what.
"""

import asyncio
import base64
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


# -- The routes --------------------------------------------------------------


def request(body=b"", headers=None, pieces=None, method="PUT"):
    """
    A request as the browser sends it, its body arriving in `pieces`.
    """

    chunks = list(pieces) if pieces is not None else [body]
    base = {
        "x-scribe-recording": "1",
        "content-type": "application/octet-stream",
        "content-length": str(sum(len(c) for c in chunks)),
    }
    base.update(headers or {})
    raw = [(k.encode(), v.encode()) for k, v in base.items() if v is not None]
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    return Request(
        {"type": "http", "method": method, "path": "/", "headers": raw, "query_string": b""},
        receive,
    )


@pytest.fixture
def backend(monkeypatch):
    """
    A signed-in caller and a backend that answers the recording routes.
    """

    got = {"calls": [], "status": 200, "answer": {"ok": True}, "raise": None}

    def handle(request: httpx.Request) -> httpx.Response:
        got["calls"].append((request.method, request.url.path, request.read()))
        got["headers"] = dict(request.headers)
        if got["raise"]:
            raise got["raise"]
        status = got["status"]
        if isinstance(status, list):
            status = status.pop(0)
        return httpx.Response(status, json=got["answer"])

    transport = httpx.MockTransport(handle)
    real = httpx.AsyncClient
    monkeypatch.setattr(
        recording_api.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw)
    )
    monkeypatch.setattr(recording_api, "_caller", lambda request: OWNER)

    class Storage:
        user = {"token": "token"}

    monkeypatch.setattr(recording_api.app, "storage", Storage)

    refreshes = []

    async def refreshed():
        refreshes.append(1)
        Storage.user["token"] = "fresh"
        return True

    monkeypatch.setattr(recording_api, "token_refresh", refreshed)
    got["refreshes"] = refreshes
    return got


def run(coroutine):
    return asyncio.run(coroutine)


def payload(response):
    return response.status_code, json.loads(response.body)


def test_a_part_reaches_the_backend_as_sent(backend):
    status, body = payload(
        run(recording_api.recording_part(RID, 3, request(pieces=[b"aa", b"bb", b"cc"])))
    )

    assert (status, body) == (200, {"ok": True})
    method, path, sent = backend["calls"][0]
    assert (method, path, sent) == ("PUT", f"/api/v1/recordings/{RID}/part/3", b"aabbcc")
    assert backend["headers"]["authorization"] == "Bearer token"


def test_an_expired_token_is_refreshed_and_the_part_sent_again(backend):
    backend["status"] = [401, 200]

    status, _ = payload(run(recording_api.recording_part(RID, 0, request(b"aa"))))

    assert status == 200
    assert len(backend["refreshes"]) == 1
    assert [c[2] for c in backend["calls"]] == [b"aa", b"aa"]
    assert backend["headers"]["authorization"] == "Bearer fresh"


def test_nothing_is_written_to_this_servers_disk(backend, monkeypatch):
    # The routes never open a file: the only copy stored anywhere but the
    # browser is the backend's, encrypted.
    import builtins

    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda *a, **k: opened.append(a) or real_open(*a, **k))
    run(recording_api.recording_part(RID, 0, request(pieces=[b"aa", b"bb"])))
    assert opened == []


def test_status_finish_and_discard_are_passed_on(backend):
    backend["answer"] = {"parts": [0, 1], "done": None}
    assert payload(run(recording_api.recording_status(RID, request(method="GET"))))[1] == {
        "parts": [0, 1],
        "done": None,
    }

    finish = request(
        json.dumps({"parts": 2, "name": "Föreläsning", "mime": "audio/webm", "extra": 1}).encode(),
        {"content-type": "application/json"},
        method="POST",
    )
    backend["answer"] = {"done": {"uuid": "job-1", "filename": "Föreläsning.webm"}}
    status, body = payload(run(recording_api.recording_finish(RID, finish)))
    assert status == 200
    assert body["done"]["uuid"] == "job-1"
    method, path, sent = backend["calls"][-1]
    assert (method, path) == ("POST", f"/api/v1/recordings/{RID}/finish")
    assert json.loads(sent) == {"parts": 2, "name": "Föreläsning", "mime": "audio/webm"}

    run(recording_api.recording_discard(RID, request(method="DELETE")))
    assert backend["calls"][-1][:2] == ("DELETE", f"/api/v1/recordings/{RID}")


def test_a_finished_recording_is_deleted_as_a_job(backend):
    run(recording_api.recording_job_delete("job-1", request(method="DELETE")))
    assert backend["calls"][-1][:2] == ("DELETE", "/api/v1/transcriber/job-1")

    # Already gone counts as deleted, not as a backend to retry.
    backend["status"] = 404
    assert payload(run(recording_api.recording_job_delete("job-1", request(method="DELETE"))))[0] == 200

    with pytest.raises(HTTPException) as caught:
        run(recording_api.recording_job_delete("../x", request(method="DELETE")))
    assert caught.value.status_code == 404


def test_missing_parts_are_passed_back_to_the_browser(backend):
    backend["status"] = 409
    backend["answer"] = {"missing": [0, 2]}
    finish = request(json.dumps({"parts": 3, "name": "", "mime": "audio/webm"}).encode(), method="POST")

    assert payload(run(recording_api.recording_finish(RID, finish))) == (409, {"missing": [0, 2]})


@pytest.mark.parametrize(
    "backend_status, answer",
    [(500, 503), (502, 503), (503, 503), (404, 503), (429, 503), (400, 422), (422, 422)],
)
def test_backend_answers_become_retry_or_give_up(backend, backend_status, answer):
    backend["status"] = backend_status

    with pytest.raises(HTTPException) as caught:
        run(recording_api.recording_part(RID, 0, request(b"aa")))

    assert caught.value.status_code == answer


def test_a_backend_that_still_says_signed_out_is_signed_out(backend):
    backend["status"] = 401

    with pytest.raises(HTTPException) as caught:
        run(recording_api.recording_part(RID, 0, request(b"aa")))

    assert caught.value.status_code == 401


def test_an_unreachable_backend_is_try_again(backend):
    backend["raise"] = httpx.ConnectError("down")

    with pytest.raises(HTTPException) as caught:
        run(recording_api.recording_part(RID, 0, request(b"aa")))

    assert caught.value.status_code == 503


def test_a_session_that_cannot_be_refreshed_is_signed_out(backend, monkeypatch):
    async def refused():
        return False

    backend["status"] = 401
    monkeypatch.setattr(recording_api, "token_refresh", refused)
    with pytest.raises(HTTPException) as caught:
        run(recording_api.recording_part(RID, 0, request(b"aa")))
    assert caught.value.status_code == 401
    assert len(backend["calls"]) == 1


def test_an_oversized_or_empty_part_is_refused_before_it_is_sent(backend):
    big = str(recording_api.MAX_PART_BYTES + 1)
    for req in (request(b"", {"content-length": big}), request(b"")):
        with pytest.raises(HTTPException) as caught:
            run(recording_api.recording_part(RID, 0, req))
        assert caught.value.status_code == 422
    assert backend["calls"] == []


def test_recording_ids_have_one_shape(backend):
    with pytest.raises(HTTPException) as caught:
        run(recording_api.recording_part("../" + "f" * 29, 0, request(b"aa")))
    assert caught.value.status_code == 422
    assert backend["calls"] == []


def test_recent_recordings_are_the_jobs_with_an_original_newest_first(backend, monkeypatch):
    monkeypatch.setattr(recording_api, "_encryption_password", lambda: "secret")
    backend["answer"] = {
        "result": {
            "jobs": [
                {"uuid": "a", "filename": "Old", "created_at": "2026-09-01 10:00", "has_original": True},
                {"uuid": "b", "filename": "Uploaded file", "created_at": "2026-09-24 10:00", "has_original": False},
                {"uuid": "c", "filename": "New", "created_at": "2026-09-24 11:00", "has_original": True, "status": "completed"},
            ]
        }
    }

    status, body = payload(run(recording_api.recording_recent(request(method="GET"))))

    assert status == 200
    assert [job["uuid"] for job in body["recordings"]] == ["c", "a"]
    assert body["recordings"][0]["status"] == "completed"
    method, path, sent = backend["calls"][0]
    assert (method, path) == ("GET", "/api/v1/transcriber")
    assert json.loads(sent) == {"encryption_password": "secret"}, "so the names come back readable"


def test_the_store_key_is_per_user_and_per_browser(monkeypatch):
    from utils import helpers

    class Storage:
        browser = {"_scribe_bk": "browser-key", "id": "browser-1"}

    monkeypatch.setattr(helpers.app, "storage", Storage)
    monkeypatch.setattr("utils.crypto.app.storage", Storage)

    mine = helpers.recording_store_key(OWNER)
    assert len(mine) == 32
    assert mine == helpers.recording_store_key(OWNER)
    assert mine != helpers.recording_store_key("1" * 32)

    Storage.browser = {"_scribe_bk": "other-key", "id": "browser-2"}
    assert mine != helpers.recording_store_key(OWNER)


def test_the_key_route_hands_over_the_key_uncached(monkeypatch):
    monkeypatch.setattr(recording_api, "_caller", lambda request: OWNER)
    monkeypatch.setattr(recording_api, "recording_store_key", lambda owner: b"k" * 32)

    response = run(recording_api.recording_key(request(method="GET")))

    assert json.loads(response.body) == {"key": base64.b64encode(b"k" * 32).decode()}
    assert response.headers["cache-control"] == "no-store"


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


def test_the_files_page_resumes_uploads():
    home = (ROOT / "pages" / "home.py").read_text()
    assert "RecorderReminder(" in home
    assert "engine_script()" in home


def test_no_blocking_http_in_the_recording_routes():
    from tests.test_event_loop_hygiene import parse, sync_httpx_calls

    assert sync_httpx_calls(parse("utils/recording_api.py")) == []


def test_the_browser_and_the_server_agree_on_where_the_routes_are():
    engine = (ROOT / "static" / "recorder_engine.js").read_text()
    assert f'const API = "{recording_api.API_PREFIX}";' in engine
    assert not recording_api.ORIGINAL_PREFIX.startswith("/api")
    # /api/* is scribe-backend's behind the reverse proxy.
    assert not recording_api.API_PREFIX.startswith("/api")


def test_the_nicegui_reloads_the_recorder_guards_are_still_there():
    # utils/recorder.js replaces four of nicegui.js's own socket handlers
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
        "run_javascript: (msg) => runJavascript(msg.code, msg.request_id),",
        # The reconnect's query is brought up to date from these two.
        "window.nextMessageId = options.query.next_message_id;",
        "window.nextMessageId = message_id + 1;",
    ):
        assert needle in client, needle

    # The server's own reload, when it cannot replay what a reconnect missed.
    outbox = (pathlib.Path(nicegui.__file__).parent / "outbox.py").read_text()
    assert "self.client.run_javascript('window.location.reload()')" in outbox

    guard = (ROOT / "utils" / "recorder.js").read_text()
    for event in ("connect", "connect_error", "try_reconnect", "run_javascript"):
        assert f'"{event}"' in guard
    assert 'const SERVER_RELOAD = "window.location.reload()";' in guard
    assert 'socket.io.on("reconnect_attempt"' in guard
    assert "query.next_message_id = window.nextMessageId" in guard


def test_the_audio_test_keeps_and_sends_nothing():
    # Test audio records a sample to play back; it lives in memory and goes
    # when the dialog closes. Nothing in it may reach storage or Scribe.
    component = (ROOT / "utils" / "recorder.js").read_text()
    test = component[component.index("// -- Test audio --") : component.index("async estimate()")]
    for forbidden in ("indexedDB", "fetch(", "XMLHttpRequest", "this.engine", "sessionStorage"):
        assert forbidden not in test, forbidden
    assert "URL.revokeObjectURL(this.testUrl)" in test
    assert 'track.stop()' in test, "the microphone is let go"
    assert '@hide="closeTest"' in component


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

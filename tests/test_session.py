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
What keeps a session -- and so an editor full of unsaved captions -- alive.

Every path here ends the same way when it goes wrong: the page reloads or
navigates away, the SRTEditor holding the reader's edits is gone, and the
work is lost back to the last save.
"""

import asyncio
import pathlib

import httpx
import pytest

from utils import token as token_module
from utils.token import (
    MAX_REFRESH_FAILURES,
    RefreshUnavailable,
    token_refresh_call,
    token_refresh_or_wait,
)


class FakeResponse:
    def __init__(self, status_code: int, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json here")

        return self._payload


class FakeClient:
    """
    Stands in for httpx.AsyncClient: answers with whatever it was given, or
    raises it if it was given an exception.
    """

    def __init__(self, answer) -> None:
        self.answer = answer

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def post(self, *args, **kwargs):
        if isinstance(self.answer, Exception):
            raise self.answer

        return self.answer


@pytest.fixture
def refresh_answers(monkeypatch):
    """
    Point the refresh call at a fake provider, with a storage it can read a
    refresh token out of.
    """

    def answer(with_this):
        monkeypatch.setattr(
            token_module.httpx, "AsyncClient", lambda *a, **k: FakeClient(with_this)
        )

    class FakeApp:
        class storage:
            user = {"refresh_token": "a-refresh-token"}

    monkeypatch.setattr(token_module, "app", FakeApp)

    return answer


class TestUnreachableIsNotRefused:
    """
    A provider that cannot be reached says nothing about whether the session
    is still good. Treating the two the same is what logged a reader out on
    a network blip, taking every unsaved caption with it.
    """

    def test_a_network_error_is_not_an_answer(self, refresh_answers):
        refresh_answers(httpx.ConnectError("no route"))

        with pytest.raises(RefreshUnavailable):
            asyncio.run(token_refresh_call())

    def test_a_server_error_is_not_an_answer(self, refresh_answers):
        refresh_answers(FakeResponse(503))

        with pytest.raises(RefreshUnavailable):
            asyncio.run(token_refresh_call())

    def test_an_answer_with_no_token_is_not_an_answer(self, refresh_answers):
        refresh_answers(FakeResponse(200))

        with pytest.raises(RefreshUnavailable):
            asyncio.run(token_refresh_call())

    def test_a_refusal_is_an_answer(self, refresh_answers):
        """
        4xx means this session is not getting another token. That is the
        session ending, and the only thing that should end it.
        """

        refresh_answers(FakeResponse(401))

        assert asyncio.run(token_refresh_call()) is None


class TestWaitingItOut:
    """
    An unreachable provider buys the reader time rather than the door. It
    does not buy them forever.
    """

    def test_a_blip_keeps_the_session(self, refresh_answers):
        refresh_answers(httpx.ConnectError("no route"))

        assert asyncio.run(token_refresh_or_wait(0)) is True

    def test_it_gives_up_eventually(self, refresh_answers):
        refresh_answers(httpx.ConnectError("no route"))

        assert asyncio.run(token_refresh_or_wait(MAX_REFRESH_FAILURES - 1)) is False

    def test_it_is_minutes_not_seconds(self):
        """
        page_init refreshes every 30 seconds, so the count is what decides
        how long a provider may be down before readers are logged out.
        """

        assert MAX_REFRESH_FAILURES * 30 >= 300


class TestPageInitCountsFailures:
    def source(self) -> str:
        return pathlib.Path("utils/common.py").read_text()

    def test_a_success_clears_the_count(self):
        source = self.source()
        body = source[source.index("async def refresh():"):]
        body = body[: body.index("ui.timer(0.1, refresh, once=True)")]

        assert 'unreachable["count"] = 0' in body
        assert 'unreachable["count"] += 1' in body

    def test_only_a_refusal_logs_out(self):
        source = self.source()
        body = source[source.index("async def refresh():"):]
        body = body[: body.index("ui.timer(0.1, refresh, once=True)")]

        logout = body.index("OIDC_APP_LOGOUT_ROUTE")

        assert body.index('unreachable["count"] += 1') < logout


class TestTheEditorKeepsItsClient:
    """
    The captions being edited live in this client's own SRTEditor on the
    server. When the socket stays down past reconnect_timeout, NiceGUI
    deletes that content and the browser reloads itself when it returns --
    with every unsaved edit gone.
    """

    def test_the_editor_page_waits_far_longer_than_the_default(self):
        page = pathlib.Path("pages/srt.py").read_text()

        assert '@ui.page("/srt", reconnect_timeout=300)' in page

    def test_the_default_is_still_short_everywhere_else(self):
        """
        A page holding nothing unsaved has no reason to keep a client alive
        for minutes after its browser has gone.
        """

        assert "reconnect_timeout=15," in pathlib.Path("main.py").read_text()


class TestThemeReloadIsOnlyForCharts:
    """
    Reloading on an OS theme change exists for Plotly, which is drawn
    server-side in one theme's colours. Everything else follows the theme
    through CSS custom properties -- and on the editor page a reload throws
    away every unsaved caption, which is exactly what a reader is doing when
    the OS switches at sunset.
    """

    def test_page_init_does_not_listen_for_it(self):
        """
        The manual dark-mode button further down does reload -- and already
        skips /srt for this very reason. What page_init must not do is
        install the automatic listener on every page it builds.
        """

        source = pathlib.Path("utils/common.py").read_text()
        body = source[source.index("def page_init("):]

        assert "_scribeThemeListener" not in body

    def test_the_chart_pages_ask_for_it_themselves(self):
        for page in (
            "pages/admin/analytics.py",
            "pages/admin/groups.py",
            "pages/admin/health.py",
        ):
            source = pathlib.Path(page).read_text()

            assert "reload_on_theme_change()" in source, page
            assert "plotly" in source, page

    def test_the_editor_does_not(self):
        assert "reload_on_theme_change" not in pathlib.Path("pages/srt.py").read_text()

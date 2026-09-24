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

from nicegui import ui

import utils.recording_api  # noqa: F401 -- registers the upload routes
from utils.common import page_init
from utils.recorder import Recorder, current_owner, engine_script
from utils.settings import get_settings
from utils.styles import default_styles

# How long the page survives its websocket being down.  Everything else in
# the app keeps NiceGUI's 15 seconds; here that would be fatal.  Past the
# timeout NiceGUI deletes the page and the browser reloads it when it gets
# back through -- and a reload stops the MediaRecorder.  What was recorded
# is safe on the device either way, but a lecture should not be cut into
# pieces because the lecture-hall wifi dropped for a minute.  Six hours is
# longer than any lecture; the price is a little server memory for an
# abandoned tab, for that long.
RECONNECT_TIMEOUT = 6 * 3600

settings = get_settings()


def create() -> None:
    @ui.page("/record", reconnect_timeout=RECONNECT_TIMEOUT)
    def record() -> None:
        """
        Record a lecture with the device's microphone.

        A page rather than a dialog on the files page: a phone is held in a
        hand or left on a lectern for an hour, and the page is the whole
        screen doing one thing -- and a page can have the long reconnect
        window above, where the files page must not.
        """

        recorder = {"element": None}

        def session_ended() -> None:
            # Handed to the page rather than acted on here: only the page
            # knows whether a recording is running. If one is, a navigation
            # would stop it, so it is said instead; if not, the page logs
            # out exactly as every other page does.
            if recorder["element"] is not None:
                recorder["element"].end_session(settings.OIDC_APP_LOGOUT_ROUTE)
            else:
                ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)

        page_init(use_drawer=True, title="Recorder", on_session_end=session_ended)

        # Signed in, or nothing. Every other page is gated by page_init's
        # token refresh navigating to the logout route when it fails, a
        # moment after the page is drawn -- and this page asks page_init not
        # to navigate (session_ended above), so it has to check for itself,
        # before anything is drawn. Everything here runs in the browser: a
        # page left open to a visitor who is not signed in is a working
        # recorder, whatever the upload route then refuses.
        owner = current_owner()
        if not owner:
            ui.navigate.to("/")
            return

        ui.add_head_html(default_styles)
        engine_script()

        with ui.column().classes("recorder-page w-full items-center"):
            recorder["element"] = Recorder(owner=owner, files_url="/home")

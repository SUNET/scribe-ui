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
Recording from the browser's microphone.

The server's part in a recording is small on purpose: it names the owner
and streams a finished recording through to the backend without storing it
(utils/recording_api.py).  Everything that keeps a recording from being lost --
writing each second to IndexedDB, sending parts while recording, retrying,
recovering what a crashed tab left -- happens in the browser
(static/recorder_engine.js), because the browser is the one place the audio
exists while it is being made, and the websocket to this server is the first
thing a phone loses.

The same component-registration gotcha applies here as to
transcript_editor.js: recorder.js is keyed by file content at import time.
recorder_engine.js is a plain static file instead, loaded by `engine_script()`
with its content hash in the URL so a browser never runs a stale copy.
"""

import hashlib
import pathlib

from nicegui import ui

from utils.recording_api import API_PREFIX, ORIGINAL_PREFIX, recording_owner
from utils.token import get_user_info

ENGINE_PATH = pathlib.Path(__file__).resolve().parent.parent / "static" / "recorder_engine.js"
ENGINE_VERSION = hashlib.sha256(ENGINE_PATH.read_bytes()).hexdigest()[:12]


def engine_script() -> None:
    """
    Load the engine into the page's head.  A plain blocking script, so it has
    run before any component that uses it is mounted.
    """

    ui.add_head_html(
        f'<script src="/static/recorder_engine.js?v={ENGINE_VERSION}"></script>'
    )


def current_owner() -> str:
    username, _ = get_user_info()

    return recording_owner(username) or ""


class Recorder(ui.element, component="recorder.js"):
    """
    The recorder itself: start, pause, stop, and the list of recordings on
    this device with what has become of each.
    """

    def __init__(self, owner: str, files_url: str = "/home") -> None:
        super().__init__()
        self._props["owner"] = owner
        self._props["filesUrl"] = files_url
        self._props["sessionEnded"] = False
        self._props["logoutUrl"] = ""
        self._props["originalUrl"] = ORIGINAL_PREFIX
        self._props["recentUrl"] = API_PREFIX + "/recent"

    def end_session(self, logout_url: str) -> None:
        """
        The sign-in is over.  With no recording running the page goes to
        `logout_url` at once, as every other page does.  With one running
        it says so instead -- a navigation would stop the recording -- and
        goes when the recording stops; everything recorded is kept in the
        browser for after the reader has signed in again.
        """

        self._props["logoutUrl"] = logout_url
        self._props["sessionEnded"] = True
        self.update()


class RecorderReminder(ui.element, component="recorder_reminder.js"):
    """
    The files page's line about recordings still on this device -- and the
    thing that resumes their uploads when the recorder is not open.
    """

    def __init__(self, owner: str, recorder_url: str = "/record") -> None:
        super().__init__()
        self._props["owner"] = owner
        self._props["recorderUrl"] = recorder_url

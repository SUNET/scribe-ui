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
The player's controls, over the foot of the picture (or, for sound alone,
on a surface of their own).

The browser's own bar is gone (see player_controls.js for why): this is what
replaces it. Everything it shows -- position, length, volume, speed -- it reads
from the video element itself, so the server is not asked for any of it. The
one thing it needs the server for is "play with context", which depends on
which caption the caret was last in, and that is the one event it emits.

It has to be made inside the `.video-frame` that holds the picture: it finds
the frame with `closest()`, lays itself over its foot, and tells it (a class)
when the recording turns out to have no picture.

The same registration gotcha applies here as to speech_timeline.js: the
component is keyed by file content at import time, so an edit to the .js
needs the server process restarted (main.py's uvicorn_reload_includes covers
it for the dev server).
"""

from nicegui import ui


class PlayerControls(
    ui.element,
    component="player_controls.js",
):
    """
    Play and pause, the stretch around a caption, speed, position and volume.

    `label` is the recording's file name. It is only shown for a recording that
    is sound alone, where there is no picture to carry it.
    """

    def __init__(self, label: str = "") -> None:
        super().__init__()
        self._props["label"] = label

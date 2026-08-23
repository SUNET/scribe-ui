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
The speech strip under the video.

Where someone is talking, where the silences are, and where the captions
break -- drawn from the word timings the transcription already carries, so
nothing is decoded and the recording is not fetched a second time. See
speech_timeline.js for what the browser does with it, and `speech_runs()` in
utils/srt_review.py for how the runs are worked out.

The same registration gotcha applies here as to transcript_editor.js: the
component is keyed by file content at import time, so an edit to the .js
needs the server process restarted (main.py's uvicorn_reload_includes covers
it for the dev server).
"""

from typing import List

from nicegui import ui


class SpeechTimeline(
    ui.element,
    component="speech_timeline.js",
):
    """
    The strip itself. Everything it draws is a prop; the playhead is not --
    the component follows the video element directly rather than being sent
    a position several times a second.
    """

    def __init__(self) -> None:
        super().__init__()
        self._props["runs"] = []
        self._props["captions"] = []
        self._props["duration"] = 0.0
        self._props["currentId"] = -1
        self._props["startDocked"] = False

    def set_speech(self, runs: List[list], duration: float) -> None:
        self._props["runs"] = runs
        self._props["duration"] = float(duration)
        self.update()

    def set_docked(self, docked: bool) -> None:
        """
        Whether the strip opens along the foot of the page rather than under
        the video.

        Only where it *starts*: from then on the reader moves it by dragging
        its grip, and the component owns that state -- the server hears about
        each move so it can be remembered for next time, and never sends the
        position back mid-session.
        """

        self._props["startDocked"] = bool(docked)
        self.update()

    def set_current(self, caption_index: int) -> None:
        """
        Which caption the text editor is on.

        Sent from the server because that is where it is known. The strip
        keeps two more states of its own -- the caption under the pointer
        and the caption being played -- and the three are deliberately not
        the same thing: hovering one caption here must not take the text
        editor's focus off another.
        """

        self._props["currentId"] = int(caption_index)
        self.update()

    def set_captions(self, captions: List[dict]) -> None:
        """
        The captions as blocks on the strip: {"id", "start", "end"}, in
        seconds. Redrawn after every structural edit -- a split, a merge, a
        retime or an undo moves them -- and it is these the reader drags.
        """

        self._props["captions"] = captions
        self.update()

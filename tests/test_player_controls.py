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
The player's own controls, under the picture, in place of the browser's bar.

What is pinned down here is the contract that made them worth building: Space
never plays or pauses the recording from the page, Ctrl+Space always does, and
the one control that reaches the editor ("play with context") plays the block
the caret was last in. How the bar looks and moves was checked in a browser;
these are the parts that can silently be undone by a later edit.
"""

import asyncio
import pathlib

import pytest

from utils.player_controls import PlayerControls
from utils.srt import SRTEditor
from utils.transcript_editor import TranscriptEditor

from tests.test_play_with_context import make_editor


def component() -> str:
    return pathlib.Path("utils/player_controls.js").read_text()


def page() -> str:
    return pathlib.Path("pages/srt.py").read_text()


def stylesheet() -> str:
    from utils.styles import default_styles

    return default_styles


def rule(selector: str) -> str:
    """The body of the first plain rule for `selector`."""

    css = stylesheet()
    start = css.index("\n    " + selector + " {")
    start = css.index("{", start) + 1

    return css[start : css.index("}", start)]


class TestTheNativeBarIsGone:
    def test_the_editor_video_has_no_controls_of_its_own(self):
        source = page()
        video = source[source.index("video = ui.video("):]
        video = video[: video.index(").classes(")]

        assert "controls=False" in video
        assert "controls=True" not in video

    def test_the_controls_sit_under_the_picture_and_say_where_they_go(self):
        source = page()

        assert "PlayerControls(filename)" in source
        assert (
            'player_controls.on("playcontext", transcript.play_with_context_here)'
            in source
        )
        # After the frame that holds the picture, before the strip.
        assert source.index("PlayerControls(filename)") > source.index(
            'ui.element("div").classes("video-frame'
        )
        assert source.index("PlayerControls(filename)") < source.index(
            "timeline = SpeechTimeline()"
        )

    def test_the_script_that_lifted_the_subtitle_over_the_bar_is_gone(self):
        """
        It followed the rules the browser draws its bar by; there is no bar
        for it to clear, and the preview stays where a viewer sees it.
        """

        assert "video-controls-visible" not in page()
        assert "video-controls-visible" not in stylesheet()


class TestSpaceNeverControlsThePlayer:
    """
    The page's head script used to play and pause on a bare Space whenever
    nothing was being typed into -- and the browser's own bar had rules of its
    own on top of that, so the same key meant different things depending on
    what happened to have focus. Now it means what it means on whatever has
    focus: a space in text, a press on a button.
    """

    def head_script(self) -> str:
        source = page()
        start = source.index("window.addEventListener('keydown'")

        return source[start : source.index("}, true);", start)]

    def test_the_handler_that_played_on_space_is_gone(self):
        script = self.head_script()

        assert "video.paused ? video.play() : video.pause();" not in script
        assert "e.key === ' '" not in script
        assert "document.querySelector('video')" not in script

    def test_the_page_says_why(self):
        assert "Space never plays or pauses the recording" in self.head_script()

    def test_ctrl_space_is_still_the_editors(self):
        source = pathlib.Path("utils/srt.py").read_text()

        assert "Play/pause video, Ctrl+Space" in source
        assert 'case " " if event.modifiers.ctrl and not event.modifiers.shift' in source

    def test_a_focused_button_does_not_also_press_on_ctrl_space(self):
        """
        With a button focused the browser would press it when the key is let
        go, and that and the editor's own toggle would cancel out. Only the
        browser's action is stopped: the event itself carries on to the page.
        """

        script = component()
        guard = script[script.index("keepModifiedSpace(event) {"):]
        guard = guard[: guard.index("\n    },")]

        assert "event.ctrlKey" in guard
        assert 'event.code === "Space"' in guard
        assert "event.preventDefault();" in guard
        assert "stopPropagation" not in guard
        # On both halves of the key.
        assert '@keydown="keepModifiedSpace"' in script
        assert '@keyup="keepModifiedSpace"' in script


class TestWhatIsOnOffer:
    def test_each_button_has_a_name(self):
        script = component()

        assert ":aria-label=\"playing ? 'Pause' : 'Play'\"" in script
        assert 'aria-label="Play with context"' in script
        assert ":aria-label=\"'Playback speed ' + rateLabel(rate)\"" in script
        assert "muted || !volume ? 'Unmute' : 'Mute'" in script

    def test_the_bars_are_native_sliders_with_names_and_spoken_values(self):
        script = component()

        assert script.count('type="range"') == 2
        assert 'aria-label="Position in the recording"' in script
        assert 'aria-label="Volume"' in script
        assert ':aria-valuetext="positionText"' in script
        assert "' percent'" in script

    def test_the_times_are_not_read_twice(self):
        """
        The slider's own spoken value says where the recording is; the figures
        beside it are for the eye.
        """

        script = component()

        assert script.count('class="player-time" aria-hidden="true"') == 2

    def test_play_with_context_names_its_shortcut(self):
        script = component()

        assert 'aria-keyshortcuts="Control+Shift+Space"' in script
        assert "@click=\"$emit('playcontext')\"" in script
        assert 'emits: ["playcontext"]' in script

    def test_a_mouse_press_does_not_take_focus_from_the_text(self):
        """
        So the reader can click Play and carry on typing, and a Space after the
        click is a space in the text. The same reason the Highlight button does
        it.
        """

        script = component()

        assert script.count("@mousedown.prevent") >= 4

    def test_the_speeds(self):
        script = component()

        assert "const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];" in script
        assert "this.video.playbackRate = rate;" in script

    def test_the_speed_menu_is_a_menu(self):
        script = component()

        assert 'aria-haspopup="menu"' in script
        assert ':aria-expanded="String(menuOpen)"' in script
        assert 'role="menu"' in script
        assert 'role="menuitemradio"' in script
        assert ':aria-checked="String(option === rate)"' in script
        # Opens on the speed in force, and Escape gives focus back.
        assert ".player-menu-item-on" in script
        assert "this.closeMenu(true)" in script

    def test_the_bar_moves_by_the_usual_steps(self):
        script = component()

        assert "const STEP = 5;" in script
        assert "const STEP_PAGE = 30;" in script
        for key in ("Home", "End", "PageUp", "PageDown"):
            assert key in script

    def test_everything_is_read_back_off_the_player(self):
        """
        Whoever started playback -- the button, Ctrl+Space, the strip, a
        caption played with its context -- the bar shows what the element is
        doing, because it reads the element rather than keeping its own count.
        """

        script = component()

        for event in ("play", "pause", "ended", "timeupdate", "seeked",
                      "durationchange", "volumechange", "ratechange"):
            assert f'"{event}"' in script
        assert "this.playing = !video.paused && !video.ended;" in script

    def test_unmuting_at_zero_brings_the_sound_up(self):
        script = component()

        assert "if (video.volume === 0) video.volume = 0.5;" in script

    def test_the_icon_is_one_line_to_change(self):
        script = component()

        assert script.count("playlist_play") == 1
        assert "const CONTEXT_ICON" in script


class TestRecordingsWithoutAPicture:
    def test_the_component_notices_and_tells_the_frame(self):
        script = component()

        assert "video.videoWidth === 0" in script
        assert "video-frame-audio" in script

    def test_the_frame_gives_way(self):
        assert "display: none;" in rule(".video-frame.video-frame-audio")

    def test_the_file_name_stands_in_for_the_picture(self):
        script = component()

        assert 'v-if="audioOnly && label"' in script
        assert PlayerControls("a.m4a")._props["label"] == "a.m4a"


class TestTheLook:
    def test_it_is_the_strips_tray_family(self):
        pill = rule(".player-pill")

        assert "border-radius: 999px;" in pill
        assert "var(--color-border-subtle)" in pill
        assert "var(--color-bg-surface)" in pill

    def test_it_answers_to_its_own_width(self):
        css = stylesheet()

        assert "container-type: inline-size;" in rule(".player-controls")
        assert "@container (max-width: 30rem)" in css

    def test_narrow_puts_the_bar_on_its_own_row(self):
        css = stylesheet()
        narrow = css[css.index("@container (max-width: 30rem)"):]
        narrow = narrow[: narrow.index("/* ── SRT editor controls")]

        assert "flex-wrap: wrap;" in narrow
        assert "order: -1;" in narrow
        assert "flex: 1 0 100%;" in narrow

    def test_the_unfilled_track_is_not_a_fainter_hairline(self):
        """
        A component's boundary has to hold 3:1 against the surface (1.4.11); a
        track drawn at half opacity measured 2.2:1.
        """

        css = stylesheet()

        assert "var(--color-border-subtle) var(--fill, 0%)" in css
        assert "background: var(--color-border-subtle);" in css

    def test_the_main_button_is_dark_on_the_dark_themes_blue(self):
        """
        White on #5b9bd5 is 2.96:1, under the 3:1 a control's glyph needs.
        """

        css = stylesheet()

        assert ".body--dark .player-btn-main," in css
        dark = css[css.index(".body--dark .player-btn-main,"):]
        assert "color: var(--color-bg-page);" in dark[: dark.index("}")]


class TestPlayWithContextFromTheButton:
    """
    Unlike Ctrl+Shift+Space the button is pressed from outside the text, so
    the block comes from where the caret was last, and failing that from the
    playhead.
    """

    @pytest.fixture
    def view(self, monkeypatch):
        editor = make_editor()
        view = TranscriptEditor(editor)
        self.notes = []
        monkeypatch.setattr(
            "utils.transcript_editor.ui.notify",
            lambda *a, **k: self.notes.append((a, k)),
        )
        self.played = []
        editor.play_range = lambda start, end: self.played.append((start, end))

        async def at(seconds):
            return seconds

        self.at = at
        view.playhead = lambda: self.at(self.seconds)
        self.seconds = 0.0

        return view

    def test_the_block_the_caret_was_last_in(self, view):
        view.caret_block = view.editor.captions[1].index

        asyncio.run(view.play_with_context_here())

        assert self.played == [view.editor.context_range(view.editor.captions[1])]

    def test_it_is_that_block_even_when_the_playhead_is_elsewhere(self, view):
        view.caret_block = view.editor.captions[1].index
        self.seconds = 1.0

        asyncio.run(view.play_with_context_here())

        assert self.played == [view.editor.context_range(view.editor.captions[1])]

    def test_before_the_caret_has_been_anywhere_it_is_the_block_at_the_playhead(
        self, view
    ):
        view.caret_block = None
        self.seconds = 8.0

        asyncio.run(view.play_with_context_here())

        assert self.played == [view.editor.context_range(view.editor.captions[2])]

    def test_a_block_that_has_gone_falls_back_to_the_playhead(self, view):
        view.caret_block = 9999
        self.seconds = 6.0

        asyncio.run(view.play_with_context_here())

        assert self.played == [view.editor.context_range(view.editor.captions[1])]

    def test_with_nothing_to_go_on_it_says_so(self, view):
        view.caret_block = None
        self.seconds = 99.0

        asyncio.run(view.play_with_context_here())

        assert self.played == []
        assert len(self.notes) == 1

    def test_it_is_not_an_edit_and_touches_nothing_on_screen(self, view):
        calls = []
        view.refresh = lambda *a, **k: calls.append("refresh")
        view.changed = lambda *a, **k: calls.append("changed")
        view.focus = lambda *a, **k: calls.append("focus")
        view.caret_block = view.editor.captions[1].index

        asyncio.run(view.play_with_context_here())

        assert calls == []


class TestSpeedAndTheRangeStop:
    def test_the_stop_is_decided_on_position_so_speed_does_not_matter(self):
        """
        Play with context stops when the position reaches the end, a frame at
        a time -- at 2x that can be a few hundredths late, never a different
        place. Nothing in it reads the rate.
        """

        script = SRTEditor.PLAY_RANGE_SCRIPT

        assert "video.currentTime >= end" in script
        assert "playbackRate" not in script

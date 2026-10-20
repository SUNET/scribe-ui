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
The player's own controls, over the foot of the picture, in place of the
browser's bar.

What is pinned down here is the contract that made them worth building: Space
never plays or pauses the recording from the page, Ctrl+Space always does, and
the one control that reaches the editor ("play with context") plays around
the playhead and never has nothing to play. How the bar looks and moves was checked in a browser;
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

    def test_the_controls_are_in_the_frame_over_the_picture(self):
        source = page()

        assert "PlayerControls(filename)" in source
        assert (
            '"playcontext", transcript.play_with_context_here' in source
        )
        # Inside the frame that holds the picture (one level in from it), so
        # they share its rounded corners and sit over its foot; before the
        # strip, which is under the frame.
        frame = source.index('ui.element("div").classes("video-frame')
        controls = source.index("PlayerControls(filename)")

        assert controls > frame
        assert controls < source.index("timeline = None")
        line_start = source.rindex("\n", 0, controls) + 1
        frame_line = source.rindex("\n", 0, frame) + 1
        indent = lambda at, text: len(text[at:]) - len(text[at:].lstrip(" "))
        assert indent(line_start, source) == indent(frame_line, source) + 4

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

    def test_its_tooltip_is_its_name_and_its_shortcut(self):
        """
        As the play button's is: the name and the keys in brackets, and not the
        sentence about what it does that it once was.
        """

        script = component()
        button = script[script.index('class="player-btn player-btn-context"'):]
        button = button[: button.index("</button>")]

        assert (
            "<q-tooltip>Play with context (Ctrl + Shift + Space)</q-tooltip>"
            in button
        )
        assert "some of what is said" not in script

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

    def test_the_position_does_not_cost_a_redraw_every_frame(self):
        """
        An animation-frame loop for the thumb was measured at about a tenth of a
        core while playing, against nothing without it; the position moves on
        timeupdate instead.
        """

        script = component()

        assert "requestAnimationFrame" not in script
        assert "cancelAnimationFrame" not in script
        assert '"timeupdate"' in script

    def test_the_bar_is_let_go_of_however_a_press_ends(self):
        """
        A click on the thumb that does not move it fires no `change`, and a
        touch gesture the browser takes over ends in `pointercancel`; with only
        `change` letting go the bar stayed frozen while the recording played
        (reproduced: it did not follow after a plain click on the thumb).
        """

        script = component()
        seek = script[script.index('class="player-range player-seek"'):]
        seek = seek[: seek.index("/>")]

        for event in ("change", "pointerdown", "pointerup", "pointercancel", "blur"):
            assert f'@{event}="' in seek, event
        assert "endScrub() {" in script

    def test_no_volume_slider_where_the_page_cannot_set_the_volume(self):
        """
        iOS never lets a page set it (it reads 1 and stays), so a slider there
        would be a control that does nothing; mute still works and stays.
        """

        script = component()

        assert 'v-if="volumeSettable"' in script
        # Asked of a throwaway element, so the real player is not touched.
        assert "new Audio()" in script
        assert "this.volumeSettable = probe.volume === 0.5;" in script
        mute = script[script.index("Unmute"):]
        assert "toggleMute" in script[: script.index("player-volume-range")]

    def test_unmuting_at_zero_brings_the_sound_up(self):
        script = component()

        assert "if (video.volume === 0) video.volume = 0.5;" in script

    def test_the_icon_is_one_line_to_change(self):
        script = component()

        assert script.count("auto_read_play") == 1
        assert 'const CONTEXT_ICON = "sym_o_auto_read_play";' in script
        # A Material Symbols name, which NiceGUI's own font already has.
        assert "playlist_play" not in script


class TestRecordingsWithoutAPicture:
    def test_the_component_notices_and_tells_the_frame(self):
        script = component()

        assert "video.videoWidth === 0" in script
        assert "video-frame-audio" in script

    def test_the_frame_becomes_the_players_own_surface(self):
        frame = rule(".video-frame.video-frame-audio")

        # Dark, as tall as the controls, and not clipping (the menu opens
        # past it).
        assert "height: auto;" in frame
        assert "overflow: visible;" in frame
        assert "background-color: var(--player-surface" in frame
        assert "display: none !important;" in rule(
            ".video-frame-audio video,\n    .video-frame-audio .video-subtitle-overlay"
        )

    def test_the_controls_stop_being_laid_over_anything(self):
        controls = rule(".video-frame-audio .player-controls")

        assert "position: static;" in controls
        assert "background: none;" in controls

    def test_the_menu_opens_downward_there(self):
        menu = rule(".video-frame-audio .player-menu")

        assert "top: calc(100% + 8px);" in menu
        assert "bottom: auto;" in menu

    def test_the_file_name_stands_in_for_the_picture(self):
        script = component()

        assert 'v-if="audioOnly && label"' in script
        assert PlayerControls("a.m4a")._props["label"] == "a.m4a"


class TestTheLook:
    def test_it_is_laid_over_the_foot_of_the_picture_on_a_tone(self):
        controls = rule(".video-frame .player-controls")

        assert "position: absolute;" in controls
        assert "bottom: 0;" in controls
        assert "linear-gradient(" in controls
        # No pill any more: the picture is the player.
        assert ".player-pill" not in stylesheet()

    def test_it_is_white_whatever_the_theme(self):
        """
        What it sits on is a video (or the audio surface), not the page.
        """

        base = rule(".player-controls")

        assert "--player-fg: #fff;" in base
        assert "color: var(--player-fg);" in base
        assert "--color-bg-page" not in base

    def test_it_answers_to_its_own_width(self):
        css = stylesheet()

        assert "container-type: inline-size;" in rule(".player-controls")
        assert "@container (max-width: 20rem)" in css

    def test_the_unfilled_track_holds_three_to_one_on_a_white_picture(self):
        """
        1.4.11. A half-white track on the tone measured 4.1:1 against a white
        picture; the tone is dense under the rows to keep it there, and a
        flatter one would not.
        """

        css = stylesheet()
        controls = rule(".video-frame .player-controls")

        assert "--player-track: rgba(255, 255, 255, 0.55);" in css
        assert "rgba(0, 0, 0, 0.72) 62%" in controls
        assert "rgba(0, 0, 0, 0.85) 0" in controls

    def test_it_goes_while_the_picture_plays_and_never_from_the_keyboard(self):
        css = stylesheet()
        script = component()
        asleep = rule(".video-frame .player-controls-asleep:not(:focus-within)")

        assert "opacity: 0;" in asleep
        # Out of reach as well as out of sight: the tap that wakes them on a
        # touch screen must not also press the button it brought back.
        assert "pointer-events: none;" in asleep
        # Only while playing, and not with the menu open, mid-drag, or without
        # a picture.
        assert (
            "this.playing && !this.awake && !this.menuOpen && !this.scrubbing"
            " && !this.audioOnly" in script
        )
        assert 'frame.addEventListener("pointermove"' in script
        assert 'frame.addEventListener("pointerdown"' in script
        assert 'frame.addEventListener("pointerleave"' in script

    def test_the_tap_that_wakes_them_is_not_a_tap_on_them(self):
        """
        Asleep they let the tap through to the picture, but the click that
        follows is aimed after they have woken and landed on the button that
        lay under the finger (touch emulation: a tap on the hidden Play paused
        the recording). The click is swallowed, for touch and pen only.
        """

        script = component()

        assert '@click.capture="swallowWakingTap"' in script
        assert 'event.pointerType !== "mouse"' in script
        assert "event.stopPropagation();" in script[script.index("swallowWakingTap(event)"):]
        assert 'frame.addEventListener("pointerdown", this.onFrameDown);' in script

    def test_a_touch_screen_is_not_given_a_rule_that_loses_to_the_fade(self):
        """
        An `(hover: none)` rule that put the opacity back was here once and
        never applied: `:not(:focus-within)` makes the fade's selector more
        specific, so on a phone the controls faded after all (seen with touch
        emulation; the test then only looked for the text of the rule). Touch
        is handled by the tap that wakes them instead.
        """

        css = stylesheet()
        block = css[
            css.index("The player's controls (utils/player_controls.js)") :
            css.index("SRT editor controls under the video")
        ]

        assert "hover: none" not in block

    def test_the_figures_and_the_speed_are_set_in_the_pages_own_type(self):
        """
        The "Uncertain words" choices beside the video are 14px at weight 500
        in the page's own face; a thin monospace for the times and the speed
        broke with that. The figures keep their width with tabular numerals.
        """

        for selector in (".player-time", ".player-speed-btn", ".player-menu-item"):
            body = rule(selector)

            assert "font-family: inherit;" in body, selector
            assert "font-size: 0.875rem;" in body, selector
            assert "font-weight: 500;" in body, selector
            assert "font-variant-numeric: tabular-nums;" in body, selector
            assert "--font-mono" not in body, selector

    def test_the_speed_is_the_bare_figure_without_a_frame(self):
        button = rule(".player-speed-btn")

        assert "border: 0;" in button
        assert "border-radius: 999px;" in button
        assert "rgba(255, 255, 255, 0.7)" not in button
        # It still says when it is open, and when the pointer is on it.
        assert "background-color:" in rule(".player-speed-btn-open")
        assert ".player-speed-btn:hover" in stylesheet()

    def test_the_focus_ring_is_white_and_wins_against_the_pages_own(self):
        """
        The page's ring is the brand colour, nearly the colour of the tone it
        would be drawn on. Its rule is !important in `@layer theme`, so this
        one has to be too, in the same layer.
        """

        css = stylesheet()
        start = css.index(
            ".player-controls.player-controls.player-controls .player-bar *:focus-visible"
        )
        layer = css[css.rindex("@layer theme {", 0, start) : start]
        ring = css[start : css.index("}", start)]

        assert layer.count("{") == layer.count("}") + 1
        assert "outline: 3px solid #fff !important;" in ring

    def test_the_speed_menu_fits_a_short_frame(self):
        script = component()

        assert "frame.clientHeight" in script
        assert "maxHeight" in script
        assert "overflow-y: auto;" in rule(".player-menu")


class TestPlayWithContextFromTheButton:
    """
    The button is about the playhead, not the caret: inside a caption it is
    that caption with its context, anywhere else the words around the moment,
    or the plain window. It never turns the reader away, and it plays the same
    stretch again while that is still the reader's current one: running, or
    stopped with neither playhead nor caret moved since.
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
        # What the player would say about the stretch: play_range starts it.
        self.state = None

        def play_range(start, end):
            self.played.append((start, end))
            self.state = "playing"

        editor.play_range = play_range

        async def context_state():
            return self.state

        editor.context_state = context_state

        async def at(seconds):
            return seconds

        view.playhead = lambda: at(self.seconds)
        self.seconds = 0.0

        return view

    def press(self, view, seconds):
        self.seconds = seconds
        asyncio.run(view.play_with_context_here())

        return self.played[-1]

    def with_a_pause(self, view):
        # Caption 2 ends at 6 and caption 3 starts at 7: a second of nothing.
        view.editor.captions[1].end_time = "00:00:06,000"

    def test_inside_a_caption_it_is_that_caption_with_its_context(self, view):
        self.press(view, 6.0)

        assert self.played == [view.editor.context_range(view.editor.captions[1])]

    def test_the_caret_plays_no_part(self, view):
        view.caret_block = view.editor.captions[0].index

        self.press(view, 6.0)

        assert self.played == [view.editor.context_range(view.editor.captions[1])]

    def test_in_a_pause_it_is_the_words_around_the_moment(self, view):
        self.with_a_pause(view)

        self.press(view, 6.5)

        assert self.played == [view.editor.context_range_at(6.5)]

    def test_with_nothing_near_it_is_the_plain_window(self, view):
        self.press(view, 99.0)

        assert self.played == [(94.0, 104.0)]

    def test_a_recording_with_no_word_timings_still_plays(self, view):
        view.editor.words = []
        self.with_a_pause(view)

        self.press(view, 6.5)

        assert self.played == [(1.5, 11.5)]

    def test_it_never_answers_with_a_message(self, view):
        self.with_a_pause(view)

        for seconds in (0.0, 6.5, 12.0, 99.0):
            self.state = None
            self.press(view, seconds)

        assert len(self.played) == 4
        assert self.notes == []

    def test_pressed_while_it_runs_it_is_the_same_stretch(self, view):
        first = self.press(view, 6.0)

        # Still playing, the playhead somewhere in the middle of it.
        assert self.state == "playing"
        assert self.press(view, 9.0) == first

    def test_stopped_and_untouched_it_is_the_same_stretch(self, view):
        first = self.press(view, 6.0)
        self.state = "stopped"

        # The playhead is where it stopped -- in caption 3 here, so going by
        # what is under it would give a different one. It is not even asked.
        assert view.caption_at(first[1]) is view.editor.captions[2]
        assert self.press(view, first[1]) == first
        assert self.press(view, 123.0) == first

    def test_a_pause_repeats_too(self, view):
        self.with_a_pause(view)
        first = self.press(view, 6.5)
        self.state = "stopped"

        assert self.press(view, first[1]) == first

    def test_after_the_reader_moved_the_playhead_it_starts_afresh(self, view):
        first = self.press(view, 6.0)
        # The player lets go of it on a pause, a seek or playing on.
        self.state = None

        second = self.press(view, 9.0)

        assert second == view.editor.context_range(view.editor.captions[2])
        assert second != first

    def test_after_the_caret_settled_elsewhere_it_starts_afresh(self, view):
        first = self.press(view, 6.0)
        self.state = "stopped"

        view.caret_moved({"id": view.editor.captions[0].index})
        second = self.press(view, 9.0)

        assert second == view.editor.context_range(view.editor.captions[2])
        assert second != first

    def test_the_shortcut_is_what_a_press_after_it_repeats(self, view):
        first = view.play_with_context({"id": view.editor.captions[0].index})
        self.state = "stopped"

        assert self.press(view, 99.0) == first

    def test_a_repeated_block_timed_to_nothing_by_an_edit_still_plays(self, view):
        self.press(view, 6.0)
        self.state = "stopped"
        view.editor.captions[1].end_time = view.editor.captions[1].start_time

        second = self.press(view, 40.0)

        assert second == view.editor.context_range_at(5.0)
        assert self.notes == []

    def test_a_repeated_block_that_has_gone_still_plays(self, view):
        self.press(view, 6.0)
        self.state = "stopped"
        view.editor.captions.pop(1)

        second = self.press(view, 40.0)

        assert second == view.editor.context_range_at(40.0)
        assert self.notes == []

    def test_it_is_not_an_edit_and_touches_nothing_on_screen(self, view):
        calls = []
        view.refresh = lambda *a, **k: calls.append("refresh")
        view.changed = lambda *a, **k: calls.append("changed")
        view.focus = lambda *a, **k: calls.append("focus")

        self.press(view, 6.0)
        self.state = None
        self.press(view, 99.0)

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

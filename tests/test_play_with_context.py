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

import asyncio
import pathlib

import pytest

from utils.caption import SRTCaption
from utils.srt import SRTEditor
from utils.srt_review import CONTEXT_WORDS
from utils.transcript_editor import TranscriptEditor


# Twelve words, a second each: word n runs from n to n + 0.8.
WORDS = {
    "version": 1,
    "words": [
        {"t": f"w{n}", "s": float(n), "e": n + 0.8} for n in range(12)
    ],
}


def make_editor(words=WORDS):
    editor = SRTEditor("job-uuid", "srt", "file.srt")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *args, **kwargs: None)

    editor.load_words(words)
    # Words 5 and 6 in the middle; the rest on either side of them.
    editor.captions = [
        SRTCaption(1, "00:00:00,000", "00:00:05,000", "w0 w1 w2 w3 w4"),
        SRTCaption(2, "00:00:05,000", "00:00:07,000", "w5 w6"),
        SRTCaption(3, "00:00:07,000", "00:00:12,000", "w7 w8 w9 w10 w11"),
    ]

    return editor


class TestContextRange:
    def test_it_is_five_words(self):
        assert CONTEXT_WORDS == 5

    def test_five_words_before_and_after(self):
        editor = make_editor()

        start, end = editor.context_range(editor.captions[1])

        # Words 0..4 are before it and 7..11 after: all five of each.
        assert start == pytest.approx(0.0)
        assert end == pytest.approx(11.8)

    def test_fewer_words_than_that_near_the_start(self):
        editor = make_editor()

        start, end = editor.context_range(editor.captions[0])

        assert start == pytest.approx(0.0)
        # w0..w4 are the caption itself, w5..w9 the context after it.
        assert end == pytest.approx(9.8)

    def test_fewer_words_than_that_near_the_end(self):
        editor = make_editor()

        start, end = editor.context_range(editor.captions[2])

        # w2..w6 before the caption; nothing after the last word, so the
        # caption's own end stands.
        assert start == pytest.approx(2.0)
        assert end == pytest.approx(12.0)

    def test_context_crosses_the_boundaries_of_the_neighbours(self):
        editor = make_editor()

        start, end = editor.context_range(editor.captions[1])

        # Further than either neighbouring caption reaches on its own side.
        assert start < editor.captions[0].get_end_seconds()
        assert end > editor.captions[2].get_start_seconds()

    def test_the_context_is_counted_in_words_not_seconds(self):
        # The same words spoken at half the pace: the stretch doubles with
        # them (both within the limit in seconds).
        def at_pace(spacing):
            words = {
                "version": 1,
                "words": [
                    {"t": f"w{n}", "s": n * spacing, "e": n * spacing + spacing * 0.8}
                    for n in range(12)
                ],
            }
            editor = make_editor(words)
            for caption, (a, b) in zip(
                editor.captions, ((0, 5), (5, 7), (7, 12))
            ):
                caption.start_time = editor.seconds_to_timestamp(a * spacing)
                caption.end_time = editor.seconds_to_timestamp(b * spacing)

            return editor.context_range(editor.captions[1])

        fast = at_pace(0.5)
        slow = at_pace(1.0)

        assert slow[1] - slow[0] == pytest.approx(2 * (fast[1] - fast[0]))

    def test_a_long_silence_is_not_played(self):
        """
        Five words back can be minutes back. Words further out than the limit
        are left out, and the silence before them is not played either.
        """

        words = {
            "version": 1,
            "words": [
                {"t": "a", "s": 0.0, "e": 0.5},
                {"t": "b", "s": 0.6, "e": 1.0},
                # Five minutes of nothing.
                {"t": "c", "s": 301.0, "e": 301.5},
                {"t": "d", "s": 301.6, "e": 302.0},
                {"t": "e", "s": 600.0, "e": 600.5},
            ],
        }
        editor = make_editor(words)
        editor.captions = [
            SRTCaption(1, "00:00:00,000", "00:00:01,000", "a b"),
            SRTCaption(2, "00:05:01,000", "00:05:02,000", "c d"),
            SRTCaption(3, "00:10:00,000", "00:10:01,000", "e"),
        ]

        # Nothing within reach on either side: the block on its own.
        assert editor.context_range(editor.captions[1]) == (301.0, 302.0)

    def test_words_inside_the_limit_still_come_with_it(self):
        words = {
            "version": 1,
            "words": [
                {"t": "far", "s": 0.0, "e": 0.5},
                {"t": "near", "s": 95.0, "e": 95.4},
                {"t": "x", "s": 96.0, "e": 97.0},
                {"t": "after", "s": 98.0, "e": 98.5},
                {"t": "later", "s": 300.0, "e": 300.5},
            ],
        }
        editor = make_editor(words)
        editor.captions = [
            SRTCaption(1, "00:00:00,000", "00:00:01,000", "far"),
            SRTCaption(2, "00:01:36,000", "00:01:37,000", "x"),
            SRTCaption(3, "00:05:00,000", "00:05:01,000", "later"),
        ]

        start, end = editor.context_range(editor.captions[1])

        # "near" is a second before, "after" a second after; the others are
        # minutes away.
        assert start == pytest.approx(95.0)
        assert end == pytest.approx(98.5)

    def test_the_limit_is_five_seconds(self):
        from utils.srt_review import CONTEXT_SECONDS

        assert CONTEXT_SECONDS == 5.0

    def test_a_word_exactly_at_the_limit_is_in(self):
        words = {
            "version": 1,
            "words": [
                {"t": "edge", "s": 5.0, "e": 5.4},
                {"t": "x", "s": 10.0, "e": 11.0},
                {"t": "edge2", "s": 11.0, "e": 16.0},
            ],
        }
        editor = make_editor(words)
        editor.captions = [SRTCaption(1, "00:00:10,000", "00:00:11,000", "x")]

        start, end = editor.context_range(editor.captions[0])

        assert start == pytest.approx(5.0)
        assert end == pytest.approx(16.0)

    def test_one_word_past_the_limit_is_out(self):
        words = {
            "version": 1,
            "words": [
                {"t": "edge", "s": 4.9, "e": 5.4},
                {"t": "x", "s": 10.0, "e": 11.0},
                {"t": "edge2", "s": 11.0, "e": 16.1},
            ],
        }
        editor = make_editor(words)
        editor.captions = [SRTCaption(1, "00:00:10,000", "00:00:11,000", "x")]

        assert editor.context_range(editor.captions[0]) == (10.0, 11.0)

    def test_the_captions_own_times_are_the_floor(self):
        editor = make_editor()
        # Timed wider than its words, on both sides.
        editor.captions[1].start_time = "00:00:04,900"
        editor.captions[1].end_time = "00:00:07,100"
        editor.captions[1].text = "w5 w6"
        editor.words = editor.words[5:7]
        editor._word_midpoints = editor._word_midpoints[5:7]

        start, end = editor.context_range(editor.captions[1])

        assert start == pytest.approx(4.9)
        assert end == pytest.approx(7.1)

    def test_edited_times_are_used_as_they_are_now(self):
        editor = make_editor()
        editor.captions[1].end_time = "00:00:06,000"

        _, end = editor.context_range(editor.captions[1])

        # w6 is now after the caption, and the first of its five: w6..w10.
        assert end == pytest.approx(10.8)

    def test_without_word_data_it_is_the_caption_alone(self):
        editor = make_editor({"version": 1, "words": []})

        assert editor.context_range(editor.captions[1]) == (5.0, 7.0)

    def test_nothing_to_play_for_a_caption_that_does_not_end_after_it_starts(self):
        editor = make_editor()
        editor.captions[1].end_time = "00:00:05,000"

        assert editor.context_range(editor.captions[1]) is None

    def test_never_before_zero(self):
        editor = make_editor()
        editor.words[0]["s"] = -0.3

        start, _ = editor.context_range(editor.captions[0])

        assert start == 0.0

    def test_a_word_without_timing_is_placed_by_its_midpoint(self):
        words = {
            "version": 1,
            "words": [{"t": "a", "s": 0.0, "e": 1.0}, {"t": "b"}],
        }
        editor = make_editor(words)
        editor.captions = [
            SRTCaption(1, "00:00:00,000", "00:00:01,000", "a"),
            SRTCaption(2, "00:00:01,000", "00:00:02,000", "b"),
        ]

        # No crash, and the stretch still covers the caption.
        start, end = editor.context_range(editor.captions[0])

        assert start == 0.0
        assert end >= 1.0


class TestPlayRange:
    def editor(self, monkeypatch, player):
        editor = make_editor()
        editor._video_player = player
        scripts = []
        monkeypatch.setattr(
            "utils.srt.ui.run_javascript", lambda script, **k: scripts.append(script)
        )

        return editor, scripts

    class Player:
        id = 7

    def test_it_runs_one_script_aimed_at_the_player(self, monkeypatch):
        editor, scripts = self.editor(monkeypatch, self.Player())

        editor.play_range(2.5, 9.25)

        assert len(scripts) == 1
        assert "getHtmlElement(7)" in scripts[0]
        assert "const start = 2.5;" in scripts[0]
        assert "const end = 9.25;" in scripts[0]

    def test_it_falls_back_to_the_first_video_without_an_id(self, monkeypatch):
        editor, scripts = self.editor(monkeypatch, object())

        editor.play_range(1.0, 2.0)

        assert 'document.querySelector("video")' in scripts[0]

    def test_no_player_means_nothing_happens(self, monkeypatch):
        editor, scripts = self.editor(monkeypatch, None)

        editor.play_range(1.0, 2.0)

        assert scripts == []

    def test_an_empty_stretch_is_not_played(self, monkeypatch):
        editor, scripts = self.editor(monkeypatch, self.Player())

        editor.play_range(2.0, 2.0)

        assert scripts == []

    def test_the_play_state_follows(self, monkeypatch):
        editor, _ = self.editor(monkeypatch, self.Player())

        editor.play_range(1.0, 2.0)

        assert editor._play_pause is True

    def test_the_script_stops_at_the_end_and_gives_way_to_the_reader(self):
        script = SRTEditor.PLAY_RANGE_SCRIPT

        # Decided a frame at a time, not on timeupdate.
        assert "requestAnimationFrame" in script
        assert "timeupdate" not in script
        assert "video.currentTime >= end" in script
        assert "video.pause();" in script
        # A pause by the reader ends the watch.
        assert "video.paused" in script
        # A second request replaces the first rather than running beside it.
        assert "video._scribeStopWatch()" in script

    def test_a_move_in_either_direction_ends_the_watch_and_leaves_it_playing(self):
        """
        Told by the player's own seeking event, which playing never raises, so
        a jump forward past the end is not mistaken for reaching it -- and no
        position is compared, which is what let a jump back keep playing and a
        jump forward pause.
        """

        script = SRTEditor.PLAY_RANGE_SCRIPT
        begin = script[script.index("const begin = () => {"):]

        assert 'video.addEventListener("seeking", leave);' in begin
        assert "start - 0.5" not in script
        # Registered after its own move to the start, which is not the reader's.
        assert begin.index('"seeking"') < begin.index("video.play();")
        assert script.index('video.addEventListener("seeked", begin') < script.index(
            "video.currentTime = start;"
        )
        # The only pause is at the end, never on a move.
        assert script.count("video.pause();") == 1

    def test_the_player_keeps_whether_the_stretch_is_still_current(self):
        script = SRTEditor.PLAY_RANGE_SCRIPT
        leave = script[script.index("const leave = () => {"):script.index("// At its end")]
        rest = script[script.index("const rest = () => {"):script.index("video._scribeStopWatch = finish;")]
        watch = script[script.index("const watch = () => {"):script.index("const begin = () => {")]

        # Running, from the moment it is asked for.
        assert 'video._scribeRange = "playing";' in script
        # Gone on anything of the reader's: a move, playing on, a pause.
        assert "video._scribeRange = null;" in leave
        assert 'video.addEventListener("play", leave);' in rest
        assert "return leave();" in watch
        # Stopped at its end, by the stop or the recording running out first.
        assert 'video._scribeRange = "stopped";' in rest
        assert watch.index("video.ended") < watch.index("video.paused")
        assert "return rest();" in watch
        # A second request cleans the first one's listeners away first, so
        # its own move to the start is not read as the reader's.
        assert script.index("video._scribeStopWatch()") < script.index(
            'video._scribeRange = "playing";'
        )

    def test_the_script_does_not_touch_focus(self):
        assert "focus" not in SRTEditor.PLAY_RANGE_SCRIPT


class TestPlayWithContextHandler:
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

        return view

    def test_the_event_reaches_the_view(self):
        source = pathlib.Path("utils/transcript_editor.py").read_text()

        assert (
            'self.body.on("playcontext", lambda event: self.play_with_context(event.args))'
            in source
        )

    def test_it_plays_the_stretch(self, view):
        block = view.editor.captions[1].index

        view.play_with_context({"id": block})

        assert self.played == [view.editor.context_range(view.editor.captions[1])]
        assert self.notes == []

    def test_it_changes_nothing_on_screen(self, view):
        calls = []
        view.refresh = lambda *a, **k: calls.append("refresh")
        view.changed = lambda *a, **k: calls.append("changed")
        view.focus = lambda *a, **k: calls.append("focus")

        view.play_with_context({"id": view.editor.captions[1].index})

        assert calls == []

    def test_it_is_not_an_edit(self, view):
        saved = []
        view.editor.save_state_for_undo = lambda *a, **k: saved.append(1)

        view.play_with_context({"id": view.editor.captions[1].index})

        assert saved == []

    def test_without_word_data_it_says_so_and_still_plays(self, view):
        view.editor.load_words({"version": 1, "words": []})

        view.play_with_context({"id": view.editor.captions[1].index})

        assert self.played == [(5.0, 7.0)]
        assert len(self.notes) == 1

    def test_a_block_that_cannot_play_says_so(self, view):
        view.editor.captions[1].end_time = "00:00:05,000"

        view.play_with_context({"id": view.editor.captions[1].index})

        assert self.played == []
        assert len(self.notes) == 1

    @pytest.mark.parametrize("args", [None, {}, {"id": 9999}, {"id": "x"}])
    def test_bad_input_is_harmless(self, view, args):
        view.play_with_context(args)

        assert self.played == []


class TestTheKey:
    def source(self):
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def keys(self, name):
        source = self.source()
        body = source[source.index(f"\n    {name}(event, at) {{") + 1:]

        return body[: body.index("\n    },")]

    def test_it_is_ctrl_shift_space_and_nothing_else(self):
        source = self.source()
        body = source[source.index("\n    playWithContextKey(event) {") + 1:]
        body = body[: body.index("\n    },")]

        assert "event.ctrlKey" in body
        assert "event.shiftKey" in body
        assert "!event.altKey" in body
        # Ctrl only, as for Ctrl+Space itself.
        assert "!event.metaKey" in body
        assert 'event.code === "Space"' in body

    def test_both_formats_report_it_with_the_block(self):
        for name in ("subtitleShortcut", "transcriptionShortcut"):
            keys = self.keys(name)

            assert "this.playWithContextKey(event)" in keys
            assert 'this.report(event, "playcontext", { id: at.id })' in keys

    def test_it_is_checked_ahead_of_the_arrows(self):
        for name in ("subtitleShortcut", "transcriptionShortcut"):
            keys = self.keys(name)

            assert keys.index("playcontext") < keys.index('"moveword"')

    def test_plain_ctrl_space_is_left_to_the_page(self):
        """
        The page's handler only takes Ctrl+Space without Shift, so the two
        cannot both fire for one key press.
        """

        source = pathlib.Path("utils/srt.py").read_text()

        assert (
            'case " " if event.modifiers.ctrl and not event.modifiers.shift'
            in source
        )


class TestContextRangeAt:
    """
    The stretch around a moment that belongs to no caption: the words about
    it, or the plain window, and never nothing.
    """

    def test_words_five_either_side(self):
        editor = make_editor()

        # Between word 5 (5.0-5.8) and word 6 (6.0-6.8): words 1-5 before,
        # 6-10 after.
        assert editor.context_range_at(5.9) == (1.0, 10.8)

    def test_a_word_further_than_the_cap_is_left_out(self):
        editor = make_editor(
            {
                "version": 1,
                "words": [
                    {"t": "a", "s": 1.0, "e": 1.5},
                    {"t": "b", "s": 20.0, "e": 20.5},
                ],
            }
        )

        # Neither is within 5 s of 10: the plain window, not the silence up
        # to a word 10 s off.
        assert editor.context_range_at(10.0) == (5.0, 15.0)

    def test_with_no_word_near_it_it_is_the_plain_window(self):
        assert make_editor().context_range_at(50.0) == (45.0, 55.0)

    def test_with_no_word_timings_at_all_it_is_the_plain_window(self):
        editor = make_editor()
        editor.words = []

        assert editor.context_range_at(20.0) == (15.0, 25.0)

    def test_with_words_only_before_it_stops_at_the_moment(self):
        editor = make_editor()

        # Words 8-11 are within 5 s of 13 and word 7 is not.
        assert editor.context_range_at(13.0) == (8.0, 13.0)

    def test_with_words_only_after_it_starts_at_the_moment(self):
        editor = make_editor(
            {"version": 1, "words": [{"t": "a", "s": 4.0, "e": 4.5}]}
        )

        assert editor.context_range_at(1.0) == (1.0, 4.5)

    def test_a_word_straddling_the_moment_is_heard_whole(self):
        editor = make_editor(
            {"version": 1, "words": [{"t": "a", "s": 5.0, "e": 5.8}]}
        )

        assert editor.context_range_at(5.2) == (5.0, 5.8)

    @pytest.mark.parametrize("moment", [0.0, 0.5, 3.3, 5.9, 12.0, 50.0])
    def test_the_moment_is_always_inside_it(self, moment):
        start, end = make_editor().context_range_at(moment)

        assert start <= moment <= end
        assert end > start

    def test_never_before_zero(self):
        editor = make_editor()
        editor.words = []

        assert editor.context_range_at(2.0) == (0.0, 7.0)
        assert editor.context_range_at(-3.0) == (0.0, 5.0)


class TestContextState:
    def editor(self, monkeypatch, player, answer):
        editor = make_editor()
        editor._video_player = player
        scripts = []

        async def run(script, **k):
            scripts.append(script)
            return answer

        monkeypatch.setattr("utils.srt.ui.run_javascript", run)

        return editor, scripts

    class Player:
        id = 7

    @pytest.mark.parametrize("answer", ["playing", "stopped"])
    def test_it_is_what_the_player_says(self, monkeypatch, answer):
        editor, scripts = self.editor(monkeypatch, self.Player(), answer)

        assert asyncio.run(editor.context_state()) == answer
        assert "getHtmlElement(7)" in scripts[0]
        assert "_scribeRange" in scripts[0]

    @pytest.mark.parametrize("answer", [None, "", "moved", 3])
    def test_anything_else_is_nothing(self, monkeypatch, answer):
        editor, _ = self.editor(monkeypatch, self.Player(), answer)

        assert asyncio.run(editor.context_state()) is None

    def test_with_no_player_it_is_nothing_and_asks_nothing(self, monkeypatch):
        editor, scripts = self.editor(monkeypatch, None, "playing")

        assert asyncio.run(editor.context_state()) is None
        assert scripts == []


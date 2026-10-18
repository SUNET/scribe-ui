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
        # The same words spoken half as fast: the stretch doubles with them.
        slow = {
            "version": 1,
            "words": [
                {"t": f"w{n}", "s": n * 2.0, "e": n * 2.0 + 1.6}
                for n in range(12)
            ],
        }
        fast = make_editor()
        slow_editor = make_editor(slow)
        for caption, (a, b) in zip(
            slow_editor.captions, ((0, 10), (10, 14), (14, 24))
        ):
            caption.start_time = slow_editor.seconds_to_timestamp(a)
            caption.end_time = slow_editor.seconds_to_timestamp(b)

        fast_range = fast.context_range(fast.captions[1])
        slow_range = slow_editor.context_range(slow_editor.captions[1])

        assert slow_range[1] - slow_range[0] == pytest.approx(
            2 * (fast_range[1] - fast_range[0])
        )

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
        # A pause by the reader, or a seek away, ends the watch.
        assert "video.paused" in script
        assert "video.currentTime < start - 0.5" in script
        # A second request replaces the first rather than running beside it.
        assert "video._scribeStopWatch()" in script

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

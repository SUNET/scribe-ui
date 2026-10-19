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
from utils.transcript_editor import TranscriptEditor


@pytest.fixture
def editor(monkeypatch):
    editor = SRTEditor("job-uuid", "srt", "file.srt")

    for name in ("refresh_display", "update_words_per_minute", "mark_as_changed"):
        setattr(editor, name, lambda *args, **kwargs: None)

    # Every undo step pushes a marker, so steps can be counted.
    editor.save_state_for_undo = lambda: editor.undo_redo_manager.undo_stack.append(
        object()
    )
    editor.notes = []
    monkeypatch.setattr(
        "utils.srt.ui.notify", lambda *a, **k: editor.notes.append(a[0])
    )

    editor.captions = [
        SRTCaption(1, "00:00:01,000", "00:00:02,000", "one"),
        SRTCaption(2, "00:00:02,500", "00:00:04,000", "two"),
        SRTCaption(3, "00:00:05,000", "00:00:06,000", "three"),
    ]

    return editor


def times(editor):
    return [(c.start_time, c.end_time) for c in editor.captions]


class TestNudgeCaptionTime:
    def test_start_later(self, editor):
        assert editor.nudge_caption_time(editor.captions[1], "start", "later")

        assert editor.captions[1].start_time == "00:00:02,600"
        assert editor.captions[1].end_time == "00:00:04,000"

    def test_start_earlier(self, editor):
        editor.nudge_caption_time(editor.captions[1], "start", "earlier")

        assert editor.captions[1].start_time == "00:00:02,400"
        assert editor.captions[1].end_time == "00:00:04,000"

    def test_end_later(self, editor):
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert editor.captions[1].start_time == "00:00:02,500"
        assert editor.captions[1].end_time == "00:00:04,100"

    def test_end_earlier(self, editor):
        editor.nudge_caption_time(editor.captions[1], "end", "earlier")

        assert editor.captions[1].end_time == "00:00:03,900"

    def test_the_neighbours_do_not_move(self, editor):
        editor.nudge_caption_time(editor.captions[1], "start", "earlier")
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert editor.captions[0].start_time == "00:00:01,000"
        assert editor.captions[0].end_time == "00:00:02,000"
        assert editor.captions[2].start_time == "00:00:05,000"
        assert editor.captions[2].end_time == "00:00:06,000"

    def test_the_text_is_untouched(self, editor):
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert [c.text for c in editor.captions] == ["one", "two", "three"]

    def test_a_step_is_a_tenth_of_a_second_without_drift(self, editor):
        for _ in range(30):
            editor.nudge_caption_time(editor.captions[1], "end", "later")

        # 4.000 + 30 * 0.1: whole milliseconds, no float residue.
        assert editor.captions[1].end_time == "00:00:07,000"

    def test_overlap_with_a_neighbour_is_allowed(self, editor):
        """
        Reporting it is the validation's job, as it is for a drag.
        """

        for _ in range(10):
            editor.nudge_caption_time(editor.captions[0], "end", "later")

        assert editor.captions[0].end_time == "00:00:03,000"
        assert editor.captions[1].start_time == "00:00:02,500"

    def test_the_start_cannot_pass_the_end(self, editor):
        caption = editor.captions[0]

        for _ in range(30):
            editor.nudge_caption_time(caption, "start", "later")

        # Stops one step short of the end.
        assert caption.start_time == "00:00:01,900"
        assert caption.end_time == "00:00:02,000"

    def test_the_end_cannot_pass_the_start(self, editor):
        caption = editor.captions[0]

        for _ in range(30):
            editor.nudge_caption_time(caption, "end", "earlier")

        assert caption.start_time == "00:00:01,000"
        assert caption.end_time == "00:00:01,100"

    def test_refusing_says_why_and_changes_nothing(self, editor):
        caption = editor.captions[0]
        caption.end_time = "00:00:01,100"
        before = times(editor)
        steps = len(editor.undo_redo_manager.undo_stack)

        assert not editor.nudge_caption_time(caption, "end", "earlier")

        assert times(editor) == before
        assert len(editor.undo_redo_manager.undo_stack) == steps
        assert editor.notes == ["The end cannot move before the start of the caption"]

    def test_the_start_cannot_go_before_the_beginning(self, editor):
        caption = editor.captions[0]
        caption.start_time = "00:00:00,050"

        # A step that would go too far goes as far as it can ...
        assert editor.nudge_caption_time(caption, "start", "earlier")
        assert caption.start_time == "00:00:00,000"

        # ... and then there is nowhere to go.
        assert not editor.nudge_caption_time(caption, "start", "earlier")
        assert editor.notes == ["The start is already at the beginning of the recording"]

    def test_the_end_stops_at_the_end_of_the_recording_when_known(self, editor):
        editor.media_seconds = 6.05
        caption = editor.captions[2]

        assert editor.nudge_caption_time(caption, "end", "later")
        assert caption.end_time == "00:00:06,050"
        assert not editor.nudge_caption_time(caption, "end", "later")
        assert editor.notes == ["The end is already at the end of the recording"]

    def test_without_a_known_length_the_end_is_not_capped(self, editor):
        editor.media_seconds = None

        assert editor.nudge_caption_time(editor.captions[2], "end", "later")

    def test_an_earlier_start_that_passes_the_previous_caption_reorders(self, editor):
        caption = editor.captions[1]
        caption.start_time = "00:00:01,050"

        editor.nudge_caption_time(caption, "start", "earlier")
        editor.nudge_caption_time(caption, "start", "earlier")

        assert [c.text for c in editor.captions] == ["two", "one", "three"]
        assert [c.index for c in editor.captions] == [1, 2, 3]

    @pytest.mark.parametrize(
        "edge,direction", [("middle", "later"), ("start", "sideways"), (None, None)]
    )
    def test_unknown_edge_or_direction_does_nothing(self, editor, edge, direction):
        before = times(editor)

        assert not editor.nudge_caption_time(editor.captions[1], edge, direction)

        assert times(editor) == before


class TestNudgeUndo:
    def steps(self, editor):
        return len(editor.undo_redo_manager.undo_stack)

    def test_one_nudge_is_one_step(self, editor):
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert self.steps(editor) == 1

    def test_a_run_of_nudges_of_the_same_edge_is_one_step(self, editor):
        for _ in range(5):
            editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert self.steps(editor) == 1

    def test_the_other_edge_is_a_new_step(self, editor):
        editor.nudge_caption_time(editor.captions[1], "end", "later")
        editor.nudge_caption_time(editor.captions[1], "start", "later")

        assert self.steps(editor) == 2

    def test_another_caption_is_a_new_step(self, editor):
        editor.nudge_caption_time(editor.captions[0], "end", "later")
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert self.steps(editor) == 2

    def test_anything_saved_in_between_ends_the_run(self, editor):
        editor.nudge_caption_time(editor.captions[1], "end", "later")
        editor.save_state_for_undo()  # an edit of some other kind
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert self.steps(editor) == 3

    def test_a_full_history_does_not_hide_a_save_in_between(self, editor):
        stack = editor.undo_redo_manager.undo_stack
        saves = []

        def save():
            saves.append(1)
            stack.append(object())
            if len(stack) > 3:
                stack.pop(0)

        editor.save_state_for_undo = save
        stack.extend(object() for _ in range(3))

        editor.nudge_caption_time(editor.captions[1], "end", "later")
        editor.save_state_for_undo()  # the depth is the same afterwards
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        # The nudge, the other save, and a new step for the second nudge.
        assert len(saves) == 3

    def test_a_pause_ends_the_run(self, editor, monkeypatch):
        clock = [100.0]
        monkeypatch.setattr("utils.srt.time.monotonic", lambda: clock[0])

        editor.nudge_caption_time(editor.captions[1], "end", "later")
        clock[0] += SRTEditor.NUDGE_UNDO_WINDOW + 0.1
        editor.nudge_caption_time(editor.captions[1], "end", "later")

        assert self.steps(editor) == 2

    def test_a_refused_nudge_saves_nothing(self, editor):
        editor.captions[0].start_time = "00:00:00,000"

        editor.nudge_caption_time(editor.captions[0], "start", "earlier")

        assert self.steps(editor) == 0


class TestNudgeHandler:
    @pytest.fixture
    def view(self, editor, monkeypatch):
        view = TranscriptEditor(editor)
        self.calls = []
        view.refresh = lambda *a, **k: self.calls.append("refresh")
        view.changed = lambda *a, **k: self.calls.append("changed")
        view.focus = lambda *a, **k: self.calls.append(("focus", a))

        return view

    def test_the_event_reaches_the_view(self):
        source = pathlib.Path("utils/transcript_editor.py").read_text()

        assert 'self.body.on("nudge", lambda event: self.nudge(event.args))' in source

    def test_it_nudges_redraws_and_puts_the_caret_back(self, view, editor):
        caption = editor.captions[1]

        view.nudge(
            {"id": caption.index, "edge": "end", "direction": "later", "offset": 2}
        )

        assert caption.end_time == "00:00:04,100"
        assert self.calls == ["refresh", "changed", ("focus", (caption.index, 2))]

    def test_the_caret_follows_the_caption_up_the_list(self, view, editor):
        caption = editor.captions[1]
        caption.start_time = "00:00:01,050"

        view.nudge(
            {"id": caption.index, "edge": "start", "direction": "earlier", "offset": 1}
        )
        view.nudge(
            {"id": caption.index, "edge": "start", "direction": "earlier", "offset": 1}
        )

        # It is caption 1 now, and the caret goes there.
        assert caption.index == 1
        assert self.calls[-1] == ("focus", (1, 1))

    def test_a_refusal_redraws_nothing(self, view, editor):
        editor.captions[0].start_time = "00:00:00,000"

        view.nudge(
            {"id": editor.captions[0].index, "edge": "start",
             "direction": "earlier", "offset": 0}
        )

        assert self.calls == []

    @pytest.mark.parametrize(
        "args",
        [
            None,
            {},
            {"id": 9999, "edge": "start", "direction": "later", "offset": 0},
            {"id": 1, "edge": "x", "direction": "later", "offset": 0},
        ],
    )
    def test_bad_input_is_harmless(self, view, editor, args):
        before = times(editor)

        view.nudge(args)

        assert times(editor) == before
        assert self.calls == []

    def test_a_missing_offset_puts_the_caret_at_the_start(self, view, editor):
        caption = editor.captions[1]

        view.nudge({"id": caption.index, "edge": "end", "direction": "later"})

        assert self.calls[-1] == ("focus", (caption.index, 0))


class TestTheKeys:
    def source(self):
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def keys(self, name):
        source = self.source()
        body = source[source.index(f"\n    {name}(event, at) {{") + 1:]

        return body[: body.index("\n    },")]

    def test_subtitles_take_them(self):
        keys = self.keys("subtitleShortcut")

        assert 'event.code === "Comma" || event.code === "Period"' in keys
        assert 'this.report(event, "nudge", {' in keys
        assert 'edge: event.shiftKey ? "end" : "start"' in keys
        assert 'direction: event.code === "Comma" ? "earlier" : "later"' in keys
        assert "offset: at.offset" in keys

    def test_ctrl_only_never_cmd_or_alt(self):
        keys = self.keys("subtitleShortcut")
        nudge = keys[keys.index("event.ctrlKey &&"):keys.index('this.report(event, "nudge"')]

        assert "event.ctrlKey" in nudge
        assert "!event.metaKey" in nudge
        assert "!event.altKey" in nudge

    def test_they_go_by_the_physical_key(self):
        """
        Shift turns , and . into ; and : on a Swedish keyboard.
        """

        keys = self.keys("subtitleShortcut")
        nudge = keys[keys.index("event.ctrlKey &&"):keys.index('this.report(event, "nudge"')]

        assert "event.key" not in nudge

    def test_transcriptions_do_not_have_them(self):
        """
        The nudge is a subtitle-editor feature: a paragraph has no strip
        and no caption times to fine-tune by ear.
        """

        assert "nudge" not in self.keys("transcriptionShortcut")

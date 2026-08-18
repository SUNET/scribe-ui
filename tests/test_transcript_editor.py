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
The transcription editor's server side: speakers, timings and the block
structure. The contenteditable itself needs a browser, but everything it
reports back is handled here and can be tested directly.
"""


import pytest

from utils.caption import SRTCaption
from utils.srt import SRTEditor
from utils.transcript_editor import TranscriptEditor, format_time_label


SEGMENTS = [
    {"speaker": "Speaker 1", "text": "ett.", "start": 0.0, "end": 1.0},
    {"speaker": "Speaker 2", "text": "tva.", "start": 1.0, "end": 2.0},
    {"speaker": "Speaker 2", "text": "tre.", "start": 2.0, "end": 3.0},
    {"speaker": "Speaker 3", "text": "fyra.", "start": 3.0, "end": 4.0},
]


@pytest.fixture
def editor():
    editor = SRTEditor("job-uuid", "txt", "file.txt")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *a, **k: None)

    # One caption per segment, so runs of the same speaker can be exercised.
    editor.captions = [
        SRTCaption(
            i + 1,
            editor.seconds_to_timestamp(s["start"]),
            editor.seconds_to_timestamp(s["end"]),
            s["text"],
            speaker=s["speaker"],
        )
        for i, s in enumerate(SEGMENTS)
    ]
    editor.speakers = {s["speaker"] for s in SEGMENTS}

    return editor


@pytest.fixture
def view(editor, monkeypatch):
    view = TranscriptEditor(editor)
    # No component attached, so refreshing is a no-op and notifications are
    # swallowed; the state changes are what matter here.
    monkeypatch.setattr("utils.transcript_editor.ui.notify", lambda *a, **k: None)

    return view


def speakers(editor):
    return [caption.speaker for caption in editor.captions]


class TestApplySpeaker:
    def test_renames_a_single_block(self, view, editor):
        view.apply_speaker(editor.captions[1], "Anna", False)

        assert speakers(editor) == ["Speaker 1", "Anna", "Speaker 2", "Speaker 3"]

    def test_renames_the_whole_run(self, view, editor):
        view.apply_speaker(editor.captions[1], "Anna", True)

        assert speakers(editor) == ["Speaker 1", "Anna", "Anna", "Speaker 3"]

    def test_a_new_name_is_remembered_for_next_time(self, view, editor):
        view.apply_speaker(editor.captions[0], "Bertil", False)

        assert "Bertil" in editor.speakers

    def test_name_is_trimmed(self, view, editor):
        view.apply_speaker(editor.captions[0], "  Anna  ", False)

        assert editor.captions[0].speaker == "Anna"

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_is_refused(self, view, editor, name):
        before = speakers(editor)

        view.apply_speaker(editor.captions[0], name, False)

        assert speakers(editor) == before

    def test_unchanged_name_is_a_no_op(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.apply_speaker(editor.captions[0], "Speaker 1", True)

        assert marked == [], "nothing changed, so nothing should be marked dirty"

    def test_run_is_resolved_before_reassignment(self, view, editor):
        """
        The run is found by matching the current speaker, so it has to be
        worked out before any of it is renamed -- otherwise renaming the first
        block cuts the run short.
        """

        view.apply_speaker(editor.captions[1], "Anna", True)

        assert speakers(editor).count("Anna") == 2


class TestSpeakerRun:
    def test_run_covers_neighbours_with_the_same_speaker(self, view, editor):
        run = view.speaker_run(editor.captions[2])

        assert [c.index for c in run] == [2, 3]

    def test_run_of_one(self, view, editor):
        assert view.speaker_run(editor.captions[0]) == [editor.captions[0]]


class TestBlocks:
    def test_one_block_per_caption(self, view, editor):
        assert len(view.blocks()) == len(editor.captions)

    def test_block_carries_speaker_and_labels(self, view):
        block = view.blocks()[0]

        assert block["speaker"] == "Speaker 1"
        assert block["start_label"] == "00:00:00 .000"
        assert block["end_label"] == "00:00:01 .000"

    def test_ids_match_caption_indices(self, view, editor):
        assert [b["id"] for b in view.blocks()] == [c.index for c in editor.captions]


class TestEventPayloads:
    """
    Everything here arrives from the browser, so nothing is trusted.
    """

    @pytest.mark.parametrize(
        "args", [None, "nonsense", {}, {"id": "1"}, {"id": None}, 42]
    )
    def test_bad_block_id_is_ignored(self, view, args):
        assert view.block_id(args) is None
        assert view.caption(view.block_id(args)) is None

    def test_unknown_block_id_is_ignored(self, view):
        assert view.caption(9999) is None

    def test_set_text_ignores_a_non_string(self, view, editor):
        before = editor.captions[0].text

        view.set_text({"id": 1, "text": None})

        assert editor.captions[0].text == before

    def test_set_text_applies(self, view, editor):
        view.set_text({"id": 1, "text": "annat."})

        assert editor.captions[0].text == "annat."

    def test_split_ignores_a_non_numeric_offset(self, view, editor):
        before = len(editor.captions)

        view.split({"id": 1, "offset": "two"})

        assert len(editor.captions) == before


class TestTimeLabel:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0.0, "00:00:00 .000"),
            (1226.86, "00:20:26 .860"),
            (3599.9999, "01:00:00 .000"),
            (-5.0, "00:00:00 .000"),
        ],
    )
    def test_matches_the_reference_format(self, seconds, expected):
        assert format_time_label(seconds) == expected


class TestEnterAtBlockEnd:
    """
    Enter at the end of a block has nothing to divide, so it starts a new
    block -- what Enter does at the end of a paragraph anywhere else. The
    subtitle editor's split is unaffected.
    """

    def test_new_block_is_added_after(self, view, editor):
        target = editor.captions[0]

        view.split({"id": target.index, "offset": len(target.text)})

        assert [c.text for c in editor.captions] == ["ett.", "", "tva.", "tre.", "fyra."]

    def test_new_block_inherits_the_speaker(self, view, editor):
        target = editor.captions[0]

        view.split({"id": target.index, "offset": len(target.text)})

        assert editor.captions[1].speaker == "Speaker 1"

    def test_new_block_claims_no_time(self, view, editor):
        """
        It sits on the boundary where the previous block ended. An empty block
        has nothing to time against, so it takes no duration rather than
        overlapping its neighbour or inventing audio.
        """

        target = editor.captions[0]

        view.split({"id": target.index, "offset": len(target.text)})
        added = editor.captions[1]

        assert added.get_start_seconds() == pytest.approx(1.0)
        assert added.get_end_seconds() == pytest.approx(1.0)

    def test_new_block_at_the_very_end_also_claims_no_time(self, view, editor):
        last = editor.captions[-1]
        boundary = last.get_end_seconds()

        view.split({"id": last.index, "offset": len(last.text)})
        added = editor.captions[-1]

        assert added.text == ""
        assert added.get_start_seconds() == pytest.approx(boundary)
        assert added.get_end_seconds() == pytest.approx(boundary)

    def test_blocks_are_renumbered(self, view, editor):
        view.split({"id": editor.captions[0].index, "offset": 4})

        assert [c.index for c in editor.captions] == list(
            range(1, len(editor.captions) + 1)
        )

    def test_trailing_whitespace_counts_as_the_end(self, view, editor):
        target = editor.captions[0]
        target.text = "ett. "

        view.split({"id": target.index, "offset": 4})

        assert editor.captions[1].text == ""

    def test_caret_inside_the_text_still_splits(self, view, editor):
        target = editor.captions[3]
        target.text = "fyra fem"

        view.split({"id": target.index, "offset": 4})

        assert [c.text for c in editor.captions[3:]] == ["fyra", "fem"]
        assert "" not in [c.text for c in editor.captions]

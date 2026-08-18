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


class TestAssignSpeaker:
    """
    Clicking a name in the menu moves this block to that speaker. One block:
    who said this is a different question from what a speaker is called.
    """

    def test_assigns_one_block(self, view, editor):
        view.assign_speaker({"id": 2, "speaker": "Speaker 3"})

        assert speakers(editor) == ["Speaker 1", "Speaker 3", "Speaker 2", "Speaker 3"]

    def test_name_is_trimmed(self, view, editor):
        view.assign_speaker({"id": 1, "speaker": "  Speaker 3  "})

        assert editor.captions[0].speaker == "Speaker 3"

    def test_a_name_not_yet_known_is_remembered(self, view, editor):
        view.assign_speaker({"id": 1, "speaker": "Ida"})

        assert "Ida" in editor.speakers

    def test_same_speaker_is_a_no_op(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.assign_speaker({"id": 1, "speaker": "Speaker 1"})

        assert marked == []

    @pytest.mark.parametrize(
        "args",
        [None, "nonsense", {}, {"id": 1}, {"id": 1, "speaker": None},
         {"id": 1, "speaker": "  "}, {"id": 9999, "speaker": "Ida"}],
    )
    def test_bad_payload_is_ignored(self, view, editor, args):
        before = speakers(editor)

        view.assign_speaker(args)

        assert speakers(editor) == before


class TestRenameSpeaker:
    """
    The pencil renames a speaker wherever it appears -- what a diarisation
    label needs, since "Speaker 2" is one person throughout.
    """

    def test_renames_every_block_with_that_name(self, view, editor):
        view.rename_speaker("Speaker 2", "Ida")

        assert speakers(editor) == ["Speaker 1", "Ida", "Ida", "Speaker 3"]

    def test_old_name_leaves_the_list(self, view, editor):
        view.rename_speaker("Speaker 2", "Ida")

        assert "Speaker 2" not in editor.speakers
        assert "Ida" in editor.speakers

    def test_renaming_onto_an_existing_name_is_refused(self, view, editor):
        """
        Merging two speakers is a different act; doing it silently here would
        make the old name unrecoverable.
        """

        view.rename_speaker("Speaker 2", "Speaker 1")

        assert speakers(editor) == ["Speaker 1", "Speaker 2", "Speaker 2", "Speaker 3"]

    @pytest.mark.parametrize("new", ["", "   ", None])
    def test_blank_name_is_refused(self, view, editor, new):
        view.rename_speaker("Speaker 2", new)

        assert "Speaker 2" in editor.speakers

    def test_renaming_to_itself_is_a_no_op(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.rename_speaker("Speaker 2", "Speaker 2")

        assert marked == []

    def test_rename_of_an_unused_speaker_touches_no_blocks(self, view, editor):
        editor.speakers.add("Leftover")
        before = speakers(editor)

        view.rename_speaker("Leftover", "Ida")

        assert speakers(editor) == before
        assert "Ida" in editor.speakers

    @pytest.mark.parametrize(
        "args", [None, "nonsense", {}, {"speaker": None}, {"speaker": "Nobody"}]
    )
    def test_bad_rename_payload_is_ignored(self, view, editor, args):
        before = speakers(editor)

        view.prompt_rename(args)

        assert speakers(editor) == before


class TestAddSpeaker:
    def test_adds_a_name_without_touching_blocks(self, view, editor):
        before = speakers(editor)

        view.add_speaker("Ida")

        assert "Ida" in editor.speakers
        assert speakers(editor) == before

    def test_duplicate_is_refused(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.add_speaker("Speaker 1")

        assert marked == []

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_is_refused(self, view, editor, name):
        before = set(editor.speakers)

        view.add_speaker(name)

        assert editor.speakers == before

    def test_name_is_trimmed(self, view, editor):
        view.add_speaker("  Ida  ")

        assert "Ida" in editor.speakers


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


class TestEditorContract:
    """
    The transcription editor drives the SRTEditor rather than duplicating it,
    so it depends on a set of methods there. Nothing else checks that they
    exist: a missing one only shows up as an AttributeError when a user clicks
    the thing that needs it. This caught seek_video going missing in a revert.
    """

    def required(self):
        import re
        from pathlib import Path

        source = Path("utils/transcript_editor.py").read_text()

        return sorted(set(re.findall(r"self\.editor\.(\w+)", source)))

    def test_every_member_it_uses_exists(self, editor):
        missing = [
            name
            for name in self.required()
            if not hasattr(editor, name)
        ]

        assert missing == [], f"SRTEditor is missing {missing}"

    def test_it_uses_more_than_nothing(self):
        """
        Guards the guard: a regex that stopped matching would pass silently.
        """

        assert len(self.required()) > 8

    def test_seeking_reaches_the_player(self, view, editor):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        editor.set_video_player(Player())

        view.seek({"id": editor.captions[1].index})

        assert sought == [pytest.approx(1.0)]

    def test_seeking_without_a_player_is_harmless(self, view, editor):
        view.seek({"id": editor.captions[0].index})

    def test_seeking_an_unknown_block_is_harmless(self, view, editor):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        editor.set_video_player(Player())

        view.seek({"id": 9999})

        assert sought == []


class TestRemoveSpeaker:
    """
    A speaker can only leave the list once nothing is attributed to it.
    Removing one that is still in use would leave those blocks pointing at a
    name the transcription no longer knows.
    """

    def test_unused_speaker_is_removed(self, view, editor):
        editor.speakers.add("Unused")

        assert view.remove_speaker("Unused") is True
        assert "Unused" not in editor.speakers

    def test_speaker_in_use_is_refused(self, view, editor):
        assert view.remove_speaker("Speaker 1") is False
        assert "Speaker 1" in editor.speakers

    def test_speaker_used_by_one_block_is_refused(self, view, editor):
        """
        The last block of a speaker still counts as in use.
        """

        assert view.speaker_in_use("Speaker 3") is True
        assert view.remove_speaker("Speaker 3") is False

    def test_unknown_name_is_refused(self, view, editor):
        assert view.remove_speaker("Nobody") is False

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_is_refused(self, view, name):
        assert view.remove_speaker(name) is False

    def test_name_is_trimmed_before_matching(self, view, editor):
        editor.speakers.add("Unused")

        assert view.remove_speaker("  Unused  ") is True

    def test_removal_marks_the_transcription_changed(self, view, editor):
        """
        The number of speakers is part of what gets saved, so this is not a
        display-only change.
        """

        marked = []
        editor.mark_as_changed = lambda: marked.append(True)
        editor.speakers.add("Unused")

        view.remove_speaker("Unused")

        assert marked == [True]

    def test_refused_removal_marks_nothing(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.remove_speaker("Speaker 1")

        assert marked == []

    def test_a_speaker_freed_by_renaming_can_then_be_removed(self, view, editor):
        """
        The realistic route: two labels are the same person, so one is renamed
        onto the other and the empty label is tidied away.
        """

        view.assign_speaker({"id": 4, "speaker": "Speaker 1"})

        assert view.speaker_in_use("Speaker 3") is False
        assert view.remove_speaker("Speaker 3") is True

    def test_speaker_in_use_is_exact(self, view, editor):
        assert view.speaker_in_use("Speaker") is False
        assert view.speaker_in_use("speaker 1") is False


class TestSeekToCaret:
    """
    Clicking in the text moves the recording to the word the caret landed on,
    so pressing play carries on from there rather than from the top of the
    block.
    """

    @pytest.fixture
    def timed(self, editor):
        editor.captions = [
            SRTCaption(1, "00:00:10,000", "00:00:20,000", "Vi har demokratin idag")
        ]
        editor.load_words({"version": 1, "words": [
            {"t": "Vi", "s": 10.0, "e": 10.4},
            {"t": "har", "s": 10.5, "e": 10.9},
            {"t": "demokratin", "s": 11.0, "e": 12.2},
            {"t": "idag", "s": 12.5, "e": 13.0},
        ]})

        return editor

    def test_caret_maps_to_the_word_it_is_in(self, view, timed):
        caption = timed.captions[0]

        assert view.time_at_offset(caption, 0) == pytest.approx(10.0)
        assert view.time_at_offset(caption, 4) == pytest.approx(10.5)
        assert view.time_at_offset(caption, 10) == pytest.approx(11.0)
        assert view.time_at_offset(caption, 20) == pytest.approx(12.5)

    def test_right_edge_of_a_word_plays_that_word(self, view, timed):
        """
        Clicking a word's right hand side puts the caret at its end. That has
        to play that word, not the next one.
        """

        assert view.time_at_offset(timed.captions[0], 2) == pytest.approx(10.0)
        assert view.time_at_offset(timed.captions[0], 6) == pytest.approx(10.5)

    def test_caret_in_the_space_plays_the_following_word(self, view, timed):
        assert view.time_at_offset(timed.captions[0], 3) == pytest.approx(10.5)

    def test_past_the_end_plays_the_last_word(self, view, timed):
        caption = timed.captions[0]

        assert view.time_at_offset(caption, len(caption.text)) == pytest.approx(12.5)
        assert view.time_at_offset(caption, 9999) == pytest.approx(12.5)

    @pytest.mark.parametrize("offset", [None, "nonsense", -5])
    def test_an_unusable_offset_falls_back_to_the_block(self, view, timed, offset):
        assert view.time_at_offset(timed.captions[0], offset) == pytest.approx(10.0)

    def test_without_word_data_it_falls_back_to_the_block(self, view, timed):
        timed.load_words(None)

        assert view.time_at_offset(timed.captions[0], 10) == pytest.approx(10.0)

    def test_an_edited_word_has_no_time_to_move_to(self, view, timed):
        """
        Nothing in the recording corresponds to a word the reader wrote, so
        there is no honest place to move to.
        """

        caption = timed.captions[0]
        caption.text = "Vi har DEMOKRATI idag"

        # Caret inside the edited word.
        assert view.time_at_offset(caption, 10) is None

    def test_the_words_around_an_edit_still_have_their_own(self, view, timed):
        caption = timed.captions[0]
        caption.text = "Vi har DEMOKRATI idag"

        assert view.time_at_offset(caption, 0) == pytest.approx(10.0)
        assert view.time_at_offset(caption, 4) == pytest.approx(10.5)
        assert view.time_at_offset(caption, 20) == pytest.approx(12.5)

    def test_clicking_an_edited_word_leaves_the_recording_alone(self, view, timed):
        """
        Reported from a screenshot: clicking a word carrying "You changed this
        word" moved the recording to the word before it, and the word-follower
        then lit that word up as though it were the one clicked.
        """

        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())
        timed.captions[0].text = "Vi har DEMOKRATI idag"

        view.seek({"id": 1, "offset": 10})

        assert sought == []

    def test_clicking_an_untouched_word_still_seeks(self, view, timed):
        """
        Guards the guard above: the seek must not have stopped working.
        """

        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())
        timed.captions[0].text = "Vi har DEMOKRATI idag"

        view.seek({"id": 1, "offset": 4})

        assert sought == [pytest.approx(10.5)]

    def test_empty_block_falls_back_to_the_block(self, view, timed):
        caption = timed.captions[0]
        caption.text = ""

        assert view.time_at_offset(caption, 0) == pytest.approx(10.0)

    def test_click_seeks_the_player(self, view, timed):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())

        view.seek({"id": 1, "offset": 10})

        assert sought == [pytest.approx(11.0)]

    def test_click_without_an_offset_seeks_the_block_start(self, view, timed):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())

        view.seek({"id": 1})

        assert sought == [pytest.approx(10.0)]


class TestSpeakerMenuIcons:
    """
    The rename control in the speaker menu.
    """

    def template(self) -> str:
        from pathlib import Path

        source = Path("utils/transcript_editor.js").read_text()
        start = source.index("template: `")

        return source[start:source.index("`,", start)]

    def rename_icon(self) -> str:
        template = self.template()
        start = template.index("renamespeaker")
        # Back up to the element the handler is on.
        opening = template.rindex("<q-icon", 0, start)

        return template[opening:template.index("</q-icon>", start) + len("</q-icon>")]

    def test_rename_uses_the_person_edit_icon(self):
        assert 'name="sym_o_person_edit"' in self.rename_icon()

    def test_it_asks_for_it_from_the_symbols_set(self):
        """
        person_edit only exists in Material Symbols, not in Material Icons.
        Without Quasar's sym_o_ prefix the name is not an icon at all and the
        ligature text renders in its place. Both fonts ship with NiceGUI.
        """

        icon = self.rename_icon()

        assert "person_edit" in icon
        assert "sym_o_person_edit" in icon, "needs the Material Symbols prefix"

    def test_it_says_what_it_does(self):
        assert "<q-tooltip>Rename speaker</q-tooltip>" in self.rename_icon()

    def test_the_tooltip_is_anchored_to_the_icon(self):
        """
        Inside the element, so Quasar anchors it there rather than to the row.
        """

        icon = self.rename_icon()

        assert icon.endswith("<q-tooltip>Rename speaker</q-tooltip></q-icon>")

    def test_it_still_only_renames(self):
        """
        The row underneath assigns the speaker, so the icon has to keep
        swallowing the click.
        """

        icon = self.rename_icon()

        assert "@click.stop=" in icon
        assert "renamespeaker" in icon

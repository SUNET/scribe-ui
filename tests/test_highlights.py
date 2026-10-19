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
The reader's own highlights: kept per word, carried through every edit that
moves words, saved with a transcription, drawn, and optionally exported.
"""

import json
import pathlib
import re

import pytest

from utils.caption import SRTCaption
from utils.srt import SRTEditor
from utils.transcript_editor import TranscriptEditor


WORDS = {
    "version": 1,
    "words": [
        {"t": "ett", "s": 0.0, "e": 0.5},
        {"t": "två", "s": 0.6, "e": 1.0},
        {"t": "tre", "s": 1.1, "e": 1.5},
        {"t": "fyra", "s": 2.0, "e": 2.4},
        {"t": "fem", "s": 2.5, "e": 2.9},
        {"t": "sex", "s": 3.0, "e": 3.5},
    ],
}


def make_editor(data_format="txt"):
    editor = SRTEditor("job-uuid", data_format, "file")

    editor.changed = 0
    editor.snapshots = 0

    def mark():
        editor.changed += 1

    def snapshot():
        editor.snapshots += 1

    editor.refresh_display = lambda *a, **k: None
    editor.update_words_per_minute = lambda *a, **k: None
    editor.update_flagged_count = lambda *a, **k: None
    editor.mark_as_changed = mark
    editor.save_state_for_undo = snapshot

    editor.load_words(WORDS)
    editor.captions = [
        SRTCaption(1, "00:00:00,000", "00:00:01,500", "ett två tre", speaker="A"),
        SRTCaption(2, "00:00:02,000", "00:00:03,500", "fyra fem sex", speaker="A"),
    ]
    editor.speakers = {"A"}

    return editor


@pytest.fixture
def editor(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "utils.srt.ui.notify", lambda message, **k: messages.append(message)
    )
    built = make_editor()
    built.messages = messages

    return built


class TestWordsInSelection:
    def test_a_selection_takes_the_words_it_touches(self, editor):
        assert editor.words_in_selection("ett två tre", 4, 7) == [1]

    def test_a_selection_ending_inside_a_word_takes_all_of_it(self, editor):
        assert editor.words_in_selection("ett två tre", 1, 5) == [0, 1]

    def test_a_selection_only_brushing_an_edge_does_not_take_that_word(self, editor):
        # Ends where "två" begins; starts where "ett" ends.
        assert editor.words_in_selection("ett två tre", 0, 4) == [0]
        assert editor.words_in_selection("ett två tre", 3, 8) == [1]

    def test_the_whole_text(self, editor):
        assert editor.words_in_selection("ett två tre", 0, 11) == [0, 1, 2]

    def test_a_backwards_selection_is_the_same(self, editor):
        assert editor.words_in_selection("ett två tre", 7, 4) == [1]

    def test_a_caret_in_a_word_takes_that_word(self, editor):
        assert editor.words_in_selection("ett två tre", 5, 5) == [1]

    def test_a_caret_against_either_edge_of_a_word_takes_that_word(self, editor):
        assert editor.words_in_selection("ett två tre", 3, 3) == [0]
        assert editor.words_in_selection("ett två tre", 4, 4) == [1]

    def test_a_caret_in_the_space_between_words_takes_none(self, editor):
        assert editor.words_in_selection("ett  två", 4, 4) == []

    def test_line_breaks_separate_words_too(self, editor):
        assert editor.words_in_selection("ett\ntvå", 4, 6) == [1]

    def test_empty_text(self, editor):
        assert editor.words_in_selection("", 0, 0) == []


class TestCarryHighlights:
    def carry(self, editor, before, after, marked):
        return editor.carry_highlights(before, after, set(marked))

    def test_words_that_stay_move_with_their_marks(self, editor):
        assert self.carry(editor, "b c", "a b c", {0}) == {1}

    def test_words_removed_take_their_marks_with_them(self, editor):
        assert self.carry(editor, "a b c", "a c", {1}) == set()
        assert self.carry(editor, "a b c", "a c", {0, 1, 2}) == {0, 1}

    def test_a_word_corrected_inside_a_highlight_stays_highlighted(self, editor):
        assert self.carry(editor, "teh cat sat", "the cat sat", {0, 1}) == {0, 1}

    def test_a_word_corrected_elsewhere_does_not_gain_one(self, editor):
        assert self.carry(editor, "teh cat sat", "the cat sat", {1}) == {1}

    def test_a_new_word_does_not_earn_a_highlight(self, editor):
        assert self.carry(editor, "a b", "a new b", set()) == set()
        assert self.carry(editor, "a b", "a b new", {0, 1}) == {0, 1}

    def test_a_word_typed_inside_a_highlight_joins_it(self, editor):
        assert self.carry(editor, "a b", "a new b", {0, 1}) == {0, 1, 2}

    def test_a_word_typed_next_to_a_highlight_does_not(self, editor):
        assert self.carry(editor, "a b c", "a b new c", {0, 1}) == {0, 1}
        assert self.carry(editor, "a b c", "new a b c", {0, 1}) == {1, 2}

    def test_a_longer_replacement_of_highlighted_words_is_highlighted(self, editor):
        assert self.carry(editor, "a x y d", "a p q r d", {1, 2}) == {1, 2, 3}

    def test_a_replacement_of_part_of_a_highlight_is_not(self, editor):
        assert self.carry(editor, "a x y d", "a p q r d", {1}) == set()

    def test_a_shorter_replacement_of_highlighted_words_is_highlighted(self, editor):
        assert self.carry(editor, "a x y d", "a p d", {1, 2}) == {1}

    def test_the_input_is_not_changed(self, editor):
        marked = {0}
        editor.carry_highlights("a b", "x a b", marked)

        assert marked == {0}

    def test_no_marks_stay_none(self, editor):
        assert self.carry(editor, "a b c", "a x c d", set()) == set()


class TestToggling:
    def test_it_highlights_the_words_selected(self, editor):
        first = editor.captions[0]

        assert editor.toggle_highlight([(first, 4, 7)]) == "added"

        assert first.highlighted_words == {1}

    def test_the_same_selection_again_takes_it_off(self, editor):
        first = editor.captions[0]
        editor.toggle_highlight([(first, 4, 7)])

        assert editor.toggle_highlight([(first, 4, 7)]) == "removed"

        assert first.highlighted_words == set()

    def test_a_mixed_selection_is_highlighted_throughout(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0}

        assert editor.toggle_highlight([(first, 0, 11)]) == "added"

        assert first.highlighted_words == {0, 1, 2}

    def test_a_selection_inside_a_highlight_takes_off_only_what_it_holds(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 1, 2}

        assert editor.toggle_highlight([(first, 4, 7)]) == "removed"

        assert first.highlighted_words == {0, 2}

    def test_a_selection_across_captions_is_one_gesture(self, editor):
        first, second = editor.captions

        editor.toggle_highlight([(first, 4, 11), (second, 0, 4)])

        assert first.highlighted_words == {1, 2}
        assert second.highlighted_words == {0}
        assert editor.snapshots == 1

    def test_across_captions_it_comes_off_only_when_all_of_it_is_highlighted(
        self, editor
    ):
        first, second = editor.captions
        first.highlighted_words = {1, 2}

        # Not all highlighted yet: the second caption's word is not.
        editor.toggle_highlight([(first, 4, 11), (second, 0, 4)])
        assert second.highlighted_words == {0}

        editor.toggle_highlight([(first, 4, 11), (second, 0, 4)])
        assert first.highlighted_words == set()
        assert second.highlighted_words == set()

    def test_nothing_selected_says_so_and_changes_nothing(self, editor):
        first = editor.captions[0]

        assert editor.toggle_highlight([(first, 3, 4)]) == ""
        assert editor.toggle_highlight([]) == ""

        assert first.highlighted_words == set()
        assert editor.snapshots == 0
        assert editor.changed == 0
        assert editor.messages == ["Select the words to highlight first"] * 2

    def test_it_is_one_undo_step(self, editor):
        editor.toggle_highlight([(editor.captions[0], 0, 11)])

        assert editor.snapshots == 1

    def test_the_text_is_untouched(self, editor):
        editor.toggle_highlight([(editor.captions[0], 0, 11)])

        assert [caption.text for caption in editor.captions] == [
            "ett två tre",
            "fyra fem sex",
        ]
        assert editor.captions[0].edited_words == set()

    def test_a_transcription_counts_it_as_a_change_to_save(self, editor):
        editor.toggle_highlight([(editor.captions[0], 0, 11)])

        assert editor.changed == 1

    def test_subtitles_get_none_for_now(self):
        """
        Plain SRT has nowhere to keep a highlight, so a set of subtitles is
        refused outright -- no change, no undo step, no notice.
        """

        editor = make_editor("srt")

        assert editor.toggle_highlight([(editor.captions[0], 0, 11)]) == ""

        assert editor.captions[0].highlighted_words == set()
        assert editor.snapshots == 0
        assert editor.changed == 0


class TestSavedWithTheTranscription:
    def reopen(self, editor):
        saved = json.dumps(editor.export_json())

        reopened = make_editor()
        reopened.captions = []
        reopened.speakers = set()
        reopened.parse_txt(saved)

        return reopened

    def test_a_copy_does_not_share_the_marks(self):
        caption = SRTCaption(1, "00:00:00,000", "00:00:01,000", "a b")
        caption.highlighted_words = {0}

        copy = caption.copy()
        copy.highlighted_words.add(1)

        assert caption.highlighted_words == {0}

    def test_they_are_in_the_saved_data_only_when_there_are_any(self):
        caption = SRTCaption(1, "00:00:00,000", "00:00:01,000", "a b")

        assert "highlighted" not in caption.to_dict()

        caption.highlighted_words = {1, 0}

        assert caption.to_dict()["highlighted"] == [0, 1]

    def test_they_come_back_when_the_file_is_opened_again(self, editor):
        editor.captions[0].highlighted_words = {0, 2}
        editor.captions[1].highlighted_words = {1}

        reopened = self.reopen(editor)

        assert [caption.highlighted_words for caption in reopened.captions] == [
            {0, 2},
            {1},
        ]

    def test_edit_marks_and_highlights_are_kept_apart(self, editor):
        editor.captions[0].edited_words = {0}
        editor.captions[0].highlighted_words = {2}

        reopened = self.reopen(editor)

        assert reopened.captions[0].edited_words == {0}
        assert reopened.captions[0].highlighted_words == {2}

    def test_a_file_saved_before_this_existed_opens_without_any(self, editor):
        reopened = self.reopen(editor)

        assert all(not caption.highlighted_words for caption in reopened.captions)

    def test_junk_in_the_file_is_ignored(self, editor):
        data = editor.export_json()
        data["segments"][0]["highlighted"] = [0, "x", None, True, 2.5, 1]
        data["segments"][1]["highlighted"] = "all of it"

        reopened = make_editor()
        reopened.captions = []
        reopened.parse_txt(json.dumps(data))

        assert reopened.captions[0].highlighted_words == {0, 1}
        assert reopened.captions[1].highlighted_words == set()


class TestFollowingTheText:
    """
    A highlight is on words, so it has to stay on them whatever the reader does
    to the text around them.
    """

    def test_typing_before_it_moves_it_along(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}

        editor.update_caption_text(first, "nytt ett två tre")

        assert first.highlighted_words == {2}

    def test_correcting_a_word_inside_it_keeps_it(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 1, 2}

        editor.update_caption_text(first, "ett tvo tre")

        assert first.highlighted_words == {0, 1, 2}

    def test_typing_a_word_gives_it_no_highlight_of_its_own(self, editor):
        first = editor.captions[0]

        editor.update_caption_text(first, "ett två tre fyra")

        assert first.highlighted_words == set()

    def test_splitting_divides_them_between_the_halves(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 2}

        editor.split_caption(first, cursor_position=7)

        assert editor.captions[0].text == "ett två"
        assert editor.captions[0].highlighted_words == {0}
        assert editor.captions[1].text == "tre"
        assert editor.captions[1].highlighted_words == {0}

    def test_splitting_with_unsent_text_keeps_them(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {2}

        editor.split_caption(first, cursor_position=8, text="nytt ett två tre")

        assert editor.captions[0].text == "nytt ett"
        assert editor.captions[0].highlighted_words == set()
        assert editor.captions[1].text == "två tre"
        assert editor.captions[1].highlighted_words == {1}

    def test_merging_with_the_next_joins_them(self, editor):
        first, second = editor.captions
        first.highlighted_words = {2}
        second.highlighted_words = {0}

        editor.merge_with_next(first)

        assert editor.captions[0].highlighted_words == {2, 3}

    def test_merging_with_the_previous_joins_them(self, editor):
        first, second = editor.captions
        first.highlighted_words = {2}
        second.highlighted_words = {0}

        editor.merge_with_previous(second)

        assert editor.captions[0].highlighted_words == {2, 3}

    def test_a_word_moved_to_the_previous_caption_takes_its_highlight(self, editor):
        first, second = editor.captions
        second.highlighted_words = {0, 2}

        editor.move_first_word_to_previous(second)

        assert first.highlighted_words == {3}
        assert second.highlighted_words == {1}

    def test_a_word_moved_to_the_next_caption_takes_its_highlight(self, editor):
        first, second = editor.captions
        first.highlighted_words = {0, 2}
        second.highlighted_words = {1}

        editor.move_last_word_to_next(first)

        assert first.highlighted_words == {0}
        assert second.highlighted_words == {0, 2}

    def test_a_word_moved_without_one_leaves_the_rest_alone(self, editor):
        first, second = editor.captions
        second.highlighted_words = {2}

        editor.move_first_word_to_previous(second)

        assert first.highlighted_words == set()
        assert second.highlighted_words == {1}

    def test_deleting_across_captions_keeps_what_is_left(self, editor):
        first, second = editor.captions
        first.highlighted_words = {0, 2}
        second.highlighted_words = {0, 2}

        # From the end of "två" in the first to just after "fyra" in the
        # second: "ett två" and " fem sex" are what is left.
        editor.delete_range(first, second, 7, 4, "")

        assert editor.captions[0].text == "ett två fem sex"
        # "ett" and "sex" were highlighted; "två" and "fem" were not.
        assert editor.captions[0].highlighted_words == {0, 3}

    def test_replacing_text_keeps_them_following_the_words(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {2}
        editor.search_term = "ett"
        editor.selected_caption = first
        editor.case_sensitive = True

        editor.replace_in_current_caption("ett nytt")

        assert first.text == "ett nytt två tre"
        assert first.highlighted_words == {3}


class TestDrawing:
    def runs(self, editor, caption):
        return editor.review_runs(caption)

    def test_nothing_is_drawn_when_nothing_is_highlighted(self, editor):
        assert self.runs(editor, editor.captions[0]) == [
            {"t": "ett två tre", "flag": False}
        ]

    def test_a_highlight_is_drawn_without_any_switch_on(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}

        runs = self.runs(editor, first)

        assert [run["t"] for run in runs if run.get("hl")] == ["två"]
        assert "".join(run["t"] for run in runs) == "ett två tre"

    def test_the_space_between_highlighted_words_is_highlighted_too(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 1}

        runs = self.runs(editor, first)

        assert [run["t"] for run in runs if run.get("hl")] == ["ett", " ", "två"]

    def test_the_space_around_a_lone_highlighted_word_is_not(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}

        runs = self.runs(editor, first)

        assert [run["t"] for run in runs if run.get("hl")] == ["två"]

    def test_a_line_break_between_highlighted_words_is_left_out(self, editor):
        first = editor.captions[0]
        first.text = "ett\ntvå"
        first.highlighted_words = {0, 1}

        runs = self.runs(editor, first)

        assert [run["t"] for run in runs if run.get("hl")] == ["ett", "två"]
        assert "".join(run["t"] for run in runs) == "ett\ntvå"

    def test_highlights_are_not_runs_with_a_flag(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0}

        assert all(run["flag"] is False for run in self.runs(editor, first))

    def test_a_changed_word_can_be_highlighted_too(self, editor):
        editor.show_my_edits = True
        first = editor.captions[0]
        first.highlighted_words = {1}
        first.edited_words = {1}

        run = [run for run in self.runs(editor, first) if run["t"] == "två"][0]

        assert run["hl"] is True
        assert run["edit"] is True

    def test_it_carries_the_word_timing_when_following_the_audio(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}

        runs = editor.review_runs(first, per_word=True)
        run = [run for run in runs if run["t"] == "två"][0]

        assert run["hl"] is True
        assert (run["s"], run["e"]) == (0.6, 1.0)

    def test_other_words_read_as_they_always_did(self, editor):
        editor.show_my_edits = True
        first = editor.captions[0]
        first.highlighted_words = {1}

        runs = self.runs(editor, first)

        assert "hl" not in [run for run in runs if run["t"] == "ett"][0]


class TestRtfExport:
    def export(self, editor, **kwargs):
        return editor.export_rtf(False, False, False, **kwargs)

    def test_a_clean_export_has_no_marking_and_no_colour_table(self, editor):
        editor.captions[0].highlighted_words = {1}
        editor.captions[0].edited_words = {0}

        clean = self.export(editor)

        assert "highlight" not in clean
        assert "colortbl" not in clean
        assert "\\ul" not in clean

    def test_a_clean_export_is_the_same_as_before_highlights_existed(self, editor):
        before = self.export(editor)

        editor.captions[0].highlighted_words = {0, 1}
        editor.captions[1].edited_words = {2}

        assert self.export(editor) == before

    def test_highlights_are_a_yellow_marker_when_asked_for(self, editor):
        editor.captions[0].highlighted_words = {1}

        rtf = self.export(editor, highlights=True)

        assert r"{\colortbl;\red255\green255\blue0;" in rtf
        assert r"ett {\highlight1 tv\u229?} tre" in rtf

    def test_a_passage_is_one_marked_stretch(self, editor):
        editor.captions[0].highlighted_words = {0, 1}

        rtf = self.export(editor, highlights=True)

        assert rtf.count(r"\highlight1") == 1
        assert r"{\highlight1 ett tv\u229?} tre" in rtf

    def test_a_piece_starting_with_a_space_keeps_it(self, editor):
        # The one space after a control word is its delimiter; any more are
        # the text. Two highlighted words with two spaces between them are
        # bridged, so the piece starts at the first word; the piece after a
        # lone highlighted word starts with the spaces.
        editor.captions[0].text = "ett  två"
        editor.captions[0].highlighted_words = {0}

        rtf = self.export(editor, highlights=True)

        assert r"{\highlight1 ett}  tv\u229?" in rtf

    def test_changed_words_are_underlined_and_teal_when_asked_for(self, editor):
        editor.captions[0].edited_words = {2}

        rtf = self.export(editor, edits=True)

        assert r"\red18\green121\blue106;" in rtf
        assert r"{\cf2\ul tre}" in rtf
        assert "highlight1" not in rtf

    def test_both_on_the_same_word(self, editor):
        editor.captions[0].edited_words = {2}
        editor.captions[0].highlighted_words = {2}

        rtf = self.export(editor, highlights=True, edits=True)

        assert r"{\highlight1\cf2\ul tre}" in rtf

    def test_each_is_independent_of_the_other(self, editor):
        editor.captions[0].edited_words = {2}
        editor.captions[0].highlighted_words = {0}

        highlights_only = self.export(editor, highlights=True)
        edits_only = self.export(editor, edits=True)

        assert r"\ul" not in highlights_only
        assert "highlight1" not in edits_only

    def test_the_text_is_the_same_with_or_without(self, editor):
        editor.captions[0].highlighted_words = {0, 1, 2}
        editor.captions[0].edited_words = {1}
        editor.captions[1].highlighted_words = {1}

        def body(rtf):
            return rtf.split(r"\fs20 ", 1)[1]

        marked = body(self.export(editor, highlights=True, edits=True))
        clean = body(self.export(editor))

        # Take the groups back out: what is left must be the clean text.
        stripped = re.sub(
            r"\{(?:\\highlight1)?(?:\\cf2\\ul)? ", "", marked
        )
        # Every group's closing brace goes, but the document's own stays.
        stripped = stripped[:-1].replace("}", "") + "}"

        assert stripped == clean

    def test_subtitles_never_carry_them_for_now(self):
        subtitles = make_editor("srt")
        subtitles.captions[0].edited_words = {0}
        subtitles.captions[0].highlighted_words = {1}

        rtf = self.export(subtitles, highlights=True, edits=True)

        assert "highlight" not in rtf
        assert "colortbl" not in rtf
        assert "\\ul" not in rtf

    def test_a_line_break_is_still_a_line_break(self, editor):
        editor.captions[0].text = "ett\ntvå"
        editor.captions[0].highlighted_words = {0, 1}

        rtf = self.export(editor, highlights=True)

        assert r"{\highlight1 ett}\line {\highlight1 tv\u229?}" in rtf

    def test_special_characters_in_a_marked_word_are_escaped(self, editor):
        editor.captions[0].text = "a {b} c"
        editor.captions[0].highlighted_words = {1}

        rtf = self.export(editor, highlights=True)

        assert r"{\highlight1 \{b\}}" in rtf

    def test_the_braces_balance(self, editor):
        editor.captions[0].highlighted_words = {0, 2}
        editor.captions[0].edited_words = {1, 2}
        editor.captions[1].highlighted_words = {0, 1, 2}

        rtf = self.export(editor, highlights=True, edits=True)
        unescaped = rtf.replace("\\{", "").replace("\\}", "")

        assert unescaped.count("{") == unescaped.count("}")


class TestOfferingTheMarks:
    """
    The export dialog offers a kind of mark only when there is one to carry,
    and only from a transcription, for now.
    """

    def test_nothing_marked_offers_nothing(self, editor):
        assert editor.rtf_marks_available() == (False, False)

    def test_each_kind_is_offered_on_its_own(self, editor):
        editor.captions[1].highlighted_words = {0}
        assert editor.rtf_marks_available() == (True, False)

        editor.captions[1].highlighted_words = set()
        editor.captions[0].edited_words = {2}
        assert editor.rtf_marks_available() == (False, True)

    def test_both(self, editor):
        editor.captions[0].highlighted_words = {0}
        editor.captions[1].edited_words = {0}

        assert editor.rtf_marks_available() == (True, True)

    def test_a_bulk_export_offers_a_kind_if_any_file_has_it(self, editor):
        other = make_editor()
        other.captions[0].highlighted_words = {1}

        assert editor.rtf_marks_available([other]) == (True, False)

    def test_subtitles_offer_nothing_for_now(self):
        subtitles = make_editor("srt")
        subtitles.captions[0].edited_words = {0}

        assert subtitles.rtf_marks_available() == (False, False)

    def test_subtitles_in_a_bulk_export_are_not_counted(self, editor):
        subtitles = make_editor("srt")
        subtitles.captions[0].edited_words = {0}

        assert editor.rtf_marks_available([subtitles]) == (False, False)

    def test_the_checkboxes_follow_it_and_start_unchecked(self):
        source = pathlib.Path("utils/srt_export.py").read_text()

        assert "rtf_hl_incl.set_visibility(has_highlights)" in source
        assert "rtf_edits_incl.set_visibility(has_edits)" in source
        assert '"Include highlights", value=False' in source
        assert '"Include my edits (underlined)", value=False' in source


class TestMarkedSpans:
    def test_the_pieces_are_the_text_again(self, editor):
        caption = editor.captions[0]
        caption.text = "ett  två\ntre"
        caption.highlighted_words = {0, 2}
        caption.edited_words = {1}

        spans = editor.marked_spans(caption, True, True)

        assert "".join(text for text, _, _ in spans) == "ett  två\ntre"

    def test_neighbouring_words_with_the_same_marks_are_one_piece(self, editor):
        caption = editor.captions[0]
        caption.highlighted_words = {0, 1}

        assert editor.marked_spans(caption, True, False) == [
            ("ett två", True, False),
            (" tre", False, False),
        ]

    def test_with_both_off_it_is_one_unmarked_piece(self, editor):
        caption = editor.captions[0]
        caption.highlighted_words = {0, 1}
        caption.edited_words = {2}

        assert editor.marked_spans(caption, False, False) == [
            ("ett två tre", False, False)
        ]

    def test_no_text_no_pieces(self, editor):
        caption = editor.captions[0]
        caption.text = ""

        assert editor.marked_spans(caption, True, True) == []


class FakeBody:
    def __init__(self):
        self.selected = []
        self.asked = 0

    def highlight_selection(self):
        self.asked += 1

    def select_range(self, *args):
        self.selected.append(args)


@pytest.fixture
def view(editor, monkeypatch):
    view = TranscriptEditor(editor)
    view.body = FakeBody()
    view.refreshed = 0
    view.refresh = lambda *a, **k: setattr(view, "refreshed", view.refreshed + 1)
    view.changed = lambda *a, **k: None

    return view


class TestTheShortcutsDialog:
    def groups(self, data_format):
        return dict(make_editor(data_format).keyboard_shortcut_groups())

    def test_a_transcription_lists_it(self):
        assert self.groups("txt")["Highlighting"] == [
            ("Highlight selection, or remove the highlight", "Ctrl + Shift + H")
        ]

    def test_subtitles_do_not_for_now(self):
        assert "Highlighting" not in self.groups("srt")


class TestTheHandler:
    def test_the_event_reaches_the_view(self):
        source = pathlib.Path("utils/transcript_editor.py").read_text()

        assert (
            'self.body.on(\n            "togglehighlight", '
            "lambda event: self.toggle_highlight(event.args)\n        )"
        ) in source

    def test_it_highlights_what_the_component_measured(self, view, editor):
        view.toggle_highlight({"spans": [{"id": 1, "start": 4, "end": 7}]})

        assert editor.captions[0].highlighted_words == {1}
        assert view.refreshed == 1

    def test_the_selection_is_put_back_after_the_redraw(self, view, editor):
        view.toggle_highlight(
            {
                "spans": [
                    {"id": 1, "start": 4, "end": 11},
                    {"id": 2, "start": 0, "end": 4},
                ]
            }
        )

        assert view.body.selected == [(1, 4, 2, 4)]

    def test_nothing_selected_changes_nothing_and_redraws_nothing(self, view, editor):
        view.toggle_highlight({"spans": [{"id": 1, "start": 3, "end": 4}]})

        assert view.refreshed == 0
        assert view.body.selected == []

    @pytest.mark.parametrize(
        "args",
        [
            None,
            "x",
            {},
            {"spans": None},
            {"spans": "all"},
            {"spans": []},
            {"spans": [None, 3, "x"]},
            {"spans": [{"id": 99, "start": 0, "end": 3}]},
            {"spans": [{"id": 1, "start": "0", "end": 3}]},
            {"spans": [{"id": 1, "start": True, "end": 3}]},
            {"spans": [{"id": 1, "start": 0}]},
        ],
    )
    def test_bad_input_is_harmless(self, view, editor, args):
        view.toggle_highlight(args)

        assert all(not caption.highlighted_words for caption in editor.captions)
        assert view.refreshed == 0

    def test_a_bad_span_does_not_stop_the_good_ones(self, view, editor):
        view.toggle_highlight(
            {
                "spans": [
                    {"id": 99, "start": 0, "end": 3},
                    {"id": 2, "start": 0, "end": 4},
                ]
            }
        )

        assert editor.captions[1].highlighted_words == {0}


class TestTheButton:
    """
    The toolbar's Highlight button, where Validate is in the subtitle editor:
    the same as the key, for whoever does not know the key.
    """

    def page(self):
        return pathlib.Path("pages/srt.py").read_text()

    def test_it_asks_the_component_for_the_selection(self, view):
        view.highlight_selection()

        assert view.body.asked == 1

    def test_it_is_harmless_before_the_editor_is_built(self, editor):
        TranscriptEditor(editor).highlight_selection()

    def test_nothing_selected_says_so_and_changes_nothing(self, view, editor):
        view.toggle_highlight({"spans": []})

        assert editor.messages == ["Select the words to highlight first"]
        assert view.refreshed == 0
        assert all(not caption.highlighted_words for caption in editor.captions)

    def test_the_component_reports_the_selection_as_the_key_does(self):
        source = pathlib.Path("utils/transcript_editor.js").read_text()
        body = source[source.index("highlightSelection() {") :]
        body = body[: body.index("\n    },")]

        assert "this.flush();" in body
        assert 'this.$emit("togglehighlight", { spans: this.highlightSpans() });' in body

    def test_it_is_in_the_toolbar_for_transcriptions_only(self):
        page = self.page()
        validate = page.index('with ui.button("Validate", icon="check")')
        highlight = page.index('with ui.button("Highlight", icon="sym_o_format_ink_highlighter")')

        # After Validate's own branch, in the else of the same test.
        between = page[validate:highlight]

        assert between.count("\n                else:\n") == 1

    def test_it_has_a_marker_pen_and_not_the_torch(self):
        """
        The plain Material Icons "highlight" is a torch. The marker pen is in
        Material Symbols Outlined, which ships with NiceGUI.
        """

        page = self.page()

        assert 'icon="sym_o_format_ink_highlighter"' in page
        assert 'icon="highlight"' not in page

    def test_it_is_a_labelled_quiet_toolbar_button_naming_its_key(self):
        page = self.page()
        start = page.index('with ui.button("Highlight", icon="sym_o_format_ink_highlighter")')
        button = page[start : start + 1400]

        assert "aria-keyshortcuts=Control+Shift+H" in button
        assert "editor-btn editor-toolbar-btn editor-quiet" in button
        assert "(Ctrl + Shift + H)" in button

    def test_a_mouse_press_does_not_take_the_selection_with_it(self):
        page = self.page()
        start = page.index('with ui.button("Highlight", icon="sym_o_format_ink_highlighter")')
        button = page[start : start + 1400]

        assert '"mousedown", js_handler="(event) => event.preventDefault()"' in button

    def test_a_click_is_the_same_as_the_key(self):
        page = self.page()
        start = page.index('with ui.button("Highlight", icon="sym_o_format_ink_highlighter")')
        button = page[start : start + 1400]

        assert '"click", lambda: transcript.highlight_selection()' in button


class TestTheComponent:
    def source(self):
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_the_key_is_ctrl_shift_h_by_physical_key(self):
        source = self.source()
        start = source.index("event.ctrlKey &&\n        event.shiftKey")
        block = source[start : start + 260]

        assert "!event.altKey" in block
        assert "!event.metaKey" in block
        assert 'event.code === "KeyH"' in block

        assert '"togglehighlight"' in source

    def test_it_is_for_transcriptions_only_for_now(self):
        source = self.source()
        start = source.index("!this.subtitleMode &&\n        event.ctrlKey &&")

        assert 'event.code === "KeyH"' in source[start : start + 260]

    def test_it_is_ahead_of_the_block_scoped_lists(self):
        """
        A selection can reach across blocks, which the lists -- working from
        the caret's own block -- cannot see.
        """

        source = self.source()

        assert source.index('"togglehighlight"') < source.index(
            "this.subtitleShortcut(event, at)"
        )

    def test_both_marking_classes_come_from_one_function(self):
        source = self.source()

        assert source.count(':class="runClass(run)"') == 2
        assert 'run.hl ? "highlight-word" : null' in source

    def test_a_highlight_is_exposed_as_marked_text(self):
        assert self.source().count(""":role="run.hl ? 'mark' : null\"""") == 2

    def test_the_selection_is_sent_one_range_per_block(self):
        source = self.source()
        body = source[source.index("highlightSpans() {") :]
        body = body[: body.index("\n    },")]

        assert "first === last" in body
        assert "this.plainText(block.textContent).length" in body

    def test_the_selection_can_be_put_back(self):
        source = self.source()

        assert "selectRange(startId, startOffset, endId, endOffset) {" in source
        assert "pointAt(block, offset) {" in source


class TestTheStyles:
    def css(self):
        return pathlib.Path("utils/styles.py").read_text()

    def rule(self, selector):
        css = self.css()
        rule = css[css.index(selector) :]

        return rule[: rule.index("}")]

    def test_it_has_its_own_colours_in_both_themes(self):
        css = self.css()

        assert css.count("--color-highlight-bg:") == 2
        assert css.count("--color-highlight-frame:") == 2
        assert css.count("--color-highlight-text:") == 2

    def test_it_does_not_pad_the_text_sideways(self):
        assert "padding: 1px 0;" in self.rule("    .highlight-word {")

    def test_it_has_a_line_above_and_below_that_does_not_depend_on_colour(self):
        rule = self.rule("    .highlight-word {")

        assert "inset 0 2px 0 var(--color-highlight-frame)" in rule
        assert "inset 0 -2px 0 var(--color-highlight-frame)" in rule

    @pytest.mark.parametrize(
        "selector, accent",
        [
            ("    .highlight-word.review-word {", "review"),
            ("    .highlight-word.edit-word {", "edit"),
            ("    .transcript-text .highlight-word.review-word[data-current] {", "review"),
            ("    .transcript-text .highlight-word.edit-word[data-current] {", "edit"),
        ],
    )
    def test_a_flagged_or_changed_word_keeps_the_frame_and_its_own_bar_outside_it(
        self, selector, accent
    ):
        rule = self.rule(selector)

        # The frame is the same line above and below as on any highlighted
        # word, so a highlight always looks like a highlight ...
        assert "inset 0 2px 0 var(--color-highlight-frame)" in rule
        assert "inset 0 -2px 0 var(--color-highlight-frame)" in rule
        # ... and the word's own bar sits outside it, where it is not taken
        # for the frame's lower line.
        assert f"0 3px 0 var(--color-{accent}-accent)" in rule
        assert f"inset 0 -2px 0 var(--color-{accent}-accent)" not in rule

    def test_the_word_being_played_keeps_the_lines(self):
        rule = self.rule("    .transcript-text .highlight-word[data-current] {")

        assert "background-color: var(--color-playing-bg);" in rule
        assert "inset 0 2px 0 var(--color-highlight-frame)" in rule

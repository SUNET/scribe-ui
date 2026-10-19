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
The reader's comments: notes on a stretch of words, kept with their own text,
carried through every edit that moves words, saved with a transcription,
drawn, opened in a box, and optionally exported as Word comments.
"""

import json
import pathlib
import re
from datetime import datetime

import pytest

from tests.test_highlights import make_editor
from utils.caption import SRTCaption, WordComment
from utils.srt_comments import COMMENT_MAX_LENGTH
from utils.transcript_editor import TranscriptEditor


def comment(words, text="note"):
    return WordComment(words, text)


def shape(caption):
    """
    A caption's comments as plain data, to compare.
    """

    return [(sorted(c.words), c.text) for c in caption.comments]


@pytest.fixture
def editor(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "utils.srt.ui.notify", lambda message, **k: messages.append(message)
    )
    built = make_editor()
    built.messages = messages

    return built


class TestTheModel:
    def test_a_copy_does_not_share_the_comments(self):
        caption = SRTCaption(1, "00:00:00,000", "00:00:01,000", "a b")
        caption.comments = [comment({0}, "one")]

        copy = caption.copy()
        copy.comments[0].words.add(1)
        copy.comments[0].text = "changed"
        copy.comments.append(comment({1}))

        assert shape(caption) == [([0], "one")]

    def test_they_are_in_the_saved_data_only_when_there_are_any(self):
        caption = SRTCaption(1, "00:00:00,000", "00:00:01,000", "a b")

        assert "comments" not in caption.to_dict()

        caption.comments = [comment({1, 0}, "why")]

        assert caption.to_dict()["comments"] == [{"words": [0, 1], "text": "why"}]


class TestSavedWithTheTranscription:
    def reopen(self, editor, mutate=None):
        data = editor.export_json()

        if mutate:
            mutate(data)

        reopened = make_editor()
        reopened.captions = []
        reopened.speakers = set()
        reopened.parse_txt(json.dumps(data))

        return reopened

    def test_they_come_back_when_the_file_is_opened_again(self, editor):
        editor.captions[0].comments = [comment({0, 1}, "first"), comment({2}, "last")]
        editor.captions[1].comments = [comment({1}, "båda åäö")]

        reopened = self.reopen(editor)

        assert [shape(c) for c in reopened.captions] == [
            [([0, 1], "first"), ([2], "last")],
            [([1], "båda åäö")],
        ]

    def test_a_file_saved_before_this_existed_opens_without_any(self, editor):
        reopened = self.reopen(editor)

        assert all(not caption.comments for caption in reopened.captions)

    def test_all_the_kinds_of_mark_are_kept_apart(self, editor):
        first = editor.captions[0]
        first.edited_words = {0}
        first.highlighted_words = {1}
        first.comments = [comment({2}, "c")]

        reopened = self.reopen(editor)

        assert reopened.captions[0].edited_words == {0}
        assert reopened.captions[0].highlighted_words == {1}
        assert shape(reopened.captions[0]) == [([2], "c")]

    @pytest.mark.parametrize(
        "saved",
        [
            "all of it",
            None,
            5,
            {},
            [None, 3, "x", []],
            [{"words": [0]}],
            [{"text": "no words"}],
            [{"words": [0], "text": ""}],
            [{"words": [0], "text": "   "}],
            [{"words": [0], "text": 5}],
            [{"words": "0", "text": "x"}],
            [{"words": [], "text": "x"}],
            [{"words": ["a", None, True, -1, 2.5, 99], "text": "x"}],
        ],
    )
    def test_junk_in_the_file_is_ignored(self, editor, saved):
        def mutate(data):
            data["segments"][0]["comments"] = saved

        reopened = self.reopen(editor, mutate)

        assert reopened.captions[0].comments == []
        assert [c.text for c in reopened.captions] == ["ett två tre", "fyra fem sex"]

    def test_a_good_comment_survives_bad_company(self, editor):
        def mutate(data):
            data["segments"][0]["comments"] = [
                "junk",
                {"words": [True, 1, "x"], "text": " kept "},
            ]

        reopened = self.reopen(editor, mutate)

        assert shape(reopened.captions[0]) == [([1], "kept")]

    def test_a_word_has_only_one_comment_whatever_the_file_says(self, editor):
        def mutate(data):
            data["segments"][0]["comments"] = [
                {"words": [0, 1], "text": "first"},
                {"words": [1, 2], "text": "second"},
            ]

        reopened = self.reopen(editor, mutate)

        assert shape(reopened.captions[0]) == [([0, 1], "first"), ([2], "second")]

    def test_a_comment_on_words_that_are_not_there_is_dropped(self, editor):
        def mutate(data):
            data["segments"][0]["comments"] = [{"words": [7, 8], "text": "stale"}]

        assert self.reopen(editor, mutate).captions[0].comments == []

    def test_an_over_long_text_is_cut_to_the_limit(self, editor):
        def mutate(data):
            data["segments"][0]["comments"] = [
                {"words": [0], "text": "x" * (COMMENT_MAX_LENGTH + 50)}
            ]

        reopened = self.reopen(editor, mutate)

        assert len(reopened.captions[0].comments[0].text) == COMMENT_MAX_LENGTH


class TestTargeting:
    def test_a_selection_takes_whole_words(self, editor):
        target = editor.comment_target(editor.captions[0], 5, 9)

        assert target == {"index": None, "text": "", "start": 4, "end": 11}

    def test_a_caret_takes_the_word_it_is_in(self, editor):
        target = editor.comment_target(editor.captions[0], 5, 5)

        assert (target["start"], target["end"]) == (4, 7)

    def test_no_word_means_no_target(self, editor):
        editor.captions[0].text = "ett  tre"

        assert editor.comment_target(editor.captions[0], 4, 4) is None

    def test_words_that_have_a_comment_open_that_comment(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "there")]

        target = editor.comment_target(first, 0, 5)

        assert target == {"index": 0, "text": "there", "start": 4, "end": 11}

    def test_a_selection_over_two_comments_opens_the_first(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0}, "one"), comment({2}, "two")]

        target = editor.comment_target(first, 0, 11)

        assert target["text"] == "one"


class TestAddingChangingRemoving:
    def test_a_comment_is_put_on_the_selected_words(self, editor):
        first = editor.captions[0]

        assert editor.set_comment(first, 0, 7, "check") == "added"

        assert shape(first) == [([0, 1], "check")]
        assert editor.snapshots == 1
        assert editor.changed == 1

    def test_the_text_of_the_caption_is_never_touched(self, editor):
        editor.set_comment(editor.captions[0], 0, 7, "check")

        assert editor.captions[0].text == "ett två tre"

    def test_the_text_is_kept_without_blank_edges(self, editor):
        editor.set_comment(editor.captions[0], 0, 3, "  hej\n  du \n")

        assert editor.captions[0].comments[0].text == "hej\n  du"

    def test_commenting_on_commented_words_changes_that_comment(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0, 1}, "old")]

        assert editor.set_comment(first, 4, 7, "new") == "changed"

        assert shape(first) == [([0, 1], "new")]

    def test_the_same_text_is_no_change(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0}, "same")]

        assert editor.set_comment(first, 0, 3, " same ") == ""
        assert editor.snapshots == 0
        assert editor.changed == 0

    def test_no_comment_is_laid_over_another(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1}, "there")]

        editor.set_comment(first, 0, 11, "wider")

        assert shape(first) == [([1], "wider")]

    def test_comments_are_kept_in_the_order_of_the_text(self, editor):
        first = editor.captions[0]

        editor.set_comment(first, 8, 11, "later")
        editor.set_comment(first, 0, 3, "earlier")

        assert [c.text for c in first.comments] == ["earlier", "later"]

    def test_an_empty_text_is_not_a_comment(self, editor):
        first = editor.captions[0]

        assert editor.set_comment(first, 0, 3, "   ") == ""
        assert editor.set_comment(first, 0, 3, None) == ""
        assert first.comments == []
        assert editor.snapshots == 0

    def test_a_text_over_the_limit_is_refused_and_says_so(self, editor):
        first = editor.captions[0]

        assert editor.set_comment(first, 0, 3, "x" * (COMMENT_MAX_LENGTH + 1)) == ""

        assert first.comments == []
        assert editor.messages == [
            f"A comment can be at most {COMMENT_MAX_LENGTH} characters"
        ]

    def test_a_text_at_the_limit_is_kept(self, editor):
        editor.set_comment(editor.captions[0], 0, 3, "x" * COMMENT_MAX_LENGTH)

        assert len(editor.captions[0].comments[0].text) == COMMENT_MAX_LENGTH

    def test_no_words_selected_says_so(self, editor):
        first = editor.captions[0]
        first.text = "ett  tre"

        assert editor.set_comment(first, 4, 4, "x") == ""

        assert editor.messages == ["Select the words to comment on first"]
        assert first.comments == []

    def test_a_comment_is_removed_with_the_words_it_is_on(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1}, "a"), comment({2}, "b")]

        assert editor.remove_comment(first, 4, 7) is True

        assert shape(first) == [([2], "b")]
        assert editor.snapshots == 1

    def test_removing_where_there_is_none_does_nothing(self, editor):
        first = editor.captions[0]
        first.comments = [comment({2}, "b")]

        assert editor.remove_comment(first, 0, 3) is False

        assert shape(first) == [([2], "b")]
        assert editor.snapshots == 0

    def test_subtitles_have_nowhere_to_keep_one(self):
        subtitles = make_editor("srt")

        assert subtitles.set_comment(subtitles.captions[0], 0, 3, "x") == ""
        assert subtitles.captions[0].comments == []
        assert subtitles.remove_comment(subtitles.captions[0], 0, 3) is False


class TestFollowingTheText:
    """
    A comment is on words, so it has to stay on them whatever the reader does
    to the text around them.
    """

    def test_typing_before_it_moves_it_along(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1}, "c")]

        editor.update_caption_text(first, "nytt ett två tre")

        assert shape(first) == [([2], "c")]

    def test_correcting_a_word_inside_it_keeps_it(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0, 1, 2}, "c")]

        editor.update_caption_text(first, "ett tvo tre")

        assert shape(first) == [([0, 1, 2], "c")]

    def test_a_word_added_inside_it_is_in_it(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0, 1}, "c")]

        editor.update_caption_text(first, "ett nytt två tre")

        assert shape(first) == [([0, 1, 2], "c")]

    def test_a_word_typed_at_its_edge_is_not_in_it(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0, 1}, "c")]

        editor.update_caption_text(first, "ett två nytt tre")

        assert shape(first) == [([0, 1], "c")]

    def test_it_goes_with_its_words_when_they_are_all_deleted(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1}, "c"), comment({2}, "d")]

        editor.update_caption_text(first, "ett tre")

        assert shape(first) == [([1], "d")]

    def test_it_is_gone_when_the_text_is_replaced_by_something_else_entirely(
        self, editor
    ):
        first = editor.captions[0]
        first.comments = [comment({0, 1, 2}, "c")]

        editor.update_caption_text(first, "")

        assert first.comments == []

    def test_splitting_divides_them_between_the_halves(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0}, "a"), comment({2}, "b")]

        editor.split_caption(first, cursor_position=7)

        assert editor.captions[0].text == "ett två"
        assert shape(editor.captions[0]) == [([0], "a")]
        assert editor.captions[1].text == "tre"
        assert shape(editor.captions[1]) == [([0], "b")]

    def test_a_comment_across_the_split_is_on_both_halves(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "both")]

        editor.split_caption(first, cursor_position=7)

        assert shape(editor.captions[0]) == [([1], "both")]
        assert shape(editor.captions[1]) == [([0], "both")]

    def test_the_two_halves_do_not_share_one_comment(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "both")]

        editor.split_caption(first, cursor_position=7)
        editor.captions[0].comments[0].text = "changed"

        assert editor.captions[1].comments[0].text == "both"

    def test_splitting_with_unsent_text_keeps_them(self, editor):
        first = editor.captions[0]
        first.comments = [comment({2}, "c")]

        editor.split_caption(first, cursor_position=8, text="nytt ett två tre")

        assert editor.captions[0].comments == []
        assert shape(editor.captions[1]) == [([1], "c")]

    def test_merging_with_the_next_joins_them_as_separate_notes(self, editor):
        first, second = editor.captions
        first.comments = [comment({2}, "a")]
        second.comments = [comment({0}, "b")]

        editor.merge_with_next(first)

        assert shape(editor.captions[0]) == [([2], "a"), ([3], "b")]

    def test_merging_with_the_previous_joins_them(self, editor):
        first, second = editor.captions
        first.comments = [comment({2}, "a")]
        second.comments = [comment({0, 1}, "b")]

        editor.merge_with_previous(second)

        assert shape(editor.captions[0]) == [([2], "a"), ([3, 4], "b")]

    def test_a_word_moved_to_the_previous_caption_leaves_the_comment(self, editor):
        first, second = editor.captions
        second.comments = [comment({0, 1}, "c")]

        editor.move_first_word_to_previous(second)

        assert first.comments == []
        assert shape(second) == [([0], "c")]

    def test_a_comment_on_only_that_word_goes_with_it(self, editor):
        first, second = editor.captions
        second.comments = [comment({0}, "c"), comment({2}, "d")]

        editor.move_first_word_to_previous(second)

        assert shape(second) == [([1], "d")]

    def test_a_word_moved_to_the_next_caption_leaves_the_comment(self, editor):
        first, second = editor.captions
        first.comments = [comment({1, 2}, "c")]
        second.comments = [comment({1}, "d")]

        editor.move_last_word_to_next(first)

        assert shape(first) == [([1], "c")]
        assert shape(second) == [([2], "d")]

    def test_deleting_across_captions_keeps_what_is_left(self, editor):
        first, second = editor.captions
        first.comments = [comment({0}, "a"), comment({1}, "b")]
        second.comments = [comment({0}, "c"), comment({2}, "d")]

        # "ett" and " fem sex" are what is left: "två" and "fyra" are gone.
        editor.delete_range(first, second, 3, 4, "")

        assert editor.captions[0].text == "ett fem sex"
        assert shape(editor.captions[0]) == [([0], "a"), ([2], "d")]

    def test_replacing_text_keeps_them_following_the_words(self, editor):
        first = editor.captions[0]
        first.comments = [comment({2}, "c")]
        editor.search_term = "ett"
        editor.selected_caption = first
        editor.case_sensitive = True

        editor.replace_in_current_caption("ett nytt")

        assert first.text == "ett nytt två tre"
        assert shape(first) == [([3], "c")]

    def test_the_marks_do_not_get_mixed_up(self, editor):
        first = editor.captions[0]
        first.edited_words = {0}
        first.highlighted_words = {1}
        first.comments = [comment({2}, "c")]

        editor.update_caption_text(first, "nytt ett två tre")

        assert first.highlighted_words == {2}
        assert shape(first) == [([3], "c")]


class TestUndo:
    """
    With the real history, not the stand-in the other tests use: a comment
    has to travel with the snapshots.
    """

    @pytest.fixture
    def real(self, editor):
        del editor.save_state_for_undo
        editor._update_undo_redo_buttons = lambda: None
        editor.update_beforeunload_state = lambda: None

        return editor

    def state(self, editor):
        first = editor.captions[0]

        return first.text, shape(first)

    def test_adding_one_can_be_undone_and_redone(self, real):
        real.set_comment(real.captions[0], 0, 7, "note")

        real.undo()
        assert self.state(real) == ("ett två tre", [])

        real.redo()
        assert self.state(real) == ("ett två tre", [([0, 1], "note")])

    def test_deleting_the_words_and_undoing_brings_both_back(self, real):
        real.set_comment(real.captions[0], 0, 7, "note")
        real.update_caption_text(real.captions[0], "tre")
        assert self.state(real) == ("tre", [])

        real.undo()

        assert self.state(real) == ("ett två tre", [([0, 1], "note")])

    def test_changing_the_text_and_removing_can_be_undone(self, real):
        first = real.captions[0]
        real.set_comment(first, 0, 3, "one")
        real.set_comment(first, 0, 3, "two")
        real.remove_comment(first, 0, 3)

        real.undo()
        assert shape(real.captions[0]) == [([0], "two")]

        real.undo()
        assert shape(real.captions[0]) == [([0], "one")]


class TestDrawing:
    def runs(self, editor, caption):
        return editor.review_runs(caption)

    def test_nothing_is_drawn_when_there_is_no_comment(self, editor):
        assert self.runs(editor, editor.captions[0]) == [
            {"t": "ett två tre", "flag": False}
        ]

    def test_a_comment_is_drawn_without_any_switch_on(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1}, "c")]

        runs = self.runs(editor, first)

        assert [run["t"] for run in runs if "cm" in run] == ["två"]
        assert "".join(run["t"] for run in runs) == "ett två tre"

    def test_each_word_says_which_comment_it_is_in(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0}, "a"), comment({2}, "b")]

        runs = self.runs(editor, first)

        assert [(r["t"], r["cm"]) for r in runs if "cm" in r] == [("ett", 0), ("tre", 1)]

    def test_the_first_word_carries_the_text_and_the_last_marks_the_end(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0, 1, 2}, "hello")]

        runs = [r for r in self.runs(editor, first) if "cm" in r and r["t"].strip()]

        assert [r.get("cf") for r in runs] == [True, None, None]
        assert [r.get("ct") for r in runs] == ["hello", None, None]
        assert [r.get("cl") for r in runs] == [None, None, True]

    def test_a_one_word_comment_is_both_first_and_last(self, editor):
        first = editor.captions[0]
        first.comments = [comment({1}, "x")]

        run = next(r for r in self.runs(editor, first) if "cm" in r)

        assert run["cf"] is True and run["cl"] is True

    def test_the_space_inside_a_comment_is_in_it(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0, 1}, "c")]

        runs = self.runs(editor, first)

        assert [(r["t"], "cm" in r) for r in runs] == [
            ("ett", True),
            (" ", True),
            ("två", True),
            (" ", False),
            ("tre", False),
        ]

    def test_the_space_between_two_comments_is_in_neither(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0}, "a"), comment({1}, "b")]

        runs = self.runs(editor, first)

        assert [(r["t"], r.get("cm")) for r in runs][:3] == [
            ("ett", 0),
            (" ", None),
            ("två", 1),
        ]

    def test_a_line_break_is_left_out(self, editor):
        first = editor.captions[0]
        first.text = "ett\ntvå"
        first.comments = [comment({0, 1}, "c")]

        runs = self.runs(editor, first)

        assert [(r["t"], "cm" in r) for r in runs] == [
            ("ett", True),
            ("\n", False),
            ("två", True),
        ]

    def test_it_sits_alongside_a_highlight_on_the_same_word(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        first.comments = [comment({1}, "c")]

        run = next(r for r in self.runs(editor, first) if r["t"] == "två")

        assert run["hl"] is True
        assert run["cm"] == 0

    def test_the_text_is_always_what_the_caption_says(self, editor):
        first = editor.captions[0]
        first.comments = [comment({0, 2}, "c")]

        assert "".join(r["t"] for r in self.runs(editor, first)) == first.text


class TestRtfExport:
    def export(self, editor, **kwargs):
        return editor.export_rtf(False, False, False, **kwargs)

    def test_a_clean_export_has_no_comment_in_it(self, editor):
        editor.captions[0].comments = [comment({1}, "secret")]

        clean = self.export(editor)

        assert "secret" not in clean
        assert "annotation" not in clean
        assert "atrf" not in clean

    def test_a_clean_export_is_the_same_as_before_comments_existed(self, editor):
        before = self.export(editor)

        editor.captions[0].comments = [comment({0, 1}, "x")]
        editor.captions[1].comments = [comment({2}, "y")]

        assert self.export(editor) == before

    def test_a_comment_is_a_word_comment_on_its_words(self, editor):
        editor.captions[0].comments = [comment({1}, "check this")]

        rtf = self.export(editor, comments=True)

        assert r"ett {\*\atrfstart 0}tv\u229?{\*\atrfend 0}" in rtf
        assert r"{\*\atnauthor Scribe}\chatn{\*\annotation{\*\atnref 0}" in rtf
        assert r"\pard\plain\f0\fs20 check this}" in rtf

    def test_the_text_between_the_markers_is_the_words(self, editor):
        editor.captions[0].comments = [comment({1, 2}, "x")]

        rtf = self.export(editor, comments=True)
        between = re.search(r"\\atrfstart 0\}(.*?)\{\\\*\\atrfend 0\}", rtf).group(1)

        assert between == r"tv\u229? tre"

    def test_each_comment_gets_a_number_of_its_own(self, editor):
        editor.captions[0].comments = [comment({0}, "a"), comment({2}, "b")]
        editor.captions[1].comments = [comment({0}, "c")]

        rtf = self.export(editor, comments=True)

        assert re.findall(r"\\atrfstart (\d+)", rtf) == ["0", "1", "2"]
        assert re.findall(r"\\atrfend (\d+)", rtf) == ["0", "1", "2"]
        assert re.findall(r"\\atnref (\d+)", rtf) == ["0", "1", "2"]

    def test_the_texts_are_escaped_and_keep_their_line_breaks(self, editor):
        editor.captions[0].comments = [comment({0}, 'a {b} \\c\nåäö "q"')]

        rtf = self.export(editor, comments=True)

        assert r'a \{b\} \\c\line \u229?\u228?\u246? "q"}' in rtf

    def test_it_goes_inside_marked_words_without_breaking_them(self, editor):
        second = editor.captions[1]
        second.highlighted_words = {0, 1}
        second.edited_words = {1, 2}
        second.comments = [comment({0}, "c")]

        rtf = self.export(editor, comments=True, highlights=True, edits=True)

        assert (
            r"{\*\atrfstart 0}{\highlight1 fyra}{\*\atrfend 0}" in rtf
        )
        # The rest of the highlighted passage carries on after the comment.
        assert r"{\highlight1  }{\highlight1\cf2\ul fem}" in rtf

    def test_a_comment_in_the_middle_of_one_marked_stretch_cuts_it_in_two(self, editor):
        second = editor.captions[1]
        second.highlighted_words = {0, 1, 2}
        second.comments = [comment({1}, "c")]

        rtf = self.export(editor, comments=True, highlights=True)

        assert (
            r"{\highlight1 fyra }{\*\atrfstart 0}{\highlight1 fem}{\*\atrfend 0}" in rtf
        )
        assert r"{\highlight1  sex}" in rtf

    def test_the_rest_of_the_document_is_unchanged_by_the_comments(self, editor):
        editor.captions[0].comments = [comment({1}, "c")]

        with_comments = self.export(editor, comments=True)
        stripped = re.sub(r"\{\\\*\\atrfstart \d+\}", "", with_comments)
        stripped = re.sub(
            r"\{\\\*\\atrfend \d+\}\{\\\*\\atnid [^}]*\}"
            r"\{\\\*\\atnauthor [^}]*\}\\chatn"
            r"\{\\\*\\annotation\{\\\*\\atnref \d+\}"
            r"\{\\\*\\atndate \d+\}[^}]*\}",
            "",
            stripped,
        )

        assert stripped == self.export(editor)

    def test_the_date_is_the_one_rtf_keeps_dates_in(self):
        # Sunday 18 October 2026, 08:21.
        from utils.srt_export import ExportMixin

        value = ExportMixin.rtf_date(datetime(2026, 10, 18, 8, 21))

        assert value & 0x3F == 21
        assert (value >> 6) & 0x1F == 8
        assert (value >> 11) & 0x1F == 18
        assert (value >> 16) & 0xF == 10
        assert (value >> 20) & 0x1FF == 126
        assert (value >> 29) & 0x7 == 0

    def test_subtitles_never_carry_them(self):
        subtitles = make_editor("srt")
        subtitles.captions[0].comments = [comment({0}, "x")]

        rtf = subtitles.export_rtf(False, False, False, comments=True)

        assert "annotation" not in rtf

    def test_a_comment_on_no_words_is_not_written(self, editor):
        editor.captions[0].comments = [comment({9}, "stale")]

        assert "annotation" not in self.export(editor, comments=True)


class TestOfferingThem:
    def test_nothing_to_offer_without_a_comment(self, editor):
        assert editor.rtf_comments_available() is False

    def test_it_is_offered_when_a_caption_has_one(self, editor):
        editor.captions[1].comments = [comment({0})]

        assert editor.rtf_comments_available() is True

    def test_a_bulk_export_offers_it_if_any_file_has_one(self, editor):
        other = make_editor()
        other.captions[0].comments = [comment({0})]

        assert editor.rtf_comments_available([other]) is True

    def test_subtitles_do_not_count(self, editor):
        subtitles = make_editor("srt")
        subtitles.captions[0].comments = [comment({0})]

        assert editor.rtf_comments_available([subtitles]) is False
        assert subtitles.rtf_comments_available() is False

    def test_the_checkbox_is_off_and_only_visible_when_offered(self):
        source = pathlib.Path("utils/srt_export.py").read_text()
        start = source.index('"Include comments"')
        block = source[start - 80 : start + 400]

        assert "value=False" in block
        assert "set_visibility(" in block
        assert "rtf_comments_available(" in block

    def test_the_export_asks_for_comments_only_when_the_box_is_shown_and_ticked(self):
        source = pathlib.Path("utils/srt_export.py").read_text()

        assert "rtf_comments_incl.visible\n" in source
        assert "and rtf_comments_incl.value" in source


class FakeBody:
    def __init__(self):
        self.selected = []
        self.scrolled = []
        self.asked = 0
        self.caret_asked = 0
        self.comment_mark = (-1, -1)

    def set_comment_mark(self, block_id, comment_index=-1):
        self.comment_mark = (block_id, comment_index)

    def comment_selection(self):
        self.asked += 1

    def select_range(self, *args):
        self.selected.append(args)

    def scroll_to_block(self, block_id):
        self.scrolled.append(block_id)

    def focus_caret(self):
        self.caret_asked += 1


class Element:
    """
    Just enough of a NiceGUI element to see what the panel did to it.
    """

    def __init__(self, value=""):
        self.value = value
        self.text = ""
        self.enabled = True
        self.visible = True
        self.properties = []

    def set_value(self, value):
        self.value = value

    def set_text(self, text):
        self.text = text

    def set_enabled(self, enabled):
        self.enabled = enabled

    def set_visibility(self, visible):
        self.visible = visible

    def props(self, props):
        self.properties.append(props)


class FakePanel:
    pass


@pytest.fixture
def view(editor, monkeypatch):
    view = TranscriptEditor(editor)
    view.body = FakeBody()
    view.refreshed = 0
    view.refresh = lambda *a, **k: setattr(view, "refreshed", view.refreshed + 1)
    view.changed = lambda *a, **k: None

    return view


@pytest.fixture
def panel(view, editor, monkeypatch):
    from utils.comments_panel import CommentsPanel

    built = CommentsPanel.__new__(CommentsPanel)
    built.transcript = view
    built.current = None
    built.pending = None

    for name in (
        "container",
        "heading",
        "position_label",
        "spoken",
        "previous",
        "next",
        "words_button",
        "detail",
        "remove_button",
        "cancel_button",
        "save_button",
    ):
        setattr(built, name, Element())

    built.container.visible = False
    built.text = Element("")
    built.focused = 0
    built.focus_text = lambda: setattr(built, "focused", built.focused + 1)
    monkeypatch.setattr(
        CommentsPanel, "focus", staticmethod(lambda element: None)
    )
    view.comments_panel = built

    return built


class TestThePanel:
    """
    The card under the video where a comment is written, read and changed.
    """

    def type(self, panel, text):
        panel.text.value = text

    def test_a_new_comment_opens_empty_on_the_words_with_focus(self, panel, editor):
        assert panel.open_for(editor.captions[0], 5, 9) is True

        assert panel.container.visible is True
        assert panel.pending == (editor.captions[0], 4, 11)
        assert panel.text.value == ""
        assert panel.heading.text == "New comment"
        assert panel.words_button.text == "\u201ctv\u00e5 tre\u201d"
        assert panel.detail.text == "A \u00b7 00:00:00.000"
        assert panel.focused == 1

    def test_opening_changes_nothing_by_itself(self, panel, editor):
        panel.open_for(editor.captions[0], 5, 9)

        assert editor.captions[0].comments == []
        assert editor.snapshots == 0
        assert panel.transcript.refreshed == 0

    def test_the_words_of_an_existing_comment_open_it_with_its_text(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({1, 2}, "there")]

        panel.open_for(editor.captions[0], 5, 5)

        assert panel.pending is None
        assert panel.current[1] is editor.captions[0].comments[0]
        assert panel.text.value == "there"
        assert panel.heading.text == "Comment 1 of 1"
        assert panel.focused == 1

    def test_no_word_means_nothing_opens(self, panel, editor):
        editor.captions[0].text = "ett  tre"

        assert panel.open_for(editor.captions[0], 4, 4) is False
        assert panel.container.visible is False

    def test_the_heading_says_where_it_is_among_all_the_comments(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "a"), comment({2}, "b")]
        editor.captions[1].comments = [comment({1}, "c")]

        panel.show(editor.captions[1], editor.captions[1].comments[0])

        assert panel.heading.text == "Comment 3 of 3"
        assert panel.position_label.text == "3 of 3"
        assert panel.spoken.text == "Comment 3 of 3."
        assert panel.previous.enabled is True
        assert panel.next.enabled is False

    def test_drawing_it_scrolls_the_text_to_the_words_unless_told_not_to(
        self, panel, editor
    ):
        editor.captions[1].comments = [comment({1}, "c")]

        panel.show(editor.captions[1], editor.captions[1].comments[0])
        panel.show(editor.captions[1], editor.captions[1].comments[0], scroll=False)

        assert panel.transcript.body.scrolled == [2]

    def test_saving_a_new_comment_puts_it_on_the_words_and_goes_back_to_them(
        self, panel, editor
    ):
        panel.open_for(editor.captions[0], 5, 9)
        self.type(panel, "  check this  ")

        panel.save()

        assert shape(editor.captions[0]) == [([1, 2], "check this")]
        assert panel.pending is None
        assert panel.current[1] is editor.captions[0].comments[0]
        assert panel.transcript.refreshed == 1
        assert panel.transcript.body.selected == [(1, 4, 1, 11)]
        assert panel.heading.text == "Comment 1 of 1"

    def test_saving_nothing_does_nothing(self, panel, editor):
        panel.open_for(editor.captions[0], 5, 9)
        self.type(panel, "   ")

        panel.save()

        assert editor.captions[0].comments == []
        assert panel.pending is not None
        assert panel.transcript.refreshed == 0

    def test_save_cannot_be_pressed_with_nothing_typed(self, panel, editor):
        panel.open_for(editor.captions[0], 5, 9)

        assert panel.save_button.enabled is False

        self.type(panel, "x")
        panel.value_changed()

        assert panel.save_button.enabled is True

    def test_saving_a_changed_text_changes_that_comment(self, panel, editor):
        editor.captions[0].comments = [comment({1}, "old")]
        panel.open_for(editor.captions[0], 5, 5)
        self.type(panel, "new")

        panel.save()

        assert shape(editor.captions[0]) == [([1], "new")]
        assert panel.transcript.body.selected == [(1, 4, 1, 7)]

    def test_cancelling_a_new_comment_makes_none_and_goes_back_to_the_words(
        self, panel, editor
    ):
        panel.open_for(editor.captions[0], 5, 9)
        self.type(panel, "abandoned")

        panel.cancel()

        assert editor.captions[0].comments == []
        assert panel.pending is None
        assert panel.container.visible is False
        assert panel.transcript.body.selected == [(1, 4, 1, 11)]

    def test_cancelling_a_new_comment_goes_back_to_the_one_that_was_on_show(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0}, "there")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        panel.open_for(editor.captions[1], 0, 4)

        panel.cancel()

        assert panel.container.visible is True
        assert panel.text.value == "there"
        assert panel.heading.text == "Comment 1 of 1"

    def test_cancelling_a_change_puts_the_old_text_back(self, panel, editor):
        editor.captions[0].comments = [comment({1}, "old")]
        panel.open_for(editor.captions[0], 5, 5)
        self.type(panel, "typed over")

        panel.cancel()

        assert panel.text.value == "old"
        assert shape(editor.captions[0]) == [([1], "old")]
        assert panel.transcript.body.selected == [(1, 4, 1, 7)]

    def test_removing_takes_the_comment_off_and_shows_the_next(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "a"), comment({2}, "b")]
        panel.open_for(editor.captions[0], 0, 3)

        panel.remove()

        assert shape(editor.captions[0]) == [([2], "b")]
        assert panel.current[1].text == "b"
        assert panel.heading.text == "Comment 1 of 1"
        assert panel.transcript.body.selected == [(1, 0, 1, 3)]

    def test_removing_the_last_one_puts_the_panel_away(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "a")]
        panel.open_for(editor.captions[0], 0, 3)

        panel.remove()

        assert editor.captions[0].comments == []
        assert panel.container.visible is False
        assert panel.current is None

    def test_a_comment_not_yet_made_cannot_be_removed(self, panel, editor):
        panel.open_for(editor.captions[0], 5, 9)

        panel.remove()

        assert editor.snapshots == 0
        assert panel.pending is not None

    def test_closing_keeps_what_was_typed_and_goes_back_to_the_words(
        self, panel, editor
    ):
        panel.open_for(editor.captions[0], 5, 9)
        self.type(panel, "kept")

        panel.close()

        assert shape(editor.captions[0]) == [([1, 2], "kept")]
        assert panel.container.visible is False
        assert panel.transcript.body.selected[-1] == (1, 4, 1, 11)

    def test_closing_with_nothing_typed_makes_nothing(self, panel, editor):
        panel.open_for(editor.captions[0], 5, 9)

        panel.close()

        assert editor.captions[0].comments == []
        assert panel.container.visible is False

    def test_the_arrows_step_through_every_comment_in_the_order_of_the_text(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0}, "a"), comment({2}, "b")]
        editor.captions[1].comments = [comment({1}, "c")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        panel.go_next()
        assert panel.text.value == "b"
        panel.go_next()
        assert panel.text.value == "c"
        assert panel.heading.text == "Comment 3 of 3"
        panel.go_next()
        assert panel.text.value == "c"
        panel.go_previous()
        assert panel.text.value == "b"

    def test_stepping_keeps_what_was_typed(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "a"), comment({2}, "b")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        self.type(panel, "a, rewritten")

        panel.go_next()

        assert shape(editor.captions[0]) == [([0], "a, rewritten"), ([2], "b")]

    def test_a_comment_being_written_cannot_be_stepped_away_from(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "a")]
        panel.open_for(editor.captions[1], 0, 4)
        self.type(panel, "half written")

        panel.go_next()
        panel.go_previous()

        assert panel.pending is not None
        assert panel.text.value == "half written"
        assert panel.previous.enabled is False and panel.next.enabled is False

    def test_the_words_button_selects_them_and_scrolls_to_them(self, panel, editor):
        editor.captions[1].comments = [comment({1}, "c")]
        panel.show(editor.captions[1], editor.captions[1].comments[0], scroll=False)

        panel.go_to_words()

        assert panel.transcript.body.scrolled == [2]
        assert panel.transcript.body.selected == [(2, 5, 2, 8)]

    def test_a_file_with_comments_opens_on_the_first_without_taking_focus(
        self, panel, editor
    ):
        editor.captions[1].comments = [comment({1}, "c")]

        panel.open_first()

        assert panel.container.visible is True
        assert panel.text.value == "c"
        assert panel.focused == 0
        assert panel.transcript.body.scrolled == []

    def test_a_file_without_comments_leaves_it_shut(self, panel, editor):
        panel.open_first()

        assert panel.container.visible is False


class TestFollowingTheCaret:
    def one(self, editor):
        editor.captions[0].comments = [comment({0}, "a")]
        editor.captions[1].comments = [comment({1}, "b")]

        return editor.captions[0].comments[0], editor.captions[1].comments[0]

    def test_a_click_on_commented_words_opens_a_shut_panel_on_the_comment(
        self, panel, editor
    ):
        first, _ = self.one(editor)

        panel.follow(editor.captions[0], first, click=True)

        assert panel.container.visible is True
        assert panel.text.value == "a"
        assert panel.focused == 0

    def test_a_key_that_crosses_commented_words_does_not_open_a_shut_panel(
        self, panel, editor
    ):
        first, _ = self.one(editor)

        panel.follow(editor.captions[0], first, click=False)

        assert panel.container.visible is False

    def test_an_open_panel_follows_the_caret_from_comment_to_comment(
        self, panel, editor
    ):
        first, second = self.one(editor)
        panel.show(editor.captions[0], first)

        panel.follow(editor.captions[1], second, click=False)

        assert panel.text.value == "b"
        assert panel.heading.text == "Comment 2 of 2"

    def test_following_does_not_scroll_the_text_under_the_caret(self, panel, editor):
        first, second = self.one(editor)
        panel.show(editor.captions[0], first, scroll=False)

        panel.follow(editor.captions[1], second, click=True)

        assert panel.transcript.body.scrolled == []

    def test_the_comment_already_on_show_is_left_alone(self, panel, editor):
        first, _ = self.one(editor)
        panel.show(editor.captions[0], first)
        self.draws = 0
        panel.draw = lambda **k: setattr(self, "draws", self.draws + 1)
        panel.text.value = "typing in it"

        panel.follow(editor.captions[0], first, click=True)

        assert self.draws == 0
        assert panel.text.value == "typing in it"

    def test_what_was_typed_is_kept_when_the_caret_moves_on(self, panel, editor):
        first, second = self.one(editor)
        panel.show(editor.captions[0], first)
        panel.text.value = "a, changed"

        panel.follow(editor.captions[1], second, click=True)

        assert first.text == "a, changed"
        assert panel.text.value == "b"

    def test_a_comment_being_written_is_kept_when_the_caret_moves_on(
        self, panel, editor
    ):
        _, second = self.one(editor)
        panel.open_for(editor.captions[0], 4, 7)
        panel.text.value = "new one"

        panel.follow(editor.captions[1], second, click=True)

        assert [c.text for c in editor.captions[0].comments] == ["a", "new one"]
        assert panel.pending is None

    def test_an_empty_comment_being_written_is_dropped_when_the_caret_moves_on(
        self, panel, editor
    ):
        _, second = self.one(editor)
        panel.open_for(editor.captions[0], 4, 7)

        panel.follow(editor.captions[1], second, click=True)

        assert [c.text for c in editor.captions[0].comments] == ["a"]
        assert panel.pending is None


class TestKeepingUpWithTheText:
    def test_a_card_that_is_still_right_keeps_what_is_being_typed(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        panel.text.value = "being typed"

        panel.sync()

        assert panel.text.value == "being typed"

    def test_a_card_that_is_still_right_is_drawn_again_without_scrolling(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        calls = []
        panel.draw = lambda **k: calls.append(k)

        panel.sync()

        assert calls == [{"scroll": False}]

    def test_a_renamed_speaker_is_the_one_the_card_names(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        assert panel.detail.text.startswith("A \u00b7 ")

        editor.captions[0].speaker = "Kim"
        panel.sync()

        assert panel.detail.text.startswith("Kim \u00b7 ")

    def test_a_renamed_speaker_is_the_one_a_new_comment_names(self, panel, editor):
        panel.open_for(editor.captions[0], 0, 3)
        assert panel.detail.text.startswith("A \u00b7 ")

        editor.captions[0].speaker = "Kim"
        panel.sync()

        assert panel.detail.text.startswith("Kim \u00b7 ")

    def test_a_word_typed_into_the_commented_words_keeps_the_card(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0, 1, 2}, "all of it")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        before = panel.current[1]

        editor.update_caption_text(editor.captions[0], "ett två ny tre")
        assert editor.captions[0].comments[0] is not before

        panel.sync()

        assert panel.container.visible is True
        assert panel.current[1] is editor.captions[0].comments[0]
        assert panel.current[1].words == {0, 1, 2, 3}
        assert panel.text.value == "all of it"

    def test_a_word_deleted_before_the_comment_keeps_the_card(self, panel, editor):
        editor.captions[0].comments = [comment({2}, "the last one")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        editor.update_caption_text(editor.captions[0], "ett tre")
        panel.sync()

        assert panel.container.visible is True
        assert panel.current[1] is editor.captions[0].comments[0]
        assert panel.current[1].words == {1}

    def test_the_card_follows_the_comment_with_the_same_text_when_there_are_two(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0}, "one"), comment({2}, "two")]
        panel.show(editor.captions[0], editor.captions[0].comments[1])

        editor.update_caption_text(editor.captions[0], "ett två ny tre")
        panel.sync()

        assert panel.current[1].text == "two"
        assert panel.current[1] is editor.captions[0].comments[1]

    def test_what_is_typed_in_the_card_is_kept_when_the_comment_is_found_again(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0, 1, 2}, "saved text")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        panel.text.value = "saved text, and more not saved yet"

        editor.update_caption_text(editor.captions[0], "ett två ny tre")
        panel.sync()

        assert panel.text.value == "saved text, and more not saved yet"

    def test_typing_in_a_block_tells_the_panel(self, view, panel, editor):
        editor.captions[0].comments = [comment({0}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        calls = []
        panel.sync = lambda: calls.append(1)

        view.set_text({"id": editor.captions[0].index, "text": "ett två tre!"})

        assert calls == [1]

    def test_deleting_the_commented_words_by_typing_puts_the_card_away(
        self, view, panel, editor
    ):
        editor.captions[0].comments = [comment({1}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        view.set_text({"id": editor.captions[0].index, "text": "ett tre"})

        assert panel.container.visible is False
        assert panel.current is None
        assert panel.transcript.body.comment_mark == (-1, -1)

    def test_a_comment_that_an_undo_replaced_is_found_again_by_its_words(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({0, 1}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        replacement = editor.captions[0].copy()
        replacement.comments[0].text = "as it was"
        editor.captions[0] = replacement

        panel.sync()

        assert panel.current[0] is replacement
        assert panel.current[1] is replacement.comments[0]
        assert panel.text.value == "as it was"
        assert panel.container.visible is True

    def test_a_comment_that_is_gone_puts_the_panel_away(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        editor.captions[0].comments = []
        panel.sync()

        assert panel.container.visible is False
        assert panel.current is None

    def test_a_comment_whose_words_were_deleted_goes_with_the_panel(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({1}, "a")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        editor.update_caption_text(editor.captions[0], "ett tre")
        panel.sync()

        assert panel.container.visible is False

    def test_a_new_comment_whose_paragraph_is_gone_is_dropped(self, panel, editor):
        panel.open_for(editor.captions[1], 0, 4)

        editor.captions = [editor.captions[0]]
        panel.sync()

        assert panel.pending is None
        assert panel.container.visible is False

    def test_a_shut_panel_is_left_alone(self, panel, editor):
        panel.sync()

        assert panel.container.visible is False

    def test_the_view_tells_the_panel_whenever_it_redraws(self, view, panel):
        calls = []
        panel.sync = lambda: calls.append(1)
        view.body.set_blocks = lambda blocks: None
        view.body.set_speakers = lambda *a: None
        view.refresh_overlay = lambda: None
        view.refresh_timeline = lambda: None
        del view.refresh
        view.blocks = lambda: []

        view.refresh()

        assert calls == [1]


class TestAskingForTheComment:
    def test_the_events_reach_the_view(self):
        source = pathlib.Path("utils/transcript_editor.py").read_text()

        assert 'self.body.on("opencomment", lambda event: self.open_comment(event.args))' in source
        assert 'self.body.on("caretcomment", lambda event: self.caret_comment(event.args))' in source

    def test_the_selected_words_open_the_panel_on_them(self, view, panel, editor):
        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert panel.pending == (editor.captions[0], 4, 11)
        assert panel.container.visible is True

    def test_nothing_selected_says_so(self, view, panel, editor):
        view.open_comment({"spans": []})

        assert editor.messages == ["Select the words to comment on first"]
        assert panel.container.visible is False

    def test_a_caret_between_words_says_so(self, view, panel, editor):
        editor.captions[0].text = "ett  tre"

        view.open_comment({"spans": [{"id": 1, "start": 4, "end": 4}]})

        assert editor.messages == ["Select the words to comment on first"]

    def test_a_selection_across_paragraphs_is_refused(self, view, panel, editor):
        view.open_comment(
            {
                "spans": [
                    {"id": 1, "start": 4, "end": 11},
                    {"id": 2, "start": 0, "end": 4},
                ]
            }
        )

        assert editor.messages == ["A comment has to stay within one paragraph"]
        assert panel.container.visible is False

    def test_a_selection_that_only_brushes_the_next_paragraph_is_within_one(
        self, view, panel, editor
    ):
        view.open_comment(
            {
                "spans": [
                    {"id": 1, "start": 4, "end": 11},
                    {"id": 2, "start": 0, "end": 0},
                ]
            }
        )

        assert editor.messages == []
        assert panel.pending[0] is editor.captions[0]

    def test_subtitles_open_nothing(self, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        subtitles = make_editor("srt")
        view = TranscriptEditor(subtitles)
        view.body = FakeBody()
        view.comments_panel = FakePanel()

        view.open_comment({"spans": [{"id": 1, "start": 0, "end": 3}]})
        view.caret_comment({"id": 1, "cm": 0, "click": True})

    def test_without_a_panel_nothing_happens(self, view, editor):
        view.comments_panel = None

        view.open_comment({"spans": [{"id": 1, "start": 0, "end": 3}]})
        view.caret_comment({"id": 1, "cm": 0})

    @pytest.mark.parametrize(
        "args",
        [
            None,
            "x",
            {},
            {"spans": None},
            {"spans": "all"},
            {"spans": [None, 3, "x"]},
            {"spans": [{"id": 99, "start": 0, "end": 3}]},
            {"spans": [{"id": 1, "start": "0", "end": 3}]},
            {"spans": [{"id": 1, "start": True, "end": 3}]},
            {"spans": [{"id": 1, "start": 0}]},
        ],
    )
    def test_bad_input_is_harmless(self, view, panel, editor, args):
        view.open_comment(args)

        assert panel.container.visible is False
        assert all(not caption.comments for caption in editor.captions)

    def test_the_caret_in_a_comment_shows_it(self, view, panel, editor):
        editor.captions[1].comments = [comment({1}, "b")]

        view.caret_comment({"id": 2, "cm": 0, "click": True})

        assert panel.text.value == "b"

    def test_a_click_is_told_from_a_key(self, view, panel, editor):
        editor.captions[1].comments = [comment({1}, "b")]

        view.caret_comment({"id": 2, "cm": 0, "click": False})
        view.caret_comment({"id": 2, "cm": 0})
        view.caret_comment({"id": 2, "cm": 0, "click": "yes"})

        assert panel.container.visible is False

    @pytest.mark.parametrize(
        "args",
        [
            None,
            {},
            {"id": 2},
            {"id": 2, "cm": "0"},
            {"id": 2, "cm": True},
            {"id": 2, "cm": 5},
            {"id": 2, "cm": -1},
            {"id": 9, "cm": 0},
        ],
    )
    def test_a_bad_caret_report_is_harmless(self, view, panel, editor, args):
        editor.captions[1].comments = [comment({1}, "b")]

        view.caret_comment(args)

        assert panel.container.visible is False


class TestTheButton:
    def page(self):
        return pathlib.Path("pages/srt.py").read_text()

    def button(self):
        page = self.page()
        start = page.index('with ui.button("Comment", icon="sym_o_add_comment")')

        return page[start : start + 1400]

    def test_it_asks_the_component_for_the_selection(self, view):
        view.comment_selection()

        assert view.body.asked == 1

    def test_it_is_harmless_before_the_editor_is_built(self, editor):
        TranscriptEditor(editor).comment_selection()

    def test_it_sits_beside_highlight_in_the_transcription_toolbar(self):
        page = self.page()

        assert page.index('with ui.button("Highlight"') < page.index(
            'with ui.button("Comment"'
        )

    def test_it_is_a_labelled_quiet_toolbar_button_naming_its_key(self):
        button = self.button()

        assert "aria-keyshortcuts=Control+Shift+K" in button
        assert "editor-btn editor-toolbar-btn editor-quiet" in button
        assert "(Ctrl + Shift + K)" in button

    def test_a_mouse_press_does_not_take_the_selection_with_it(self):
        assert (
            '"mousedown", js_handler="(event) => event.preventDefault()"'
            in self.button()
        )

    def test_a_click_is_the_same_as_the_key(self):
        assert '"click", lambda: transcript.comment_selection()' in self.button()

    def test_the_icon_is_a_material_symbol_that_exists(self):
        """
        sym_o_ is Material Symbols Outlined, which ships with NiceGUI and
        has add_comment; a name the font lacks would draw its own letters.
        """

        assert 'icon="sym_o_add_comment"' in self.page()


class TestThePanelSource:
    def source(self):
        return pathlib.Path("utils/comments_panel.py").read_text()

    def test_it_is_drawn_like_the_validation_card_in_its_own_colour(self):
        source = self.source()

        assert '"validation-panel is-comment w-full"' in source
        assert "validation-panel-head" in source and "validation-panel-step" in source

    def test_it_has_previous_next_position_and_close_with_names(self):
        source = self.source()

        for label in (
            'aria-label="Previous comment"',
            'aria-label="Next comment"',
            'aria-label="Close comments panel"',
        ):
            assert label in source

    def test_the_heading_names_the_section_and_can_take_focus(self):
        source = self.source()

        assert 'aria-labelledby="comments-panel-heading"' in source
        assert "id=comments-panel-heading tabindex=-1" in source

    def test_the_position_is_spoken_in_a_live_region(self):
        assert '"role=status aria-live=polite aria-atomic=true"' in self.source()

    def test_the_text_is_limited_as_the_server_limits_it(self):
        assert "maxlength={COMMENT_MAX_LENGTH}" in self.source()

    def test_keys_typed_in_the_text_stay_in_it(self):
        source = self.source()

        assert '"keydown", js_handler="(event) => event.stopPropagation()"' in source

    def test_escape_abandons_and_ctrl_or_cmd_enter_saves(self):
        source = self.source()

        assert 'self.text.on("keydown.escape", self.cancel)' in source
        assert 'self.text.on("keydown.ctrl.enter", self.save)' in source
        assert 'self.text.on("keydown.meta.enter", self.save)' in source

    def test_it_starts_shut(self):
        assert "self.container.set_visibility(False)" in self.source()

    def test_the_page_builds_it_for_transcriptions_and_opens_a_file_that_has_comments(self):
        page = pathlib.Path("pages/srt.py").read_text()
        start = page.index("transcript.comments_panel = CommentsPanel(transcript)")
        block = page[start - 900 : start]

        assert "else:" in block
        assert "transcript.comments_panel.open_first()" in page[start : start + 200]
        assert "data_format" not in page[start : start + 200]

    def test_the_validation_panel_is_still_subtitles_only(self):
        page = pathlib.Path("pages/srt.py").read_text()
        start = page.index("editor.validation_panel = ValidationPanel(")

        assert 'if data_format == "srt":' in page[start - 200 : start]


class TestWhereItIs:
    """
    A transcription does not show a caption's number, so the card says where
    a comment is by what is shown beside the text, and the text marks it.
    """

    def test_it_is_the_speaker_and_the_start_time_as_the_editor_shows_them(
        self, panel, editor
    ):
        editor.captions[1].speaker = "Speaker 2"
        editor.captions[1].comments = [comment({0}, "here")]

        panel.show(editor.captions[1], editor.captions[1].comments[0])

        from utils.transcript_editor import format_time_label

        assert panel.detail.text == (
            "Speaker 2 \u00b7 " + format_time_label(editor.captions[1].get_start_seconds())
        )
        assert "Paragraph" not in panel.detail.text

    def test_without_a_speaker_it_is_the_time_alone(self, panel, editor):
        from utils.comments_panel import where_text

        editor.captions[0].speaker = ""

        assert where_text(editor.captions[0]) == "00:00:00.000"

    def test_the_comment_on_show_is_marked_in_the_text(self, panel, editor):
        editor.captions[1].comments = [comment({0}, "a"), comment({2}, "b")]

        panel.show(editor.captions[1], editor.captions[1].comments[1])

        assert panel.transcript.body.comment_mark == (editor.captions[1].index, 1)

    def test_a_comment_being_written_marks_its_caption_only(self, panel, editor):
        panel.open_for(editor.captions[0], 5, 9)

        assert panel.transcript.body.comment_mark == (editor.captions[0].index, -1)

    def test_stepping_moves_the_marking_with_the_card(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "first")]
        editor.captions[1].comments = [comment({1}, "second")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        panel.go_next()

        assert panel.transcript.body.comment_mark == (editor.captions[1].index, 0)

        panel.go_previous()

        assert panel.transcript.body.comment_mark == (editor.captions[0].index, 0)

    def test_following_the_caret_marks_the_comment_it_lands_on(self, panel, editor):
        editor.captions[1].comments = [comment({1}, "second")]

        panel.follow(editor.captions[1], editor.captions[1].comments[0], click=True)

        assert panel.transcript.body.comment_mark == (editor.captions[1].index, 0)

    def test_closing_the_card_takes_the_marking_off(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "x")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        panel.close()

        assert panel.transcript.body.comment_mark == (-1, -1)

    def test_a_comment_that_is_gone_takes_the_marking_with_it(self, panel, editor):
        editor.captions[0].comments = [comment({0}, "x")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        editor.captions[0].comments = []

        panel.sync()

        assert panel.container.visible is False
        assert panel.transcript.body.comment_mark == (-1, -1)

    def test_the_marking_is_set_again_when_the_comment_has_moved_in_its_caption(
        self, panel, editor
    ):
        editor.captions[0].comments = [comment({2}, "late")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])
        editor.captions[0].comments.insert(0, comment({0}, "early"))

        panel.sync()

        assert panel.transcript.body.comment_mark == (editor.captions[0].index, 1)

    def test_removing_the_last_comment_takes_it_off(self, panel, editor):
        editor.captions[0].comments = [comment({1}, "only")]
        panel.show(editor.captions[0], editor.captions[0].comments[0])

        panel.remove()

        assert panel.transcript.body.comment_mark == (-1, -1)

    def test_the_body_keeps_the_marking_and_ignores_a_repeat(self):
        from utils.transcript_editor import TranscriptBody

        body = TranscriptBody.__new__(TranscriptBody)
        body._props = {"commentId": -1, "commentIndex": -1}
        updates = []
        body.update = lambda: updates.append(1)

        body.set_comment_mark(3, 1)
        body.set_comment_mark(3, 1)

        assert (body._props["commentId"], body._props["commentIndex"]) == (3, 1)
        assert len(updates) == 1

    def test_the_editor_clears_it_with_none(self, view):
        marks = []
        view.body.set_comment_mark = lambda *a: marks.append(a)

        view.mark_comment(None)
        view.mark_comment(2, 0)

        assert marks == [(-1, -1), (2, 0)]


class TestPanelHelpers:
    def test_the_quote_is_one_line(self):
        from utils.comments_panel import quote_of

        assert quote_of("two\n  lines   here") == "two lines here"

    def test_a_long_quote_is_shortened(self):
        from utils.comments_panel import QUOTE_LENGTH, quote_of

        quoted = quote_of("word " * 50)

        assert len(quoted) == QUOTE_LENGTH
        assert quoted.endswith("\u2026")

    def test_the_heading(self):
        from utils.comments_panel import heading_text

        assert heading_text(True, 0, 3) == "New comment"
        assert heading_text(False, 1, 3) == "Comment 2 of 3"


class TestTheComponent:
    def source(self):
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def method(self, name):
        source = self.source()
        body = source[source.index(f"\n    {name}(") :]

        return body[: body.index("\n    },") + 7]

    def test_the_key_is_ctrl_shift_k_by_physical_key(self):
        source = self.source()
        start = source.index('event.code === "KeyK"')
        block = source[start - 220 : start + 60]

        assert "!this.subtitleMode" in block
        assert "event.ctrlKey" in block and "event.shiftKey" in block
        assert "!event.altKey" in block
        assert "!event.metaKey" in block

    def test_it_is_ahead_of_the_block_scoped_lists(self):
        source = self.source()

        assert source.index('"opencomment", { spans }') < source.index(
            "this.subtitleShortcut(event, at)"
        )

    def test_the_button_reports_the_selection_as_the_key_does(self):
        body = self.method("commentSelection")

        assert "this.flush();" in body
        assert '"opencomment", { spans: this.highlightSpans() }' in body

    def test_the_caret_in_a_comment_is_reported_once_per_comment(self):
        body = self.method("reportCommentCaret")

        assert "key === this.lastCommentKey && !clicked" in body
        assert '"caretcomment", { ...at, click: clicked }' in body

    def test_only_a_collapsed_caret_in_commented_words_counts(self):
        body = self.method("commentAtCaret")

        assert "!selection.isCollapsed" in body
        assert 'closest?.("[data-comment]")' in body

    def test_keys_report_it_and_a_click_reports_it_as_a_click(self):
        update = self.method("updateCaretBlock")
        click = self.method("onClick")

        assert "this.reportCommentCaret();" in update
        assert "this.reportCommentCaret(true);" in click

    def test_commented_words_are_marked_up_with_what_a_screen_reader_needs(self):
        source = self.source()

        assert source.count(':data-comment="run.cm"') == 2
        assert (
            source.count(
                """:aria-description="run.cf ? 'Comment: ' + run.ct : null\""""
            )
            == 2
        )

    def test_the_classes_come_from_the_one_function(self):
        source = self.source()

        assert source.count(':class="runClass(run)"') == 2
        assert 'run.cm !== undefined ? "comment-word" : null' in source
        assert 'run.cl ? "comment-end" : null' in source

    def test_the_comment_on_show_is_marked_on_its_caption_and_its_words(self):
        source = self.source()

        assert "commentId: { type: Number, default: -1 }" in source
        assert "commentIndex: { type: Number, default: -1 }" in source
        assert "'transcript-cell-commenting': block.id === commentId" in source
        assert "block.id === this.commentId" in source
        assert "run.cm === this.commentIndex" in source
        assert source.count("isCommentOnShow(run, block)") == 3  # two templates and the method

    def test_nothing_of_the_old_box_is_left(self):
        source = self.source()

        for gone in ("comment-box", "showComment", "peekcomment", "leaveComment"):
            assert gone not in source


class TestTheStyles:
    def css(self):
        return pathlib.Path("utils/styles.py").read_text()

    def rule(self, selector):
        css = self.css()
        rule = css[css.index(selector) :]

        return rule[: rule.index("}")]

    def test_it_has_its_own_colour_in_both_themes(self):
        assert self.css().count("--color-comment-line:") == 2

    def test_commented_words_have_a_dotted_underline_that_is_not_only_colour(self):
        rule = self.rule("    .comment-word {")

        assert "text-decoration-line: underline;" in rule
        assert "text-decoration-style: dotted;" in rule
        assert "text-decoration-thickness: 3px;" in rule
        assert "text-underline-offset: 4px;" in rule
        assert "var(--color-comment-line)" in rule

    def test_the_underline_takes_no_room_and_no_box_shadow(self):
        rule = self.rule("    .comment-word {")

        assert "padding" not in rule
        assert "margin" not in rule
        assert "box-shadow" not in rule
        assert "::after" not in rule

    def test_nothing_is_added_after_the_last_word(self):
        css = self.css()

        assert ".comment-end::after" not in css
        assert ".comment-word::after" not in css

    def test_the_caption_on_show_has_a_rule_and_an_outline_in_the_comment_colour(self):
        rule = self.rule("    .transcript-cell-commenting {")

        assert "border-left-width: 3px;" in rule
        assert "inset 0 0 0 2px var(--color-comment-line)" in rule
        assert "var(--color-comment-line)" in rule

    def test_it_comes_after_the_rules_it_has_to_win_over(self):
        css = self.css()
        at = css.index("    .transcript-cell-commenting {")

        for earlier in (
            "    .transcript-cell-editing {",
            "    .transcript-cell-invalid {",
            "    .transcript-cell-highlighted {",
        ):
            assert css.index(earlier) < at

    def test_the_words_on_show_get_a_tint_that_leaves_their_own_wash_showing(self):
        rule = self.rule("    .comment-word[data-comment-current] {")

        # background-image paints above background-color, so a highlighted,
        # flagged or changed word keeps its own wash underneath.
        assert "background-image" in rule
        assert "background-color" not in rule
        assert "18%" in rule
        assert "padding" not in rule
        assert "box-shadow" not in rule

    @pytest.mark.parametrize(
        "line,walls",
        [
            (
                "#a1136a",
                [
                    ("#ffffff", "#111827"),
                    ("#fff1a3", "#2b2400"),
                    ("#ede9fb", "#2f1c66"),
                    ("#dcf2ee", "#10453d"),
                    ("#dbe4f0", "#111827"),
                ],
            ),
            (
                "#ff9fd2",
                [
                    ("#16181d", "#e6e8eb"),
                    ("#5a4a00", "#fff6cc"),
                    ("#2f2748", "#ece7ff"),
                    ("#1d3b37", "#dff5f0"),
                    ("#1c3252", "#e6e8eb"),
                ],
            ),
        ],
    )
    def test_the_tint_keeps_the_text_and_the_line_readable(self, line, walls):
        def rgb(colour):
            return [int(colour[i : i + 2], 16) for i in (1, 3, 5)]

        def luminance(channels):
            linear = [
                (c / 255) / 12.92
                if c / 255 <= 0.03928
                else ((c / 255 + 0.055) / 1.055) ** 2.4
                for c in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def ratio(a, b):
            lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
            return (lighter + 0.05) / (darker + 0.05)

        for wall, text in walls:
            tinted = [
                round(w * 0.82 + t * 0.18) for w, t in zip(rgb(wall), rgb(line))
            ]

            assert ratio(rgb(text), tinted) >= 4.5
            assert ratio(rgb(line), tinted) >= 3

    def test_the_panel_has_the_colour_of_the_underline(self):
        rule = self.rule("    .validation-panel.is-comment {")

        assert "--vp-tone: var(--color-comment-line);" in rule

    def test_nothing_of_the_old_box_is_left(self):
        assert ".comment-box" not in self.css()

    @pytest.mark.parametrize(
        "line,backgrounds",
        [
            ("#a1136a", ["#ffffff", "#fff1a3", "#ede9fb", "#dcf2ee", "#dbe4f0"]),
            ("#ff9fd2", ["#16181d", "#5a4a00", "#2f2748", "#1d3b37", "#1c3252"]),
        ],
    )
    def test_the_line_is_visible_on_every_wash_a_word_can_have(self, line, backgrounds):
        def luminance(colour):
            channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
            linear = [
                c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels
            ]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        for background in backgrounds:
            lighter, darker = sorted(
                (luminance(line), luminance(background)), reverse=True
            )

            assert (lighter + 0.05) / (darker + 0.05) >= 3

    def test_the_colours_in_the_test_are_the_ones_in_the_stylesheet(self):
        css = self.css()

        assert "--color-comment-line: #a1136a;" in css
        assert "--color-comment-line: #ff9fd2;" in css

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

import pytest

from utils.caption import SRTCaption, WordComment
from utils.srt import SRTEditor


# Two blocks, six words, one continuous run of speech.
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


@pytest.fixture
def editor():
    editor = SRTEditor("job-uuid", "srt", "file.srt")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *args, **kwargs: None)

    editor.load_words(WORDS)
    editor.captions = [
        SRTCaption(1, "00:00:00,000", "00:00:01,500", "ett två tre"),
        SRTCaption(2, "00:00:02,000", "00:00:03,500", "fyra fem sex"),
    ]

    return editor


class TestMoveFirstWordToPrevious:
    def test_moves_the_word(self, editor):
        editor.move_first_word_to_previous(editor.captions[1])

        assert editor.captions[0].text == "ett två tre fyra"
        assert editor.captions[1].text == "fem sex"

    def test_retimes_both_blocks_from_the_word_data(self, editor):
        editor.move_first_word_to_previous(editor.captions[1])

        first, second = editor.captions

        # Previous block ends where the moved word ("fyra") ends.
        assert first.get_end_seconds() == pytest.approx(2.4)
        # Current block starts where its new first word ("fem") starts.
        assert second.get_start_seconds() == pytest.approx(2.5)

    def test_refuses_on_the_first_block(self, editor):
        editor.move_first_word_to_previous(editor.captions[0])

        assert editor.captions[0].text == "ett två tre"

    def test_the_only_word_is_a_merge_with_the_previous_block(self, editor):
        editor.captions[1] = SRTCaption(2, "00:00:02,000", "00:00:03,500", "fyra")

        outcome = editor.move_first_word_to_previous(editor.captions[1])

        assert outcome == "merged"
        assert len(editor.captions) == 1
        assert editor.captions[0].text.split() == ["ett", "två", "tre", "fyra"]

    def test_a_move_does_not_say_it_merged(self, editor):
        assert editor.move_first_word_to_previous(editor.captions[1]) is None

    def test_nothing_to_do_does_not_say_it_merged(self, editor):
        assert editor.move_first_word_to_previous(editor.captions[0]) is None


class TestMoveLastWordToNext:
    def test_moves_the_word(self, editor):
        editor.move_last_word_to_next(editor.captions[0])

        assert editor.captions[0].text == "ett två"
        assert editor.captions[1].text == "tre fyra fem sex"

    def test_retimes_both_blocks_from_the_word_data(self, editor):
        editor.move_last_word_to_next(editor.captions[0])

        first, second = editor.captions

        # Next block starts where the moved word ("tre") starts.
        assert second.get_start_seconds() == pytest.approx(1.1)
        # Current block ends where its new last word ("två") ends.
        assert first.get_end_seconds() == pytest.approx(1.0)

    def test_refuses_on_the_last_block(self, editor):
        editor.move_last_word_to_next(editor.captions[-1])

        assert editor.captions[-1].text == "fyra fem sex"

    def test_the_only_word_is_a_merge_with_the_next_block(self, editor):
        editor.captions[0] = SRTCaption(1, "00:00:00,000", "00:00:01,500", "ett")

        outcome = editor.move_last_word_to_next(editor.captions[0])

        assert outcome == "merged"
        assert len(editor.captions) == 1
        assert editor.captions[0].text.split() == ["ett", "fyra", "fem", "sex"]

    def test_a_move_does_not_say_it_merged(self, editor):
        assert editor.move_last_word_to_next(editor.captions[0]) is None

    def test_nothing_to_do_does_not_say_it_merged(self, editor):
        assert editor.move_last_word_to_next(editor.captions[-1]) is None


class TestWithoutWordData:
    """
    Older results carry no word timings. The text still moves; the timings
    are left alone rather than invented.
    """

    def test_text_moves_and_timings_are_untouched(self, editor):
        editor.load_words(None)
        before = editor.captions[0].end_time

        editor.move_last_word_to_next(editor.captions[0])

        assert editor.captions[0].text == "ett två"
        assert editor.captions[1].text == "tre fyra fem sex"
        assert editor.captions[0].end_time == before


class TestLineBreaksSurvive:
    """
    A two-line subtitle must not collapse to one line when a word moves.
    """

    def test_remainder_keeps_its_line_break(self, editor):
        editor.captions[0] = SRTCaption(
            1, "00:00:00,000", "00:00:01,500", "ett två\ntre fyra"
        )

        editor.move_first_word_to_previous(editor.captions[1])

        assert "\n" in editor.captions[0].text

    def test_splitting_helpers_preserve_separators(self):
        assert SRTEditor.split_off_first_word("ett två\ntre") == ("ett", "två\ntre")
        assert SRTEditor.split_off_last_word("ett två\ntre") == ("ett två", "tre")
        assert SRTEditor.split_off_first_word("ensam") == ("ensam", "")
        assert SRTEditor.split_off_last_word("ensam") == ("", "ensam")


class TestTimestampFormatting:
    """
    Re-timing writes timestamps back, so the formatter has to round-trip.
    """

    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0.0, "00:00:00,000"),
            (2.4, "00:00:02,400"),
            (1.1, "00:00:01,100"),
            (2.9, "00:00:02,900"),
            (7261.25, "02:01:01,250"),
            # Rounding must carry through every field, not strand a
            # timestamp on 60 seconds or 60 minutes.
            (59.9999, "00:01:00,000"),
            (3599.9999, "01:00:00,000"),
        ],
    )
    def test_formats_and_carries(self, editor, seconds, expected):
        assert editor.seconds_to_timestamp(seconds) == expected

    @pytest.mark.parametrize(
        "seconds", [0.0, 0.5, 1.1, 2.4, 2.9, 59.5, 61.001, 3661.75, 7261.25]
    )
    def test_round_trips(self, editor, seconds):
        stamp = editor.seconds_to_timestamp(seconds)
        parsed = SRTCaption(1, stamp, stamp, "").get_start_seconds()

        assert parsed == pytest.approx(seconds, abs=0.001)

    def test_never_emits_an_out_of_range_field(self, editor):
        for tenth in range(0, 40000):
            stamp = editor.seconds_to_timestamp(tenth * 0.0999)
            hours, minutes, rest = stamp.split(":")
            secs, millis = rest.split(",")

            assert int(minutes) < 60, stamp
            assert int(secs) < 60, stamp
            assert int(millis) < 1000, stamp



class TestMoveTextBeforeCursorToPrevious:
    """
    Everything before the cursor goes to the end of the previous block; the
    word the cursor is in goes with it, whole.
    """

    def test_moves_the_words_before_the_cursor(self, editor):
        # "fyra |fem sex"
        outcome = editor.move_text_before_cursor_to_previous(editor.captions[1], 5)

        assert outcome == "moved"
        assert editor.captions[0].text == "ett två tre fyra"
        assert editor.captions[1].text == "fem sex"

    def test_the_word_under_the_cursor_goes_too(self, editor):
        # "fyra fe|m sex"
        editor.move_text_before_cursor_to_previous(editor.captions[1], 7)

        assert editor.captions[0].text == "ett två tre fyra fem"
        assert editor.captions[1].text == "sex"

    def test_a_cursor_inside_the_first_word_moves_that_word(self, editor):
        editor.move_text_before_cursor_to_previous(editor.captions[1], 2)

        assert editor.captions[0].text == "ett två tre fyra"
        assert editor.captions[1].text == "fem sex"

    def test_retimes_both_blocks_from_the_word_data(self, editor):
        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        first, second = editor.captions

        # Ends where "fem" ends; the rest starts where "sex" starts.
        assert first.get_end_seconds() == pytest.approx(2.9)
        assert second.get_start_seconds() == pytest.approx(3.0)

    def test_whitespace_between_the_parts_is_not_carried(self, editor):
        editor.captions[1].text = "fyra   fem sex"

        editor.move_text_before_cursor_to_previous(editor.captions[1], 7)

        assert editor.captions[0].text == "ett två tre fyra"
        assert editor.captions[1].text == "fem sex"

    def test_a_line_break_inside_the_moved_text_survives(self, editor):
        editor.captions[1].text = "fyra\nfem sex"

        editor.move_text_before_cursor_to_previous(editor.captions[1], 6)

        assert editor.captions[0].text == "ett två tre fyra\nfem"
        assert editor.captions[1].text == "sex"

    def test_the_wording_is_unchanged(self, editor):
        before = " ".join(c.text for c in editor.captions)

        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        assert " ".join(c.text for c in editor.captions) == before

    def test_everything_before_the_cursor_is_a_merge(self, editor):
        for offset in (len("fyra fem sex"), len("fyra fem sex") - 1):
            ed = SRTEditor("job-uuid", "srt", "file.srt")
            for name in ("refresh_display", "update_words_per_minute",
                         "save_state_for_undo", "mark_as_changed"):
                setattr(ed, name, lambda *args, **kwargs: None)
            ed.load_words(WORDS)
            ed.captions = [
                SRTCaption(1, "00:00:00,000", "00:00:01,500", "ett två tre"),
                SRTCaption(2, "00:00:02,000", "00:00:03,500", "fyra fem sex"),
            ]

            outcome = ed.move_text_before_cursor_to_previous(ed.captions[1], offset)

            assert outcome == "merged"
            assert len(ed.captions) == 1
            assert ed.captions[0].text == "ett två tre\nfyra fem sex"
            assert ed.captions[0].get_end_seconds() == pytest.approx(3.5)

    def test_refuses_on_the_first_block(self, editor):
        outcome = editor.move_text_before_cursor_to_previous(editor.captions[0], 4)

        assert outcome == ""
        assert editor.captions[0].text == "ett två tre"

    def test_refuses_when_there_is_no_text_before_the_cursor(self, editor):
        outcome = editor.move_text_before_cursor_to_previous(editor.captions[1], 0)

        assert outcome == ""
        assert editor.captions[0].text == "ett två tre"
        assert editor.captions[1].text == "fyra fem sex"

    def test_a_cursor_after_leading_whitespace_has_nothing_before_it(self, editor):
        editor.captions[1].text = "  fyra fem sex"

        outcome = editor.move_text_before_cursor_to_previous(editor.captions[1], 2)

        assert outcome == ""

    def test_one_undo_step(self, editor):
        saved = []
        editor.save_state_for_undo = lambda *a, **k: saved.append(1)

        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        assert len(saved) == 1

    def test_a_merge_is_one_undo_step_too(self, editor):
        saved = []
        editor.save_state_for_undo = lambda *a, **k: saved.append(1)

        editor.move_text_before_cursor_to_previous(editor.captions[1], 12)

        assert len(saved) == 1

    def test_marks_follow_their_words(self, editor):
        editor.captions[0].edited_words = {0}
        editor.captions[1].edited_words = {0, 2}

        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        # "fyra" and "fem" went to the previous block as words 3 and 4; "sex"
        # is now the first word of this one.
        assert editor.captions[0].edited_words == {0, 3}
        assert editor.captions[1].edited_words == {0}

    def test_without_word_data_the_text_moves_and_the_timings_stay(self, editor):
        editor.load_words({"version": 1, "words": []})
        before = [(c.start_time, c.end_time) for c in editor.captions]

        outcome = editor.move_text_before_cursor_to_previous(editor.captions[1], 5)

        assert outcome == "moved"
        assert editor.captions[0].text == "ett två tre fyra"
        assert [(c.start_time, c.end_time) for c in editor.captions] == before

    def test_an_empty_previous_block_takes_the_text_without_a_leading_space(self, editor):
        editor.captions[0].text = ""

        editor.move_text_before_cursor_to_previous(editor.captions[1], 5)

        assert editor.captions[0].text == "fyra"


class TestMoveTextAfterCursorToNext:
    def test_moves_the_words_after_the_cursor(self, editor):
        # "ett |två tre"
        outcome = editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert outcome == "moved"
        assert editor.captions[0].text == "ett"
        assert editor.captions[1].text == "två tre fyra fem sex"

    def test_the_word_under_the_cursor_goes_too(self, editor):
        # "ett t|vå tre"
        editor.move_text_after_cursor_to_next(editor.captions[0], 5)

        assert editor.captions[0].text == "ett"
        assert editor.captions[1].text == "två tre fyra fem sex"

    def test_a_cursor_at_the_end_of_a_word_leaves_that_word(self, editor):
        # "ett| två tre"
        editor.move_text_after_cursor_to_next(editor.captions[0], 3)

        assert editor.captions[0].text == "ett"
        assert editor.captions[1].text == "två tre fyra fem sex"

    def test_retimes_both_blocks_from_the_word_data(self, editor):
        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        first, second = editor.captions

        assert second.get_start_seconds() == pytest.approx(0.6)
        assert first.get_end_seconds() == pytest.approx(0.5)

    def test_whitespace_between_the_parts_is_not_carried(self, editor):
        editor.captions[0].text = "ett   två tre"

        editor.move_text_after_cursor_to_next(editor.captions[0], 5)

        assert editor.captions[0].text == "ett"
        assert editor.captions[1].text == "två tre fyra fem sex"

    def test_the_wording_is_unchanged(self, editor):
        before = " ".join(c.text for c in editor.captions)

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert " ".join(c.text for c in editor.captions) == before

    def test_everything_after_the_cursor_is_a_merge(self, editor):
        outcome = editor.move_text_after_cursor_to_next(editor.captions[0], 0)

        assert outcome == "merged"
        assert len(editor.captions) == 1
        assert editor.captions[0].text == "ett två tre\nfyra fem sex"

    def test_a_cursor_inside_the_first_word_is_a_merge(self, editor):
        outcome = editor.move_text_after_cursor_to_next(editor.captions[0], 2)

        assert outcome == "merged"
        assert len(editor.captions) == 1

    def test_refuses_on_the_last_block(self, editor):
        outcome = editor.move_text_after_cursor_to_next(editor.captions[-1], 4)

        assert outcome == ""
        assert editor.captions[-1].text == "fyra fem sex"

    def test_refuses_when_there_is_no_text_after_the_cursor(self, editor):
        outcome = editor.move_text_after_cursor_to_next(editor.captions[0], 11)

        assert outcome == ""
        assert editor.captions[0].text == "ett två tre"
        assert editor.captions[1].text == "fyra fem sex"

    def test_one_undo_step(self, editor):
        saved = []
        editor.save_state_for_undo = lambda *a, **k: saved.append(1)

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert len(saved) == 1

    def test_a_merge_is_one_undo_step_too(self, editor):
        saved = []
        editor.save_state_for_undo = lambda *a, **k: saved.append(1)

        editor.move_text_after_cursor_to_next(editor.captions[0], 0)

        assert len(saved) == 1

    def test_marks_follow_their_words(self, editor):
        editor.captions[0].edited_words = {0, 2}
        editor.captions[1].edited_words = {1}

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        # "två tre" are now words 0 and 1 of the next block, ahead of its
        # own words, which move along by two.
        assert editor.captions[0].edited_words == {0}
        assert editor.captions[1].edited_words == {1, 3}

    def test_without_word_data_the_text_moves_and_the_timings_stay(self, editor):
        editor.load_words({"version": 1, "words": []})
        before = [(c.start_time, c.end_time) for c in editor.captions]

        outcome = editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert outcome == "moved"
        assert editor.captions[1].text == "två tre fyra fem sex"
        assert [(c.start_time, c.end_time) for c in editor.captions] == before

    def test_an_empty_next_block_takes_the_text_without_a_trailing_space(self, editor):
        editor.captions[1].text = ""

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert editor.captions[1].text == "två tre"


def words_of(caption):
    """
    A caption's comments as plain data: (sorted words, text).
    """

    return [(sorted(c.words), c.text) for c in caption.comments]


class TestMovedTextKeepsItsMarks:
    """
    A highlight and a comment are on words, counted from the first word of
    their block, so text moved to the next or previous block takes them along:
    left where they were, they would sit on whatever words are now at those
    positions, or in the other block altogether.
    """

    def test_a_comment_on_text_sent_to_the_previous_block_goes_with_it(self, editor):
        editor.captions[1].comments = [WordComment({0}, "about fyra")]

        # "fyra fem| sex": fyra and fem go.
        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        assert words_of(editor.captions[0]) == [([3], "about fyra")]
        assert editor.captions[1].comments == []

    def test_a_comment_on_the_words_left_behind_keeps_its_words(self, editor):
        editor.captions[1].comments = [WordComment({2}, "about sex")]

        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        assert editor.captions[0].comments == []
        assert words_of(editor.captions[1]) == [([0], "about sex")]

    def test_a_comment_across_the_cursor_is_on_both_sides(self, editor):
        editor.captions[1].comments = [WordComment({1, 2}, "fem and sex")]

        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        assert words_of(editor.captions[0]) == [([4], "fem and sex")]
        assert words_of(editor.captions[1]) == [([0], "fem and sex")]

    def test_the_comments_the_previous_block_already_had_stay_where_they_are(
        self, editor
    ):
        editor.captions[0].comments = [WordComment({0, 1}, "old")]
        editor.captions[1].comments = [WordComment({0}, "new")]

        editor.move_text_before_cursor_to_previous(editor.captions[1], 5)

        assert words_of(editor.captions[0]) == [([0, 1], "old"), ([3], "new")]

    def test_a_highlight_on_text_sent_to_the_previous_block_goes_with_it(self, editor):
        editor.captions[0].highlighted_words = {0}
        editor.captions[1].highlighted_words = {0, 2}

        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)

        assert editor.captions[0].highlighted_words == {0, 3}
        assert editor.captions[1].highlighted_words == {0}

    def test_a_comment_on_text_sent_to_the_next_block_goes_with_it(self, editor):
        editor.captions[0].comments = [WordComment({2}, "about tre")]

        # "ett |två tre": två and tre go.
        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert editor.captions[0].comments == []
        assert words_of(editor.captions[1]) == [([1], "about tre")]

    def test_a_comment_on_the_words_kept_stays(self, editor):
        editor.captions[0].comments = [WordComment({0}, "about ett")]

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert words_of(editor.captions[0]) == [([0], "about ett")]
        assert editor.captions[1].comments == []

    def test_the_comments_the_next_block_already_had_move_along(self, editor):
        editor.captions[0].comments = [WordComment({2}, "moved")]
        editor.captions[1].comments = [WordComment({0}, "own")]

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert words_of(editor.captions[1]) == [([1], "moved"), ([2], "own")]

    def test_a_comment_across_the_cursor_is_on_both_blocks_going_next(self, editor):
        editor.captions[0].comments = [WordComment({0, 1, 2}, "all of it")]

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert words_of(editor.captions[0]) == [([0], "all of it")]
        assert words_of(editor.captions[1]) == [([0, 1], "all of it")]

    def test_a_highlight_on_text_sent_to_the_next_block_goes_with_it(self, editor):
        editor.captions[0].highlighted_words = {0, 2}
        editor.captions[1].highlighted_words = {1}

        editor.move_text_after_cursor_to_next(editor.captions[0], 4)

        assert editor.captions[0].highlighted_words == {0}
        assert editor.captions[1].highlighted_words == {1, 3}

    def test_every_comment_is_still_there_after_a_move_either_way(self, editor):
        editor.captions[0].comments = [WordComment({1}, "a")]
        editor.captions[1].comments = [WordComment({1}, "b")]

        editor.move_text_before_cursor_to_previous(editor.captions[1], 8)
        texts = sorted(c.text for cap in editor.captions for c in cap.comments)

        assert texts == ["a", "b"]

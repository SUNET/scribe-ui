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

from utils.caption import SRTCaption
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

    def test_refuses_to_empty_a_block(self, editor):
        editor.captions[1] = SRTCaption(2, "00:00:02,000", "00:00:03,500", "fyra")

        editor.move_first_word_to_previous(editor.captions[1])

        assert editor.captions[1].text == "fyra"
        assert editor.captions[0].text == "ett två tre"


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

    def test_refuses_to_empty_a_block(self, editor):
        editor.captions[0] = SRTCaption(1, "00:00:00,000", "00:00:01,500", "ett")

        editor.move_last_word_to_next(editor.captions[0])

        assert editor.captions[0].text == "ett"


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


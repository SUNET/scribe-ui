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

import json
import re

import pytest

from utils.caption import SRTCaption
from utils.srt import DEFAULT_REVIEW_SENSITIVITY, SRTEditor


PAYLOAD = {
    "version": 1,
    "words": [
        {"t": "Hej", "s": 0.0, "e": 0.5, "c": 0.99},
        {"t": "på", "s": 0.6, "e": 0.8, "c": 0.15},
        {"t": "dig", "s": 1.0, "e": 1.4, "c": 0.95},
        {"t": "idag", "s": 3.0, "e": 3.6, "c": 0.70},
    ],
}

TEXT = "Hej på dig idag"


@pytest.fixture
def editor():
    """
    An editor with the UI side effects of editing stubbed out.
    """

    editor = SRTEditor("job-uuid", "srt", "file.srt")
    editor.refresh_display = lambda *args, **kwargs: None
    editor.update_words_per_minute = lambda *args, **kwargs: None
    editor.save_state_for_undo = lambda *args, **kwargs: None
    editor.mark_as_changed = lambda *args, **kwargs: None

    return editor


def caption(text: str = TEXT) -> SRTCaption:
    return SRTCaption(1, "00:00:00,000", "00:00:04,000", text)


class TestLoadWords:
    """
    Parsing of the word timing payload.
    """

    def test_loads_payload(self, editor):
        editor.load_words(PAYLOAD)

        assert [word["t"] for word in editor.words] == ["Hej", "på", "dig", "idag"]
        assert editor.has_confidence is True

    def test_loads_json_string(self, editor):
        editor.load_words(json.dumps(PAYLOAD))

        assert len(editor.words) == 4

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            "",
            "not json",
            [1, 2, 3],
            {"words": "not a list"},
            {"version": 99, "words": [{"t": "Hej", "s": 0.0, "e": 0.5}]},
            {"version": 1, "words": [{"s": 0.0, "e": 0.5}]},
        ],
    )
    def test_rejects_unusable_payload(self, editor, payload):
        editor.load_words(payload)

        assert editor.words == []
        assert editor.has_confidence is False

    def test_a_word_without_a_timing_is_still_a_word(self, editor):
        """
        Text is what makes an entry a word; a timing only says where in the
        recording it was said. Dropping it left a hole in the transcript that
        read as a word the reader had written.
        """

        editor.load_words(
            {"version": 1, "words": [{"t": "Hej", "c": 0.15}]}
        )

        assert [word["t"] for word in editor.words] == ["Hej"]
        assert editor.words[0]["c"] == pytest.approx(0.15)
        assert editor.has_confidence is True

    def test_a_word_without_a_timing_is_not_timed(self, editor):
        editor.load_words({"version": 1, "words": [{"t": "Hej"}]})

        assert editor.words[0].keys() == {"t"}
        assert editor.word_is_timed(editor.words[0]) is False

    def test_an_unusable_timing_leaves_the_word_behind(self, editor):
        editor.load_words(
            {"version": 1, "words": [{"t": "Hej", "s": "soon", "e": "later"}]}
        )

        assert [word["t"] for word in editor.words] == ["Hej"]
        assert editor.word_is_timed(editor.words[0]) is False

    def test_timings_without_confidence(self, editor):
        editor.load_words({"version": 1, "words": [{"t": "Hej", "s": 0.0, "e": 0.5}]})

        assert len(editor.words) == 1
        assert editor.has_confidence is False
        assert editor.flagged_word_count() == 0

    def test_words_are_sorted_by_start_time(self, editor):
        editor.load_words(
            {
                "version": 1,
                "words": [
                    {"t": "b", "s": 1.0, "e": 1.5},
                    {"t": "a", "s": 0.0, "e": 0.5},
                ],
            }
        )

        assert [word["t"] for word in editor.words] == ["a", "b"]


class TestWordLookup:
    """
    Mapping words onto captions by time.
    """

    def test_caption_words(self, editor):
        editor.load_words(PAYLOAD)

        assert [word["t"] for word in editor.caption_words(caption())] == [
            "Hej",
            "på",
            "dig",
            "idag",
        ]

    def test_range_excludes_words_outside_it(self, editor):
        editor.load_words(PAYLOAD)

        assert [word["t"] for word in editor.words_in_range(0.0, 1.0)] == ["Hej", "på"]

    def test_range_is_empty_without_word_data(self, editor):
        assert editor.words_in_range(0.0, 10.0) == []

    def test_caption_words_carry_their_scores(self, editor):
        editor.load_words(PAYLOAD)

        assert [word["c"] for word in editor.caption_words(caption())] == [
            0.99,
            0.15,
            0.95,
            0.70,
        ]


class TestCaptionsDivideTheRecording:
    """
    A word's own timing cannot be relied on to sit inside the segment it was
    transcribed in. Reported from a real recording: whisper dated a segment from
    2.32 and that segment's first word from 0.00, reaching back into the silence
    before it. Matching each caption only against its own range left that word
    claimed by nobody.
    """

    # The numbers are the ones that were reported.
    REPORTED = {
        "version": 1,
        "words": [
            {"t": "Ja,", "s": 0.0, "e": 1.62, "c": 0.686},
            {"t": "tack", "s": 2.96, "e": 4.08, "c": 0.421},
            {"t": "för", "s": 4.08, "e": 4.32, "c": 0.604},
            {"t": "inbjudan.", "s": 4.32, "e": 5.08, "c": 0.946},
            {"t": "Jag", "s": 5.14, "e": 5.2, "c": 0.726},
            {"t": "ska", "s": 5.2, "e": 5.4, "c": 0.538},
        ],
    }

    @pytest.fixture
    def reported(self, editor):
        editor.load_words(self.REPORTED)
        editor.captions = [
            SRTCaption(1, "00:00:02,320", "00:00:05,100", "Ja, tack för inbjudan."),
            SRTCaption(2, "00:00:05,140", "00:00:13,220", "Jag ska"),
        ]

        return editor

    def test_a_word_timed_before_its_caption_is_still_claimed(self, reported):
        assert [word["t"] for word in reported.caption_words(reported.captions[0])] == [
            "Ja,", "tack", "för", "inbjudan.",
        ]

    def test_the_next_caption_does_not_take_it_as_well(self, reported):
        assert [word["t"] for word in reported.caption_words(reported.captions[1])] == [
            "Jag", "ska",
        ]

    def test_every_word_is_claimed_exactly_once(self, reported):
        claimed = [
            word["t"]
            for caption in reported.captions
            for word in reported.caption_words(caption)
        ]

        assert sorted(claimed) == sorted(word["t"] for word in reported.words)

    def test_it_aligns_and_so_is_not_taken_for_an_edit(self, reported):
        aligned = reported.aligned_words(reported.captions[0])

        assert all(word is not None for word in aligned)

    def test_it_can_be_flagged_for_review_again(self, reported):
        """
        A word no caption claimed could never be marked, whatever its score.
        """

        reported.show_uncertain_words = True
        reported.set_review_sensitivity("high")
        caption = reported.captions[0]

        assert "Ja," in [
            run["t"] for run in reported.review_runs(caption, caption.text)
            if run["flag"]
        ]

    def test_the_last_caption_claims_what_trails_off_the_end(self, reported):
        """
        A word can drift past its segment as well as before it.
        """

        reported.load_words({"version": 1, "words": [
            {"t": "Ja,", "s": 0.0, "e": 1.0},
            {"t": "slut", "s": 30.0, "e": 31.0},
        ]})

        assert [word["t"] for word in reported.caption_words(reported.captions[1])] == [
            "slut"
        ]

    def test_a_caption_of_its_own_still_answers_for_its_own_range(self, editor):
        """
        Nothing to bound it against, so it behaves as it always did.
        """

        editor.load_words(self.REPORTED)
        loose = SRTCaption(1, "00:00:02,320", "00:00:05,100", "Ja, tack för inbjudan.")

        assert [word["t"] for word in editor.caption_words(loose)] == [
            "tack", "för", "inbjudan.",
        ]


class TestSplitAtCursor:
    """
    Splitting a caption where the caret sits.
    """

    def test_splits_text_at_the_cursor(self, editor):
        editor.load_words(PAYLOAD)
        target = caption()
        editor.captions = [target]

        editor.split_caption(target, cursor_position=len("Hej på "), text=TEXT)

        assert [c.text for c in editor.captions] == ["Hej på", "dig idag"]

    def test_uses_the_silence_between_words(self, editor):
        editor.load_words(PAYLOAD)
        target = caption()
        editor.captions = [target]

        editor.split_caption(target, cursor_position=len("Hej på "), text=TEXT)

        first, second = editor.captions

        # "på" ends at 0.8 and "dig" starts at 1.0.
        assert first.get_end_seconds() == pytest.approx(0.9)
        assert first.end_time == second.start_time
        assert second.get_end_seconds() == pytest.approx(4.0)

    def test_keeps_uncommitted_edits(self, editor):
        editor.load_words(PAYLOAD)
        target = caption()
        editor.captions = [target]

        editor.split_caption(target, cursor_position=8, text="Hej PAA dig idag")

        assert [c.text for c in editor.captions] == ["Hej PAA", "dig idag"]

    @pytest.mark.parametrize("position", [0, len(TEXT), 99, -3, None])
    def test_never_produces_an_empty_caption(self, editor, position):
        editor.load_words(PAYLOAD)
        target = caption()
        editor.captions = [target]

        editor.split_caption(target, cursor_position=position, text=TEXT)

        assert all(c.text.strip() for c in editor.captions)

    def test_falls_back_to_proportional_without_word_data(self, editor):
        target = caption()
        editor.captions = [target]

        editor.split_caption(target, cursor_position=len("Hej på "), text=TEXT)

        first = editor.captions[0]

        assert 0.0 < first.get_end_seconds() < 4.0


class TestSplitWithoutCursor:
    """
    The pre-existing split behaviour, which results without word timings and
    callers that pass no caret position still rely on.
    """

    def test_single_line_is_halved(self, editor):
        target = caption()
        editor.captions = [target]

        editor.split_caption(target)

        first, second = editor.captions

        assert (first.text, second.text) == ("Hej på", "dig idag")
        assert first.get_end_seconds() == pytest.approx(2.0)

    def test_multi_line_splits_on_the_line_break(self, editor):
        target = caption("line one\nline two")
        editor.captions = [target]

        editor.split_caption(target)

        assert [c.text for c in editor.captions] == ["line one", "line two"]
        assert editor.captions[0].get_end_seconds() == pytest.approx(2.0)


class TestReviewMarking:
    """
    Marking of words worth reviewing, and the flagged counter.
    """

    def test_low_sensitivity_flags_only_the_least_confident(self, editor):
        editor.load_words(PAYLOAD)
        editor.captions = [caption()]

        assert editor.review_sensitivity == "low"
        # Only "på" at 0.15 sits below the low threshold of 0.25.
        assert editor.flagged_word_count() == 1

    def test_raising_sensitivity_flags_strictly_more(self, editor):
        editor.load_words(PAYLOAD)
        editor.captions = [caption()]

        counts = []

        for sensitivity in ("low", "medium", "high"):
            editor.set_review_sensitivity(sensitivity)
            counts.append(editor.flagged_word_count())

        assert counts == sorted(counts), counts
        assert counts[0] < counts[-1], "high must flag more than low"

    def test_unknown_sensitivity_is_ignored(self, editor):
        editor.load_words(PAYLOAD)

        editor.set_review_sensitivity("nonsense")

        assert editor.review_sensitivity == "low"

    def test_marks_flagged_words_only(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        html = editor.get_review_html(caption())

        # "på" (0.15) is flagged at low sensitivity; the rest are not.
        assert html.count('class="review-word"') == 1
        assert ">på<" in html

    def test_every_marking_is_identical(self, editor):
        """
        The score is not precise enough to grade flagged words against each
        other, so they must all look and read the same.
        """

        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True
        editor.set_review_sensitivity("high")

        html = editor.get_review_html(caption())
        markings = re.findall(r'<span class="([^"]*)"', html)

        assert len(markings) > 1
        assert set(markings) == {"review-word"}
        assert html.count("This word may need review") == 2 * len(markings)

    def test_no_marking_when_nothing_is_flagged(self, editor):
        editor.load_words(
            {"version": 1, "words": [{"t": "Hej", "s": 0.0, "e": 0.5, "c": 0.99}]}
        )
        editor.show_uncertain_words = True

        assert editor.get_review_html(caption("Hej")) is None

    def test_no_marking_without_confidence_scores(self, editor):
        editor.load_words({"version": 1, "words": [{"t": "Hej", "s": 0.0, "e": 0.5}]})
        editor.show_uncertain_words = True

        assert editor.get_review_html(caption("Hej")) is None
        assert editor.flagged_word_count() == 0

    def test_shared_tooltip_carries_no_score(self, editor):
        """
        One message for every flagged word, and never a raw number.
        """

        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        html = editor.get_review_html(caption())

        assert "title=" not in html
        assert 'data-review="This word may need review"' in html
        assert 'aria-label="This word may need review"' in html
        assert "%" not in html
        assert "0.15" not in html

    def test_escapes_caption_text(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        html = editor.get_review_html(caption("Hej på <b>dig</b> idag"))

        assert "<b>" not in html
        assert "&lt;b&gt;" in html

    def test_keeps_line_breaks(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        html = editor.get_review_html(caption("Hej på\ndig idag"))

        assert "<br>" in html

    def test_counter_reports_zero_while_switched_off(self, editor):
        editor.load_words(PAYLOAD)

        class Label:
            text = None

            def set_text(self, value):
                self.text = value

        editor.captions = [caption()]
        label = Label()
        editor.set_flagged_count_element(label)

        assert label.text == "0 flagged", "off by default, so nothing is flagged"

        editor.set_show_uncertain_words(True)

        assert label.text == "1 flagged"

        editor.set_show_uncertain_words(False)

        assert label.text == "0 flagged"

    def test_counter_follows_sensitivity(self, editor):
        editor.load_words(PAYLOAD)

        class Label:
            text = None

            def set_text(self, value):
                self.text = value

        editor.captions = [caption()]
        label = Label()
        editor.set_flagged_count_element(label)
        editor.set_show_uncertain_words(True)
        editor.set_review_sensitivity("high")

        assert label.text == f"{editor.flagged_word_count()} flagged"


class TestPersistedReviewState:
    """
    Review preferences survive a reload via app.storage.user.
    """

    def test_restores_both_preferences(self, editor):
        editor.restore_review_state(True, "high")

        assert editor.show_uncertain_words is True
        assert editor.review_sensitivity == "high"

    @pytest.mark.parametrize("stored", ["", None, "HIGH", "medium ", 3, "nonsense"])
    def test_unrecognised_sensitivity_falls_back_to_the_default(self, editor, stored):
        """
        A value left by an older editor must not silently flag nothing.
        """

        editor.restore_review_state(True, stored)

        assert editor.review_sensitivity == DEFAULT_REVIEW_SENSITIVITY

    @pytest.mark.parametrize("stored", [None, "", 0, "no"])
    def test_show_flag_is_coerced(self, editor, stored):
        editor.restore_review_state(stored, "low")

        assert editor.show_uncertain_words is bool(stored)

    def test_restoring_does_not_touch_the_caption_list(self, editor):
        """
        Runs before the first render, so it must not refresh anything.
        """

        def explode(*args, **kwargs):
            raise AssertionError("restore must not refresh the display")

        editor.refresh_display = explode

        editor.restore_review_state(True, "high")

    def test_restored_state_drives_the_markup(self, editor):
        editor.load_words(PAYLOAD)
        editor.captions = [caption()]
        editor.restore_review_state(True, "high")

        html = editor.get_review_html(caption())

        assert html is not None
        assert html.count('class="review-word"') == editor.flagged_word_count()


class TestMarkingSurvivesEditing:
    """
    The marking must describe the text on screen, not the text the model
    originally produced. Both cases here were reported as bugs.
    """

    def marked(self, editor, text):
        """Words actually marked in a caption, in order."""
        editor.show_uncertain_words = True
        html = editor.get_review_html(caption(text))

        return re.findall(r'aria-label="[^"]*">([^<]*)</span>', html or "")

    def test_editing_a_flagged_word_clears_its_score(self, editor):
        """
        "på" is flagged; replacing it must not leave the flag on whatever the
        user typed instead -- that score described a different word.
        """

        editor.load_words(PAYLOAD)

        assert self.marked(editor, TEXT) == ["på"]
        assert self.marked(editor, "Hej två dig idag") == []

    def test_inserting_a_word_does_not_shift_the_marking(self, editor):
        """
        Inserting a word must not push the flag onto its neighbour.
        """

        editor.load_words(PAYLOAD)

        # "på" stays flagged; the inserted word takes no flag of its own.
        assert self.marked(editor, "Hej på nytt dig idag") == ["på"]
        assert self.marked(editor, "helt Hej på dig idag") == ["på"]

    def test_deleting_a_word_keeps_the_rest_aligned(self, editor):
        editor.load_words(PAYLOAD)

        assert self.marked(editor, "Hej på idag") == ["på"]

    def test_recasing_and_punctuation_keep_the_score(self, editor):
        """
        Only the word itself decides the match, so tidying punctuation or
        capitalisation must not silently drop a flag.
        """

        editor.load_words(PAYLOAD)

        assert self.marked(editor, "Hej På, dig idag") == ["På,"]

    def test_rewriting_the_caption_entirely_flags_nothing(self, editor):
        editor.load_words(PAYLOAD)

        assert self.marked(editor, "helt annan text här") == []

    def test_count_drops_when_a_flagged_word_is_fixed(self, editor):
        editor.load_words(PAYLOAD)
        editor.captions = [caption(TEXT)]

        assert editor.flagged_word_count() == 1

        editor.captions = [caption("Hej två dig idag")]

        assert editor.flagged_word_count() == 0

    def test_repeated_words_stay_aligned(self, editor):
        """
        SequenceMatcher's autojunk heuristic drops frequently repeated
        elements; it must stay off or repeated words lose their scores.
        """

        editor.load_words(
            {
                "version": 1,
                "words": [
                    {"t": "ja", "s": i * 0.01, "e": i * 0.01 + 0.005, "c": 0.10}
                    for i in range(300)
                ],
            }
        )

        text = " ".join(["ja"] * 300)
        words = editor.aligned_words(caption(text))

        assert all(word and word["c"] == 0.10 for word in words), (
            "alignment dropped words"
        )


class TestPersistedAutoscroll:
    """
    Autoscroll survives a reload, like the review preferences.
    """

    @pytest.mark.parametrize("stored", [True, False])
    def test_restores_the_stored_value(self, editor, stored):
        editor.set_autoscroll(stored)

        assert editor.autoscroll is stored

    @pytest.mark.parametrize("stored", [None, "", 0, 1, "yes"])
    def test_coerces_whatever_was_stored(self, editor, stored):
        """
        The value arrives straight from storage, so it may be any JSON type.
        """

        editor.set_autoscroll(stored)

        assert editor.autoscroll is bool(stored)


class TestReviewBackdrop:
    """
    The highlight layer painted behind an open caption text area.
    """

    def test_mirrors_the_text_exactly(self, editor):
        """
        The layer has to hold the same characters as the text area, or the
        highlight boxes drift off their words.
        """

        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        html = editor.review_backdrop_html(caption(), TEXT)
        stripped = re.sub(r"<[^>]+>", "", html)

        assert stripped == TEXT

    def test_marks_the_flagged_word(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        assert 'class="review-word"' in editor.review_backdrop_html(caption(), TEXT)

    def test_returns_markup_even_with_nothing_flagged(self, editor):
        """
        get_review_html returns None when nothing is marked; the layer cannot,
        or it would stop mirroring the text area.
        """

        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        assert editor.review_backdrop_html(caption(), "helt annan text") != ""
        assert editor.get_review_html(caption(), "helt annan text") is None

    def test_returns_markup_with_the_toggle_off(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = False

        html = editor.review_backdrop_html(caption(), TEXT)

        assert "review-word" not in html
        assert re.sub(r"<[^>]+>", "", html) == TEXT

    def test_tracks_uncommitted_text(self, editor):
        """
        Typing repaints the layer from the live value, before the caption has
        been updated.
        """

        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True
        target = caption()

        assert "review-word" in editor.review_backdrop_html(target, TEXT)
        # Same caption object, but the word has been typed over.
        assert "review-word" not in editor.review_backdrop_html(
            target, "Hej TVÅ dig idag"
        )

    def test_escapes_the_text(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        html = editor.review_backdrop_html(caption(), "Hej <b>på</b> dig")

        assert "<b>" not in html
        assert "&lt;b&gt;" in html

    def test_trailing_newline_keeps_a_line_box(self, editor):
        """
        A text area shows an empty last line for a trailing newline; without
        this the layer is one line short and every box below shifts up.
        """

        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        assert editor.review_backdrop_html(caption(), "Hej\n").endswith("<br>")


class TestReviewRuns:
    """
    The transcription editor renders the marking itself, from runs rather than
    from markup, so the runs have to reconstruct the text exactly.
    """

    def joined(self, runs):
        return "".join(run["t"] for run in runs)

    def test_runs_reconstruct_the_text(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        assert self.joined(editor.review_runs(caption())) == TEXT

    def test_flagged_word_is_its_own_run(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        runs = editor.review_runs(caption())
        flagged = [run["t"] for run in runs if run["flag"]]

        assert flagged == ["på"]

    def test_unflagged_text_is_merged(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        runs = editor.review_runs(caption())

        assert runs == [
            {"t": "Hej ", "flag": False},
            {"t": "på", "flag": True},
            {"t": " dig idag", "flag": False},
        ]

    def test_whitespace_is_preserved(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        assert self.joined(editor.review_runs(caption("Hej på\ndig  idag"))) == (
            "Hej på\ndig  idag"
        )

    def test_toggle_off_gives_one_unflagged_run(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = False

        assert editor.review_runs(caption()) == [{"t": TEXT, "flag": False}]

    def test_empty_text(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        assert editor.review_runs(caption("")) == []

    def test_tracks_uncommitted_text(self, editor):
        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        runs = editor.review_runs(caption(), "Hej TVÅ dig idag")

        assert not any(run["flag"] for run in runs)
        assert self.joined(runs) == "Hej TVÅ dig idag"


class TestRenderOverride:
    """
    One editor draws every caption now, whichever format is open. Everything
    that changes the captions funnels through refresh_display, which only
    ever forwards to it -- there is no separate caption renderer to redirect
    away from any more.
    """

    @pytest.fixture
    def live(self):
        """
        An editor with the real refresh_display, which the shared fixture
        stubs out. These tests are about what refresh_display does.
        """

        editor = SRTEditor("job-uuid", "txt", "file.txt")
        editor.save_state_for_undo = lambda *a, **k: None
        editor.mark_as_changed = lambda *a, **k: None
        editor.update_words_per_minute = lambda *a, **k: None

        return editor

    def test_forwards_to_the_document_editor_when_built(self, live):
        calls = []
        live.render_override = lambda: calls.append("document")

        live.refresh_display(force_full_refresh=True)

        assert calls == ["document"]

    def test_does_nothing_before_the_editor_is_built(self, live):
        # render_override is still None at this point -- refresh_display is
        # called this early by some setup paths, and must not raise.
        assert live.render_override is None

        live.refresh_display(force_full_refresh=True)

    def test_toggling_uncertain_words_redraws_the_document(self, live):
        calls = []
        live.render_override = lambda: calls.append("document")

        live.set_show_uncertain_words(True)

        assert calls == ["document"]

    def test_sensitivity_change_redraws_the_document(self, live):
        calls = []
        live.show_uncertain_words = True
        live.render_override = lambda: calls.append("document")

        live.set_review_sensitivity("high")

        assert calls == ["document"]

    def test_split_and_merge_redraw_the_document(self, live):
        live.captions = [
            SRTCaption(1, "00:00:00,000", "00:00:02,000", "ett tva tre fyra"),
            SRTCaption(2, "00:00:02,000", "00:00:04,000", "fem sex sju"),
        ]
        calls = []
        live.render_override = lambda: calls.append("document")

        live.split_caption(live.captions[0])
        live.merge_with_next(live.captions[0])

        assert calls == ["document", "document"]

class TestWordHighlightRuns:
    """
    Following the audio word by word needs one run per word, carrying its
    timing. Merged runs cannot be highlighted individually.
    """

    def test_every_word_becomes_its_own_run(self, editor):
        editor.load_words(PAYLOAD)

        runs = editor.review_runs(caption(), per_word=True)
        words = [run["t"] for run in runs if run["t"].strip()]

        assert words == ["Hej", "på", "dig", "idag"]

    def test_words_carry_their_timings(self, editor):
        editor.load_words(PAYLOAD)

        runs = editor.review_runs(caption(), per_word=True)
        timed = [(run["t"], run["s"], run["e"]) for run in runs if "s" in run]

        assert timed == [
            ("Hej", 0.0, 0.5),
            ("på", 0.6, 0.8),
            ("dig", 1.0, 1.4),
            ("idag", 3.0, 3.6),
        ]

    def test_reconstructs_the_text(self, editor):
        editor.load_words(PAYLOAD)

        runs = editor.review_runs(caption(), per_word=True)

        assert "".join(run["t"] for run in runs) == TEXT

    def test_edited_word_gets_no_timing(self, editor):
        """
        An edited word has no timing we can attribute to it, so it is simply
        never highlighted rather than borrowing its neighbour's.
        """

        editor.load_words(PAYLOAD)

        runs = editor.review_runs(caption(), "Hej TVÅ dig idag", per_word=True)
        timings = {run["t"]: run.get("s") for run in runs if run["t"].strip()}

        assert timings["TVÅ"] is None
        assert timings["dig"] == 1.0, "the others stay aligned"

    def test_review_toggle_still_governs_flags(self, editor):
        editor.load_words(PAYLOAD)

        editor.show_uncertain_words = False
        assert not any(
            run["flag"] for run in editor.review_runs(caption(), per_word=True)
        )

        editor.show_uncertain_words = True
        assert any(
            run["flag"] for run in editor.review_runs(caption(), per_word=True)
        )

    def test_merged_runs_are_unchanged_by_default(self, editor):
        """
        One element per word is only paid for when it is asked for.
        """

        editor.load_words(PAYLOAD)
        editor.show_uncertain_words = True

        assert editor.review_runs(caption()) == [
            {"t": "Hej ", "flag": False},
            {"t": "på", "flag": True},
            {"t": " dig idag", "flag": False},
        ]

    @pytest.mark.parametrize("stored", [None, "", 0, 1, "yes"])
    def test_stored_preference_is_coerced(self, editor, stored):
        editor.set_highlight_word(stored)

        assert editor.highlight_word is bool(stored)


class TestSplitAtBlockEdges:
    """
    A caret at the very start or end of a block has nothing on one side of it.
    Falling back to the halfway split there breaks a word the user never asked
    to touch -- pressing Enter after a one word block turned "Hej" into
    "He" / "j".
    """

    @pytest.fixture
    def live(self):
        editor = SRTEditor("job-uuid", "txt", "file.txt")
        for name in ("refresh_display", "update_words_per_minute",
                     "save_state_for_undo", "mark_as_changed"):
            setattr(editor, name, lambda *a, **k: None)

        return editor

    def block(self, live, text="Hej"):
        target = SRTCaption(1, "00:00:00,000", "00:00:02,000", text)
        live.captions = [target]

        return target

    @pytest.mark.parametrize("position", [0, 3, 99, -2])
    def test_edge_caret_leaves_the_block_whole(self, live, position):
        target = self.block(live)

        live.split_caption(target, cursor_position=position)

        assert [c.text for c in live.captions] == ["Hej"]

    def test_trailing_space_still_counts_as_the_edge(self, live):
        target = self.block(live, "Hej ")

        live.split_caption(target, cursor_position=4)

        assert len(live.captions) == 1

    def test_caret_inside_a_word_still_splits(self, live):
        """
        Deliberate, so it is honoured: the caret says where.
        """

        target = self.block(live)

        live.split_caption(target, cursor_position=1)

        assert [c.text for c in live.captions] == ["H", "ej"]

    def test_no_caret_still_halves(self, live):
        """
        The Split button and results without word data rely on this.
        """

        target = self.block(live)

        live.split_caption(target)

        assert [c.text for c in live.captions] == ["H", "ej"]

    def test_refused_split_keeps_uncommitted_typing(self, live):
        target = self.block(live)

        live.split_caption(target, cursor_position=6, text="Hejsan")

        assert [c.text for c in live.captions] == ["Hejsan"]

    def test_refused_split_saves_no_undo_state(self, live):
        """
        Enter at the end of a block is easy to hit repeatedly; it should not
        fill the undo stack with states that changed nothing.
        """

        saved = []
        live.save_state_for_undo = lambda: saved.append(True)
        target = self.block(live)

        live.split_caption(target, cursor_position=3)

        assert saved == []


class TestShortcutScope:
    """
    There is one editor now, for both formats, and one key handler. What
    remains bound is the conventional file, history, search and playback set.
    Every editing operation was dropped: each duplicated a gesture the
    document editor already provides on its own (Enter to split,
    Backspace/Delete to merge, a click to delete a caption outright), and with
    ignore=[] they fired while the reader was typing.
    """

    @pytest.fixture
    def live(self):
        editor = SRTEditor("job-uuid", "txt", "file.txt")
        for name in ("update_words_per_minute", "save_state_for_undo",
                     "mark_as_changed"):
            setattr(editor, name, lambda *a, **k: None)
        editor.captions = [
            SRTCaption(1, "00:00:00,000", "00:00:02,000", "ett tva"),
            SRTCaption(2, "00:00:02,000", "00:00:04,000", "tre fyra"),
        ]
        editor.refresh_display = lambda *a, **k: None

        return editor

    def press(self, editor, key, **modifiers):
        """Feed one keydown through the real handler."""
        import asyncio
        from types import SimpleNamespace

        flags = {"ctrl": False, "meta": False, "shift": False, "alt": False}
        flags.update(modifiers)
        asyncio.run(editor.handle_key_event(SimpleNamespace(
            key=key,
            action=SimpleNamespace(keydown=True),
            modifiers=SimpleNamespace(**flags),
        )))

    @pytest.mark.parametrize(
        "key,modifiers",
        [
            ("m", {"ctrl": True}),                     # merge next
            ("M", {"ctrl": True}),                     # merge previous
            ("d", {"ctrl": True}),                     # delete caption
            ("Enter", {"ctrl": True}),                 # split
            ("Enter", {"meta": True}),                 # split
            ("Enter", {"ctrl": True, "shift": True}),  # add caption
            ("V", {"ctrl": True, "shift": True}),      # validate
            ("ArrowDown", {"alt": True}),              # next caption
            ("ArrowUp", {"alt": True}),                # previous caption
            ("ArrowUp", {"ctrl": True}),               # move word up
            ("ArrowDown", {"ctrl": True}),             # move word down
            ("ArrowUp", {"meta": True}),               # move word up
            ("ArrowDown", {"meta": True}),             # move word down
        ],
    )
    def test_no_editing_shortcut_changes_anything(self, live, key, modifiers):
        """
        None of these are bound any more, in either editor. Pressing them must
        leave the captions exactly as they were.
        """

        live.selected_caption = live.captions[0]
        before = [(c.text, c.start_time, c.end_time) for c in live.captions]

        self.press(live, key, **modifiers)

        assert [(c.text, c.start_time, c.end_time) for c in live.captions] == before

    def test_shared_shortcuts_fire_in_both_editors(self, live):
        saved = []
        live.save_srt_changes = lambda: saved.append(True)

        self.press(live, "s", ctrl=True)
        live.render_override = lambda: None
        self.press(live, "s", meta=True)

        assert saved == [True, True]

    def test_undo_and_redo_still_fire(self, live):
        calls = []
        live.undo = lambda: calls.append("undo")
        live.redo = lambda: calls.append("redo")

        self.press(live, "z", ctrl=True)
        self.press(live, "y", ctrl=True)
        self.press(live, "z", meta=True, shift=True)

        assert calls == ["undo", "redo", "redo"]

    def test_find_works_whichever_format_is_open(self, live):
        opened = []
        live.create_search_panel = lambda **kwargs: opened.append(True)

        self.press(live, "f", ctrl=True)
        live.render_override = lambda: None
        self.press(live, "f", ctrl=True)

        assert opened == [True, True]

    def test_no_selection_does_not_raise(self, live, monkeypatch):
        # Escape reaches for the browser, which is not here.
        monkeypatch.setattr("utils.srt.ui.run_javascript", lambda *a, **k: None)
        live.create_search_panel = lambda **kwargs: None
        live.save_srt_changes = lambda: None
        live.selected_caption = None

        for key, mods in (("Escape", {}), ("s", {"ctrl": True}), ("f", {"ctrl": True})):
            self.press(live, key, **mods)

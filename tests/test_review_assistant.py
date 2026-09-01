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
The review assistant (SUNET/scribe-ui#74): what it proposes, what it does
when a proposal is accepted, and -- most of all -- what it refuses to do on
its own.

The rule underneath every test here is that this is a review tool and not
an editor. Nothing reaches the captions that the reader has not pressed
Accept on, and nothing is saved.
"""

import pytest

from utils.caption import SRTCaption
from utils.review_assistant import (
    CONTEXT_CHARS,
    DRAG_SCRIPT,
    MAX_SUGGESTIONS,
    ReviewAssistant,
    Suggestion,
    apply_suggestion,
    excerpt,
    matching_captions,
    occurrences,
    parse_suggestions,
    read_domain_code,
)
from utils.srt import SRTEditor


def caption(index: int, text: str) -> SRTCaption:
    return SRTCaption(
        index=index,
        start_time=f"00:00:{index:02d},000",
        end_time=f"00:00:{index + 1:02d},000",
        text=text,
        speaker="Speaker 1",
    )


@pytest.fixture
def editor() -> SRTEditor:
    editor = SRTEditor("job-uuid", "txt", "lecture.mp4")

    # Drawing needs a running client; the undo history deliberately does
    # not, and it is what these tests are about.
    editor.refresh_display = lambda *a, **k: None
    editor.update_words_per_minute = lambda *a, **k: None
    editor.update_beforeunload_state = lambda *a, **k: None
    editor._update_undo_redo_buttons = lambda *a, **k: None

    editor.captions = [
        caption(1, "The patient was given a dos of the medicine."),
        caption(2, "Doctor Lindquist examined the patient again."),
        caption(3, "Doctor Lindqvist wrote the referral that afternoon."),
    ]

    return editor


class TestReadingWhatCameBack:
    """
    JSON Lines, because the answer arrives in pieces and one bad line should
    cost one suggestion rather than all of them.
    """

    def test_one_object_per_line(self):
        found = parse_suggestions(
            '{"find": "dos", "replace": "dos", "kind": "terminology"}\n'
            '{"find": "Lindquist", "replace": "Lindqvist", "kind": "name", '
            '"why": "Namnet stavas olika."}\n'
        )

        # The first is dropped: a suggestion that changes nothing is not a
        # suggestion.
        assert len(found) == 1
        assert found[0].find == "Lindquist"
        assert found[0].replace == "Lindqvist"
        assert found[0].why == "Namnet stavas olika."
        assert found[0].kind_label == "Name"

    def test_a_broken_line_costs_only_itself(self):
        found = parse_suggestions(
            "Here are my suggestions:\n"
            '{"find": "dos", "replace": "dose"}\n'
            "{not json at all}\n"
            '{"find": "referral", "replace": "referral letter"}\n'
        )

        assert [entry.find for entry in found] == ["dos", "referral"]

    def test_a_numbered_or_bulleted_line_is_still_read(self):
        found = parse_suggestions('- {"find": "dos", "replace": "dose"}')

        assert [entry.find for entry in found] == ["dos"]

    def test_an_answer_with_nothing_in_it_is_not_an_error(self):
        assert parse_suggestions("") == []
        assert parse_suggestions("The transcript looks fine to me.") == []

    def test_a_model_that_will_not_stop_is_cut_off(self):
        answer = "\n".join(
            '{"find": "word%d", "replace": "term%d"}' % (n, n) for n in range(200)
        )

        assert len(parse_suggestions(answer)) == MAX_SUGGESTIONS

    def test_an_unknown_kind_still_gets_a_label(self):
        found = parse_suggestions('{"find": "a", "replace": "b", "kind": "banana"}')

        assert found[0].kind_label == "Suggestion"


class TestFindingTheText:
    """
    A suggestion carries the exact text it replaces, and it has to be found
    the way a reader would read it -- as words, not as a substring.
    """

    def test_a_word_is_not_found_inside_another(self, editor):
        editor.captions = [caption(1, "The dosering was written down.")]

        assert occurrences(editor.captions, "dos") == 0

    def test_every_place_is_counted(self, editor):
        editor.captions = [caption(1, "dos and dos"), caption(2, "another dos")]

        assert occurrences(editor.captions, "dos") == 3
        assert len(matching_captions(editor.captions, "dos")) == 2

    def test_a_phrase_ending_in_punctuation_still_matches(self, editor):
        editor.captions = [caption(1, "He said (roughly): the dose.")]

        assert occurrences(editor.captions, "(roughly):") == 1


class TestAccepting:
    """
    The only thing that changes a caption. One press, one undo step.
    """

    def test_it_changes_every_place_the_text_appears(self, editor):
        changed = apply_suggestion(
            editor, Suggestion(find="Lindquist", replace="Lindqvist")
        )

        assert changed == 1
        assert "Lindqvist" in editor.captions[1].text
        assert "Lindquist" not in editor.captions[1].text

    def test_one_decision_is_one_undo_step(self, editor):
        editor.captions = [caption(1, "dos here"), caption(2, "dos there")]
        before = [entry.text for entry in editor.captions]

        apply_suggestion(editor, Suggestion(find="dos", replace="dose"))

        assert [entry.text for entry in editor.captions] == ["dose here", "dose there"]

        editor.undo()

        assert [entry.text for entry in editor.captions] == before

    def test_an_accepted_change_is_marked_as_the_readers_own(self, editor):
        # Accepting is the reader editing the transcription, and the editor
        # marks edited words for exactly that reason.
        apply_suggestion(editor, Suggestion(find="Lindquist", replace="Lindqvist"))

        assert editor.captions[1].edited_words

    def test_a_replacement_is_literal_text(self, editor):
        # It comes from a model, not from a programmer: a backslash or a
        # \\g in it is text, never an instruction to the regular expression
        # engine.
        editor.captions = [caption(1, "the path is here")]

        apply_suggestion(editor, Suggestion(find="path", replace=r"C:\**\g<0>"))

        assert editor.captions[0].text == r"the C:\**\g<0> is here"

    def test_nothing_happens_when_the_text_is_gone(self, editor):
        assert apply_suggestion(editor, Suggestion(find="nowhere", replace="x")) == 0
        assert editor.captions[0].text.startswith("The patient")


class TestReadingTheDomain:
    """
    The codes come from the hub, so extending the list there does not need a
    frontend release.
    """

    codes = ["1.1", "2.1", "2.11", "3.2", "0.2"]

    def test_a_bare_code(self):
        assert read_domain_code("3.2", self.codes) == "3.2"

    def test_a_code_in_a_sentence(self):
        assert read_domain_code("I would say 3.2 here.", self.codes) == "3.2"

    def test_a_longer_code_is_not_read_as_a_shorter_one(self):
        assert read_domain_code("2.11", self.codes) == "2.11"

    def test_a_label_is_not_a_code(self):
        # A model that answered with a label has not answered the question.
        # The reader is shown an empty picker rather than a confident wrong
        # classification.
        assert read_domain_code("Clinical medicine", self.codes) is None
        assert read_domain_code("", self.codes) is None


class TestSteppingThrough:
    """
    Accept, Dismiss and Skip are three different answers, and the issue asks
    for all three: dismissing is a decision and is final, skipping is the
    absence of one and comes round again.
    """

    @pytest.fixture
    def assistant(self, editor, monkeypatch) -> ReviewAssistant:
        monkeypatch.setattr(
            "utils.review_assistant.ui.notify", lambda *a, **k: None
        )
        assistant = ReviewAssistant(editor, language="Swedish")
        assistant.queue = [
            Suggestion(find="Lindquist", replace="Lindqvist"),
            Suggestion(find="dos", replace="dose"),
        ]
        # The dialog is not built in these tests; what is under test is the
        # order decisions are taken in, not how they are drawn.
        assistant._draw_current = lambda: None
        assistant._finish = lambda: setattr(assistant, "finished", True)
        assistant.finished = False

        return assistant

    def test_accepting_applies_and_moves_on(self, assistant, editor):
        assistant._accept()

        assert "Lindqvist" in editor.captions[1].text
        assert assistant.outcome.accepted == 1
        assert assistant._current().find == "dos"

    def test_dismissing_changes_nothing(self, assistant, editor):
        before = [entry.text for entry in editor.captions]

        assistant._dismiss()

        assert [entry.text for entry in editor.captions] == before
        assert assistant.outcome.dismissed == 1
        assert assistant._current().find == "dos"

    def test_a_skipped_suggestion_comes_round_again(self, assistant):
        assistant._skip()

        assert assistant._current().find == "dos"

        assistant._dismiss()

        assert assistant._current().find == "Lindquist"

    def test_skipping_everything_ends_the_review(self, assistant):
        assistant._skip()
        assistant._skip()

        assert assistant.finished is True

    def test_a_suggestion_the_transcription_no_longer_matches_is_dropped(
        self, assistant, editor
    ):
        # Suggestions are written against the transcription as it was when
        # the review started, and accepting one changes it. Offering a
        # later suggestion against text nobody can see is worse than
        # dropping it.
        editor.captions[1].text = "Doctor Lindqvist examined the patient again."

        assert assistant._current().find == "dos"
        assert assistant.outcome.stale == 1

    def test_it_is_not_offered_without_a_domain_list(self, editor):
        assistant = ReviewAssistant(editor, language="Swedish", client=object())

        assert assistant.available is False

        assistant.set_catalogue(
            {
                "domains": [
                    {
                        "code": "3.2",
                        "label": "Clinical medicine",
                        "group": "3",
                        "group_label": "Medical and health sciences",
                    }
                ]
            }
        )

        assert assistant.available is True
        assert (
            assistant.domain_label("3.2")
            == "Medical and health sciences — Clinical medicine"
        )


class TestTheDialogsOwnShape:
    """
    Accept, Dismiss and Skip are pressed dozens of times in a row. Where
    they are, and what colour they are, is part of whether the review can
    be got through at all.
    """

    def css(self) -> str:
        import re

        from utils.styles import default_styles

        return re.sub(r"/\*.*?\*/", "", default_styles, flags=re.S)

    def rule(self, selector: str) -> str:
        import re

        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.css()):
            if selector in [part.strip() for part in match.group(1).split(",")]:
                return match.group(2)

        raise AssertionError(f"no rule for {selector}")

    def test_the_card_does_not_grow_with_the_suggestion(self):
        # A card that resized with a long explanation would move all three
        # buttons out from under the pointer between one suggestion and the
        # next. A long one scrolls inside the box instead.
        body = self.rule(".review-body")

        assert "height: min(19rem, calc(100vh - 12rem))" in body
        assert "overflow-y: auto" in body

    def test_the_spinner_sits_in_the_middle_of_the_card(self):
        # Nothing else is on the card while it is up, and a spinner in the
        # top corner of an empty box reads as a fault rather than as work
        # going on.
        working = self.rule(".review-working")

        assert "justify-content: center" in working
        assert "align-items: center" in working
        assert "min-height: 100%" in working

    def test_the_three_answers_are_not_blue(self):
        # Quasar gives a flat button the primary colour, which here is the
        # brand blue: three blue words in a row read as three links, and
        # Accept is the only one of the three that changes anything.
        for selector in (
            ".body--light .q-btn.review-action",
            ".body--dark .q-btn.review-action",
        ):
            assert "var(--color-text-primary)" in self.rule(selector)

    def test_accept_is_the_one_that_carries_the_brand(self):
        assert "var(--color-brand-primary)" in self.rule(
            ".body--light .q-btn.review-primary"
        )


def test_no_button_in_the_dialog_asks_for_a_colour():
    """
    NiceGUI colours a button "primary" unless told otherwise, and that puts
    Quasar's own text-primary class on it -- which carries !important, so a
    stylesheet rule is not a reliable way to take it back off. Asking for no
    colour leaves the button inheriting the page's text colour, which is
    what these want: three blue words in a row read as three links, and
    Accept is the only one of them that changes the transcription.
    """

    import ast
    from pathlib import Path

    tree = ast.parse(Path("utils/review_assistant.py").read_text())
    buttons = 0

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        target = node.func

        if not (
            isinstance(target, ast.Attribute)
            and target.attr == "button"
            and isinstance(target.value, ast.Name)
            and target.value.id == "ui"
        ):
            continue

        buttons += 1
        colours = [word for word in node.keywords if word.arg == "color"]

        assert colours, "every button in the dialog has to say color=None"
        assert isinstance(colours[0].value, ast.Constant)
        assert colours[0].value.value is None

    assert buttons >= 8


class TestTheSentenceAround:
    """
    "dos" against "dose" cannot be judged on its own: whether it is a
    mishearing or the word the speaker meant is decided by what is around
    it.
    """

    def test_the_match_is_kept_apart_from_its_surroundings(self):
        before, hit, after = excerpt("The dos was too high.", 4, 7)

        assert (before, hit, after) == ("The ", "dos", " was too high.")

    def test_a_long_caption_is_cut_back_on_both_sides(self):
        text = "x" * 400 + " dos " + "y" * 400
        before, hit, after = excerpt(text, 401, 404)

        assert hit == "dos"
        assert before.startswith("…")
        assert after.endswith("…")
        assert len(before) <= CONTEXT_CHARS + 1
        assert len(after) <= CONTEXT_CHARS + 1

    def test_line_breaks_are_flattened(self):
        # One line of a card, not the caption being edited.
        before, hit, after = excerpt("first line\nthe dos here", 15, 18)

        assert "\n" not in before + hit + after
        assert before == "first line the "


class TestArrivingWhileStillGenerating:
    """
    The answer is JSON Lines precisely so a finished line can be read while
    the rest is still being written. A reader should be deciding on the
    first suggestion while the model is still finding the fifth.
    """

    @pytest.fixture
    def assistant(self, editor, monkeypatch) -> ReviewAssistant:
        monkeypatch.setattr(
            "utils.review_assistant.ui.notify", lambda *a, **k: None
        )
        assistant = ReviewAssistant(editor, language="Swedish")
        assistant.drawn = []
        assistant._draw_current = lambda: assistant.drawn.append("card")
        assistant._update_progress = lambda: assistant.drawn.append("count")
        assistant._on_the_page = lambda: __import__("contextlib").nullcontext()
        assistant.streaming = True

        return assistant

    def test_the_first_finished_line_takes_the_spinner_away(self, assistant):
        assistant._collect('{"find": "dos", "replace": "dose"}\n')

        assert [entry.find for entry in assistant.queue] == ["dos"]
        assert assistant.drawn == ["card"]

    def test_a_half_arrived_line_is_not_offered(self, assistant):
        assistant._collect('{"find": "dos", "repl')

        assert assistant.queue == []
        assert assistant.drawn == []

        assistant._collect('ace": "dose"}\n')

        assert [entry.find for entry in assistant.queue] == ["dos"]

    def test_later_suggestions_do_not_redraw_the_card(self, assistant):
        # Redrawing would move what the reader is reading, several times a
        # second while the answer arrives.
        assistant._collect('{"find": "dos", "replace": "dose"}\n')
        assistant.deciding = True
        assistant._collect('{"find": "Lindquist", "replace": "Lindqvist"}\n')

        assert assistant.drawn == ["card", "count"]
        assert len(assistant.queue) == 2

    def test_a_skipped_suggestion_is_not_re_ordered_by_an_arrival(
        self, assistant
    ):
        # The queue is appended to, never rebuilt from the answer: Skip
        # moves a suggestion to the back of this same list, and rebuilding
        # would undo the reader's own decisions.
        assistant._collect('{"find": "dos", "replace": "dose"}\n')
        assistant.deciding = True
        assistant.queue[0].state = "dismissed"
        assistant._collect('{"find": "Lindquist", "replace": "Lindqvist"}\n')

        assert [entry.state for entry in assistant.queue] == [
            "dismissed",
            "pending",
        ]

    def test_the_counter_says_more_are_coming(self, assistant):
        assistant._collect('{"find": "dos", "replace": "dose"}\n')

        assert "still looking" in assistant._progress_text()

        assistant.streaming = False

        assert assistant._progress_text() == "Last suggestion"


class TestGettingOutOfTheWay:
    """
    A suggestion is judged against the transcription it came out of, and the
    card sits over that very text.
    """

    def css(self) -> str:
        import re

        from utils.styles import default_styles

        return re.sub(r"/\*.*?\*/", "", default_styles, flags=re.S)

    def rule(self, selector: str) -> str:
        import re

        for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", self.css()):
            if selector in [part.strip() for part in match.group(1).split(",")]:
                return match.group(2)

        raise AssertionError(f"no rule for {selector}")

    def test_the_page_behind_stays_readable(self):
        # seamless: no backdrop and no scroll lock, so the reader can read
        # the paragraph around the word, scroll, and play the recording
        # again without closing the review and losing their place in it.
        source = open("utils/review_assistant.py").read()

        assert 'ui.dialog().props("persistent seamless")' in source

    def test_the_header_is_the_handle(self):
        header = self.rule(".review-header")

        assert "cursor: move" in header

        # Not the card itself: a drag begun on the excerpt or in the
        # replacement box is a text selection the reader meant.
        assert "cursor: move" not in self.rule(".review-dialog")

    def test_the_close_button_is_not_a_handle(self):
        assert "cursor: pointer" in self.rule(".review-header .q-btn")

    def test_the_card_cannot_be_dragged_off_the_screen(self):
        # One dragged past the bottom could not be dragged back, since the
        # handle went with it.
        assert "window.innerHeight - box.bottom" in DRAG_SCRIPT
        assert "window.innerWidth - box.right" in DRAG_SCRIPT
        assert "clamp" in DRAG_SCRIPT

    def test_the_drag_is_not_a_round_trip_per_pixel(self):
        # The listeners are the page's own, on the window so a fast drag
        # that outruns the header keeps working.
        assert "window.addEventListener('pointermove'" in DRAG_SCRIPT
        assert "handle.addEventListener('pointerdown'" in DRAG_SCRIPT


class TestRewordingASuggestion:
    """
    The replacement is the reader's to change before accepting it. A model
    that heard the wrong word usually heard the right kind of thing, and a
    reader who can see what was meant should not have to dismiss the
    suggestion and go and find the caption to type one word into it.
    """

    @pytest.fixture
    def assistant(self, editor, monkeypatch) -> ReviewAssistant:
        monkeypatch.setattr(
            "utils.review_assistant.ui.notify", lambda *a, **k: None
        )
        assistant = ReviewAssistant(editor, language="Swedish")
        assistant.queue = [Suggestion(find="Lindquist", replace="Lindqvist")]
        assistant._draw_current = lambda: None

        return assistant

    def test_what_the_reader_typed_is_what_is_applied(self, assistant, editor):
        assistant._current().replace = "Lindkvist"

        assistant._accept()

        assert "Lindkvist" in editor.captions[1].text
        assert assistant.outcome.accepted == 1
        assert assistant.outcome.edited == 1

    def test_an_untouched_suggestion_is_not_counted_as_reworded(
        self, assistant, editor
    ):
        assistant._accept()

        assert assistant.outcome.accepted == 1
        assert assistant.outcome.edited == 0

    def test_the_reader_gets_the_spaces_they_meant_and_no_others(
        self, assistant, editor
    ):
        assistant._current().replace = "  Lindkvist  "

        assistant._accept()

        assert "a Lindkvist e" not in editor.captions[1].text
        assert "Doctor Lindkvist examined" in editor.captions[1].text

    def test_an_emptied_replacement_is_never_applied(self, assistant, editor):
        # Emptying the box asks for no change, which is Dismiss -- it must
        # not reach the captions as a deletion nobody asked for.
        before = [entry.text for entry in editor.captions]
        assistant._current().replace = "   "

        assistant._accept()

        assert [entry.text for entry in editor.captions] == before
        assert assistant.outcome.accepted == 0

    def test_typing_the_transcribed_text_back_is_no_change(self, assistant):
        assistant._current().replace = "Lindquist"

        assert assistant._current().applicable is False

    def test_undo_takes_the_reworded_count_back_with_it(self, assistant):
        assistant._current().replace = "Lindkvist"

        assistant._accept()
        assistant._undo()

        assert assistant.outcome.edited == 0
        assert assistant.outcome.accepted == 0


class TestUndoingAnAccept:
    """
    Accepting is one undo step, so the editor's own history is what puts the
    text back. Nothing is remembered in the assistant but which suggestion
    to offer again.
    """

    @pytest.fixture
    def assistant(self, editor, monkeypatch) -> ReviewAssistant:
        monkeypatch.setattr(
            "utils.review_assistant.ui.notify", lambda *a, **k: None
        )
        assistant = ReviewAssistant(editor, language="Swedish")
        assistant.queue = [
            Suggestion(find="Lindquist", replace="Lindqvist"),
            Suggestion(find="dos", replace="dose"),
        ]
        assistant._draw_current = lambda: None

        return assistant

    def test_the_text_goes_back_and_the_suggestion_comes_back(
        self, assistant, editor
    ):
        before = [entry.text for entry in editor.captions]

        assistant._accept()

        assert assistant.last_accepted is not None

        assistant._undo()

        assert [entry.text for entry in editor.captions] == before
        assert assistant.outcome.accepted == 0
        assert assistant.outcome.changed == 0
        assert assistant._current().find == "Lindquist"

    def test_only_the_most_recent_accept_can_be_taken_back(
        self, assistant, editor
    ):
        # Reaching further into the editor's history than the change the
        # assistant made itself would be undoing the reader's own typing.
        assistant._accept()
        assistant._undo()

        assert assistant.last_accepted is None

        assistant._undo()

        assert assistant.outcome.accepted == 0
        assert "Lindquist" in editor.captions[1].text

    def test_dismissing_leaves_nothing_to_undo(self, assistant):
        assistant._dismiss()

        assert assistant.last_accepted is None


def test_a_review_adds_up_what_both_requests_cost(editor, monkeypatch):
    # Two requests behind one review -- the classification and the review
    # itself -- and the reader is told what the pair came to.
    monkeypatch.setattr("utils.review_assistant.ui.notify", lambda *a, **k: None)

    assistant = ReviewAssistant(editor, language="Swedish")
    assistant._draw_domain = lambda: None
    assistant._take_new_suggestions = lambda: None
    assistant._draw_current = lambda: None
    assistant._on_the_page = lambda: __import__("contextlib").nullcontext()

    assistant._domain_ready(
        {"input_tokens": 900, "output_tokens": 4, "gpu_seconds": 0.3}
    )
    assistant._suggestions_ready(
        {"input_tokens": 900, "output_tokens": 300, "gpu_seconds": 6.2}
    )

    assert assistant.spent == {
        "input_tokens": 1800,
        "output_tokens": 304,
        "gpu_seconds": 6.5,
    }

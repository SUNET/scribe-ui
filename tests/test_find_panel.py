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
Find and replace as a card in a deck of its own, behaving as a word
processor's Find does: every occurrence is a match, Replace changes the
current one, closing takes the marks off.
"""

import pathlib

import pytest

from utils.caption import SRTCaption, WordComment
from utils.srt import SRTEditor
from utils.srt_search import utf16_offset

TEXTS = [
    "The cat sat on the mat",
    "A dog and a cat and another cat",
    "Nothing to see here",
    "The end of the cat story",
]


def source(path: str) -> str:
    return pathlib.Path(path).read_text()


def build_editor(monkeypatch):
    monkeypatch.setattr("utils.srt_search.ui.notify", lambda *a, **k: None)

    editor = SRTEditor("job-uuid", "srt", "file.srt")
    for name in (
        "update_flagged_count",
        "update_words_per_minute",
        "mark_as_changed",
        "update_beforeunload_state",
    ):
        setattr(editor, name, lambda *a, **k: None)

    editor.captions = [
        SRTCaption(i + 1, "00:00:00,000", "00:00:04,000", text)
        for i, text in enumerate(TEXTS)
    ]
    editor.marks = []
    editor.on_find_marks = lambda marks, current: editor.marks.append((marks, current))

    return editor


@pytest.fixture
def editor(monkeypatch):
    return build_editor(monkeypatch)


def where(editor):
    """(caption index, start) of every match, in order."""

    return [(i, s) for i, s, _e in editor.search_results]


class TestEveryOccurrenceIsAMatch:
    def test_each_occurrence_is_one_match_in_the_order_of_the_text(self, editor):
        editor.search_captions("cat")

        assert where(editor) == [(1, 4), (2, 12), (2, 28), (4, 15)]
        assert len(editor.search_results) == 4

    def test_a_match_is_where_it_starts_and_ends(self, editor):
        editor.search_captions("cat")

        index, start, end = editor.search_results[0]

        assert editor.captions[0].text[start:end] == "cat"

    def test_case_is_ignored_unless_asked_for(self, editor):
        editor.search_captions("THE")
        assert len(editor.search_results) == 5

        editor.case_sensitive = True
        editor.search_captions("The")
        assert where(editor) == [(1, 0), (4, 0)]

    def test_a_term_is_taken_as_typed_not_as_a_pattern(self, editor):
        editor.captions[2].text = "Is this (it)? Yes."
        editor.search_captions("(it)?")

        assert where(editor) == [(3, 8)]

    def test_a_space_at_the_end_is_part_of_the_term_but_only_spaces_are_no_search(
        self, editor
    ):
        editor.search_captions("cat ")
        assert where(editor) == [(1, 4), (2, 12), (4, 15)]

        editor.search_captions("   ")
        assert editor.search_results == []

    def test_it_starts_from_the_caption_the_reader_is_on(self, editor):
        editor.selected_caption = editor.captions[1]
        editor.search_captions("cat")

        assert editor.current_search_index == 1
        assert editor.search_results[editor.current_search_index][:2] == (2, 12)


class TestSteppingThroughThem:
    def test_next_and_previous_go_round_the_end(self, editor):
        editor.search_captions("cat")
        editor.current_search_index = 0

        editor.navigate_search_results(-1)
        assert editor.current_search_index == 3

        editor.navigate_search_results(1)
        assert editor.current_search_index == 0

    def test_a_second_match_in_the_same_caption_is_still_reached(self, editor):
        """
        select_caption() toggles, so going to a second match in the caption
        already on would have un-selected it and not scrolled.
        """

        scrolled = []
        editor.on_select = scrolled.append
        editor.search_captions("cat")
        editor.current_search_index = 1
        editor.reveal_current()
        editor.current_search_index = 2
        editor.reveal_current()

        assert editor.selected_caption is editor.captions[1]
        assert scrolled[-1] is editor.captions[1]
        assert len(scrolled) >= 2

    def test_nothing_happens_without_matches(self, editor):
        editor.search_captions("zebra")
        editor.navigate_search_results(1)

        assert editor.search_results == []
        assert editor.current_search_index == 0


class TestReplacingTheCurrentMatch:
    def test_only_the_current_occurrence_changes(self, editor):
        editor.search_captions("cat")
        editor.current_search_index = 2  # the second "cat" of the second caption

        editor.replace_in_current_match("fox")

        assert editor.captions[1].text == "A dog and a cat and another fox"
        assert editor.captions[0].text == "The cat sat on the mat"
        assert editor.captions[3].text == "The end of the cat story"

    def test_it_moves_on_to_the_next_match(self, editor):
        editor.search_captions("cat")
        editor.current_search_index = 0

        editor.replace_in_current_match("fox")

        assert editor.captions[0].text == "The fox sat on the mat"
        # Three are left, and the reader is on the first of them.
        assert len(editor.search_results) == 3
        assert editor.search_results[editor.current_search_index][:2] == (2, 12)

    def test_what_was_put_in_is_not_found_again_straight_away(self, editor):
        editor.search_captions("cat")
        editor.current_search_index = 0

        editor.replace_in_current_match("cat cat")

        index, start, _end = editor.search_results[editor.current_search_index]

        assert editor.captions[0].text == "The cat cat sat on the mat"
        # Past both of the new words, not on the first of them.
        assert (index, start) == (2, 12)

    def test_the_last_match_wraps_to_the_first(self, editor):
        editor.search_captions("cat")
        editor.current_search_index = 3

        editor.replace_in_current_match("fox")

        assert editor.search_results[editor.current_search_index][:2] == (1, 4)

    def test_it_is_one_undo_step(self, editor):
        saved = []
        editor.save_state_for_undo = lambda: saved.append(1)
        editor.search_captions("cat")
        editor.replace_in_current_match("fox")

        assert saved == [1]

    def test_replace_all_is_one_undo_step_too(self, editor):
        saved = []
        editor.save_state_for_undo = lambda: saved.append(1)
        editor.search_captions("cat")
        editor.replace_all("fox")

        assert saved == [1]

    def test_with_nothing_found_nothing_is_replaced(self, editor):
        editor.search_captions("zebra")
        editor.replace_in_current_match("fox")

        assert [c.text for c in editor.captions] == TEXTS

    def test_replace_all_still_changes_every_occurrence(self, editor):
        editor.search_captions("cat")
        editor.replace_all("fox")

        assert editor.captions[1].text == "A dog and a fox and another fox"
        assert editor.captions[0].text == "The fox sat on the mat"
        assert editor.captions[3].text == "The end of the fox story"
        assert editor.search_results == []

    def test_replace_all_keeps_the_case_it_is_given(self, editor):
        editor.search_captions("the")
        editor.replace_all("A")

        assert editor.captions[0].text == "A cat sat on A mat"


class TestReplaceIsTheSameAsEditingByHand:
    """
    Replacing a word is the reader changing it, exactly as typing over it is:
    whatever a comment, a highlight or an edit mark does when the word is
    edited in the text, it does when the word is replaced from the card.
    """

    @staticmethod
    def marked(editor):
        # "The cat sat on the mat": words 0..5. A comment on "cat sat", a
        # highlight on "cat sat on", an edit mark on "cat".
        caption = editor.captions[0]
        caption.comments = [WordComment({1, 2}, "check this")]
        caption.highlighted_words = {1, 2, 3}
        caption.edited_words = {1}

        return caption

    @staticmethod
    def state(caption):
        return (
            caption.text,
            [(sorted(c.words), c.text) for c in caption.comments],
            sorted(caption.highlighted_words),
            sorted(caption.edited_words),
        )

    @pytest.mark.parametrize(
        "replacement", ["fox", "Cat", "cat", "red fox", "big red fox", ""]
    )
    def test_a_marked_word_comes_out_as_when_it_is_typed_over(
        self, monkeypatch, replacement
    ):
        replaced = build_editor(monkeypatch)
        by_hand = build_editor(monkeypatch)

        replaced_caption = self.marked(replaced)
        by_hand_caption = self.marked(by_hand)

        replaced.search_captions("cat")
        replaced.current_search_index = 0
        replaced.replace_in_current_match(replacement)

        text = by_hand_caption.text.replace("cat", replacement, 1)
        by_hand.update_caption_text(by_hand_caption, text)

        assert self.state(replaced_caption) == self.state(by_hand_caption)

    @pytest.mark.parametrize("term, replacement", [("The", "A big"), ("mat", "rug"), ("sat", "")])
    def test_a_word_beside_the_marks_comes_out_the_same_too(
        self, monkeypatch, term, replacement
    ):
        replaced = build_editor(monkeypatch)
        by_hand = build_editor(monkeypatch)

        replaced_caption = self.marked(replaced)
        by_hand_caption = self.marked(by_hand)

        replaced.search_captions(term)
        replaced.current_search_index = 0
        replaced.replace_in_current_match(replacement)

        text = by_hand_caption.text.replace(term, replacement, 1)
        by_hand.update_caption_text(by_hand_caption, text)

        assert self.state(replaced_caption) == self.state(by_hand_caption)

    def test_replace_all_comes_out_the_same_as_editing_each_by_hand(self, monkeypatch):
        replaced = build_editor(monkeypatch)
        by_hand = build_editor(monkeypatch)

        replaced_caption = self.marked(replaced)
        by_hand_caption = self.marked(by_hand)

        replaced.search_captions("the")
        replaced.replace_all("a")

        by_hand.update_caption_text(by_hand_caption, "a cat sat on a mat")

        assert self.state(replaced_caption) == self.state(by_hand_caption)

    def test_a_comment_on_a_replaced_word_stays_with_its_replacement(self, editor):
        caption = self.marked(editor)

        editor.search_captions("cat")
        editor.current_search_index = 0
        editor.replace_in_current_match("fox")

        # One word for one: the comment and the highlight stay on it, and
        # it is marked as the reader's own.
        assert [(sorted(c.words), c.text) for c in caption.comments] == [
            ([1, 2], "check this")
        ]
        assert 1 in caption.highlighted_words
        assert 1 in caption.edited_words

    def test_a_comment_whose_words_are_all_replaced_by_nothing_goes(self, editor):
        caption = editor.captions[0]
        caption.comments = [WordComment({1}, "only the cat")]

        editor.search_captions("cat")
        editor.current_search_index = 0
        editor.replace_in_current_match("")

        assert caption.comments == []


class TestSayingWhenCommentsGoWithTheWords:
    """
    Replacing a word with nothing (or with a different number of words, when
    not all of what it replaced was commented) takes its comment with it, as
    deleting the word by hand does. The reader is told afterwards, with Undo
    as the way back, rather than asked first.
    """

    @staticmethod
    def notes(editor, monkeypatch):
        said = []
        monkeypatch.setattr(
            "utils.srt_search.ui.notify",
            lambda message, **kwargs: said.append((message, kwargs.get("type"))),
        )

        return said

    def test_a_replacement_that_keeps_the_comment_says_nothing_about_it(
        self, editor, monkeypatch
    ):
        said = self.notes(editor, monkeypatch)
        editor.captions[0].comments = [WordComment({1}, "note")]

        editor.search_captions("cat")
        editor.current_search_index = 0
        editor.replace_in_current_match("fox")

        assert said == [("Replacement made", "positive")]

    def test_replacing_with_nothing_says_the_comment_went(self, editor, monkeypatch):
        said = self.notes(editor, monkeypatch)
        editor.captions[0].comments = [WordComment({1}, "note")]

        editor.search_captions("cat")
        editor.current_search_index = 0
        editor.replace_in_current_match("")

        assert said == [
            (
                "Replacement made. 1 comment was removed with the replaced text."
                " Undo restores it.",
                "warning",
            )
        ]

    def test_a_comment_that_survives_on_other_words_is_not_counted(
        self, editor, monkeypatch
    ):
        said = self.notes(editor, monkeypatch)
        editor.captions[0].comments = [WordComment({1, 2}, "note")]

        editor.search_captions("cat")
        editor.current_search_index = 0
        editor.replace_in_current_match("")

        assert said == [("Replacement made", "positive")]

    def test_replace_all_counts_every_comment_it_took(self, editor, monkeypatch):
        said = self.notes(editor, monkeypatch)
        editor.captions[0].comments = [WordComment({1}, "one")]
        editor.captions[1].comments = [
            WordComment({4}, "two"),
            WordComment({0}, "kept"),
        ]

        editor.search_captions("cat")
        editor.replace_all("")

        assert said == [
            (
                "Replaced 4 occurrences. 2 comments were removed with the"
                " replaced text. Undo restores them.",
                "warning",
            )
        ]
        assert [c.text for c in editor.captions[1].comments] == ["kept"]

    def test_replace_all_that_loses_nothing_stays_a_plain_message(
        self, editor, monkeypatch
    ):
        said = self.notes(editor, monkeypatch)
        editor.captions[0].comments = [WordComment({1}, "one")]

        editor.search_captions("cat")
        editor.replace_all("fox")

        assert said == [("Replaced 4 occurrences", "positive")]


class TestTheMarksInTheText:
    def test_every_match_is_handed_on_with_where_it_is(self, editor):
        editor.search_captions("cat")

        marks, current = editor.marks[-1]

        assert [(m["id"], m["s"], m["e"]) for m in marks] == [
            (1, 4, 7),
            (2, 12, 15),
            (2, 28, 31),
            (4, 15, 18),
        ]
        assert current == editor.current_search_index

    def test_the_offsets_are_counted_the_way_the_browser_counts(self):
        # One character in Python, two in JavaScript.
        assert utf16_offset("a😀b", 2) == 3
        assert utf16_offset("abc", 2) == 2

    def test_an_edit_makes_a_match_or_takes_one_away(self, editor):
        editor.search_captions("cat")
        assert len(editor.search_results) == 4

        editor.captions[2].text = "A cat appears"
        editor.refresh_display()
        assert len(editor.search_results) == 5

        editor.captions[0].text = "The dog sat on the mat"
        editor.refresh_display()
        assert len(editor.search_results) == 4

    def test_clearing_takes_every_mark_off(self, editor):
        editor.search_captions("cat")
        editor.clear_search()

        marks, current = editor.marks[-1]

        assert marks == [] and current == -1
        assert editor.search_term == ""
        assert editor.search_results == []

    def test_the_card_is_told_where_the_reader_is(self, editor):
        told = []

        class Card:
            def show_position(self, current, total, term):
                told.append((current, total, term))

        editor.find_panel = Card()
        editor.search_captions("cat")

        assert told[-1] == (editor.current_search_index, 4, "cat")


class TestTheCard:
    def test_it_is_called_find_and_replace_and_its_button_find(self):
        panel = source("utils/find_panel.py")
        search = source("utils/srt_search.py")

        assert 'ui.label("Find and replace")' in panel
        assert 'ui.button("Find", icon="search")' in search
        assert "Find & Replace" not in panel + search

    def test_it_is_a_deck_of_its_own_with_its_own_colour(self):
        panel = source("utils/find_panel.py")
        css = source("utils/styles.py")

        assert '"validation-panel is-find w-full"' in panel
        assert ".validation-panel.is-find {" in css
        assert "--vp-tone: var(--color-find-line);" in css

    def test_it_is_built_after_the_first_deck_so_it_lies_under_it(self):
        page = source("pages/srt.py")

        assert page.index("ValidationPanel(") < page.index("FindPanel(")
        assert page.index("CommentsPanel(transcript)") < page.index("FindPanel(")
        # Not inside the format's own branch: both formats have it.
        tail = page[page.index("FindPanel(") - 400 : page.index("FindPanel(")]
        assert "if data_format" not in tail.split("open_first()")[-1]

    def test_the_header_is_the_other_cards_header(self):
        panel = source("utils/find_panel.py")

        for part in (
            "validation-panel-head",
            "validation-panel-heading",
            "validation-panel-nav",
            "validation-panel-step",
            "validation-panel-position",
            "validation-panel-close",
        ):
            assert part in panel

        assert 'aria-label="Previous match"' in panel
        assert 'aria-label="Next match"' in panel
        assert 'aria-label="Close find and replace"' in panel

    def test_the_matches_are_said_in_a_live_region_and_focus_stays(self):
        panel = source("utils/find_panel.py")

        assert "role=status aria-live=polite aria-atomic=true" in panel

    def test_what_is_said(self):
        from utils.find_panel import position_text, spoken_text

        assert position_text(2, 12) == "3 of 12"
        assert spoken_text(2, 12, "cat") == "3 of 12 matches"
        assert spoken_text(0, 0, "cat") == "No matches"
        assert spoken_text(0, 0, "") == ""
        assert spoken_text(0, 0, "   ") == ""

    def test_match_case_is_a_toggle_with_one_name(self):
        panel = source("utils/find_panel.py")

        assert 'aria-label="Match case"' in panel
        assert "aria-pressed=false" in panel
        assert "aria-pressed={'true' if on else 'false'}" in panel

    def test_replace_is_unfolded_on_demand_and_says_so(self):
        panel = source("utils/find_panel.py")

        assert "aria-expanded=false" in panel
        assert "aria-controls=find-panel-replace" in panel
        assert "id=find-panel-replace" in panel
        assert "self.replace_block.set_visibility(False)" in panel
        assert "aria-expanded={'true' if expanded else 'false'}" in panel

    def test_the_replace_buttons_do_the_two_things(self):
        panel = source("utils/find_panel.py")

        assert "replace_in_current_match" in panel
        assert "self.editor.replace_all(" in panel
        assert 'ui.button(\n                                "Replace", on_click=self.replace_one' in panel

    def test_enter_steps_and_shift_enter_steps_back(self):
        panel = source("utils/find_panel.py")
        enter = panel[panel.index("def enter(") : panel.index("def toggle_case(")]

        assert 'self.input.on("keydown.enter", self.enter, args=["shiftKey"])' in panel
        assert "navigate_search_results(-1 if shift else 1)" in enter
        # A look that has not happened yet comes first and is not stepped past.
        assert enter.index("search_captions(") < enter.index("navigate_search_results")

    def test_the_search_waits_for_the_typing_but_the_value_does_not(self):
        panel = source("utils/find_panel.py")

        assert '"update:model-value"' in panel
        assert "throttle=0.3" in panel
        assert "leading_events=False" in panel

    def test_what_is_typed_stays_in_the_field_except_find_and_replace_keys(self):
        panel = source("utils/find_panel.py")

        assert "event.stopPropagation()" in panel
        assert "key === 'f' || key === 'h'" in panel

    def test_escape_closes_it_from_either_field(self):
        panel = source("utils/find_panel.py")

        assert 'self.input.on("keydown.escape", self.close)' in panel
        assert 'self.replace_input.on("keydown.escape", self.close)' in panel

    def test_closing_takes_the_marks_off_and_hands_focus_back(self):
        panel = source("utils/find_panel.py")
        close = panel[panel.index("    def close(") : panel.index("    # -- Looking")]

        assert "self.container.set_visibility(False)" in close
        assert "self.editor.clear_search()" in close
        assert "focus_element(target)" in close
        # What was typed is kept for the next time: the field is not emptied.
        assert "input.set_value" not in close
        assert "input.value =" not in close

    def test_opening_marks_the_matches_of_what_is_in_the_field(self):
        panel = source("utils/find_panel.py")
        opening = panel[panel.index("    def open(") : panel.index("    def focus_field")]

        assert "self.container.set_visibility(True)" in opening
        assert "self.editor.search_captions(self.input.value" in opening
        assert "self.focus_field()" in opening

    def test_opening_waits_for_nothing_from_the_browser(self):
        panel = source("utils/find_panel.py")

        assert "await" not in panel
        assert "background_tasks" not in panel

    def test_the_selected_words_go_into_the_field_when_it_opens(self):
        panel = source("utils/find_panel.py")

        assert "getSelection()" in panel
        assert 'closest(".transcript-text")' in panel
        assert "text.length > 100" in panel
        assert "ui.run_javascript(FILL_FROM_SELECTION_JS" in panel
        # The field reports the new value as a typed one, so the search runs.
        assert 'new Event("input", { bubbles: true })' in panel

    def test_the_selection_is_read_before_the_field_takes_focus(self):
        panel = source("utils/find_panel.py")
        opening = panel[panel.index("    def open(") : panel.index("    def focus_field")]

        assert opening.index("run_javascript") < opening.index("focus_field")


class TestTheKeys:
    def test_ctrl_f_and_cmd_f_open_find_and_ctrl_h_opens_it_with_replace(self):
        keys = source("utils/srt.py")

        assert keys.count("self.open_find()") == 2
        assert 'case "h" if event.modifiers.ctrl and not event.modifiers.shift:' in keys
        assert "self.open_find(replace=True)" in keys

    def test_cmd_h_is_not_taken(self):
        keys = source("utils/srt.py")

        assert 'case "h" if event.modifiers.meta' not in keys

    def test_the_browsers_own_ctrl_h_is_held_back(self):
        page = source("pages/srt.py")

        assert "e.ctrlKey && ! e.metaKey && ! e.shiftKey && ! e.altKey && e.key.toLowerCase() === 'h'" in page

    def test_the_toolbar_says_find_and_the_shortcut_list_says_find_and_replace(self):
        render = source("utils/srt_render.py")

        assert '("Find", "Ctrl/⌘ + F"), ("Replace", "Ctrl + H")' in render

    def test_the_toolbar_button_opens_the_card_and_names_its_key(self):
        search = source("utils/srt_search.py")

        assert "aria-keyshortcuts=Control+F" in search
        assert "self.open_find()" in search


class TestTheLook:
    def test_the_steel_blue_is_in_both_themes(self):
        css = source("utils/styles.py")

        assert css.count("--color-find-line:") == 2
        assert css.count("--color-find-bg:") == 2

    def test_the_words_found_have_a_heavy_dashed_underline_and_the_current_a_wash(self):
        css = source("utils/styles.py")
        found = css[css.index("::highlight(find-match) {") :]
        found = found[: found.index("}")]
        current = css[css.index("::highlight(find-current) {") :]
        current = current[: current.index("}")]

        assert "underline dashed var(--color-find-line) 3px" in found
        assert "underline dashed var(--color-find-line) 3px" in current
        assert "background-color: var(--color-find-bg)" in current

    def test_a_match_does_not_mark_its_caption_so_validate_has_the_block(self):
        """
        Validate marks whole captions (amber, red); Find marks only the words,
        so the two do not fight over the block.
        """

        css = source("utils/styles.py")
        py = source("utils/transcript_editor.py")
        js = source("utils/transcript_editor.js")
        caption = source("utils/caption.py")

        assert "transcript-cell-found" not in css + js
        assert '"found"' not in py
        assert "is_highlighted" not in caption + source("utils/srt_search.py")


class TestPaintingTheWords:
    def test_the_component_takes_the_matches_and_which_is_current(self):
        js = source("utils/transcript_editor.js")
        py = source("utils/transcript_editor.py")

        assert "findMarks: { type: Array" in js
        assert "findCurrent: { type: Number" in js
        assert 'self._props["findMarks"] = []' in py
        assert "def set_find(" in py
        assert "self.editor.on_find_marks = self.set_find_marks" in py

    def test_they_are_painted_with_the_highlight_registry_not_with_elements(self):
        js = source("utils/transcript_editor.js")
        paint = js[js.index("    paintFind(force = false) {") : js.index("    clearFind() {")]

        assert 'CSS.highlights.set("find-match"' in paint
        assert 'CSS.highlights.set("find-current"' in paint
        assert "new Range()" in paint
        assert "createElement" not in paint
        assert "innerHTML" not in paint
        assert "!CSS.highlights" in paint

    def test_they_are_painted_again_when_the_text_is_rebuilt_and_dropped_when_it_goes(self):
        js = source("utils/transcript_editor.js")

        assert "this.paintFind(true);" in js
        assert "this.clearFind();" in js[js.index("beforeUnmount()") :]

    def test_nothing_is_repainted_when_nothing_changed(self):
        js = source("utils/transcript_editor.js")
        paint = js[js.index("    paintFind(force = false) {") : js.index("    clearFind() {")]

        assert "signature === this.findSignature" in paint

    def test_the_server_sends_the_marks_only_when_they_change(self):
        py = source("utils/transcript_editor.py")
        setter = py[py.index("    def set_find(") : py.index("    def set_follow(")]

        assert 'self._props["findMarks"] == marks' in setter
        assert "return" in setter

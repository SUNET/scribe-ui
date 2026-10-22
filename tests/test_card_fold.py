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
Folding a card in the deck to its header (utils/card_fold.py).

The fold itself is built here with NiceGUI's own elements, outside a browser;
how the three cards use it is read from their source and the stylesheet, as
the other panel tests do.
"""

import pathlib

import pytest
from nicegui import ui

import utils.card_fold as card_fold
from utils.card_fold import CardFold, fold_icon, fold_tip

ROOT = pathlib.Path(__file__).parent.parent


def source(path: str) -> str:
    return (ROOT / path).read_text()


@pytest.fixture
def fold(monkeypatch):
    """
    A fold in a wrapper, with the browser's focus recorded instead of moved.
    """

    focused = []
    monkeypatch.setattr(card_fold, "focus_element", focused.append)

    # No client of its own: elements made outside a page land in NiceGUI's
    # script-mode client, as in the other tests that build them.
    with ui.element("div") as wrap:
        with ui.element("div"):
            made = CardFold(wrap, "Test card", "test-body")
            heading = made.heading(ui.label("Heading"))

    made.wrap_for_test = wrap
    made.heading_for_test = heading
    made.focused = focused
    return made


class TestTheFoldButton:
    def test_it_starts_open(self, fold):
        assert fold.folded is False
        assert "data-folded" not in fold.wrap_for_test._props
        assert fold.button._props["aria-expanded"] == "true"
        assert fold.button._props["icon"] == fold_icon(False)

    def test_it_is_a_disclosure_button_for_the_body(self, fold):
        assert fold.button._props["aria-controls"] == "test-body"
        assert fold.button._props["aria-label"] == "Test card"

    def test_its_name_does_not_change_with_the_state(self, fold):
        fold.set_folded(True)

        assert fold.button._props["aria-label"] == "Test card"

    def test_it_says_what_it_will_do(self):
        assert fold_tip(False) == "Fold"
        assert fold_tip(True) == "Unfold"

    def test_the_chevron_does_not_point_the_way_next_does(self):
        # Next is chevron_right, in the header's other end.
        assert fold_icon(True) == "chevron_right"
        assert fold_icon(False) == "expand_more"


class TestFoldingAndUnfolding:
    def test_folding_marks_the_wrapper_not_the_card(self, fold):
        fold.set_folded(True)

        assert fold.wrap_for_test._props["data-folded"] == "true"

    def test_folding_changes_the_button(self, fold):
        fold.set_folded(True)

        assert fold.button._props["aria-expanded"] == "false"
        assert fold.button._props["icon"] == fold_icon(True)
        assert fold.tip.text == "Unfold"

    def test_unfolding_puts_it_all_back(self, fold):
        fold.set_folded(True)
        fold.unfold()

        assert fold.folded is False
        assert "data-folded" not in fold.wrap_for_test._props
        assert fold.button._props["aria-expanded"] == "true"
        assert fold.button._props["icon"] == fold_icon(False)
        assert fold.tip.text == "Fold"

    def test_toggle_goes_back_and_forth(self, fold):
        fold.toggle()
        assert fold.folded is True

        fold.toggle()
        assert fold.folded is False

    def test_folding_leaves_focus_on_the_button(self, fold):
        fold.set_folded(True)

        assert fold.focused == [fold.button]

    def test_unfolding_does_not_move_focus(self, fold):
        fold.set_folded(True)
        fold.focused.clear()
        fold.unfold()

        assert fold.focused == []

    def test_unfolding_an_open_card_does_nothing(self, fold):
        changes = []
        fold.on_change = changes.append

        fold.unfold()

        assert changes == []
        assert fold.focused == []

    def test_a_change_is_reported(self, fold):
        changes = []
        fold.on_change = changes.append

        fold.set_folded(True)
        fold.set_folded(True)
        fold.unfold()

        assert changes == [True, False]


class TestTheHeading:
    def test_a_click_on_it_folds(self, fold):
        assert "validation-panel-heading-fold" in fold.heading_for_test._classes

        events = [listener.type for listener in fold.heading_for_test._event_listeners.values()]
        assert "click" in events


class TestTheThreeCards:
    @pytest.mark.parametrize(
        "path, name, body_id",
        [
            ("utils/find_panel.py", "Find and replace", "find-panel-body"),
            ("utils/validation_panel.py", "Validation", "validation-panel-body"),
            ("utils/comments_panel.py", "Comments", "comments-panel-body"),
        ],
    )
    def test_each_has_a_fold_before_its_heading_and_a_body_to_fold(
        self, path, name, body_id
    ):
        code = source(path)

        assert "from utils.card_fold import CardFold" in code
        assert f'"{name}"' in code
        assert code.count(f"id={body_id}") == 1
        assert code.index("CardFold(") < code.index("self.fold.heading(")

    def test_find_opens_whole(self):
        code = source("utils/find_panel.py")
        opening = code[code.index("def open(") : code.index("def focus_field(")]

        assert "self.fold.unfold()" in opening

    def test_find_is_unfolded_when_closed(self):
        code = source("utils/find_panel.py")
        closing = code[code.index("def close(") : code.index("# -- Looking")]

        assert "self.fold.unfold()" in closing

    def test_validate_opens_whole_and_is_unfolded_when_closed(self):
        code = source("utils/validation_panel.py")
        showing = code[code.index("def show(") : code.index("def folded_changed(")]
        closing = code[code.index("def close(") : code.index("# -- Skip link")]

        assert "self.fold.unfold()" in showing
        assert "self.fold.unfold()" in closing

    def test_validate_says_where_the_reader_is_while_folded(self):
        code = source("utils/validation_panel.py")

        # Outside the body, which is gone while folded.
        assert code.index("self.folded_spoken = ") < code.index('"id=validation-panel-body')
        assert "if speak and self.fold.folded" in code


class TestTheLook:
    def test_a_folded_card_keeps_its_header_and_what_is_read_aloud(self):
        css = source("utils/styles.py")

        assert ".validation-panel-wrap[data-folded] .validation-panel > :not(.validation-panel-head):not(.sr-only)" in css

    def test_a_folded_validate_card_loses_its_filters_too(self):
        css = source("utils/styles.py")

        assert ".validation-panel-wrap[data-folded] .validation-panel-filters" in css

    def test_the_header_has_the_room_the_chevron_needs(self):
        css = source("utils/styles.py")

        assert ".validation-panel-head:has(.validation-panel-fold)" in css
        assert ".validation-panel .validation-panel-fold" in css

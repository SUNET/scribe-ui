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
Folding a card in the deck to its header.

Validate, Comments and Find are cards in one deck under the video, and more
than one can be open at once. Each can be folded to its header row -- the
heading, the position and Previous/Next, and the close button stay -- so that
the transcript keeps its room, and unfolded again from the chevron before the
heading.

What folding means:

- **The chevron is the control**, a button with aria-expanded and
  aria-controls like the Replace toggle in Find. Clicking the heading does the
  same, as a convenience for the mouse; it is not a second way for the
  keyboard.
- **The header stays**, so a folded card still says what it is and where the
  reader is ("3 of 12"), and Previous/Next still step. The text of the body
  goes (display: none), so nothing in it can be reached while it is folded.
- **Folding never takes anything away.** What was typed in a comment is still
  there; the matches stay marked; the issue stays on screen in the text.
- **Opening a card unfolds it.** Following the caret to another comment or
  stepping through issues does not: the reader folded it on purpose.
- **Closing a card forgets it was folded.** The next time it opens it opens
  whole.

The state is an attribute on the card's wrapper (data-folded), not a class:
the validation card sets its own classes afresh on every redraw.
"""

from typing import Callable, Optional

from nicegui import ui

from utils.common import focus_element


def fold_icon(folded: bool) -> str:
    """
    Pointing right when folded, down when open: the same pair as the Replace
    toggle in Find.
    """

    return "chevron_right" if folded else "expand_more"


def fold_tip(folded: bool) -> str:
    """
    What the tooltip says the button will do.
    """

    return "Unfold" if folded else "Fold"


class CardFold:
    """
    The fold of one card. Built inside the card's header, before its heading,
    so the chevron comes first.

    Parameters:
        wrap: the card's wrapper, which carries data-folded.
        name: what the card is, for the button's name ("Find and replace").
        body_id: the id of the body that is folded away.
        on_change: called with the new state when the card is folded or
            unfolded.

    The card's heading is made next and given to heading(), so that a click on
    it folds the card too.
    """

    def __init__(
        self,
        wrap: ui.element,
        name: str,
        body_id: str,
        on_change: Optional[Callable[[bool], None]] = None,
    ):
        self.wrap = wrap
        self.on_change = on_change
        self.folded = False

        # The name stays the same, folded or not -- aria-expanded says which --
        # as Find's Replace toggle does.
        self.button = (
            ui.button(icon=fold_icon(False), on_click=self.toggle, color=None)
            .props(f'flat aria-label="{name}" aria-expanded=true aria-controls={body_id}')
            .classes("editor-btn editor-icon validation-panel-fold")
        )

        with self.button:
            self.tip = ui.tooltip(fold_tip(False))

    def heading(self, heading: ui.element) -> ui.element:
        """
        Let a click on the card's heading fold it as well.
        """

        heading.classes(add="validation-panel-heading-fold").on("click", self.toggle)
        return heading

    def toggle(self) -> None:
        self.set_folded(not self.folded)

    def set_folded(self, folded: bool) -> None:
        if folded == self.folded:
            return

        self.folded = folded

        if folded:
            self.wrap.props("data-folded=true")
        else:
            self.wrap.props(remove="data-folded")

        self.button.props(f"aria-expanded={'false' if folded else 'true'}")
        self.button.props(f"icon={fold_icon(folded)}")
        self.tip.set_text(fold_tip(folded))

        # Whatever had focus inside the body is gone; the button is where the
        # reader was a moment ago.
        if folded:
            focus_element(self.button)

        if self.on_change is not None:
            self.on_change(folded)

    def unfold(self) -> None:
        self.set_folded(False)

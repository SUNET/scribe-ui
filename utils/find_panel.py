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
The Find card: where a term is looked for, stepped through and replaced.

A card under the video, built like the validation panel's and the comments
panel's and drawn like them -- a stripe down the left and a tinted header, with
Previous, the position and Next in the header -- in the steel blue the matches
are marked with. It is a deck of its own: with the validation or the comments
card open, Find is the card under it; with neither, it is the first.

It behaves the way a word processor's Find does:

- **Live.** Matches are looked for as the term is typed, every one of them
  is marked in the text (its words with a heavy dashed underline, the caption
  they are in with a wash) and the current one is marked more strongly.
- **Enter and Shift+Enter** step to the next and the previous match, round
  the end. Previous and Next in the header do the same.
- **Replace** changes the current match -- that one occurrence -- and moves on
  to the next; **Replace all** changes every one, in one undo step.
- **Ctrl/Cmd+F** opens it with the field ready, and with the selected words
  in it if some are selected. **Ctrl+H** opens it with Replace unfolded.
- **Closing it takes the marks off the text.** Escape, the x and the Find
  button all leave the text as it was. What was in the field is still there
  when it is opened again.
- Focus is never taken from where the reader put it: stepping brings the
  caption into view, and what is said ("3 of 12 matches") is a live region.
"""

from typing import Callable, Optional

from nicegui import background_tasks, ui

from utils.common import focus_element


# The words selected in the text, for a Find that starts from them: nothing
# when there is no selection, when it is not in the text, or when it is more
# than a phrase.
SELECTED_WORDS_JS = """
(() => {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) return "";
  const text = selection.toString();
  if (text.length > 100 || text.includes("\\n")) return "";
  const node = selection.anchorNode;
  const element = node && (node.nodeType === 1 ? node : node.parentElement);
  return element && element.closest(".transcript-text") ? text : "";
})()
"""


def position_text(current: int, total: int) -> str:
    """
    "3 of 12" -- where the reader is among the matches.
    """

    return f"{current + 1} of {total}"


def spoken_text(current: int, total: int, term: str) -> str:
    """
    What the live region says as the matches change. Nothing without a term.
    """

    if not term.strip():
        return ""

    if not total:
        return "No matches"

    return f"{position_text(current, total)} matches"


class FindPanel:
    """
    Built once, hidden, under the video.

    Parameters:
        editor: the SRTEditor whose captions are searched (SearchMixin).
        return_focus: the element that gets focus when the card is closed.
    """

    def __init__(
        self,
        editor,
        return_focus: Callable[[], Optional[ui.element]] = lambda: None,
    ) -> None:
        self.editor = editor
        self.return_focus = return_focus
        self.expanded = False

        with ui.element("div").classes("validation-panel-wrap w-full") as self.container:
            with ui.element("section").classes(
                "validation-panel is-find w-full"
            ).props('role=search aria-labelledby="find-panel-heading"') as self.panel:
                with ui.element("div").classes("validation-panel-head"):
                    self.heading = (
                        ui.label("Find and replace")
                        .classes("validation-panel-heading")
                        .props("id=find-panel-heading tabindex=-1")
                    )

                    with ui.element("div").classes("validation-panel-nav"):
                        self.previous = ui.button(
                            icon="chevron_left",
                            on_click=lambda: self.editor.navigate_search_results(-1),
                            color=None,
                        ).props('flat aria-label="Previous match"').classes(
                            "validation-panel-step"
                        )
                        self.position_label = ui.label("").classes(
                            "validation-panel-position"
                        )
                        self.next = ui.button(
                            icon="chevron_right",
                            on_click=lambda: self.editor.navigate_search_results(1),
                            color=None,
                        ).props('flat aria-label="Next match"').classes(
                            "validation-panel-step"
                        )

                    ui.button(icon="close", on_click=self.close).props(
                        'flat aria-label="Close find and replace"'
                    ).classes("editor-btn editor-icon validation-panel-close").tooltip(
                        "Close"
                    )

                # Said as the matches change, while focus stays in the field.
                self.spoken = ui.label("").classes("sr-only").props(
                    "role=status aria-live=polite aria-atomic=true"
                )

                with ui.element("div").classes("validation-panel-body"):
                    with ui.element("div").classes("find-panel-row"):
                        self.input = (
                            ui.input(label="Find", value=editor.search_term)
                            .props("outlined dense clearable")
                            .classes("find-panel-input")
                        )
                        self.case_button = (
                            ui.button("Aa", on_click=self.toggle_case)
                            .props(
                                "flat dense no-caps aria-pressed=false "
                                'aria-label="Match case"'
                            )
                            .classes("find-panel-case")
                        )
                        self.case_button.tooltip("Match case")

                    # What is typed here stays here: the page has shortcuts of
                    # its own (undo, save, play) that would otherwise act on
                    # the transcript while a word is being typed. Find's own
                    # keys are let through so Ctrl+F and Ctrl+H work from the
                    # field.
                    stop_keys = (
                        "(event) => { const key = event.key.toLowerCase();"
                        " if (!((event.ctrlKey || event.metaKey) &&"
                        " (key === 'f' || key === 'h'))) event.stopPropagation(); }"
                    )
                    self.input.on("keydown", js_handler=stop_keys)
                    self.input.on("keydown.escape", self.close)
                    self.input.on("keydown.enter", self.enter, args=["shiftKey"])
                    # Looked for a moment after the typing stops: the value
                    # itself is kept as it is typed (Enter reads it), the
                    # search waits.
                    self.input.on(
                        "update:model-value",
                        self.typed,
                        throttle=0.3,
                        leading_events=False,
                    )

                    self.replace_toggle = (
                        ui.button("Replace", icon="chevron_right", on_click=self.toggle_replace)
                        .props(
                            "flat dense no-caps aria-expanded=false "
                            "aria-controls=find-panel-replace"
                        )
                        .classes("find-panel-disclosure")
                    )

                    with ui.element("div").props("id=find-panel-replace").classes(
                        "find-panel-replace"
                    ) as self.replace_block:
                        self.replace_input = (
                            ui.input(label="Replace with")
                            .props("outlined dense clearable")
                            .classes("w-full")
                        )
                        self.replace_input.on("keydown", js_handler=stop_keys)
                        self.replace_input.on("keydown.escape", self.close)
                        self.replace_input.on("keydown.enter", self.replace_one)

                        with ui.element("div").classes(
                            "comments-panel-actions find-panel-actions"
                        ).props('role=group aria-label="Replace"'):
                            self.replace_button = ui.button(
                                "Replace", on_click=self.replace_one
                            ).props("flat dense no-caps")
                            self.replace_all_button = ui.button(
                                "Replace all", on_click=self.replace_everywhere
                            ).props("flat dense no-caps")

        self.replace_block.set_visibility(False)
        self.container.set_visibility(False)
        self.show_position(0, 0, "")

    # -- Opening and closing -------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.container.visible

    def open(self, replace: bool = False) -> None:
        """
        Show the card with the field ready -- with the words selected in the
        text in it, if there are some, as a word processor does -- and mark
        the matches of what is in it.
        """

        background_tasks.create(self.open_with_selection(replace))

    async def open_with_selection(self, replace: bool) -> None:
        selected = ""

        try:
            selected = await self.input.client.run_javascript(SELECTED_WORDS_JS)
        except Exception:  # The page went away, or took too long to answer.
            selected = ""

        self.container.set_visibility(True)

        if replace:
            self.set_replace(True)

        if selected and selected != self.input.value:
            self.input.set_value(selected)
            self.editor.search_captions(selected)
        else:
            # Back with what was there: the marks went when it was closed.
            self.editor.search_captions(self.input.value or "")

        self.focus_field()

    def focus_field(self) -> None:
        self.input.run_method("focus")
        self.input.run_method("select")

    def close(self) -> None:
        """
        Put the card away and take its marks off the text. What is in the
        field stays, for the next time.
        """

        self.container.set_visibility(False)
        self.editor.clear_search()

        target = self.return_focus()

        if target is not None:
            focus_element(target)

    # -- Looking -------------------------------------------------------------

    def typed(self, event=None) -> None:
        if self.input.value != self.editor.search_term:
            self.editor.search_captions(self.input.value or "")

    def enter(self, event) -> None:
        """
        Enter steps to the next match, Shift+Enter to the previous one. When
        the field has been typed in since the last look, that look comes
        first, and lands on the first match: nothing is stepped past.
        """

        if (self.input.value or "") != self.editor.search_term:
            self.editor.search_captions(self.input.value or "")
            return

        shift = bool(event.args.get("shiftKey")) if isinstance(event.args, dict) else False
        self.editor.navigate_search_results(-1 if shift else 1)

    def toggle_case(self) -> None:
        self.editor.case_sensitive = not self.editor.case_sensitive
        on = self.editor.case_sensitive

        self.case_button.props(f"aria-pressed={'true' if on else 'false'}")
        self.case_button.classes(
            add="find-panel-case-on" if on else "", remove="" if on else "find-panel-case-on"
        )

        if self.editor.search_term:
            self.editor.search_captions(self.editor.search_term)

    def show_position(self, current: int, total: int, term: str) -> None:
        """
        Where the reader is among the matches: in the header, and said.
        """

        self.position_label.set_text(position_text(current, total) if total else "")
        self.spoken.set_text(spoken_text(current, total, term))
        self.previous.set_enabled(total > 0)
        self.next.set_enabled(total > 0)
        self.replace_button.set_enabled(total > 0)
        self.replace_all_button.set_enabled(total > 0)

    # -- Replacing -----------------------------------------------------------

    def toggle_replace(self) -> None:
        self.set_replace(not self.expanded)

    def set_replace(self, expanded: bool) -> None:
        self.expanded = expanded
        self.replace_block.set_visibility(expanded)
        self.replace_toggle.props(f"aria-expanded={'true' if expanded else 'false'}")
        self.replace_toggle.props(f"icon={'expand_more' if expanded else 'chevron_right'}")

    def replace_one(self) -> None:
        self.editor.replace_in_current_match(self.replace_input.value or "")

    def replace_everywhere(self) -> None:
        self.editor.replace_all(self.replace_input.value or "")

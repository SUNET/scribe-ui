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
Find and replace across a transcription's captions.
"""

import re

from typing import Optional

from nicegui import ui



class SearchMixin:
    """
    The search panel and the search state behind it.
    """

    def search_captions(self, search_term: str) -> None:
        """
        Search for captions containing the search term.
        """

        self.search_term = search_term
        self.search_results = []

        # Track which captions change highlight state
        changed_indices = set()

        # Clear previous highlights
        for caption in self.captions:
            if caption.is_highlighted:
                caption.is_highlighted = False
                changed_indices.add(caption.index)

        if not search_term.strip():
            self.refresh_display(
                specific_indices=changed_indices if changed_indices else None
            )
            self.update_search_info()
            return

        # Find matching captions
        for i, caption in enumerate(self.captions):
            if caption.matches_search(search_term, self.case_sensitive):
                self.search_results.append(i)
                caption.is_highlighted = True
                changed_indices.add(caption.index)

        self.current_search_index = 0
        self.refresh_display(
            specific_indices=changed_indices if changed_indices else None
        )
        self.update_search_info()

        if self.search_results:
            self.scroll_to_result(0)


    def navigate_search_results(self, direction: int) -> None:
        """
        Navigate through search results (direction:  1 for next, -1 for previous).
        """
        if not self.search_results:
            return

        self.current_search_index = (self.current_search_index + direction) % len(
            self.search_results
        )
        self.scroll_to_result(self.current_search_index)
        self.update_search_info()


    def scroll_to_result(self, result_index: int) -> None:
        """
        Scroll to a specific search result.
        """
        if not self.search_results or result_index >= len(self.search_results):
            return

        caption_index = self.search_results[result_index]
        # Select the caption to make it visible
        if caption_index < len(self.captions):
            self.select_caption(self.captions[caption_index])


    def replace_in_current_caption(self, replacement: str) -> None:
        """
        Replace search term in currently selected caption.
        """
        if not self.selected_caption or not self.search_term:
            ui.notify("No caption selected or search term empty", type="warning")
            return

        if self.selected_caption.matches_search(self.search_term, self.case_sensitive):
            # Save state before making changes
            self.save_state_for_undo()

            if self.case_sensitive:
                new_text = self.selected_caption.text.replace(
                    self.search_term, replacement
                )
            else:
                # Case-insensitive replacement
                pattern = re.compile(re.escape(self.search_term), re.IGNORECASE)
                new_text = pattern.sub(replacement, self.selected_caption.text)

            # Replacing a word is the reader changing it, exactly as typing
            # over it is -- and a replacement of a different length shifts
            # every mark after it along. Worked out here rather than through
            # update_caption_text, which would take a second undo snapshot on
            # top of the one already taken above.
            self.selected_caption.edited_words = self.retag_edits(
                self.selected_caption.text,
                new_text,
                self.selected_caption.edited_words,
            )
            self.selected_caption.text = new_text
            self.update_flagged_count()
            self.refresh_display()
            ui.notify("Replacement made", type="positive")
        else:
            ui.notify("Current caption doesn't contain search term", type="warning")


    def replace_all(self, replacement: str) -> None:
        """
        Replace search term in all matching captions.
        """
        if not self.search_term:
            ui.notify("No search term entered", type="warning")
            return

        # Check if there are any matches before saving state
        has_matches = any(
            caption.matches_search(self.search_term, self.case_sensitive)
            for caption in self.captions
        )

        if has_matches:
            # Save state before making changes
            self.save_state_for_undo()

        count = 0
        for caption in self.captions:
            if caption.matches_search(self.search_term, self.case_sensitive):
                if self.case_sensitive:
                    new_text = caption.text.replace(self.search_term, replacement)
                else:
                    pattern = re.compile(re.escape(self.search_term), re.IGNORECASE)
                    new_text = pattern.sub(replacement, caption.text)

                # See replace_in_current_caption: the replaced word is an edit
                # of the reader's, and a replacement of a different length
                # moves every mark after it. One undo snapshot covers the whole
                # Replace All, so this cannot go through update_caption_text.
                caption.edited_words = self.retag_edits(
                    caption.text, new_text, caption.edited_words
                )
                caption.text = new_text
                count += 1

        if count > 0:
            self.update_flagged_count()
            # Refresh search results
            self.search_captions(self.search_term)
            ui.notify(f"Replaced {count} occurrences", type="positive")
        else:
            ui.notify("No matches found to replace", type="info")


    def update_search_info(self) -> None:
        """
        Update search information display.
        """
        if hasattr(self, "search_info_label") and self.search_info_label:
            if self.search_results:
                info_text = f"{self.current_search_index + 1} of {len(self.search_results)} matches"
            else:
                info_text = "No matches" if self.search_term else ""
            self.search_info_label.set_text(info_text)


    def get_highlighted_text(self, text: str) -> str:
        """
        Get text with search term highlighted (for display purposes).
        """
        if not self.search_term or not text:
            return text

        if self.case_sensitive:
            highlighted = text.replace(
                self.search_term,
                f'<mark style="background-color: yellow; padding: 2px;">{self.search_term}</mark>',
            )
        else:
            pattern = re.compile(f"({re.escape(self.search_term)})", re.IGNORECASE)
            highlighted = pattern.sub(
                r'<mark style="background-color:  yellow; padding: 2px;">\1</mark>',
                text,
            )

        return highlighted


    def create_search_panel(self, open_window: Optional[bool] = False) -> None:
        """
        Create the search panel UI.
        """

        with ui.dialog() as self.search_container:
            with ui.card().classes("w-1/2 max-w-full").style("padding: 16px;"):
                # Title
                ui.label("Find & Replace").classes("text-h6 mb-3")

                # FIND SECTION
                with ui.column().classes("w-full gap-2"):
                    ui.label("Find").classes("text-caption text-theme-secondary")

                    with ui.row().classes("w-full items-center gap-2"):
                        search_input = (
                            ui.input(
                                placeholder="Search in captions…",
                                value=self.search_term,
                            )
                            .classes("flex-1")
                            .props("outlined dense clearable")
                        )

                        ui.button(icon="search").props("flat dense round").classes(
                            "editor-btn"
                        ).on(
                            "click", lambda: self.search_captions(search_input.value)
                        ).tooltip(
                            "Find"
                        )

                    with ui.row().classes("w-full items-center justify-between mt-1"):
                        ui.checkbox("Case sensitive").bind_value_to(
                            self, "case_sensitive"
                        ).on(
                            "update:model-value",
                            lambda: (
                                self.search_captions(search_input.value)
                                if self.search_term
                                else None
                            ),
                        )

                        # Navigation + info
                        with ui.row().classes("items-center gap-1"):
                            ui.button(icon="keyboard_arrow_up").props(
                                "flat dense round"
                            ).classes("editor-btn").on(
                                "click", lambda: self.navigate_search_results(-1)
                            ).tooltip(
                                "Previous match"
                            )
                            ui.button(icon="keyboard_arrow_down").props(
                                "flat dense round"
                            ).classes("editor-btn").on(
                                "click", lambda: self.navigate_search_results(1)
                            ).tooltip(
                                "Next match"
                            )

                            self.search_info_label = ui.label("").classes(
                                "text-caption text-theme-secondary"
                            )

                ui.separator().classes("my-3")

                # REPLACE SECTION
                with ui.column().classes("w-full gap-2"):
                    ui.label("Replace").classes("text-caption text-theme-secondary")

                    replace_input = (
                        ui.input(
                            placeholder="Replace with…",
                        )
                        .classes("w-full")
                        .props("outlined dense clearable")
                    )

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Replace").props("flat dense").classes(
                            "editor-btn"
                        ).on(
                            "click",
                            lambda: self.replace_in_current_caption(
                                replace_input.value
                            ),
                        )

                        ui.button("Replace all").props("flat dense").classes(
                            "editor-btn"
                        ).on("click", lambda: self.replace_all(replace_input.value))

                ui.separator().classes("my-3")

                with ui.row().classes("w-full justify-end"):
                    ui.button("Close").props("flat dense").classes("editor-btn").on(
                        "click", self.search_container.close
                    )

                # Enter key support for search
                search_input.on(
                    "keydown.enter",
                    lambda: self.search_captions(search_input.value),
                )

        if open_window:
            self.search_container.open()
        else:
            ui.button("Search", icon="search").props("flat").classes(
                "editor-btn editor-toolbar-btn"
            ).on("click", lambda: self.search_container.open())

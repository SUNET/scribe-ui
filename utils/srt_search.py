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

Every occurrence of the term is a match, in the order of the text, and one of
them is the current one -- the way a word processor's Find has it. Enter and the
arrows step from one to the next (and round the end), Replace changes the
current one and moves on, Replace all changes every one. The matches are
marked in the text while the Find card is open (their words only: a whole
caption's tint is Validate's) and are gone when it is closed.
"""

import re

from typing import Optional

from nicegui import ui


def utf16_offset(text: str, position: int) -> int:
    """
    `position` in `text`, counted the way the browser counts it. A character
    outside the basic plane (most emoji) is one in Python and two in
    JavaScript, and the marks are drawn there.
    """

    return len(text[:position].encode("utf-16-le")) // 2


class SearchMixin:
    """
    The search state behind the Find card (utils/find_panel.py).

    `search_results` is a list of (caption index, start, end): where each
    occurrence is in its caption's text. `current_search_index` is the one
    the reader is on.
    """

    def find_pattern(self) -> Optional["re.Pattern"]:
        """
        The term as a pattern, or None when there is nothing to look for. The
        term is taken as typed -- a space at the end is part of it -- but one
        of nothing but spaces is not a search.
        """

        if not self.search_term or not self.search_term.strip():
            return None

        flags = 0 if self.case_sensitive else re.IGNORECASE

        return re.compile(re.escape(self.search_term), flags)


    def find_occurrences(self) -> list:
        """
        Every occurrence of the term, in the order of the text.
        """

        pattern = self.find_pattern()

        if pattern is None:
            return []

        return [
            (caption.index, match.start(), match.end())
            for caption in self.captions
            for match in pattern.finditer(caption.text)
        ]


    def caption_by_index(self, index: int):
        return next((c for c in self.captions if c.index == index), None)


    def rebuild_matches(self, after: Optional[tuple] = None) -> None:
        """
        Look for the term again, keep the current match where it was -- or,
        where it is gone, at the next one. `after` is a (caption index, character) to land on or after; by
        default where the current match is now.

        Done on every redraw while a term is set: an edit can make a match
        or take one away.
        """

        if after is None and self.search_results:
            at = min(self.current_search_index, len(self.search_results) - 1)
            after = self.search_results[at][:2]

        self.search_results = self.find_occurrences()

        self.current_search_index = 0

        if after is not None:
            for at, (caption_index, start, _end) in enumerate(self.search_results):
                if (caption_index, start) >= after:
                    self.current_search_index = at
                    break


    def search_start(self) -> tuple:
        """
        Where a new search begins: the caption the reader is on, so that
        typing a term finds the next one from there rather than snapping
        back to the top.
        """

        if self.selected_caption is not None:
            return (self.selected_caption.index, 0)

        return (0, 0)


    def search_captions(self, search_term: str) -> None:
        """
        Look for a term, mark every occurrence, and go to the first one at or
        after where the reader is.
        """

        self.search_term = search_term
        self.search_results = []
        self.rebuild_matches(after=self.search_start())

        self.refresh_display()

        if self.search_results:
            self.reveal_current()


    def clear_search(self) -> None:
        """
        Forget the term: nothing is marked in the text any more. What the
        Find card shows in its own field is the card's business.
        """

        had = bool(self.search_term) or bool(self.search_results)

        self.search_term = ""
        self.search_results = []
        self.current_search_index = 0

        if had:
            self.refresh_display()


    def mark_found(self) -> None:
        """
        Tell the text which words are matches, and the card where the reader
        is among them. Called after every redraw.
        """

        marks = []

        for caption_index, start, end in self.search_results:
            caption = self.caption_by_index(caption_index)

            if caption is None:
                continue

            marks.append(
                {
                    "id": caption_index,
                    "s": utf16_offset(caption.text, start),
                    "e": utf16_offset(caption.text, end),
                }
            )

        if self.on_find_marks is not None:
            self.on_find_marks(marks, self.current_search_index if marks else -1)

        self.update_search_info()


    def navigate_search_results(self, direction: int) -> None:
        """
        Step to the next (1) or previous (-1) match, round the end.
        """

        if not self.search_results:
            return

        self.current_search_index = (self.current_search_index + direction) % len(
            self.search_results
        )
        self.mark_found()
        self.reveal_current()


    def reveal_current(self) -> None:
        """
        Bring the caption of the current match into view and seek the
        recording to it. Not select_caption(): that toggles, so a second
        match in the same caption would have un-selected it and not scrolled.
        """

        if not self.search_results:
            return

        caption = self.caption_by_index(self.search_results[self.current_search_index][0])

        if caption is None:
            return

        if self.selected_caption is caption:
            if self.on_select:
                self.on_select(caption)
        else:
            self.select_caption(caption)


    def replace_in_current_match(self, replacement: str) -> None:
        """
        Change the current match -- that one occurrence, not the others in the
        same caption -- and move to the next, as a word processor's Replace
        does.
        """

        if not self.search_results:
            ui.notify("No match to replace", type="warning", timeout=None, close_button="Close")
            return

        # What the card shows is what is replaced: look again first, in case
        # the text was typed into since.
        self.rebuild_matches()

        if not self.search_results:
            ui.notify("No match to replace", type="warning", timeout=None, close_button="Close")
            return

        caption_index, start, end = self.search_results[self.current_search_index]
        caption = self.caption_by_index(caption_index)

        if caption is None:
            return

        # Save state before making changes
        self.save_state_for_undo()

        new_text = caption.text[:start] + replacement + caption.text[end:]

        # Replacing a word is the reader changing it, exactly as typing
        # over it is -- and a replacement of a different length shifts
        # every mark after it along. Worked out here rather than through
        # update_caption_text, which would take a second undo snapshot on
        # top of the one already taken above.
        self.carry_marks(caption, new_text)
        caption.text = new_text
        self.update_flagged_count()

        # On to the next one: the first that starts after what was put in.
        self.search_results = []
        self.rebuild_matches(after=(caption_index, start + len(replacement)))

        self.refresh_display()
        self.reveal_current()
        ui.notify("Replacement made", type="positive")


    def replace_all(self, replacement: str) -> None:
        """
        Replace search term in all matching captions.
        """
        pattern = self.find_pattern()

        if pattern is None:
            ui.notify("No search term entered", type="warning", timeout=None, close_button="Close")
            return

        # Check if there are any matches before saving state
        has_matches = any(pattern.search(caption.text) for caption in self.captions)

        if has_matches:
            # Save state before making changes
            self.save_state_for_undo()

        count = 0
        for caption in self.captions:
            found = len(pattern.findall(caption.text))

            if found:
                new_text = pattern.sub(lambda _match: replacement, caption.text)

                # See replace_in_current_match: the replaced word is an edit
                # of the reader's, and a replacement of a different length
                # moves every mark after it. One undo snapshot covers the whole
                # Replace All, so this cannot go through update_caption_text.
                self.carry_marks(caption, new_text)
                caption.text = new_text
                count += found

        if count > 0:
            self.update_flagged_count()
            self.search_captions(self.search_term)
            ui.notify(f"Replaced {count} occurrences", type="positive")
        else:
            ui.notify("No matches found to replace", type="info")


    def update_search_info(self) -> None:
        """
        Tell the card where the reader is among the matches.
        """

        if self.find_panel is not None:
            self.find_panel.show_position(
                self.current_search_index, len(self.search_results), self.search_term
            )


    def create_search_panel(self) -> None:
        """
        The toolbar's Find button. The card itself is built with the others,
        under the video (utils/find_panel.py), and opens from here and from
        Ctrl/Cmd+F.
        """

        with ui.button("Find", icon="search").props(
            "flat aria-keyshortcuts=Control+F"
        ).classes("editor-btn editor-toolbar-btn editor-quiet") as self.find_button:
            self.find_button.tooltip("Find (Ctrl/\u2318 + F)")
            self.find_button.on("click", lambda: self.open_find())


    def open_find(self, replace: bool = False) -> None:
        """
        Open the Find card, if the page has one.
        """

        if self.find_panel is not None:
            self.find_panel.open(replace=replace)

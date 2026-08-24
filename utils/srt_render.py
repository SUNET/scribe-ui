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
Validation and the caption-list bookkeeping that both editors share.

Subtitles and transcriptions are both drawn by the document editor now (see
utils/transcript_editor.py) -- there is no separate per-caption card
renderer here any more. What is left is format-agnostic: refresh_display,
which forwards to whichever editor built itself, and validation, which is
specific to subtitles (a transcription has no line-length or line-count
guideline to check).
"""

from typing import Optional

from nicegui import ui

from utils.caption import SRTCaption
from utils.settings import get_settings

settings = get_settings()

CHARACTER_LIMIT_EXCEEDED_COLOR = "text-red"


class RenderMixin:
    """
    Caption list bookkeeping, validation and the shortcut help.
    """

    def caption_line_counts(self, caption: SRTCaption) -> list:
        """
        A caption's character-count guideline, one entry per line, for the
        document editor to show in the margin beside that line rather than
        as one summary under the caption. Each entry flags whether that line
        has gone past CHARACTER_LIMIT ("exceeded"). A count answers for its
        own line's length and nothing else: a caption with more lines than
        MAX_SUBTITLE_LINES used to turn every count in it red, which said
        lines were too long when they were not -- "Validate" is what
        reports the line count, and the tooltip still names it. This only
        flags; nothing is truncated or auto-wrapped.
        """

        lines = caption.text.split("\n")
        too_many_lines = len(lines) > settings.MAX_SUBTITLE_LINES

        counts = []

        for line in lines:
            length = len(line)
            exceeded = length > settings.CHARACTER_LIMIT

            tooltip = (
                f"Guideline: max {settings.CHARACTER_LIMIT} characters per line, "
                f"{settings.MAX_SUBTITLE_LINES} lines."
            )
            if exceeded:
                tooltip += f" This line is {length} characters."
            if too_many_lines:
                tooltip += f" {len(lines)} lines in this caption."

            counts.append(
                {
                    "length": length,
                    "exceeded": exceeded,
                    "tooltip": tooltip,
                }
            )

        return counts

    def refresh_display(
        self, force_full_refresh: bool = False, specific_indices: set = None
    ) -> None:
        """
        Ask the document editor to redraw.

        force_full_refresh and specific_indices are accepted rather than
        removed so every existing call site -- splits, merges, undo, the
        review toggle -- keeps working unchanged: the component always
        redraws every block regardless, and NiceGUI's own diffing is what
        keeps that cheap, not this distinction.
        """

        if self.render_override is not None:
            self.render_override()

        # Splits, merges and deletions all land here, and each of them can
        # change how many words are flagged.
        self.update_flagged_count()


    def collect_validation_issues(self) -> list:
        """
        Every issue in the caption list, one entry per caption that has any.

        Grouped by caption rather than accumulated in check order, so a
        caption with four problems is one thing to look at rather than four
        lines scattered through the report, and separated into errors and
        warnings: an empty caption or one ending before it starts is broken,
        while a line over the guideline or a caption gone in half a second is
        readable text that a viewer will struggle with. Both are worth
        reporting; only one of them means the file is wrong.

        Each entry is {"caption", "errors", "warnings"}, ordered by the
        caption's own position in the list. `is_valid` is set here as it
        always was, so the editor's own red rules follow from the same pass.
        """

        issues: dict = {}

        def report(caption, message: str, error: bool) -> None:
            entry = issues.get(caption.index)

            if entry is None:
                entry = {"caption": caption, "errors": [], "warnings": []}
                issues[caption.index] = entry

            entry["errors" if error else "warnings"].append(message)
            caption.is_valid = False

        for caption in self.captions:
            if not caption.text.strip():
                report(caption, "No text.", error=True)

            if caption.get_end_seconds() < caption.get_start_seconds():
                report(caption, "Ends before it starts.", error=True)

            # Subtitle guidelines. A transcription's blocks are a speaker's
            # whole turn, with no length to keep to and no viewer reading
            # them off a screen.
            if self.data_format == "srt":
                lines = caption.text.split("\n")

                for number, line in enumerate(lines, start=1):
                    if len(line) > settings.CHARACTER_LIMIT:
                        report(
                            caption,
                            f"Line {number} is {len(line)} characters "
                            f"(max {settings.CHARACTER_LIMIT}).",
                            error=False,
                        )

                if len(lines) > settings.MAX_SUBTITLE_LINES:
                    report(
                        caption,
                        f"{len(lines)} lines "
                        f"(max {settings.MAX_SUBTITLE_LINES}).",
                        error=False,
                    )

                seconds = caption.get_end_seconds() - caption.get_start_seconds()

                # Only worth saying about a caption that has a duration at
                # all -- one ending before it starts is already reported as
                # the error it is, and does not need a second line saying it
                # is also short.
                if 0 <= seconds < settings.MIN_CAPTION_SECONDS:
                    report(
                        caption,
                        f"On screen for {seconds:.2f}s "
                        f"(min {settings.MIN_CAPTION_SECONDS}s).",
                        error=False,
                    )

        # Timing against the neighbours. Two captions sharing a start time
        # are reported once, as the duplicate they are -- the old third
        # check ("multiple captions start at the same time") said the same
        # thing again in different words, so one pair of captions could be
        # reported three times over.
        seen_times = set()

        for caption in self.captions:
            times = (caption.start_time, caption.end_time)

            if times in seen_times:
                report(caption, "Same timing as an earlier caption.", error=True)

            seen_times.add(times)

        for current, following in zip(self.captions, self.captions[1:]):
            if current.get_end_seconds() > following.get_start_seconds():
                report(
                    current,
                    f"Overlaps caption #{following.index}.",
                    error=True,
                )
                report(
                    following,
                    f"Overlaps caption #{current.index}.",
                    error=True,
                )

        return [issues[index] for index in sorted(issues)]

    def validate_captions(self):
        """
        Check the captions and report what came back, caption by caption.
        """

        changed_indices = {
            caption.index for caption in self.captions if not caption.is_valid
        }

        for caption in self.captions:
            caption.is_valid = True

        issues = self.collect_validation_issues()
        changed_indices |= {entry["caption"].index for entry in issues}

        # Refresh display to show validation state changes - only update changed captions
        self.refresh_display(
            specific_indices=changed_indices if changed_indices else None
        )

        self.show_validation_report(issues)

    def show_validation_report(self, issues: list) -> None:
        """
        The report itself. Every caption listed is a row that jumps to it --
        finding "#47" by scrolling for it is the one thing a reader has to do
        with this report, so the report does it.
        """

        error_count = sum(1 for entry in issues if entry["errors"])
        warning_count = len(issues) - error_count

        with ui.dialog() as dialog:
            with ui.card().classes("p-6").style(
                "max-width: 700px; min-width: 500px; max-height: 90vh; overflow-y: auto;"
            ):
                # Header
                with ui.row().classes("w-full items-center justify-between mb-4"):
                    ui.label("Subtitle validation").classes("text-h5 font-bold")
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense color=grey-7"
                    )

                ui.separator().classes("mb-4")

                if issues:
                    with ui.card().classes("border-l-4 p-4 mb-4 w-full").style(
                        "background-color: var(--color-status-error-bg); "
                        "border-left-color: var(--color-status-error-border);"
                    ):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("error", size="md").style(
                                "color: var(--color-text-danger);"
                            )
                            ui.label(
                                self.validation_summary(error_count, warning_count)
                            ).classes("text-h6 font-semibold")

                    with ui.column().classes("w-full gap-2 max-h-96 overflow-y-auto"):
                        for entry in issues:
                            self.validation_row(entry, dialog)
                else:
                    with ui.card().classes("border-l-4 p-4 w-full").style(
                        "background-color: var(--color-status-ok-bg); "
                        "border-left-color: var(--color-status-ok-border);"
                    ):
                        with ui.row().classes("items-center gap-3"):
                            ui.icon("check_circle", size="lg").style(
                                "color: var(--color-status-ok-border);"
                            )
                            with ui.column().classes("gap-1"):
                                ui.label("All captions are valid!").classes(
                                    "text-h6 font-semibold"
                                )
                                ui.label(
                                    f"{self.caption_count(len(self.captions))} checked"
                                ).classes("text-body2 text-theme-secondary")

                # What was checked, so the report can be read without going
                # looking for the numbers behind it.
                if self.data_format == "srt":
                    ui.label(
                        f"Guidelines: max {settings.CHARACTER_LIMIT} characters "
                        f"per line, max {settings.MAX_SUBTITLE_LINES} lines, "
                        f"at least {settings.MIN_CAPTION_SECONDS}s on screen."
                    ).classes("text-caption text-theme-muted mt-4")

                # Footer
                with ui.row().classes("w-full justify-end mt-4").style(
                    "position: sticky; bottom: -24px; background-color: var(--color-bg-surface); padding-bottom: 8px; z-index: 1;"
                ):
                    ui.button("Close", on_click=dialog.close).props("color=primary")

            dialog.open()

    @staticmethod
    def caption_count(count: int) -> str:
        return f"{count} caption" if count == 1 else f"{count} captions"

    def validation_summary(self, error_count: int, warning_count: int) -> str:
        """
        What the report found, counted by kind rather than as one total: an
        error means the file is wrong, a warning means a viewer will
        struggle, and a reader deciding what to do next needs them apart.
        """

        parts = []

        if error_count:
            parts.append(f"{self.caption_count(error_count)} with errors")
        if warning_count:
            parts.append(f"{self.caption_count(warning_count)} with warnings")

        return ", ".join(parts)

    def validation_row(self, entry: dict, dialog) -> None:
        """
        One caption and everything found in it, as a row that jumps to it.
        """

        caption = entry["caption"]
        errors = entry["errors"]

        def jump() -> None:
            dialog.close()
            self.select_caption(caption)

        with ui.row().classes(
            "items-start gap-2 w-full validation-issue"
        ).on("click", jump):
            colour = (
                "var(--color-text-danger)"
                if errors
                else "var(--color-severity-maint-icon)"
            )
            ui.icon("error" if errors else "warning", size="sm").style(
                f"color: {colour}; margin-top: 2px;"
            )

            with ui.column().classes("gap-0"):
                ui.label(f"Caption #{caption.index}").classes(
                    "text-body2 font-semibold"
                )

                for message in errors + entry["warnings"]:
                    ui.label(message).classes("text-body2 text-theme-secondary")

    def keyboard_shortcuts_title(self) -> str:
        """
        What the dialog calls itself: a reader has subtitles open or a
        transcription open, never both, and the list inside is worded for
        whichever it is.
        """

        if self.data_format == "srt":
            return "Subtitle keyboard shortcuts"

        return "Transcription keyboard shortcuts"

    def keyboard_shortcut_groups(self) -> list:
        """
        The dialog's own contents, as (group, [(action, keys), ...]).
        Separate from the dialog that draws them so the wording can be
        checked without a UI, the same way collect_validation_issues is
        separate from the report that shows it.
        """

        # One dialog, worded for whichever format is open: a reader editing
        # subtitles is working on captions and a reader editing a
        # transcription on paragraphs, and a list that says "block" says it
        # to neither of them. The keys themselves match all the way through
        # -- split, line break, the word moves, merge and delete mean the
        # same thing in each -- so the two lists differ in their nouns and
        # in the two rows subtitles alone have: add-after, the keyboard's
        # half of a caption row a transcription does not have, and validate.
        # Each list is deliberately a closed set of the keys that format
        # offers, and nothing else: Backspace at the start of a block still
        # merges it and the caption row's icons still do what they do, but
        # neither is a shortcut worth naming here. Enter itself
        # matches: Enter starts a new caption (a new paragraph, in a
        # transcription) and Shift+Enter breaks the line inside the one
        # being edited -- what Enter does in a document, and what
        # Shift+Enter does in most things that have both. Ctrl/Cmd+Enter
        # still splits too, which is what it meant when Enter itself was the
        # line break.
        subtitles = self.data_format == "srt"

        editing = (
            [
                ("Split caption at cursor", "Enter"),
                ("New line", "Shift + Enter"),
                ("Move first word to previous caption", "Ctrl/⌘ + ↑"),
                ("Move last word to next caption", "Ctrl/⌘ + ↓"),
                ("Merge with next", "Ctrl + M"),
                ("Add caption after", "Ctrl/⌘ + Shift + Enter"),
                ("Delete caption", "Ctrl + D"),
            ]
            if subtitles
            else [
                ("Split paragraph at cursor", "Enter"),
                ("New line", "Shift + Enter"),
                ("Move first word to previous paragraph", "Ctrl/⌘ + ↑"),
                ("Move last word to next paragraph", "Ctrl/⌘ + ↓"),
                ("Merge with next", "Ctrl + M"),
                ("Delete paragraph", "Ctrl + D"),
            ]
        )

        shortcut_groups = [
            ("Editing", editing),
            (
                "File operations",
                [
                    ("Save file", "Ctrl/⌘ + S"),
                    ("Export file", "Ctrl/⌘ + E"),
                    ("Find", "Ctrl/⌘ + F"),
                ]
                # Validate is a subtitle's alone: it checks the line-length
                # and line-count guidelines only subtitles are held to.
                + ([("Validate captions", "Ctrl + Shift + V")] if subtitles else []),
            ),
            (
                "History",
                [
                    ("Undo", "Ctrl/⌘ + Z"),
                    ("Redo", "Ctrl + Y / ⌘ + Shift + Z"),
                ],
            ),
            (
                "Transport",
                [
                    ("Play/Pause", "Ctrl + Space"),
                ],
            ),
        ]

        return shortcut_groups

    def show_keyboard_shortcuts(self, open_window: Optional[bool] = False) -> None:
        """
        Show keyboard shortcuts dialog.
        """

        shortcut_groups = self.keyboard_shortcut_groups()

        with ui.dialog() as dialog:
            with ui.card().classes("w-2/3 max-w-2xl").style(
                "padding: 24px; max-height: 90vh; overflow-y: auto;"
            ):
                ui.label(self.keyboard_shortcuts_title()).classes(
                    "text-h5 mb-4 font-bold"
                )

                with ui.column().classes("w-full gap-4"):
                    for group_name, shortcuts in shortcut_groups:
                        ui.label(group_name).classes(
                            "text-subtitle1 font-semibold mt-2"
                        )
                        with ui.column().classes("w-full gap-1 ml-4"):
                            for action, keys in shortcuts:
                                with ui.row().classes(
                                    "justify-between w-full items-center"
                                ):
                                    ui.label(action).classes("text-body1")
                                    # The keys themselves are the point of
                                    # the row, so they are drawn in the same
                                    # ink as the action beside them rather
                                    # than the muted grey a chip inherits --
                                    # a border says "key" without taking the
                                    # contrast to do it.
                                    ui.label(keys).classes(
                                        "text-body2 font-mono px-2 py-1 rounded"
                                    ).style(
                                        "background-color: var(--color-bg-surface-alt); "
                                        "color: var(--color-text-primary); "
                                        "border: 1px solid var(--color-border);"
                                    )

                # The footer sits on top of the list as it scrolls under it,
                # so it needs a fill of its own -- the card's own, not the
                # grey it had, which read as a separate panel stuck to the
                # bottom of a white dialog.
                with ui.row().classes("w-full justify-end mt-4").style(
                    "position: sticky; bottom: -24px; "
                    "background-color: var(--color-bg-surface); "
                    "padding-bottom: 8px; z-index: 1;"
                ):
                    ui.button("Close").props("flat color=primary").on(
                        "click", dialog.close
                    )

        if open_window:
            dialog.open()
        else:
            ui.button("Shortcuts", icon="keyboard").props("flat").classes(
                "editor-btn editor-toolbar-btn"
            ).on("click", lambda: dialog.open()).classes("button-open-search")

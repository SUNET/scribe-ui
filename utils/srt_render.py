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
from utils.common import focus_element
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

        Each entry is {"caption", "errors", "warnings", "items"}, ordered by
        the caption's own position in the list. `errors` and `warnings` are
        the one-line messages; `items` holds the same issues one by one for
        the validation panel (utils/validation_panel.py), each with a short
        heading naming the rule ("Line exceeds 42 characters"), a detail
        saying how this caption breaks it ("Line 2 has 48 characters.") and
        the character offset the caret should land at to fix it, and which
        rule it breaks (`rule`, one of RULE_LABELS in validation_panel.py),
        for the panel to show some kinds and not others -- see
        validation_items(). `is_valid` is set here as it always was, so the
        editor's own red rules follow from the same pass.
        """

        issues: dict = {}

        def report(
            caption,
            message: str,
            error: bool,
            title: str,
            detail: str,
            rule: str,
            offset: int = 0,
        ) -> None:
            entry = issues.get(caption.index)

            if entry is None:
                entry = {
                    "caption": caption,
                    "errors": [],
                    "warnings": [],
                    "items": [],
                }
                issues[caption.index] = entry

            entry["errors" if error else "warnings"].append(message)
            entry["items"].append(
                {
                    "caption": caption,
                    "error": error,
                    "title": title,
                    "detail": detail,
                    "rule": rule,
                    "offset": offset,
                }
            )
            caption.is_valid = False
            caption.has_error = caption.has_error or error

        for caption in self.captions:
            if not caption.text.strip():
                report(
                    caption,
                    "No text.",
                    error=True,
                    title="No text",
                    detail="The caption is empty.",
                    rule="empty",
                )

            if caption.get_end_seconds() < caption.get_start_seconds():
                report(
                    caption,
                    "Ends before it starts.",
                    error=True,
                    title="Ends before it starts",
                    rule="order",
                    detail=(
                        f"Starts at {caption.start_time}, "
                        f"ends at {caption.end_time}."
                    ),
                )

            # Subtitle guidelines. A transcription's blocks are a speaker's
            # whole turn, with no length to keep to and no viewer reading
            # them off a screen.
            if self.data_format == "srt":
                lines = caption.text.split("\n")
                line_start = 0

                for number, line in enumerate(lines, start=1):
                    if len(line) > settings.CHARACTER_LIMIT:
                        report(
                            caption,
                            f"Line {number} is {len(line)} characters "
                            f"(max {settings.CHARACTER_LIMIT}).",
                            error=False,
                            title=(
                                f"Line exceeds {settings.CHARACTER_LIMIT} "
                                "characters"
                            ),
                            detail=f"Line {number} has {len(line)} characters.",
                            rule="length",
                            # Where the line runs past the guideline, which
                            # is where the break usually wants to go.
                            offset=line_start + settings.CHARACTER_LIMIT,
                        )
                    line_start += len(line) + 1

                if len(lines) > settings.MAX_SUBTITLE_LINES:
                    report(
                        caption,
                        f"{len(lines)} lines "
                        f"(max {settings.MAX_SUBTITLE_LINES}).",
                        error=False,
                        title=f"More than {settings.MAX_SUBTITLE_LINES} lines",
                        detail=f"It has {len(lines)} lines.",
                        rule="lines",
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
                        title=(
                            f"Shorter than {settings.MIN_CAPTION_SECONDS}s "
                            "on screen"
                        ),
                        detail=f"On screen for {seconds:.2f}s.",
                        rule="short",
                    )

        # Timing against the neighbours. Two captions sharing a start time
        # are reported once, as the duplicate they are -- the old third
        # check ("multiple captions start at the same time") said the same
        # thing again in different words, so one pair of captions could be
        # reported three times over.
        seen_times: dict = {}

        for caption in self.captions:
            times = (caption.start_time, caption.end_time)

            if times in seen_times:
                report(
                    caption,
                    "Same timing as an earlier caption.",
                    error=True,
                    title="Same timing as an earlier caption",
                    rule="duplicate",
                    detail=(
                        "Starts and ends at the same time as caption "
                        f"{seen_times[times].index}."
                    ),
                )
            else:
                seen_times[times] = caption

        for current, following in zip(self.captions, self.captions[1:]):
            if current.get_end_seconds() > following.get_start_seconds():
                report(
                    current,
                    f"Overlaps caption #{following.index}.",
                    error=True,
                    title="Overlapping timestamps",
                    rule="overlap",
                    detail=f"Overlaps caption {following.index}.",
                )
                report(
                    following,
                    f"Overlaps caption #{current.index}.",
                    error=True,
                    title="Overlapping timestamps",
                    rule="overlap",
                    detail=f"Overlaps caption {current.index}.",
                )

        return [issues[index] for index in sorted(issues)]

    @staticmethod
    def validation_items(issues: list) -> list:
        """
        The issues one by one, in caption order, for the validation panel to
        step through with Previous and Next. A caption with several issues
        comes up once for each -- the panel reviews issues, not captions.
        """

        return [item for entry in issues for item in entry["items"]]

    def run_validation(self) -> list:
        """
        Check every caption again and redraw their markings; answer the
        issues (as collect_validation_issues does). What Validate and the
        panel's "Check again" share: the whole list is always checked,
        since a fix to one caption's timing can clear or cause an overlap
        with its neighbour.
        """

        changed_indices = {
            caption.index for caption in self.captions if not caption.is_valid
        }

        for caption in self.captions:
            caption.is_valid = True
            caption.has_error = False

        issues = self.collect_validation_issues()
        changed_indices |= {entry["caption"].index for entry in issues}

        # Refresh display to show validation state changes - only update changed captions
        self.refresh_display(
            specific_indices=changed_indices if changed_indices else None
        )

        return issues

    def revalidate_items(self) -> list:
        """
        The panel's "Check again": every issue, freshly checked, one by one.
        """

        return self.validation_items(self.run_validation())

    def validate_captions(self):
        """
        Check the captions and report what came back, caption by caption.
        """

        issues = self.run_validation()

        # The docked panel under the video (issue #138) when the page has
        # one; the dialog otherwise.
        panel = getattr(self, "validation_panel", None)
        if panel is not None:
            panel.show(self.validation_items(issues), len(self.captions))
        else:
            self.show_validation_report(issues)

    def show_validation_report(self, issues: list) -> None:
        """
        The report itself. Every caption listed is a row that jumps to it --
        finding "#47" by scrolling for it is the one thing a reader has to do
        with this report, so the report does it.
        """

        error_count = sum(1 for entry in issues if entry["errors"])
        warning_count = len(issues) - error_count

        with ui.dialog().props('aria-label="Subtitle validation"') as dialog:
            with ui.card().classes("p-6").style(
                "max-width: 700px; min-width: 500px; max-height: 90vh; overflow-y: auto;"
            ):
                # Header
                with ui.row().classes("w-full items-center justify-between mb-4"):
                    ui.label("Subtitle validation").classes("text-h5 font-bold")
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense color=grey-7 aria-label='Close validation dialog'"
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
        shortcut_title = self.keyboard_shortcuts_title()

        with ui.dialog().props(f'aria-label="{shortcut_title}"') as dialog:
            with ui.card().classes("w-2/3 max-w-2xl").style(
                "padding: 24px; max-height: 90vh; overflow-y: auto;"
            ):
                ui.label(shortcut_title).classes(
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
                    close_button = ui.button("Close").props(
                        "flat color=primary"
                    ).on("click", dialog.close)

        def focus_close_button_on_open(event) -> None:
            # The dialog is opened two ways below (open_window, and the
            # toolbar button), so focus is moved here, on the dialog's
            # own value change (on_value_change, which also fires for a
            # server-side open(); "update:model-value" is only the browser's
            # own report and never comes for one), rather than duplicated at each open()
            # call site. Without this, focus stays on whatever
            # triggered the open -- the toolbar button, or nowhere in
            # particular when opened programmatically -- and a Space
            # keypress meant for a control inside the dialog instead
            # falls through to the browser's native video play/pause
            # shortcut (see F-74).
            if event.sender.value:
                focus_element(close_button)

        dialog.on_value_change(focus_close_button_on_open)

        if open_window:
            dialog.open()
        else:
            # An icon: looked up now and then, not used while working.
            ui.button(icon="keyboard").props(
                'flat aria-label="Keyboard shortcuts"'
            ).classes("editor-btn editor-icon").on(
                "click", lambda: dialog.open()
            ).tooltip("Keyboard shortcuts")

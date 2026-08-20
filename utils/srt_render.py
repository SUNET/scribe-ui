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
        alone has drifted past the guideline -- over CHARACTER_LIMIT, or the
        caption has more than MAX_SUBTITLE_LINES of them, in which case every
        line's count is flagged, not only the one that is individually long.
        This only flags it, the same as "Validate" does; nothing is
        truncated or auto-wrapped.
        """

        lines = caption.text.split("\n")
        too_many_lines = len(lines) > settings.MAX_SUBTITLE_LINES

        counts = []

        for line in lines:
            length = len(line)
            line_too_long = length > settings.CHARACTER_LIMIT

            tooltip = (
                f"Guideline: max {settings.CHARACTER_LIMIT} characters per line, "
                f"{settings.MAX_SUBTITLE_LINES} lines."
            )
            if line_too_long:
                tooltip += f" This line is {length} characters."
            if too_many_lines:
                tooltip += f" {len(lines)} lines in this caption."

            counts.append(
                {
                    "length": length,
                    "exceeded": line_too_long or too_many_lines,
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


    def validate_captions(self):
        """
        Validate captions for overlapping times, empty text, and character limits.
        """
        # Track which captions changed validity
        changed_indices = set()

        # Reset all captions to valid first
        for caption in self.captions:
            if not caption.is_valid:
                changed_indices.add(caption.index)
            caption.is_valid = True

        errors = []
        seen_times = set()
        start_times = {}
        errorenous_captions = []

        for caption in self.captions:
            # Check for empty text
            if not caption.text.strip():
                errors.append(f"Caption #{caption.index} has no text.")
                caption.is_valid = False
                errorenous_captions.append(caption)
                changed_indices.add(caption.index)

            # Check character limit per line and line count (only for SRT format)
            if self.data_format == "srt":
                lines = caption.text.split("\n")

                for line in lines:
                    if len(line) > settings.CHARACTER_LIMIT:
                        errors.append(
                            f"Caption #{caption.index} has a line with {len(line)} characters (max {settings.CHARACTER_LIMIT})."
                        )
                        caption.is_valid = False
                        if caption not in errorenous_captions:
                            errorenous_captions.append(caption)
                        changed_indices.add(caption.index)
                        break

                if len(lines) > settings.MAX_SUBTITLE_LINES:
                    errors.append(
                        f"Caption #{caption.index} has {len(lines)} lines (max {settings.MAX_SUBTITLE_LINES})."
                    )
                    caption.is_valid = False
                    if caption not in errorenous_captions:
                        errorenous_captions.append(caption)
                    changed_indices.add(caption.index)

            if (caption.start_time, caption.end_time) in seen_times:
                errors.append(f"Caption #{caption.index} has duplicate timestamp.")
                caption.is_valid = False
                if caption not in errorenous_captions:
                    errorenous_captions.append(caption)
                changed_indices.add(caption.index)

            seen_times.add((caption.start_time, caption.end_time))

            if caption.start_time in start_times:
                start_times[caption.start_time].append(caption.index)
            else:
                start_times[caption.start_time] = [caption.index]

            if caption.get_end_seconds() < caption.get_start_seconds():
                caption.is_valid = False
                if caption not in errorenous_captions:
                    errorenous_captions.append(caption)
                changed_indices.add(caption.index)
                errors.append(
                    f"Caption #{caption.index} has end time before start time."
                )

        # Check for overlapping times
        for i in range(len(self.captions) - 1):
            current = self.captions[i]
            next_caption = self.captions[i + 1]

            if current.get_end_seconds() > next_caption.get_start_seconds():
                current.is_valid = False
                next_caption.is_valid = False
                if current not in errorenous_captions:
                    errorenous_captions.append(current)
                if next_caption not in errorenous_captions:
                    errorenous_captions.append(next_caption)
                changed_indices.add(current.index)
                changed_indices.add(next_caption.index)
                errors.append(
                    f"Caption #{current.index} overlaps with caption #{next_caption.index}."
                )

        # Find start times with multiple captions
        for start_time, indices in start_times.items():
            if len(indices) > 1:
                errors.append(
                    f"Multiple captions start at the same time: {', '.join(map(str, indices))}."
                )

                for cap in self.captions:
                    if cap.index in indices:
                        if cap not in errorenous_captions:
                            errorenous_captions.append(cap)
                        cap.is_valid = False
                        changed_indices.add(cap.index)

        # Find blocks which are shorter than 0.8 seconds
        for caption in self.captions:
            caption_length = caption.get_end_seconds() - caption.get_start_seconds()
            if caption_length < 0.8:
                errors.append(
                    f"Caption #{caption.index} is very short ({caption_length:.2f} seconds)."
                )
                if caption not in errorenous_captions:
                    errorenous_captions.append(caption)
                caption.is_valid = False
                changed_indices.add(caption.index)

        # Refresh display to show validation state changes - only update changed captions
        self.refresh_display(
            specific_indices=changed_indices if changed_indices else None
        )

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

                if errors:
                    # Error summary
                    with ui.card().classes("border-l-4 p-4 mb-4").style(
                        "background-color: var(--color-status-error-bg); border-left-color: var(--color-status-error-border);"
                    ):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("error", size="md").style(
                                "color: var(--color-text-danger);"
                            )
                            ui.label(
                                f"{len(set(errorenous_captions))} caption(s) with issues found"
                            ).classes("text-h6 font-semibold")

                    # Error list
                    with ui.column().classes("w-full gap-2 max-h-96 overflow-y-auto"):
                        for error in errors:
                            with ui.row().classes("items-start gap-2"):
                                ui.icon("warning", size="sm").style(
                                    "color: var(--color-text-danger); margin-top: 4px;"
                                )
                                ui.label(error).classes("text-body2")
                else:
                    # Success message
                    with ui.card().classes("border-l-4 p-4").style(
                        "background-color: var(--color-status-ok-bg); border-left-color: var(--color-status-ok-border);"
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
                                    f"{len(self.captions)} caption(s) checked"
                                ).classes("text-body2 text-theme-secondary")

                # Footer
                with ui.row().classes("w-full justify-end mt-4").style(
                    "position: sticky; bottom: -24px; background-color: var(--color-bg-surface); padding-bottom: 8px; z-index: 1;"
                ):
                    ui.button("Close", on_click=dialog.close).props("color=primary")

            dialog.open()


    def show_keyboard_shortcuts(self, open_window: Optional[bool] = False) -> None:
        """
        Show keyboard shortcuts dialog.
        """

        # One editor now, for both formats, but Enter itself differs: a
        # subtitle is short enough that the reader controls its own line
        # breaks, which is a far more frequent thing to want there than
        # starting a new timed cue, so bare Enter is a line break and
        # splitting moves to Ctrl/Cmd+Enter. Running speech has no manual
        # line breaks, so a transcription keeps plain Enter for splitting.
        subtitles = self.data_format == "srt"

        shortcut_groups = [
            (
                "Editing",
                (
                    [
                        ("New line in the caption", "Enter"),
                        ("Split caption at cursor", "Ctrl/⌘ + Enter"),
                        ("Join with the caption above", "Backspace at the start"),
                        ("Join with the caption below", "Delete at the end"),
                        ("New caption after this one", "Ctrl/⌘ + Enter at the end"),
                        ("Split caption at cursor (mouse)", "Click its split icon"),
                        ("Merge with the caption below (mouse)", "Click its merge icon"),
                        ("Add a caption after this one", "Click its + icon"),
                        ("Delete a caption", "Click its trash icon"),
                    ]
                    if subtitles
                    else [
                        ("Split block at cursor", "Enter"),
                        ("Join with the block above", "Backspace at the start"),
                        ("Join with the block below", "Delete at the end"),
                        ("New block after this one", "Enter at the end"),
                    ]
                ),
            ),
            (
                "File Operations",
                [
                    ("Save file", "Ctrl/⌘ + S"),
                    ("Export file", "Ctrl/⌘ + E"),
                    ("Find", "Ctrl/⌘ + F"),
                ],
            ),
            (
                "History",
                [
                    ("Undo", "Ctrl/⌘ + Z"),
                    ("Redo", "Ctrl + Y / ⌘ + Shift + Z"),
                ],
            ),
            (
                "Video",
                [
                    ("Play/Pause", "Ctrl + Space"),
                ],
            ),
        ]

        with ui.dialog() as dialog:
            with ui.card().classes("w-2/3 max-w-2xl").style(
                "padding: 24px; max-height: 90vh; overflow-y: auto;"
            ):
                ui.label("Keyboard shortcuts").classes("text-h5 mb-4 font-bold")

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
                                    ui.label(keys).classes(
                                        "text-body2 font-mono px-2 py-1 rounded"
                                    ).style(
                                        "background-color: var(--color-bg-surface-hover);"
                                    )

                with ui.row().classes("w-full justify-end mt-4").style(
                    "position: sticky; bottom: -24px; background-color: var(--color-bg-surface-alt); padding-bottom: 8px; z-index: 1;"
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

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
Drawing the caption list, and the dialogs that sit alongside it.

Every caption is a card: prose until selected, a set of fields and actions
once it is. refresh_display rebuilds only what changed, so typing in one
caption does not redraw the whole transcription.
"""

from typing import Optional

from nicegui import ui

from utils.caption import SRTCaption
from utils.settings import get_settings

settings = get_settings()

CHARACTER_LIMIT_EXCEEDED_COLOR = "text-red"


class RenderMixin:
    """
    Caption cards, the caption list, validation and the shortcut help.
    """

    def create_caption_input(self, caption: SRTCaption):
        """
        The text area for an open caption, with the review highlighting shown
        behind it.

        A text area cannot render markup, so the highlights are painted on a
        layer underneath: that layer holds the same text in a transparent
        colour and shows only the highlight boxes, while the text area sits on
        top with a transparent background. Keeping the text in a real text
        area is the point -- caret, selection, undo, IME and the caret offset
        the split shortcut reads all keep working untouched.

        The two layers must agree on every metric that affects where a
        character lands, so both take their font, padding and wrapping from
        the same rules in styles.py rather than inheriting them.
        """

        with ui.element("div").classes("caption-editor w-full"):
            backdrop = ui.html(
                self.review_backdrop_html(caption, caption.text), sanitize=False
            ).classes("caption-highlights")
            backdrop.props('aria-hidden=true')

            text_area = (
                ui.textarea(value=caption.text)
                .classes("caption-entry w-full")
                # autogrow rather than a fixed height: a text area that never
                # scrolls cannot scroll out of step with the layer behind it.
                .props("borderless autogrow")
            )

            def repaint(event) -> None:
                # The new value comes on the event itself. Reading it back off
                # the element would race NiceGUI's own listener for the same
                # event and could repaint one keystroke behind.
                value = event.args

                if not isinstance(value, str):
                    value = event.sender.value or ""

                backdrop.set_content(self.review_backdrop_html(caption, value))

            # Throttled, so the highlighting follows typing without a round
            # trip per keystroke. The authoritative pass runs on blur.
            text_area.on("update:model-value", repaint, throttle=0.3)

        return text_area

    def create_caption_card(self, caption: SRTCaption) -> ui.card:
        """
        Create a visual card for a caption.
        """

        card_class = "cursor-pointer border-0 transition-all duration-200 w-full"

        if not caption.is_valid:
            card_class += " caption-card-invalid"
        elif caption.is_selected and caption.is_highlighted:
            # Slightly darker yellow background
            card_class += " shadow-lg caption-card-selected-highlighted"
        elif caption.is_selected:
            card_class += " shadow-lg"
        elif caption.is_highlighted:
            card_class += " caption-card-highlighted"
        else:
            card_class += " hover:shadow-md shadow-none"

        # Create container for this caption that persists
        container = ui.column().classes("w-full")

        with container:
            with ui.card().classes(card_class) as card:
                # Caption text (editable when selected)
                if caption.is_selected:
                    with ui.row().classes("w-full justify-between") as action_row:
                        action_row.props("id=action_row")
                        ui.label(f"#{caption.index}").classes(
                            "font-bold text-sm text-theme-muted"
                        )

                        if self.data_format == "txt":
                            self.speakers.add(caption.speaker)
                            speaker_select = ui.select(
                                options=list(self.speakers),
                                value=caption.speaker,
                                with_input=True,
                                label="Speaker",
                                new_value_mode="add",
                            )
                        else:
                            speaker_select = None

                        start_input = ui.input("", value=caption.start_time).props(
                            "dense borderless"
                        )
                        end_input = ui.input("", value=caption.end_time).props(
                            "dense borderless"
                        )

                    start_input.on(
                        "blur",
                        lambda: self.update_caption_timing(
                            caption, start_input.value, end_input.value
                        ),
                    )
                    end_input.on(
                        "blur",
                        lambda: self.update_caption_timing(
                            caption, start_input.value, end_input.value
                        ),
                    )

                    text_area = self.create_caption_input(caption)
                    text_area.on(
                        "blur",
                        lambda e: self.update_caption_text(caption, e.sender.value),
                    )

                    # Only one caption is open at a time, so this is the text
                    # area the caret lives in when splitting.
                    self._active_text_area = text_area

                    # Action buttons
                    with ui.row().classes("w-full justify-between"):
                        split_button = ui.button("Split", icon="call_split").props(
                            "flat dense"
                        ).classes("editor-btn editor-caption-btn")
                        split_button.on(
                            "click", lambda: self.split_caption_at_cursor(caption)
                        )
                        with split_button:
                            ui.tooltip("Split at the cursor (Ctrl/⌘ + Enter)")
                        ui.button("Merge prev", icon="merge_type").props(
                            "flat dense"
                        ).classes("editor-btn editor-caption-btn").on(
                            "click",
                            lambda: (
                                self.merge_with_previous(caption)
                                if self.captions.index(caption) > 0
                                else None
                            ),
                        )
                        ui.button("Merge next", icon="merge_type").props(
                            "flat dense"
                        ).classes("editor-btn editor-caption-btn").on(
                            "click",
                            lambda: (
                                self.merge_with_next(caption)
                                if self.captions.index(caption) < len(self.captions) - 1
                                else None
                            ),
                        )

                        ui.button("Close").props("flat dense").classes(
                            "editor-btn editor-caption-btn caption-close"
                        ).on(
                            "click",
                            lambda: self.select_caption(
                                caption,
                                speaker_select,
                                True,
                                new_text=text_area.value,
                            ),
                        )

                        ui.button("Add").props("flat dense").classes(
                            "editor-btn editor-caption-btn"
                        ).on("click", lambda: self.add_caption_after(caption))

                        ui.button("Delete").props("flat dense").classes(
                            "editor-btn editor-caption-btn"
                        ).style("color: var(--color-text-danger) !important;").on(
                            "click", lambda: self.remove_caption(caption)
                        )
                else:
                    # Show text with search highlighting
                    if caption.is_highlighted and self.search_term:
                        highlighted_text = self.get_highlighted_text(caption.text)

                        with ui.row():
                            ui.label(f"#{caption.index}").classes("font-bold text-sm")

                            if self.data_format == "txt":
                                ui.label(f"{caption.speaker}:").classes(
                                    "font-bold text-sm"
                                )
                        ui.label(f"{caption.start_time} - {caption.end_time}").classes(
                            "text-sm text-theme-muted"
                        )

                        ui.html(highlighted_text, sanitize=False).classes(
                            "text-sm leading-relaxed whitespace-pre-wrap"
                        )
                    else:
                        with ui.row().classes("w-full justify-between"):
                            with ui.row():
                                ui.label(f"#{caption.index}").classes(
                                    "font-bold text-sm"
                                )

                                if self.data_format == "txt":
                                    ui.label(f"{caption. speaker}:").classes(
                                        "font-bold text-sm"
                                    )
                            ui.label(
                                f"{caption.start_time} - {caption.end_time}"
                            ).classes("text-sm text-theme-muted")
                        with ui.row().classes("w-full justify-between items-end"):
                            review_html = (
                                self.get_review_html(caption)
                                if self.show_uncertain_words
                                else None
                            )

                            if review_html:
                                ui.html(review_html, sanitize=False).classes(
                                    "text-sm leading-relaxed whitespace-pre-wrap"
                                )
                            else:
                                ui.label(caption.text).classes(
                                    "text-sm leading-relaxed whitespace-pre-wrap"
                                )
                            text_color = "text-theme-muted"

                            tooltip_text = (
                                "Character count."
                                if self.data_format == "txt"
                                else f"Character count.  Max {settings.CHARACTER_LIMIT} per line (guideline)."
                            )

                            lines = caption.text.split("\n")
                            line_lengths = [str(len(x)) for x in lines]

                            # Check for exceeded limit
                            exceeded = self.data_format != "txt" and any(
                                len(x) > settings.CHARACTER_LIMIT for x in lines
                            )
                            if exceeded:
                                text_color = settings.CHARACTER_LIMIT_EXCEEDED_COLOR
                                tooltip_text = f"Character limit of {settings.CHARACTER_LIMIT} exceeded in one or more lines."

                            character_label = "/".join(line_lengths)

                            with ui.row().classes("items-center gap-1"):
                                if exceeded:
                                    ui.icon("warning", size="xs").style(
                                        "color: var(--color-text-danger);"
                                    )
                                with ui.label(f"({character_label})").classes(
                                    f"text-sm text-right {text_color}"
                                ):
                                    ui.tooltip(tooltip_text)

                card.on(
                    "click",
                    lambda: (
                        self.select_caption(caption)
                        if not caption.is_selected
                        else None
                    ),
                )

        # Store reference to container
        self.caption_containers[caption.index] = container
        return card


    def refresh_display(
        self, force_full_refresh: bool = False, specific_indices: set = None
    ) -> None:
        """Refresh the caption display - only recreate if necessary

        Args:
            force_full_refresh: If True, recreate all captions
            specific_indices: If provided, only update these specific caption indices
        """
        if self.main_container:
            if force_full_refresh or not self.caption_containers:
                # Full refresh - clear and recreate everything
                self.main_container.clear()
                self.caption_containers.clear()
                with self.main_container:
                    if not self.captions:
                        ui.label("No captions loaded").classes(
                            "text-theme-muted text-center p-8"
                        )
                    else:
                        for caption in self.captions:
                            self.create_caption_card(caption)
            else:
                # Incremental update - update existing containers
                current_indices = {cap.index for cap in self.captions}
                existing_indices = set(self.caption_containers.keys())

                # Remove containers for deleted captions
                for idx in existing_indices - current_indices:
                    if idx in self.caption_containers:
                        container = self.caption_containers[idx]
                        container.clear()
                        container.delete()
                        del self.caption_containers[idx]

                # Add new captions or update existing ones
                with self.main_container:
                    for caption in self.captions:
                        # Only update if no specific_indices filter, or if index is in the filter
                        should_update = (
                            specific_indices is None
                            or caption.index in specific_indices
                        )

                        if caption.index not in self.caption_containers:
                            # New caption - create it
                            self.create_caption_card(caption)
                        elif should_update:
                            # Existing caption - update it only if needed
                            container = self.caption_containers[caption.index]
                            container.clear()
                            with container:
                                self.update_caption_card_content(caption)

        # Splits, merges and deletions all land here, and each of them can
        # change how many words are flagged.
        self.update_flagged_count()


    def update_caption_card_content(self, caption: SRTCaption) -> None:
        """
        Update the content of an existing caption card
        """
        card_class = "cursor-pointer border-0 transition-all duration-200 w-full"

        if not caption.is_valid:
            card_class += " caption-card-invalid"
        elif caption.is_selected and caption.is_highlighted:
            card_class += " shadow-lg caption-card-selected-highlighted"
        elif caption.is_selected:
            card_class += " shadow-lg"
        elif caption.is_highlighted:
            card_class += " caption-card-highlighted"
        else:
            card_class += " hover:shadow-md shadow-none"

        with ui.card().classes(card_class) as card:
            if caption.is_selected:
                with ui.row().classes("w-full justify-between") as action_row:
                    action_row.props("id=action_row")
                    ui.label(f"#{caption.index}").classes(
                        "font-bold text-sm text-theme-muted"
                    )

                    if self.data_format == "txt":
                        speaker_select = ui.select(
                            options=list(self.speakers),
                            value=caption.speaker,
                            with_input=True,
                            label="Speaker",
                            new_value_mode="add",
                        )
                    else:
                        speaker_select = None

                    start_input = ui.input("", value=caption.start_time).props(
                        "dense borderless"
                    )
                    end_input = ui.input("", value=caption.end_time).props(
                        "dense borderless"
                    )

                start_input.on(
                    "blur",
                    lambda: self.update_caption_timing(
                        caption, start_input.value, end_input.value
                    ),
                )
                end_input.on(
                    "blur",
                    lambda: self.update_caption_timing(
                        caption, start_input.value, end_input.value
                    ),
                )

                text_area = self.create_caption_input(caption)
                text_area.on(
                    "blur", lambda e: self.update_caption_text(caption, e.sender.value)
                )

                self._active_text_area = text_area

                with ui.row().classes("w-full justify-between"):
                    split_button = ui.button("Split", icon="call_split").props(
                        "flat dense"
                    ).classes("editor-btn editor-caption-btn")
                    split_button.on(
                        "click", lambda: self.split_caption_at_cursor(caption)
                    )
                    with split_button:
                        ui.tooltip("Split at the cursor (Ctrl/⌘ + Enter)")
                    ui.button("Merge prev", icon="merge_type").props(
                        "flat dense"
                    ).classes("editor-btn editor-caption-btn").on(
                        "click",
                        lambda: (
                            self.merge_with_previous(caption)
                            if self.captions.index(caption) > 0
                            else None
                        ),
                    )
                    ui.button("Merge next", icon="merge_type").props(
                        "flat dense"
                    ).classes("editor-btn editor-caption-btn").on(
                        "click",
                        lambda: (
                            self.merge_with_next(caption)
                            if self.captions.index(caption) < len(self.captions) - 1
                            else None
                        ),
                    )

                    ui.button("Close").props("flat dense").classes(
                        "editor-btn editor-caption-btn caption-close"
                    ).on(
                        "click",
                        lambda: self.select_caption(
                            caption, speaker_select, True, new_text=text_area.value
                        ),
                    )

                    ui.button("Add").props("flat dense").classes(
                        "editor-btn editor-caption-btn"
                    ).on("click", lambda: self.add_caption_after(caption))

                    ui.button("Delete").props("flat dense").classes(
                        "editor-btn editor-caption-btn"
                    ).style("color: var(--color-text-danger) !important;").on(
                        "click", lambda: self.remove_caption(caption)
                    )
            else:
                if caption.is_highlighted and self.search_term:
                    highlighted_text = self.get_highlighted_text(caption.text)

                    with ui.row():
                        ui.label(f"#{caption.index}").classes("font-bold text-sm")

                        if self.data_format == "txt":
                            ui.label(f"{caption.speaker}:").classes("font-bold text-sm")
                    ui.label(f"{caption.start_time} - {caption.end_time}").classes(
                        "text-sm text-theme-muted"
                    )

                    ui.html(highlighted_text, sanitize=False).classes(
                        "text-sm leading-relaxed whitespace-pre-wrap"
                    )
                else:
                    with ui.row().classes("w-full justify-between"):
                        with ui.row():
                            ui.label(f"#{caption.index}").classes("font-bold text-sm")

                            if self.data_format == "txt":
                                ui.label(f"{caption. speaker}:").classes(
                                    "font-bold text-sm"
                                )
                        ui.label(f"{caption.start_time} - {caption.end_time}").classes(
                            "text-sm text-theme-muted"
                        )
                    with ui.row().classes("w-full justify-between items-end"):
                        review_html = (
                            self.get_review_html(caption)
                            if self.show_uncertain_words
                            else None
                        )

                        if review_html:
                            ui.html(review_html, sanitize=False).classes(
                                "text-sm leading-relaxed whitespace-pre-wrap"
                            )
                        else:
                            ui.label(caption.text).classes(
                                "text-sm leading-relaxed whitespace-pre-wrap"
                            )
                        text_color = "text-theme-muted"

                        tooltip_text = (
                            "Character count."
                            if self.data_format == "txt"
                            else f"Character count.  Max {settings.CHARACTER_LIMIT} per line (guideline)."
                        )

                        lines = caption.text.split("\n")
                        line_lengths = [str(len(x)) for x in lines]

                        # Check for exceeded limit
                        exceeded = self.data_format != "txt" and any(
                            len(x) > settings.CHARACTER_LIMIT for x in lines
                        )
                        if exceeded:
                            text_color = settings.CHARACTER_LIMIT_EXCEEDED_COLOR
                            tooltip_text = f"Character limit of {settings.CHARACTER_LIMIT} exceeded in one or more lines."

                        character_label = "/".join(line_lengths)

                        with ui.row().classes("items-center gap-1"):
                            if exceeded:
                                ui.icon("warning", size="xs").style(
                                    "color: var(--color-text-danger);"
                                )
                            with ui.label(f"({character_label})").classes(
                                f"text-sm text-right {text_color}"
                            ):
                                ui.tooltip(tooltip_text)

            card.on(
                "click",
                lambda: (
                    self.select_caption(caption) if not caption.is_selected else None
                ),
            )


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

            # Check character limit per line (only for SRT format)
            if self.data_format == "srt":
                for line in caption.text.split("\n"):
                    if len(line) > settings.CHARACTER_LIMIT:
                        errors.append(
                            f"Caption #{caption.index} has a line with {len(line)} characters (max {settings.CHARACTER_LIMIT})."
                        )
                        caption.is_valid = False
                        if caption not in errorenous_captions:
                            errorenous_captions.append(caption)
                        changed_indices.add(caption.index)
                        break

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

        shortcut_groups = [
            (
                "Navigation",
                [
                    ("Next caption", "Alt + ↓"),
                    ("Previous caption", "Alt + ↑"),
                    ("Close/deselect block", "Esc"),
                ],
            ),
            (
                "Editing",
                [
                    ("Split caption at cursor", "Ctrl/⌘ + Enter"),
                    ("Move first word to previous block", "Ctrl/⌘ + ↑"),
                    ("Move last word to next block", "Ctrl/⌘ + ↓"),
                    ("Merge with next", "Ctrl + M"),
                    ("Merge with previous", "Ctrl + Shift + M"),
                    ("Add caption after", "Ctrl/⌘ + Shift + Enter"),
                    ("Delete caption", "Ctrl + D"),
                ],
            ),
            (
                "File Operations",
                [
                    ("Save file", "Ctrl/⌘ + S"),
                    ("Export file", "Ctrl/⌘ + E"),
                    ("Find", "Ctrl/⌘ + F"),
                    ("Validate captions", "Ctrl + Shift + V"),
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

        with ui.dialog().props('aria-label="Keyboard shortcuts"') as dialog:
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

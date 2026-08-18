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

import httpx
import json
import re

from nicegui import events, ui
from typing import Callable, List, Optional
from utils.caption import SRTCaption
from utils.common import get_auth_header
from utils.settings import get_settings
from utils.srt_export import ExportMixin
from utils.srt_render import RenderMixin, CHARACTER_LIMIT_EXCEEDED_COLOR
from utils.srt_review import (
    AUTOSCROLL_KEY,
    DEFAULT_REVIEW_SENSITIVITY,
    EDIT_TOOLTIP,
    EDITS_SHOW_KEY,
    REVIEW_SENSITIVITIES,
    REVIEW_SENSITIVITY_KEY,
    REVIEW_SHOW_KEY,
    REVIEW_TOOLTIP,
    WORDS_FORMAT_VERSION,
    ReviewMixin,
)
from utils.srt_search import SearchMixin
from utils.undo_redo import UndoRedoManager

# Re-exported so that `from utils.srt import ...` keeps working for everything
# that was here before the module was split up.
__all__ = [
    "AUTOSCROLL_KEY",
    "CHARACTER_LIMIT_EXCEEDED_COLOR",
    "DEFAULT_REVIEW_SENSITIVITY",
    "EDITS_SHOW_KEY",
    "EDIT_TOOLTIP",
    "REVIEW_SENSITIVITIES",
    "REVIEW_SENSITIVITY_KEY",
    "REVIEW_SHOW_KEY",
    "REVIEW_TOOLTIP",
    "WORDS_FORMAT_VERSION",
    "SRTEditor",
]

settings = get_settings()


class SRTEditor(ReviewMixin, SearchMixin, ExportMixin, RenderMixin):
    def __init__(self, uuid: str, srt_format: str, filename: str):
        """
        Initialize the SRT editor with empty captions and other properties.
        """

        self.uuid = uuid
        self.srt_format = srt_format
        self.captions: List[SRTCaption] = []
        self.selected_caption: Optional[SRTCaption] = None
        self.caption_cards = {}
        self.caption_containers = {}
        self.main_container = None
        self.search_term = ""
        self.search_results = []
        self.current_search_index = 0
        self.case_sensitive = False
        self.search_container = None
        self._video_player = None
        self.autoscroll = False

        # Follow the audio word by word. Off by default: it needs one element
        # per word, which is only worth paying for when it is being used.
        self.highlight_word = False

        # Set by a view that draws the captions itself, so that refreshing
        # goes to that view instead of the caption card list.
        self.render_override: Optional[Callable] = None
        self.words_per_minute_element = None
        self.speakers = set()
        self.data_format = None
        self.filename = filename

        # Per-word timings, empty for results produced before they existed.
        self.words: List[dict] = []
        self._word_midpoints: List[float] = []
        self.has_confidence = False
        self.show_uncertain_words = False
        self.show_my_edits = False
        self.review_sensitivity = DEFAULT_REVIEW_SENSITIVITY
        self.flagged_count_element = None
        self._active_text_area = None

        # Initialize undo/redo manager
        self.undo_redo_manager = UndoRedoManager()
        self.undo_button = None
        self.redo_button = None

        # Track unsaved changes
        self._has_unsaved_changes = False
        self._save_confirmation_dialog = None
        self._pending_action_after_save: Optional[Callable] = None
        self._play_pause = False

    def has_unsaved_changes(self) -> bool:
        """
        Check if there are unsaved changes.
        """

        return self._has_unsaved_changes

    def mark_as_changed(self) -> None:
        """
        Mark the editor as having unsaved changes.
        """

        self._has_unsaved_changes = True

    def mark_as_saved(self) -> None:
        """
        Mark the editor as having no unsaved changes.
        """

        self._has_unsaved_changes = False

    def setup_beforeunload_warning(self) -> None:
        """
        Setup browser beforeunload warning for unsaved changes.
        """

        ui.run_javascript(
            """
            window.addEventListener('beforeunload', function(e) {
                if (window.hasUnsavedChanges) {
                    e.preventDefault();
                    e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
                    return e.returnValue;
                }
            });
        """
        )

    def update_beforeunload_state(self) -> None:
        """
        Update the browser's beforeunload state based on unsaved changes.
        """

        if self._has_unsaved_changes:
            ui.run_javascript("window.hasUnsavedChanges = true;")
        else:
            ui.run_javascript("window.hasUnsavedChanges = false;")

    def show_save_confirmation_dialog(
        self,
        on_save: Optional[Callable] = None,
        on_discard: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ) -> None:
        """
        Show a dialog asking the user to save, discard, or cancel.
        """

        def handle_save():
            dialog.close()
            self.save_srt_changes()
            if on_save:
                on_save()

        def handle_discard():
            dialog.close()
            self.mark_as_saved()
            self.update_beforeunload_state()
            if on_discard:
                on_discard()

        def handle_cancel():
            dialog.close()
            if on_cancel:
                on_cancel()

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label("Unsaved changes").classes("text-h6 q-mb-md")
            ui.label("You have unsaved changes. What would you like to do?").classes(
                "q-mb-lg"
            )

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=handle_cancel).props("flat")
                ui.button("Discard", on_click=handle_discard).props("flat color=red")
                ui.button("Save", on_click=handle_save).props("color=primary")

        dialog.open()

    def close_editor(self, redirect_url: Optional[str] = None) -> None:
        """
        Close the editor, prompting to save if there are unsaved changes.
        If redirect_url is provided, navigate there after closing.
        """

        def do_close():
            if redirect_url:
                ui.navigate.to(redirect_url)

        # if self.has_unsaved_changes():
        #     self.show_save_confirmation_dialog(
        #         on_save=do_close,
        #         on_discard=do_close,
        #         on_cancel=None,  # Just close the dialog, don't navigate
        #     )
        # else:
        do_close()

    def save_state_for_undo(self) -> None:
        """
        Save the current state before making changes.
        """

        self.undo_redo_manager.save_state(self.captions)
        self._update_undo_redo_buttons()
        # Mark as having unsaved changes
        self.mark_as_changed()
        self.update_beforeunload_state()

    def undo(self) -> None:
        """
        Undo the last action.
        """
        previous_state = self.undo_redo_manager.undo(self.captions)
        if previous_state is not None:
            self.captions = previous_state
            self.selected_caption = None
            self.renumber_captions()
            self.update_words_per_minute()
            self.refresh_display(force_full_refresh=True)
            self._update_undo_redo_buttons()
            # Mark as having unsaved changes (undo is still a change from saved state)
            self.mark_as_changed()
            self.update_beforeunload_state()
        else:
            ui.notify("Nothing to undo", type="info", position="bottom")

    def redo(self) -> None:
        """
        Redo the last undone action.
        """
        next_state = self.undo_redo_manager.redo(self.captions)
        if next_state is not None:
            self.captions = next_state
            self.selected_caption = None
            self.renumber_captions()
            self.update_words_per_minute()
            self.refresh_display(force_full_refresh=True)
            self._update_undo_redo_buttons()
            # Mark as having unsaved changes
            self.mark_as_changed()
            self.update_beforeunload_state()
        else:
            ui.notify("Nothing to redo", type="info", position="bottom")

    def _update_undo_redo_buttons(self) -> None:
        """
        Update the enabled state of undo/redo buttons.
        """
        if self.undo_button:
            if self.undo_redo_manager.can_undo():
                self.undo_button.enable()
                self.undo_button.props("flat dense color=black")
            else:
                self.undo_button.disable()
                self.undo_button.props("flat dense color=grey")

        if self.redo_button:
            if self.undo_redo_manager.can_redo():
                self.redo_button.enable()
                self.redo_button.props("flat dense color=black")
            else:
                self.redo_button.disable()
                self.redo_button.props("flat dense color=grey")

    def create_undo_redo_panel(self) -> None:
        """
        Create the undo/redo buttons panel.
        """
        with ui.row().classes("gap-2"):
            self.undo_button = (
                ui.button("Undo", icon="undo")
                .props("flat")
                .classes("editor-btn editor-toolbar-btn")
                .on("click", self.undo)
            )
            self.undo_button.disable()

            self.redo_button = (
                ui.button("Redo", icon="redo")
                .props("flat")
                .classes("editor-btn editor-toolbar-btn")
                .on("click", self.redo)
            )
            self.redo_button.disable()

    def save_srt_changes(self) -> None:
        try:
            if self.srt_format == "srt":
                data = self.export_srt()
                fmt = "srt"
            else:
                data = json.dumps(self.export_json())
                fmt = "json"

            jsondata = {"format": fmt, "data": data}
            headers = get_auth_header()
            headers["Content-Type"] = "application/json"
            res = httpx.put(
                f"{settings.API_URL}/api/v1/transcriber/{self.uuid}/result",
                headers=headers,
                json=jsondata,
            )
            res.raise_for_status()
        except httpx.HTTPError as e:
            ui.notify(f"Error:  Failed to save file:  {e}", type="negative")
            return

        # Mark as saved after successful save
        self.mark_as_saved()
        self.update_beforeunload_state()

        ui.notify(
            "File saved successfully",
            type="positive",
            position="bottom",
            icon="check_circle",
        )

    def set_highlight_word(self, highlight_word: bool) -> None:
        """
        Set whether the word being played is highlighted.

        Coerced, because the value can come straight from stored preferences.
        """

        self.highlight_word = bool(highlight_word)

    def set_autoscroll(self, autoscroll: bool) -> None:
        """
        Set autoscroll property.

        Coerced, because the value can come straight from stored preferences.
        """
        self.autoscroll = bool(autoscroll)

    async def handle_key_event(self, event: events.KeyEventArguments) -> None:
        # Only handle keydown events, not keyup to prevent double-firing
        if not event.action.keydown:
            return

        # The caption operations belong to the subtitle editor. A transcription
        # is drawn by the document editor, which has no selected caption for
        # them to act on and its own, better bindings for the same jobs: Enter
        # splits a block, Backspace and Delete at the edges join them. Leaving
        # these bound there would fire operations on nothing.
        captions = self.render_override is None

        match event.key:
            # Play/pause video, Ctrl+Space
            case " " if event.modifiers.ctrl and not event.modifiers.shift and not event.modifiers.alt and not event.modifiers.meta:
                if self._video_player:
                    if self._play_pause:
                        self._video_player.pause()
                        self._play_pause = False
                    else:
                        self._video_player.play()
                        self._play_pause = True

            # Undo, Ctrl+Z
            case "z" if event.modifiers.ctrl and not event.modifiers.shift:
                self.undo()
            case "z" if event.modifiers.meta and not event.modifiers.shift:
                self.undo()

            # Redo, Ctrl+Y
            case "y" if event.modifiers.ctrl and not event.modifiers.shift:
                self.redo()
            case "z" if event.modifiers.meta and event.modifiers.shift:
                self.redo()
            case "y" if event.modifiers.meta and not event.modifiers.shift:
                self.redo()

            # Close block, Escape
            case "Escape" if captions:
                # Click the "Close" button to save changes before closing
                # This behaves the same as clicking the Close button
                ui.run_javascript("document.querySelector('.caption-close')?.click()")

            # Open find, Ctrl+F
            case "f" if captions and event.modifiers.ctrl and not event.modifiers.shift:
                self.create_search_panel(open_window=True)
            case "f" if captions and event.modifiers.meta and not event.modifiers.shift:
                self.create_search_panel(open_window=True)

            # Save file, Ctrl+S / Cmd+S
            case "s" if event.modifiers.ctrl or event.modifiers.meta:
                self.save_srt_changes()

            # Export file, Ctrl+E / Cmd+E
            case "e" if event.modifiers.ctrl and not event.modifiers.shift:
                self.show_export_dialog(self.filename)
            case "e" if event.modifiers.meta and not event.modifiers.shift:
                self.show_export_dialog(self.filename)
            # Everything else
            case _:
                pass

    def select_next_caption(self) -> None:
        """
        Select the next caption in the list.
        """

        if not self.captions:
            return

        if self.selected_caption:
            current_index = self.captions.index(self.selected_caption)

            if current_index + 1 >= len(self.captions):
                return

            self.select_caption(self.captions[current_index + 1])
        else:
            self.select_caption(self.captions[0])

    def select_prev_caption(self) -> None:
        """
        Select the previous caption in the list.
        """

        if not self.captions:
            return

        if self.selected_caption:
            current_index = self.captions.index(self.selected_caption)
            if current_index > 0:
                self.select_caption(self.captions[current_index - 1])
            else:
                self.select_caption(self.captions[0])

    def set_words_per_minute_element(self, element) -> None:
        """
        Set the element to display words per minute.
        """

        self.words_per_minute_element = element

    def update_words_per_minute(self) -> None:
        """
        Update the words per minute display.
        """

        if self.words_per_minute_element:
            wpm = self.get_words_per_minute()
            self.words_per_minute_element.set_content(
                f"<b>Words per minute:</b> {wpm:.2f}"
            )

    def get_words_per_minute(self) -> float:
        """
        Calculate the average words per minute based on caption text.
        """

        total_words = sum(len(caption.text.split()) for caption in self.captions)
        total_seconds = sum(
            caption.get_end_seconds() - caption.get_start_seconds()
            for caption in self.captions
        )

        if total_seconds == 0:
            return 0.0

        return (total_words / total_seconds) * 60.0

    def seek_video(self, seconds: float) -> None:
        """
        Move the video to a point in the recording, if a player is attached.
        """

        if self._video_player:
            self._video_player.seek(seconds)

    def set_video_player(self, player) -> None:
        """
        Set the video player for the editor.
        """

        self._video_player = player

    def parse_txt(self, data: dict) -> None:
        """
        Parse TXT content and populate captions list.

        Raw output from the worker arrives as many short diarisation segments
        in lower case, so it is merged into readable blocks and capitalised.
        Anything saved from the editor says so, and is taken exactly as it is:
        merging it again would undo the reader's splits, and capitalising it
        again would undo their corrections.
        """

        self.data_format = "txt"

        original_data = json.loads(data)
        raw_segments = original_data.get("segments")

        if not raw_segments:
            return

        if original_data.get("preserve_segments"):
            segments = [segment.copy() for segment in raw_segments]
        else:
            segments = self.tidy_segments(raw_segments)

        for index, segment in enumerate(segments):
            if not segment.get("text", "").strip():
                continue

            restored = SRTCaption(
                index,
                self.seconds_to_timestamp(segment.get("start", 0.0)),
                self.seconds_to_timestamp(segment.get("end", 0.0)),
                segment["text"],
                speaker=segment.get("speaker", ""),
            )

            # Which words the reader had changed, as the last save recorded
            # them. Absent from the worker's own output and from anything saved
            # before this was kept, and then nothing is marked.
            marks = segment.get("edited")

            if isinstance(marks, list):
                restored.edited_words = {
                    position for position in marks if isinstance(position, int)
                }

            self.captions.append(restored)
            self.speakers.add(segment.get("speaker", ""))

        self.renumber_captions()

    def tidy_segments(self, raw_segments: list) -> list:
        """
        Turn the worker's diarisation segments into readable blocks.

        Neighbouring segments by one speaker are joined until the block is long
        enough and has reached the end of a sentence, and the text is
        capitalised -- the models emit it in lower case.
        """

        max_words = 50

        merged = []
        current = raw_segments[0].copy()

        for segment in raw_segments[1:]:
            past_limit = len(current["text"].split()) >= max_words

            if segment["speaker"] != current["speaker"]:
                merged.append(current)
                current = segment.copy()
            elif past_limit and current["text"].rstrip().endswith("."):
                merged.append(current)
                current = segment.copy()
            else:
                current["text"] += " " + segment["text"]
                current["end"] = segment["end"]
                current["duration"] = current["end"] - current["start"]

        merged.append(current)

        for segment in merged:
            text = segment.get("text", "")

            if text.strip():
                text = re.sub(
                    r"(\.\s+)([a-z])",
                    lambda match: match.group(1) + match.group(2).upper(),
                    text,
                )
                segment["text"] = text[0].upper() + text[1:]

        return merged

    def parse_srt(self, srt_content: str) -> None:
        """
        Parse SRT content and populate captions list.
        """

        self.data_format = "srt"

        caption_blocks = re.split(r"\n\s*\n", srt_content.strip())

        for block in caption_blocks:
            if not block.strip():
                continue

            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue

            try:
                index = int(lines[0])
                timestamp_line = lines[1]

                lines[2:] = [line.lstrip() for line in lines[2:]]
                text = "\n".join(lines[2:])

                # Parse timestamp
                if " --> " in timestamp_line:
                    start_time, end_time = timestamp_line.split(" --> ")
                    caption = SRTCaption(
                        index, start_time.strip(), end_time.strip(), text
                    )
                    self.captions.append(caption)
            except (ValueError, IndexError):
                continue

        self.renumber_captions()





    def renumber_captions(self) -> None:
        """
        Renumber all captions sequentially.
        """

        for i, caption in enumerate(self.captions, 1):
            caption.index = i

    def format_time_display(self, timestamp: str) -> str:
        """
        Format timestamp for display.
        """

        return str(timestamp).replace(",", ".")

    def seconds_to_timestamp(self, seconds: float) -> str:
        """
        Convert seconds back to SRT timestamp format.
        """

        # Round to whole milliseconds first, then split. Rounding each field
        # on its own lets a carry strand a timestamp on 59 seconds or 60
        # minutes. Rounding rather than truncating matters because 2.4 is
        # held as 2.39999..., which would otherwise lose a millisecond off
        # most timestamps; the worker writes them the same way.
        total_milliseconds = max(0, int(round(seconds * 1000)))

        hours, remainder = divmod(total_milliseconds, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, milliseconds = divmod(remainder, 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"








    async def read_text_area_state(self) -> Optional[dict]:
        """
        Read the live value and caret offset out of the caption text area.

        Returns None whenever the caret cannot be determined -- no text area
        open, the browser did not answer in time, or an unexpected payload --
        so callers fall back to splitting without a caret.
        """

        text_area = self._active_text_area

        if text_area is None:
            return None

        try:
            state = await ui.run_javascript(
                f"""
                (() => {{
                    const root = getHtmlElement({text_area.id})
                        || getElement({text_area.id})?.$el;
                    if (!root || !root.querySelector) return null;
                    const el = root.matches("textarea")
                        ? root
                        : root.querySelector("textarea");
                    if (!el) return null;
                    return {{value: el.value, pos: el.selectionStart}};
                }})()
                """,
                timeout=2.0,
            )
        except Exception:
            return None

        if not isinstance(state, dict):
            return None

        value = state.get("value")
        position = state.get("pos")

        if not isinstance(value, str) or not isinstance(position, int):
            return None

        return {"value": value, "position": position}

    async def split_caption_at_cursor(self, caption: SRTCaption) -> None:
        """
        Split a caption where the caret sits, falling back to a halfway split
        when the caret position is unavailable.
        """

        if not caption:
            return

        state = await self.read_text_area_state()

        if state is None:
            self.split_caption(caption)
            return

        self.split_caption(
            caption, cursor_position=state["position"], text=state["value"]
        )

    def split_time(
        self,
        caption: SRTCaption,
        first_part: str,
        second_part: str,
        at_cursor: bool = False,
    ) -> float:
        """
        Timestamp to cut a caption at, best source first:

        1. the silence between the last word of the first half and the first
           word of the second half, when per-word timings are available,
        2. the split point's position through the text, scaled over the
           caption's duration -- only for a caret-driven split, where the two
           halves are usually uneven,
        3. the middle of the caption, which is what an unaided split has
           always done.
        """

        start_seconds = caption.get_start_seconds()
        end_seconds = caption.get_end_seconds()
        duration = end_seconds - start_seconds

        if duration <= 0:
            return end_seconds

        words = self.caption_words(caption)
        offset = len(first_part.split())

        if words and 0 < offset < len(words):
            before = words[offset - 1]
            after = words[offset]

            # Both sides have to be placed in the recording for the gap between
            # them to mean anything. Without that, the fallbacks below decide.
            if self.word_is_timed(before) and self.word_is_timed(after):
                boundary = (before["e"] + after["s"]) / 2

                if start_seconds < boundary < end_seconds:
                    return boundary

        if at_cursor:
            first_length = len(first_part.strip())
            total_length = first_length + len(second_part.strip())

            if total_length > 0:
                proportional = start_seconds + duration * (first_length / total_length)

                if start_seconds < proportional < end_seconds:
                    return proportional

        return start_seconds + duration / 2

    def split_caption(
        self,
        caption: SRTCaption,
        cursor_position: Optional[int] = None,
        text: Optional[str] = None,
    ) -> None:
        """
        Split a caption into two parts.

        Splits at ``cursor_position`` when given, and halfway through when it
        is not.

        A caret at the very edge of the block is refused rather than falling
        back to halving: the caret says exactly where the user wanted the
        break, and there is nothing on one side of it. Halving instead would
        cut a word they never asked to touch.
        """

        if not caption:
            return

        source = caption.text if text is None else text
        first_part = None
        second_part = None
        at_cursor = False

        if cursor_position is not None:
            # Clamped, because the offset comes from the browser.
            position = max(0, min(int(cursor_position), len(source)))
            head = source[:position].strip()
            tail = source[position:].strip()

            if not (head and tail):
                # Nothing to divide. Keep any uncommitted typing, but leave
                # the block whole.
                if text is not None and text != caption.text:
                    self.update_caption_text(caption, text)

                return

            first_part = head
            second_part = tail
            at_cursor = True

        # Save state before making changes
        self.save_state_for_undo()

        if text is not None and text != caption.text:
            # The text area holds edits that have not been committed yet;
            # splitting must not discard them, nor the marks they earned.
            caption.edited_words = self.retag_edits(
                caption.text, text, caption.edited_words
            )
            caption.text = text
            self.mark_as_changed()

        if first_part is None:
            text_lines = caption.text.split("\n")

            if len(text_lines) == 1:
                # Split single line in half
                text = caption.text
                mid_point = len(text) // 2
                # Find nearest space to split at
                while mid_point > 0 and text[mid_point] != " ":
                    mid_point -= 1
                if mid_point == 0:
                    mid_point = len(text) // 2

                first_part = text[:mid_point].strip()
                second_part = text[mid_point:].strip()
            else:
                # Split at middle line
                mid_line = len(text_lines) // 2
                first_part = "\n".join(text_lines[:mid_line])
                second_part = "\n".join(text_lines[mid_line:])

        # Calculate time split
        end_seconds = caption.get_end_seconds()
        mid_seconds = self.split_time(caption, first_part, second_part, at_cursor)

        # Marks follow their words across the break.
        kept, moved = self.split_edits(
            caption.edited_words, len(first_part.split())
        )

        # Update first caption
        caption.text = first_part
        caption.edited_words = kept
        caption.end_time = self.seconds_to_timestamp(mid_seconds)

        # Create second caption
        new_caption = SRTCaption(
            caption.index + 1,
            self.seconds_to_timestamp(mid_seconds),
            self.seconds_to_timestamp(end_seconds),
            second_part,
            speaker=caption.speaker,
        )
        new_caption.edited_words = moved

        # Insert new caption
        caption_index = self.captions.index(caption)
        self.captions.insert(caption_index + 1, new_caption)

        self.renumber_captions()
        self.update_words_per_minute()
        self.refresh_display(force_full_refresh=True)

    @staticmethod
    def split_off_first_word(text: str) -> tuple:
        """
        Split text into its first word and the remainder.

        Separators are preserved in the remainder, so a two-line subtitle
        keeps its line break instead of collapsing to one line.
        """

        parts = re.split(r"(\s+)", text.strip())

        if len(parts) < 3:
            return text.strip(), ""

        return parts[0], "".join(parts[2:]).strip()

    @staticmethod
    def split_off_last_word(text: str) -> tuple:
        """
        Split text into everything up to the last word, and the last word.
        """

        parts = re.split(r"(\s+)", text.strip())

        if len(parts) < 3:
            return "", text.strip()

        return "".join(parts[:-2]).strip(), parts[-1]

    def move_first_word_to_previous(self, caption: SRTCaption) -> None:
        """
        Move the first word of a block to the end of the previous one.

        Both blocks are re-timed from the word data: the previous block now
        ends where the moved word ends, and this one starts where its new
        first word starts.
        """

        if not caption:
            return

        position = self.captions.index(caption)

        if position == 0:
            ui.notify("No previous block to move the word to", type="warning")
            return

        moved_word, remaining = self.split_off_first_word(caption.text)

        if not remaining:
            ui.notify(
                "That is the only word in the block -- merge instead",
                type="warning",
            )
            return

        # Resolve the timings before the text changes, since words are matched
        # to a block by its time range.
        aligned = self.aligned_words(caption)
        moved_timing = aligned[0] if aligned else None
        next_timing = aligned[1] if len(aligned) > 1 else None

        self.save_state_for_undo()

        previous = self.captions[position - 1]
        previous.text = f"{previous.text.rstrip()} {moved_word}"
        caption.text = remaining

        if self.word_is_timed(moved_timing) and self.word_is_timed(next_timing):
            previous.end_time = self.seconds_to_timestamp(moved_timing["e"])
            caption.start_time = self.seconds_to_timestamp(next_timing["s"])
        else:
            ui.notify(
                "Word moved, but the timings could not be updated",
                type="warning",
            )

        self.finish_word_move()

    def move_last_word_to_next(self, caption: SRTCaption) -> None:
        """
        Move the last word of a block to the start of the next one.

        Both blocks are re-timed from the word data: the next block now starts
        where the moved word starts, and this one ends where its new last word
        ends.
        """

        if not caption:
            return

        position = self.captions.index(caption)

        if position == len(self.captions) - 1:
            ui.notify("No next block to move the word to", type="warning")
            return

        remaining, moved_word = self.split_off_last_word(caption.text)

        if not remaining:
            ui.notify(
                "That is the only word in the block -- merge instead",
                type="warning",
            )
            return

        aligned = self.aligned_words(caption)
        moved_timing = aligned[-1] if aligned else None
        previous_timing = aligned[-2] if len(aligned) > 1 else None

        self.save_state_for_undo()

        following = self.captions[position + 1]
        following.text = f"{moved_word} {following.text.lstrip()}"
        caption.text = remaining

        if self.word_is_timed(moved_timing) and self.word_is_timed(previous_timing):
            following.start_time = self.seconds_to_timestamp(moved_timing["s"])
            caption.end_time = self.seconds_to_timestamp(previous_timing["e"])
        else:
            ui.notify(
                "Word moved, but the timings could not be updated",
                type="warning",
            )

        self.finish_word_move()

    def finish_word_move(self) -> None:
        """
        Shared bookkeeping after a word has moved between blocks.
        """

        self.mark_as_changed()
        self.update_words_per_minute()
        self.refresh_display(force_full_refresh=True)

    def add_caption_after(self, caption: SRTCaption) -> None:
        """
        Add a new caption after the selected one.
        """

        if not caption:
            return

        # Save state before making changes
        self.save_state_for_undo()

        # Calculate new caption timing
        start_seconds = caption.get_end_seconds()

        # Find next caption or add 3 seconds if it's the last one
        caption_index = self.captions.index(caption)
        if caption_index < len(self.captions) - 1:
            next_caption = self.captions[caption_index + 1]
            end_seconds = next_caption.get_start_seconds()
        else:
            end_seconds = start_seconds + 3.0

        # Create new caption
        new_caption = SRTCaption(
            caption.index + 1,
            self.seconds_to_timestamp(start_seconds),
            self.seconds_to_timestamp(end_seconds),
            "New caption text",
            speaker=caption.speaker,
        )

        # Insert new caption
        self.captions.insert(caption_index + 1, new_caption)

        self.renumber_captions()
        self.refresh_display(force_full_refresh=True)
        self.update_words_per_minute()

    def remove_caption(self, caption: SRTCaption) -> None:
        """
        Remove a caption.
        """

        if not caption:
            return

        if len(self.captions) > 1:  # Don't remove if it's the only caption
            # Save state before making changes
            self.save_state_for_undo()

            self.captions.remove(caption)
            self.renumber_captions()
            self.refresh_display(force_full_refresh=True)
        else:
            ui.notify("Cannot remove the only remaining caption", type="warning")

        self.update_words_per_minute()

    def select_caption(
        self,
        caption: SRTCaption,
        speaker: Optional[ui.input] = None,
        button: Optional[bool] = False,
        seek: Optional[bool] = True,
        new_text: Optional[str] = None,
    ) -> None:
        """
        Select/deselect a caption.
        """

        if speaker:
            self.speakers.add(speaker.value)
            self.selected_caption.speaker = speaker.value

        old_selected = self.selected_caption

        if self.selected_caption:
            self.selected_caption.is_selected = False

        if self.selected_caption == caption:
            self.selected_caption = None
        else:
            caption.is_selected = True
            self.selected_caption = caption

            # Get caption start time
            if self._video_player and seek:
                start_seconds = caption.get_start_seconds()
                self._video_player.seek(start_seconds)

        if new_text is not None and new_text != caption.text:
            self.update_caption_text(
                caption, caption.text, force=True
            )  # To mark as changed
            caption.text = new_text

        self.update_words_per_minute()

        # Only update the captions that changed state
        indices_to_update = set()
        if old_selected:
            indices_to_update.add(old_selected.index)
        if caption:
            indices_to_update.add(caption.index)
        self.refresh_display(specific_indices=indices_to_update)

        if self.selected_caption:
            ui.run_javascript(
                """
                requestAnimationFrame(() => {
                    const el = document.getElementById("action_row");
                    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
                });
                """
            )

    def update_caption_text(
        self, caption: SRTCaption, new_text: str, force: Optional[bool] = False
    ) -> None:
        """
        Update caption text.
        """

        # Only save state if text actually changed
        if caption.text != new_text or force:
            self.save_state_for_undo()
            # Worked out before the text is replaced, while there is still
            # something to compare it against.
            caption.edited_words = self.retag_edits(
                caption.text, new_text, caption.edited_words
            )
            caption.text = new_text
            # Editing a word can take it off the count, or put one on it.
            self.update_flagged_count()

    def update_caption_timing(
        self, caption: SRTCaption, start_time: str, end_time: str
    ) -> None:
        """
        Update caption timing.
        """
        # Only save state if timing actually changed
        if caption.start_time != start_time or caption.end_time != end_time:
            self.save_state_for_undo()
            caption.start_time = start_time
            caption.end_time = end_time
            # Only update this specific caption
            self.refresh_display(specific_indices={caption.index})


    def get_caption_from_time(self, caption_time: float) -> Optional[SRTCaption]:
        """
        Get caption at a specific time.
        """

        for caption in self.captions:
            if caption.get_start_seconds() <= caption_time < caption.get_end_seconds():
                return caption

        return None

    async def select_caption_from_video(self) -> None:
        if not self.autoscroll:
            return

        current_time = await ui.run_javascript(
            """
            (() => { return document.querySelector("video").currentTime })()
            """
        )

        caption = self.get_caption_from_time(current_time)

        if caption:
            if self.selected_caption != caption:
                self.select_caption(caption, seek=False)

    def merge_with_next(self, caption: SRTCaption) -> None:
        """
        Merge the current caption with the next one.
        Update the current cation with the text and end_time from
        the next caption and remove the next caption.
        """

        if not caption:
            return

        caption_index = self.captions.index(caption)
        if caption_index == len(self.captions) - 1:
            ui.notify("No next caption to merge with", type="warning")
            return

        # Save state before making changes
        self.save_state_for_undo()

        next_caption = self.captions[caption_index + 1]

        # Merge text and update end time
        caption.edited_words = self.joined_edits(
            caption.edited_words,
            next_caption.edited_words,
            len(caption.text.split()),
        )
        caption.text += "\n" + next_caption.text
        caption.end_time = next_caption.end_time

        # Remove next caption
        self.captions.remove(next_caption)

        self.renumber_captions()
        self.update_words_per_minute()
        self.refresh_display(force_full_refresh=True)

    def merge_with_previous(self, caption: SRTCaption) -> None:
        """
        Merge the current caption with the previous one.
        Update the current cation with the text and end_time from
        the previous caption and remove the previous caption.
        """

        if not caption:
            return

        caption_index = self.captions.index(caption)
        if caption_index == 0:
            ui.notify("No previous caption to merge with", type="warning")
            return

        # Save state before making changes
        self.save_state_for_undo()

        previous_caption = self.captions[caption_index - 1]

        # Merge text and update end time
        previous_caption.edited_words = self.joined_edits(
            previous_caption.edited_words,
            caption.edited_words,
            len(previous_caption.text.split()),
        )
        previous_caption.text += "\n" + caption.text
        previous_caption.end_time = caption.end_time

        # Remove current caption
        self.captions.remove(caption)

        self.renumber_captions()
        self.update_words_per_minute()
        self.refresh_display(force_full_refresh=True)








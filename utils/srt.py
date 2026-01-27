import json
import re
import requests

from nicegui import events, ui
from typing import Callable, List, Optional
from utils.caption import SRTCaption
from utils.common import default_styles, get_auth_header
from utils.settings import get_settings
from utils.undo_redo import UndoRedoManager

CHARACTER_LIMIT_EXCEEDED_COLOR = "text-red"
CHARACTER_LIMIT = 42

settings = get_settings()


class SRTEditor:
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
        self.__video_player = None
        self.autoscroll = False
        self.words_per_minute_element = None
        self.speakers = set()
        self.data_format = None
        self.filename = filename

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
            ui.label("Unsaved Changes").classes("text-h6 q-mb-md")
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
        """Save the current state before making changes."""

        self.undo_redo_manager.save_state(self.captions)
        self._update_undo_redo_buttons()
        # Mark as having unsaved changes
        self.mark_as_changed()
        self.update_beforeunload_state()

    def undo(self) -> None:
        """Undo the last action."""
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
        """Redo the last undone action."""
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
        """Update the enabled state of undo/redo buttons."""
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
        """Create the undo/redo buttons panel."""
        with ui.row().classes("gap-2"):
            self.undo_button = (
                ui.button("Undo", icon="undo")
                .props("flat dense color=grey")
                .on("click", self.undo)
            )
            self.undo_button.disable()

            self.redo_button = (
                ui.button("Redo", icon="redo")
                .props("flat dense color=grey")
                .on("click", self.redo)
            )
            self.redo_button.disable()

    def save_srt_changes(self) -> None:
        try:
            if self.srt_format == "srt":
                data = self.export_srt()
            else:
                data = json.dumps(self.export_json())

            jsondata = {"format": self.srt_format, "data": data}
            headers = get_auth_header()
            headers["Content-Type"] = "application/json"
            res = requests.put(
                f"{settings.API_URL}/api/v1/transcriber/{self.uuid}/result",
                headers=headers,
                json=jsondata,
            )
            res.raise_for_status()
        except requests.exceptions.RequestException as e:
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

    def set_autoscroll(self, autoscroll: bool) -> None:
        """
        Set autoscroll property.
        """
        self.autoscroll = autoscroll

    def handle_key_event(self, event: events.KeyEventArguments) -> None:
        # Only handle keydown events, not keyup to prevent double-firing
        if not event.action.keydown:
            return

        match event.key:
            # Next block of captions, Ctrl+Down
            case "ArrowDown" if event.modifiers.alt and not event.modifiers.shift and not event.modifiers.ctrl and not event.modifiers.meta:
                self.select_next_caption()

            # Prev block of captions, Ctrl+Up
            case "ArrowUp" if event.modifiers.alt and not event.modifiers.shift and not event.modifiers.ctrl and not event.modifiers.meta:
                self.select_prev_caption()

            # Split block, Alt+Enter
            case "Enter" if event.modifiers.ctrl and not event.modifiers.shift and not event.modifiers.alt and not event.modifiers.meta:
                self.split_caption(self.selected_caption)
            case "Enter" if event.modifiers.meta and not event.modifiers.shift and not event.modifiers.alt and not event.modifiers.ctrl:
                self.split_caption(self.selected_caption)

            # Merge block with next, Ctrl+M
            case "m" if event.modifiers.ctrl:
                self.merge_with_next(self.selected_caption)

            # Merge block with previous, Ctrl+Shift+M
            case "M" if event.modifiers.ctrl:
                self.merge_with_previous(self.selected_caption)

            # Add caption after, Shift+Ctrl+Enter
            case "Enter" if event.modifiers.ctrl and event.modifiers.shift:
                self.add_caption_after(self.selected_caption)
            case "Enter" if event.modifiers.meta and event.modifiers.shift:
                self.add_caption_after(self.selected_caption)

            # Delete block, Ctrl+Shift+D
            case "d" if event.modifiers.ctrl:
                self.remove_caption(self.selected_caption)

            # Validate captions, Ctrl+Shift+V
            case "v" if event.modifiers.ctrl:
                self.validate_captions()

            # Play/pause video, Ctrl+Space
            case " " if event.modifiers.ctrl and not event.modifiers.shift and not event.modifiers.alt and not event.modifiers.meta:
                if self.__video_player:
                    if self._play_pause:
                        self.__video_player.pause()
                        self._play_pause = False
                    else:
                        self.__video_player.play()
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
            case "Escape":
                # Click the "Close" button to save changes before closing
                # This behaves the same as clicking the Close button
                ui.run_javascript("document.querySelector('.button-close')?.click()")

            # Open find, Ctrl+F
            case "f" if event.modifiers.ctrl and not event.modifiers.shift:
                self.create_search_panel(open_window=True)
            case "f" if event.modifiers.meta and not event.modifiers.shift:
                self.create_search_panel(open_window=True)

            # Save file, Ctrl+S / Cmd+S
            case "s" if event.modifiers.ctrl or event.modifiers.meta:
                self.save_srt_changes()

            # Export file, Ctrl+E / Cmd+E
            case "e" if event.modifiers.ctrl and not event.modifiers.shift:
                self.show_export_dialog(self.filename)
            case "e" if event.modifiers.meta and not event.modifiers.shift:
                self.show_export_dialog(self.filename)

            # ? to show help
            case "?" if event.modifiers.shift and not event.modifiers.ctrl:
                self.show_keyboard_shortcuts(open_window=True)

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

    def set_video_player(self, player) -> None:
        """
        Set the video player for the editor.
        """

        self.__video_player = player

    def parse_txt(self, data: dict) -> None:
        """
        Parse TXT content and populate captions list.
        """

        self.data_format = "txt"

        original_data = json.loads(data)

        if not original_data.get("segments"):
            return

        raw_segments = original_data["segments"]

        if not raw_segments:
            return

        concatenated = []
        current = raw_segments[0].copy()

        for segment in raw_segments[1:]:
            if segment["speaker"] == current["speaker"]:
                current["text"] += " " + segment["text"]
                current["end"] = segment["end"]
                current["duration"] = current["end"] - current["start"]
            else:
                concatenated.append(current)
                current = segment.copy()

        concatenated.append(current)

        for index, seg in enumerate(concatenated):
            if seg.get("text", "").strip():
                start_time = self.seconds_to_timestamp(seg.get("start", 0.0))
                end_time = self.seconds_to_timestamp(seg.get("end", 0.0))

                self.captions.append(
                    SRTCaption(
                        index,
                        start_time,
                        end_time,
                        seg["text"],
                        speaker=seg["speaker"],
                    )
                )
                self.speakers.add(seg["speaker"])

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

    def export_csv(self) -> str:
        """
        Export to CSV format.
        Fields: Start time, stop time, speaker, text
        """
        lines = []
        for caption in self.captions:
            escaped_text = caption.text.replace('"', '""')
            lines.append(
                f'"{caption.start_time}","{caption.end_time}","{caption.speaker}","{escaped_text}"'
            )
        return "\n".join(lines)

    def export_tsv(self) -> str:
        """
        Export to TSV format.
        Fields: Start time, stop time, speaker, text
        """
        lines = []
        for caption in self.captions:
            escaped_text = caption.text.replace("\t", "    ").replace("\n", " ")
            lines.append(
                f"{caption.start_time}\t{caption.end_time}\t{caption.speaker}\t{escaped_text}"
            )
        return "\n".join(lines)

    def export_rtf(
        self,
        speakers: bool,
        times: bool,
        block_nr: bool,
        ts_which: str = "both",
        ts_fmt: str = "srt",
    ) -> str:
        """
        Export captions to RTF format with proper Unicode handling.
        """

        def fmt_ts(ts: str, f: str) -> str:
            """Format timestamp according to selected format."""
            p = ts.replace(",", ":").split(":")
            h, m, s, ms = int(p[0]), int(p[1]), int(p[2]), int(p[3])
            if f == "seconds":
                return f"{h*3600 + m*60 + s + ms/1000:.3f}"
            if f == "ms":
                return str(h * 3600000 + m * 60000 + s * 1000 + ms)
            if f == "vtt":
                return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
            return ts

        def to_rtf_unicode(text: str) -> str:
            result = []
            for ch in text:
                code = ord(ch)
                if code < 128:
                    if ch in ["\\", "{", "}"]:
                        result.append("\\" + ch)
                    else:
                        result.append(ch)
                elif code <= 0xFFFF:
                    # BMP character - use signed 16-bit representation
                    signed_code = code if code <= 0x7FFF else code - 0x10000
                    result.append(f"\\u{signed_code}?")
                else:
                    # Supplementary character (outside BMP) - use UTF-16 surrogate pair
                    code -= 0x10000
                    high_surrogate = 0xD800 + (code >> 10)
                    low_surrogate = 0xDC00 + (code & 0x3FF)
                    # Surrogates are always > 0x7FFF, convert to signed
                    result.append(
                        f"\\u{high_surrogate - 0x10000}?\\u{low_surrogate - 0x10000}?"
                    )
            return "".join(result)

        rtf_content = (
            r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}" r"\viewkind4\uc1\pard\f0\fs20 "
        )

        parts = []

        for caption in self.captions:
            header_parts = []
            if block_nr:
                header_parts.append(to_rtf_unicode(f"[{caption.index}]"))

            if times:
                ts_parts = []
                if ts_which in ["start", "both"]:
                    ts_parts.append(fmt_ts(caption.start_time, ts_fmt))
                if ts_which in ["end", "both"]:
                    ts_parts.append(fmt_ts(caption.end_time, ts_fmt))
                if ts_parts:
                    header_parts.append(to_rtf_unicode(f"({' - '.join(ts_parts)})"))

            if speakers:
                header_parts.append(to_rtf_unicode(f"{caption.speaker}:"))

            # Build RTF data with consistent bold formatting for header
            rtf_data = ""
            if header_parts:
                rtf_data = r"\b " + " ".join(header_parts) + r"\b0\line "

            rtf_data += (
                to_rtf_unicode(caption.text).replace("\n", r"\line ") + r"\line\line "
            )

            parts.append(rtf_data)

        rtf_content += "".join(parts) + "}"

        return rtf_content

    def export_txt(self) -> str:
        """
        Export captions to TXT format.
        """

        txt_content = "\n\n".join(
            f"{caption.speaker}: {caption. start_time} - {caption.end_time}\n{caption.text}"
            for caption in self.captions
        )

        return txt_content.strip()

    def export_json(self) -> str:
        return {
            "segments": [seg.to_dict() for seg in self.captions],
            "speaker_count": len(self.speakers),
            "full_transcription": " ".join(seg.text for seg in self.captions),
        }

    def export_srt(self) -> str:
        """
        Export captions to SRT format.
        """

        return "\n\n".join(caption.to_srt_format() for caption in self.captions)

    def export_vtt(self) -> str:
        """
        Export captions to VTT format.
        """

        parts = ["WEBVTT\n\n"]
        for caption in self.captions:
            parts.append(f"{caption.index}\n")
            parts.append(
                f"{caption.start_time.replace(',', '.')} --> {caption.end_time.replace(',', '.')}\n"
            )
            parts.append(f"{caption.text}\n\n")
        return "".join(parts)

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

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        milliseconds = int((secs % 1) * 1000)
        secs = int(secs)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

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

            self.selected_caption.text = new_text
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
                    caption.text = caption.text.replace(self.search_term, replacement)
                else:
                    pattern = re.compile(re.escape(self.search_term), re.IGNORECASE)
                    caption.text = pattern.sub(replacement, caption.text)
                count += 1

        if count > 0:
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

    def split_caption(self, caption: SRTCaption) -> None:
        """
        Split a caption into two parts.
        """

        if not caption:
            return

        # Save state before making changes
        self.save_state_for_undo()

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
        start_seconds = caption.get_start_seconds()
        end_seconds = caption.get_end_seconds()
        mid_seconds = (start_seconds + end_seconds) / 2

        # Update first caption
        caption.text = first_part
        caption.end_time = self.seconds_to_timestamp(mid_seconds)

        # Create second caption
        new_caption = SRTCaption(
            caption.index + 1,
            self.seconds_to_timestamp(mid_seconds),
            self.seconds_to_timestamp(end_seconds),
            second_part,
        )

        # Insert new caption
        caption_index = self.captions.index(caption)
        self.captions.insert(caption_index + 1, new_caption)

        self.renumber_captions()
        self.update_words_per_minute()
        self.refresh_display(force_full_refresh=True)

    def add_caption_after(self, caption: SRTCaption) -> None:
        """
        Add a new caption after the selected one.
        """

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
            if self.__video_player and seek:
                start_seconds = caption.get_start_seconds()
                self.__video_player.seek(start_seconds)

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
            caption.text = new_text

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
                    ui.label("Find").classes("text-caption text-gray-600")

                    with ui.row().classes("w-full items-center gap-2"):
                        search_input = (
                            ui.input(
                                placeholder="Search in captions…",
                                value=self.search_term,
                            )
                            .classes("flex-1")
                            .props("outlined dense clearable")
                        )

                        ui.button(icon="search").props(
                            "flat dense round color=black"
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
                                "flat dense round color=black"
                            ).on(
                                "click", lambda: self.navigate_search_results(-1)
                            ).tooltip(
                                "Previous match"
                            )
                            ui.button(icon="keyboard_arrow_down").props(
                                "flat dense round color=black"
                            ).on(
                                "click", lambda: self.navigate_search_results(1)
                            ).tooltip(
                                "Next match"
                            )

                            self.search_info_label = ui.label("").classes(
                                "text-caption text-gray-600"
                            )

                ui.separator().classes("my-3")

                # REPLACE SECTION
                with ui.column().classes("w-full gap-2"):
                    ui.label("Replace").classes("text-caption text-gray-600")

                    replace_input = (
                        ui.input(
                            placeholder="Replace with…",
                        )
                        .classes("w-full")
                        .props("outlined dense clearable")
                    )

                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Replace").props("flat dense color=black").on(
                            "click",
                            lambda: self.replace_in_current_caption(
                                replace_input.value
                            ),
                        )

                        ui.button("Replace all").props("flat dense color=black").on(
                            "click", lambda: self.replace_all(replace_input.value)
                        )

                ui.separator().classes("my-3")

                with ui.row().classes("w-full justify-end"):
                    ui.button("Close").props("flat dense color=black").on(
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
            ui.button("Search").props("icon=search flat dense color=black").on(
                "click", lambda: self.search_container.open()
            ).classes("button-open-search")

    def get_caption_from_time(self, caption_time: float) -> Optional[SRTCaption]:
        """
        Get caption at a specific time.
        """

        for caption in self.captions:
            if caption.get_start_seconds() <= caption_time <= caption.get_end_seconds():
                return caption

        return None

    async def select_caption_from_video(self) -> None:
        if not self.autoscroll:
            return

        current_time = await ui.run_javascript(
            """(() => { return document.querySelector("video").currentTime })()"""
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

        caption_index = self.captions.index(caption)
        if caption_index == len(self.captions) - 1:
            ui.notify("No next caption to merge with", type="warning")
            return

        # Save state before making changes
        self.save_state_for_undo()

        next_caption = self.captions[caption_index + 1]

        # Merge text and update end time
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

        caption_index = self.captions.index(caption)
        if caption_index == 0:
            ui.notify("No previous caption to merge with", type="warning")
            return

        # Save state before making changes
        self.save_state_for_undo()

        previous_caption = self.captions[caption_index - 1]

        # Merge text and update end time
        previous_caption.text += "\n" + caption.text
        previous_caption.end_time = caption.end_time

        # Remove current caption
        self.captions.remove(caption)

        self.renumber_captions()
        self.update_words_per_minute()
        self.refresh_display(force_full_refresh=True)

    def create_caption_card(self, caption: SRTCaption) -> ui.card:
        """
        Create a visual card for a caption.
        """

        card_class = "cursor-pointer border-0 transition-all duration-200 w-full"

        if not caption.is_valid:
            card_class += " border-red-400 bg-red-50 hover:border-red-500"
        elif caption.is_selected and caption.is_highlighted:
            # Slightly darker yellow background
            card_class += (
                " shadow-lg border-yellow-400 bg-yellow-100 hover:border-yellow-500"
            )
        elif caption.is_selected:
            card_class += " shadow-lg"
        elif caption.is_highlighted:
            card_class += " border-yellow-400 bg-yellow-50 hover:border-yellow-500"
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
                            "font-bold text-sm text-gray-500"
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

                    text_area = (
                        ui.textarea(value=caption.text)
                        .classes("w-full")
                        .props("outlined input-class=h-32")
                    )
                    text_area.on(
                        "blur",
                        lambda e: self.update_caption_text(caption, e.sender.value),
                    )

                    # Action buttons
                    # Row with buttons to the left
                    with ui.row().classes("w-full justify-between"):
                        ui.button("Split", icon="call_split", color="blue").props(
                            "flat dense"
                        ).on("click", lambda: self.split_caption(caption))
                        ui.button("Merge with previous", icon="merge_type").props(
                            "flat dense"
                        ).on(
                            "click",
                            lambda: (
                                self.merge_with_previous(caption)
                                if self.captions.index(caption) > 0
                                else None
                            ),
                        )
                        ui.button("Merge with next", icon="merge_type").props(
                            "flat dense"
                        ).on(
                            "click",
                            lambda: (
                                self.merge_with_next(caption)
                                if self.captions.index(caption) < len(self.captions) - 1
                                else None
                            ),
                        )

                        with ui.row().classes("gap-2"):
                            ui.button("Close").props("flat dense").on(
                                "click",
                                lambda: self.select_caption(
                                    caption,
                                    speaker_select,
                                    True,
                                    new_text=text_area.value,
                                ),
                            ).classes("button-close")

                            if self.data_format == "txt":
                                ui.button("Add", color="green").props("flat dense").on(
                                    "click", lambda: self.add_caption_after(caption)
                                )

                            ui.button("Delete", color="red").props("flat dense").on(
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
                            "text-sm text-gray-500"
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
                            ).classes("text-sm text-gray-500")
                        with ui.row().classes("w-full justify-between items-end"):
                            ui.label(caption.text).classes(
                                "text-sm leading-relaxed whitespace-pre-wrap"
                            )
                            text_color = "text-gray-500"

                            tooltip_text = (
                                "Character count."
                                if self.data_format == "txt"
                                else "Character count.  Max 42 per line (guideline)."
                            )

                            lines = caption.text.split("\n")
                            line_lengths = [str(len(x)) for x in lines]

                            # Check for exceeded limit
                            if self.data_format != "txt" and any(
                                len(x) > CHARACTER_LIMIT for x in lines
                            ):
                                text_color = CHARACTER_LIMIT_EXCEEDED_COLOR
                                tooltip_text = f"Character limit of {CHARACTER_LIMIT} exceeded in one or more lines."

                            character_label = "/".join(line_lengths)

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
                            "text-gray-500 text-center p-8"
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

    def update_caption_card_content(self, caption: SRTCaption) -> None:
        """Update the content of an existing caption card"""
        card_class = "cursor-pointer border-0 transition-all duration-200 w-full"

        if not caption.is_valid:
            card_class += " border-red-400 bg-red-50 hover:border-red-500"
        elif caption.is_selected and caption.is_highlighted:
            card_class += (
                " shadow-lg border-yellow-400 bg-yellow-100 hover:border-yellow-500"
            )
        elif caption.is_selected:
            card_class += " shadow-lg"
        elif caption.is_highlighted:
            card_class += " border-yellow-400 bg-yellow-50 hover:border-yellow-500"
        else:
            card_class += " hover:shadow-md shadow-none"

        with ui.card().classes(card_class) as card:
            if caption.is_selected:
                with ui.row().classes("w-full justify-between") as action_row:
                    action_row.props("id=action_row")
                    ui.label(f"#{caption.index}").classes(
                        "font-bold text-sm text-gray-500"
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

                text_area = (
                    ui.textarea(value=caption.text)
                    .classes("w-full")
                    .props("outlined input-class=h-32")
                )
                text_area.on(
                    "blur", lambda e: self.update_caption_text(caption, e.sender.value)
                )

                with ui.row().classes("w-full justify-between"):
                    ui.button("Split", icon="call_split", color="blue").props(
                        "flat dense"
                    ).on("click", lambda: self.split_caption(caption))
                    ui.button("Merge with previous", icon="merge_type").props(
                        "flat dense"
                    ).on(
                        "click",
                        lambda: (
                            self.merge_with_previous(caption)
                            if self.captions.index(caption) > 0
                            else None
                        ),
                    )
                    ui.button("Merge with next", icon="merge_type").props(
                        "flat dense"
                    ).on(
                        "click",
                        lambda: (
                            self.merge_with_next(caption)
                            if self.captions.index(caption) < len(self.captions) - 1
                            else None
                        ),
                    )

                    with ui.row().classes("gap-2"):
                        ui.button("Close").props("flat dense").on(
                            "click",
                            lambda: self.select_caption(
                                caption, speaker_select, True, new_text=text_area.value
                            ),
                        ).classes("button-close")

                        if self.data_format == "txt":
                            ui.button("Add", color="green").props("flat dense").on(
                                "click", lambda: self.add_caption_after(caption)
                            )

                        ui.button("Delete", color="red").props("flat dense").on(
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
                        "text-sm text-gray-500"
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
                            "text-sm text-gray-500"
                        )
                    with ui.row().classes("w-full justify-between items-end"):
                        ui.label(caption.text).classes(
                            "text-sm leading-relaxed whitespace-pre-wrap"
                        )
                        text_color = "text-gray-500"

                        tooltip_text = (
                            "Character count."
                            if self.data_format == "txt"
                            else "Character count.  Max 42 per line (guideline)."
                        )

                        lines = caption.text.split("\n")
                        line_lengths = [str(len(x)) for x in lines]

                        # Check for exceeded limit
                        if self.data_format != "txt" and any(
                            len(x) > CHARACTER_LIMIT for x in lines
                        ):
                            text_color = CHARACTER_LIMIT_EXCEEDED_COLOR
                            tooltip_text = f"Character limit of {CHARACTER_LIMIT} exceeded in one or more lines."

                        character_label = "/".join(line_lengths)

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
        warnings = []
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
                    if len(line) > CHARACTER_LIMIT:
                        errors.append(
                            f"Caption #{caption.index} has a line with {len(line)} characters (max {CHARACTER_LIMIT})."
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

        with ui.dialog() as dialog:
            with ui.card().classes("p-6").style("max-width: 700px; min-width: 500px;"):
                # Header
                with ui.row().classes("w-full items-center justify-between mb-4"):
                    ui.label("Subtitle Validation").classes("text-h5 font-bold")
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense color=grey-7"
                    )

                ui.separator().classes("mb-4")

                if errors:
                    # Error summary
                    with ui.card().classes("bg-red-50 border-l-4 p-4 mb-4").style(
                        "border-left-color: #dc2626;"
                    ):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("error", size="md").classes("text-red-600")
                            ui.label(
                                f"{len(set(errorenous_captions))} caption(s) with issues found"
                            ).classes("text-h6 font-semibold text-red-900")

                    # Error list
                    with ui.column().classes("w-full gap-2 max-h-96 overflow-y-auto"):
                        for error in errors:
                            with ui.row().classes("items-start gap-2"):
                                ui.icon("warning", size="sm").classes(
                                    "text-red-600 mt-1"
                                )
                                ui.label(error).classes("text-body2")
                else:
                    # Success message
                    with ui.card().classes("bg-green-50 border-l-4 p-4").style(
                        "border-left-color: #16a34a;"
                    ):
                        with ui.row().classes("items-center gap-3"):
                            ui.icon("check_circle", size="lg").classes("text-green-600")
                            with ui.column().classes("gap-1"):
                                ui.label("All captions are valid!").classes(
                                    "text-h6 font-semibold text-green-900"
                                )
                                ui.label(
                                    f"{len(self.captions)} caption(s) checked"
                                ).classes("text-body2 text-green-700")

                # Footer
                with ui.row().classes("w-full justify-end mt-4"):
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
                    ("Split caption", "Ctrl/⌘ + Enter"),
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
                    ("Validate captions", "Ctrl + V"),
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
            with ui.card().classes("w-2/3 max-w-2xl").style("padding: 24px;"):
                ui.label("Keyboard Shortcuts").classes("text-h5 mb-4 font-bold")

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
                                        "text-body2 font-mono bg-gray-100 px-2 py-1 rounded"
                                    )

                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Close").props("flat color=primary").on(
                        "click", dialog.close
                    )

        if open_window:
            dialog.open()
        else:
            ui.button("Shortcuts").props("icon=keyboard flat dense color=black").on(
                "click", lambda: dialog.open()
            ).classes("button-open-search")

    def show_export_dialog(self, filename: str) -> None:
        """
        Show comprehensive export dialog with format options and live preview.
        """
        ui.add_head_html(default_styles)
        with ui.dialog() as dialog:
            with ui.card().classes("p-6").style(
                "min-width: 1000px; max-width: 1400px; background-color: #ffffff;"
            ):
                # Header
                with ui.row().classes("w-full items-center justify-between mb-4"):
                    ui.label("Export Transcription").classes(
                        "text-h5 font-bold text-black"
                    )
                    ui.button(icon="close", on_click=dialog.close).props(
                        "flat round dense color=grey-7"
                    )

                ui.separator().classes("mb-4")

                # Two-column layout
                with ui.row().classes("w-full gap-6"):
                    # Left: Options (40%)
                    with ui.column().classes("gap-4").style("flex: 0 0 400px;"):
                        # Format
                        ui.label("Format").classes("text-subtitle1 font-semibold")
                        if self.data_format == "srt":
                            format_opts = {
                                "srt": "SubRip (.srt)",
                                "vtt": "WebVTT (.vtt)",
                            }
                        else:
                            format_opts = {
                                "txt": "Text (.txt)",
                                "json": "JSON (.json)",
                                "rtf": "RTF (.rtf)",
                                "csv": "CSV (.csv)",
                                "tsv": "TSV (.tsv)",
                            }

                        fmt = (
                            ui.select(
                                options=format_opts, value=list(format_opts.keys())[0]
                            )
                            .classes("w-full")
                            .props("outlined dense")
                        )

                        ui.separator()

                        # Options container - will show/hide based on format
                        options_container = ui.column().classes("gap-4")

                        with options_container:
                            # Timestamps (for txt, json, csv, tsv)
                            ts_section = ui.column().classes("gap-2")
                            with ts_section:
                                ui.label("Timestamps").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                ts_incl = ui.checkbox("Include timestamps", value=True)

                                with ui.row().classes("w-full gap-2 items-center"):
                                    ts_which = (
                                        ui.select(
                                            options={
                                                "both": "Start & End",
                                                "start": "Start only",
                                                "end": "End only",
                                            },
                                            value="both",
                                            label="Timestamp range",
                                        )
                                        .classes("flex-1")
                                        .props("dense outlined")
                                    )
                                    ts_pos = (
                                        ui.select(
                                            options={
                                                "before": "Before text",
                                                "after": "After text",
                                            },
                                            value="before",
                                            label="Position",
                                        )
                                        .classes("flex-1")
                                        .props("dense outlined")
                                    )
                                    ts_pos.visible = False

                                ts_fmt = (
                                    ui.select(
                                        options={
                                            "srt": "SRT (00:00:00,000)",
                                            "vtt": "VTT (00:00:00.000)",
                                            "seconds": "Seconds (0.000)",
                                            "ms": "Milliseconds",
                                        },
                                        value="srt",
                                        label="Format",
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                ui.separator()

                            # Text options (for txt only)
                            txt_section = ui.column().classes("gap-2")
                            with txt_section:
                                ui.label("Text Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                txt_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                txt_idx_incl = ui.checkbox(
                                    "Include block numbers", value=False
                                )
                                txt_sep_type = (
                                    ui.select(
                                        options={
                                            "\\n\\n": "Double newline",
                                            "\\n": "Single newline",
                                            "---": "Line",
                                            "custom": "Custom",
                                        },
                                        value="\\n\\n",
                                        label="Separator",
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                txt_sep_custom = (
                                    ui.input(placeholder="Custom separator")
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                txt_sep_custom.visible = False
                                txt_sep_type.on(
                                    "update:model-value",
                                    lambda e: setattr(
                                        txt_sep_custom, "visible", e.args == "custom"
                                    ),
                                )
                                ui.separator()

                            # RTF options
                            rtf_section = ui.column().classes("gap-2")
                            with rtf_section:
                                ui.label("RTF Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                rtf_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                rtf_idx_incl = ui.checkbox(
                                    "Include block numbers", value=False
                                )
                                ui.separator()

                            # CSV options (for csv only)
                            csv_section = ui.column().classes("gap-2")
                            with csv_section:
                                ui.label("CSV Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                csv_hdr = ui.checkbox("Include header row", value=True)
                                csv_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                csv_qt = (
                                    ui.input(label="Quote character", value='"')
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                csv_delim = (
                                    ui.input(label="Delimiter", value=",")
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                ui.separator()

                            # TSV options (for tsv only)
                            tsv_section = ui.column().classes("gap-2")
                            with tsv_section:
                                ui.label("TSV Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                tsv_hdr = ui.checkbox("Include header row", value=True)
                                tsv_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                tsv_tab_type = (
                                    ui.select(
                                        options={
                                            "\\t": "Real tab character",
                                            "spaces": "Spaces",
                                        },
                                        value="\\t",
                                        label="Tab type",
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                tsv_tab_width = (
                                    ui.number(
                                        label="Tab width (spaces)",
                                        value=4,
                                        min=1,
                                        max=16,
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                tsv_tab_width.visible = False
                                tsv_tab_type.on(
                                    "update:model-value",
                                    lambda e: setattr(
                                        tsv_tab_width, "visible", e.args == "spaces"
                                    ),
                                )
                                ui.separator()

                            # JSON options (for json only)
                            json_section = ui.column().classes("gap-2")
                            with json_section:
                                ui.label("JSON Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                json_indent = (
                                    ui.number(
                                        label="Indentation spaces",
                                        value=2,
                                        min=0,
                                        max=8,
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                json_ascii = ui.checkbox(
                                    "Escape non-ASCII characters", value=False
                                )
                                ui.separator()

                        def update_options_visibility():
                            """Show/hide options based on selected format"""
                            current_fmt = fmt.value

                            # SRT/VTT - no options
                            ts_section.visible = current_fmt in [
                                "txt",
                                "json",
                                "csv",
                                "tsv",
                                "rtf",
                            ]
                            txt_section.visible = current_fmt == "txt"
                            csv_section.visible = current_fmt == "csv"
                            tsv_section.visible = current_fmt == "tsv"
                            json_section.visible = current_fmt == "json"
                            rtf_section.visible = current_fmt == "rtf"

                        fmt.on(
                            "update:model-value", lambda: update_options_visibility()
                        )
                        update_options_visibility()

                    # Right: Preview (60%)
                    with ui.column().classes("flex-1"):
                        ui.label("Preview").classes("text-subtitle1 font-semibold mb-2")
                        with ui.card().classes("bg-gray-900 p-4").style(
                            "height: 550px; overflow-y: auto;"
                        ):
                            prev = (
                                ui.html("", sanitize=False)
                                .classes("text-white")
                                .style(
                                    "font-family: 'Courier New', monospace; font-size: 13px; white-space: pre-wrap;"
                                )
                            )
                        cnt_lbl = ui.label("").classes("text-caption mt-2")

                def upd_prev():
                    try:
                        caps = self.captions[:5]
                        out = ""

                        def fmt_ts(ts, f):
                            p = ts.replace(",", ":").split(":")
                            h, m, s, ms = int(p[0]), int(p[1]), int(p[2]), int(p[3])
                            if f == "seconds":
                                return f"{h*3600 + m*60 + s + ms/1000:.3f}"
                            if f == "ms":
                                return str(h * 3600000 + m * 60000 + s * 1000 + ms)
                            if f == "vtt":
                                return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
                            return ts  # srt format

                        def build_ts_str(cap):
                            """Build timestamp string based on options"""
                            if not ts_incl.value:
                                return ""
                            parts = []
                            if ts_which.value in ["start", "both"]:
                                parts.append(fmt_ts(cap.start_time, ts_fmt.value))
                            if ts_which.value in ["end", "both"]:
                                parts.append(fmt_ts(cap.end_time, ts_fmt.value))
                            return " - ".join(parts) if parts else ""

                        if fmt.value == "srt":
                            out = "\n\n".join(c.to_srt_format() for c in caps)
                        elif fmt.value == "vtt":
                            out = "WEBVTT\n\n" + "\n\n".join(
                                f"{c.index}\n{c.start_time.replace(',','.')} --> {c.end_time.replace(',','.')}\n{c.text}"
                                for c in caps
                            )
                        elif fmt.value == "txt":
                            parts = []
                            for c in caps:
                                p_parts = []
                                if txt_idx_incl and txt_idx_incl.value:
                                    p_parts.append(f"[{c.index}]")

                                ts_str = build_ts_str(c)
                                if ts_str and ts_pos.value == "before":
                                    p_parts.append(f"({ts_str})")

                                if txt_spk_incl and txt_spk_incl.value:
                                    p_parts.append(f"{c.speaker}:")

                                # Add text on new line or same line
                                if p_parts:
                                    p = " ".join(p_parts) + "\n" + c.text
                                else:
                                    p = c.text

                                if ts_str and ts_pos.value == "after":
                                    p += f"\n({ts_str})"

                                parts.append(p)
                            s = (
                                txt_sep_custom.value
                                if txt_sep_type.value == "custom"
                                else txt_sep_type.value.replace("\\n", "\n")
                            )
                            out = s.join(parts)
                        elif fmt.value == "rtf":
                            parts = []
                            for c in caps:
                                p_parts = []
                                if rtf_idx_incl and rtf_idx_incl.value:
                                    p_parts.append(f"[{c.index}]")

                                ts_str = build_ts_str(c)
                                if ts_str:
                                    p_parts.append(f"({ts_str})")

                                if rtf_spk_incl and rtf_spk_incl.value:
                                    p_parts.append(f"{c.speaker}:")

                                # Add text on new line or same line
                                if p_parts:
                                    p = " ".join(p_parts) + "\n" + c.text
                                else:
                                    p = c.text

                                parts.append(p)
                            out = "\n\n".join(parts)
                        elif fmt.value == "json":
                            d = {"total": len(self.captions), "captions": []}
                            for c in caps:
                                cd = {
                                    "index": c.index,
                                    "speaker": c.speaker,
                                    "text": c.text,
                                }
                                if ts_incl.value:
                                    if ts_which.value in ["start", "both"]:
                                        cd["start"] = fmt_ts(c.start_time, ts_fmt.value)
                                    if ts_which.value in ["end", "both"]:
                                        cd["end"] = fmt_ts(c.end_time, ts_fmt.value)
                                d["captions"].append(cd)
                            out = json.dumps(
                                d,
                                indent=int(json_indent.value),
                                ensure_ascii=json_ascii.value,
                            )
                        elif fmt.value == "csv":
                            q = csv_qt.value
                            delim = csv_delim.value
                            lines = []
                            if csv_hdr.value:
                                h = ["index"]
                                if ts_incl.value:
                                    if ts_which.value in ["start", "both"]:
                                        h.append("start")
                                    if ts_which.value in ["end", "both"]:
                                        h.append("end")
                                if csv_spk_incl.value:
                                    h.append("speaker")
                                h.append("text")
                                lines.append(delim.join(f"{q}{x}{q}" for x in h))
                            for c in caps:
                                r = [str(c.index)]
                                if ts_incl.value:
                                    if ts_which.value in ["start", "both"]:
                                        r.append(fmt_ts(c.start_time, ts_fmt.value))
                                    if ts_which.value in ["end", "both"]:
                                        r.append(fmt_ts(c.end_time, ts_fmt.value))
                                if csv_spk_incl.value:
                                    r.append(c.speaker)
                                r.append(c.text.replace(q, q + q).replace("\n", " "))
                                lines.append(delim.join(f"{q}{x}{q}" for x in r))
                            out = "\n".join(lines)
                        elif fmt.value == "tsv":
                            # Determine tab character
                            if tsv_tab_type.value == "\\t":
                                tab_char = "\t"
                            else:
                                tab_char = " " * int(tsv_tab_width.value)

                            lines = []
                            if tsv_hdr.value:
                                h = ["index"]
                                if ts_incl.value:
                                    if ts_which.value in ["start", "both"]:
                                        h.append("start")
                                    if ts_which.value in ["end", "both"]:
                                        h.append("end")
                                if tsv_spk_incl.value:
                                    h.append("speaker")
                                h.append("text")
                                lines.append(tab_char.join(h))
                            for c in caps:
                                r = [str(c.index)]
                                if ts_incl.value:
                                    if ts_which.value in ["start", "both"]:
                                        r.append(fmt_ts(c.start_time, ts_fmt.value))
                                    if ts_which.value in ["end", "both"]:
                                        r.append(fmt_ts(c.end_time, ts_fmt.value))
                                if tsv_spk_incl.value:
                                    r.append(c.speaker)
                                r.append(c.text.replace("\t", "  ").replace("\n", " "))
                                lines.append(tab_char.join(r))
                            out = "\n".join(lines)
                        elif fmt.value == "rtf":
                            # Show RTF source code for preview
                            parts = []
                            for c in caps:
                                parts.append(
                                    f"{c.speaker}: {c.start_time} - {c.end_time}"
                                )
                                parts.append(c.text.replace("\n", "\\line "))
                                parts.append("")
                            out = "\n".join(parts)
                        else:
                            out = "(RTF preview unavailable)"

                        if len(self.captions) > 5:
                            out += f"\n\n... {len(self.captions)-5} more captions"

                        import html

                        prev.set_content(html.escape(out).replace("\n", "<br>"))
                        cnt_lbl.set_text(
                            f"Total: {len(self.captions)} | Showing: {min(5, len(self.captions))}"
                        )
                    except Exception as e:
                        import html

                        prev.set_content(
                            f"<span style='color:#f88'>{html.escape(str(e))}</span>"
                        )

                # Connect updates
                for ctrl in [fmt, ts_incl, ts_fmt, ts_which, ts_pos]:
                    ctrl.on("update:model-value", lambda: upd_prev())

                # CSV controls
                csv_hdr.on("update:model-value", lambda: upd_prev())
                csv_spk_incl.on("update:model-value", lambda: upd_prev())
                csv_qt.on("blur", lambda: upd_prev())
                csv_delim.on("blur", lambda: upd_prev())

                # TSV controls
                tsv_hdr.on("update:model-value", lambda: upd_prev())
                tsv_spk_incl.on("update:model-value", lambda: upd_prev())
                tsv_tab_type.on("update:model-value", lambda: upd_prev())
                tsv_tab_width.on("blur", lambda: upd_prev())

                # JSON controls
                json_indent.on("blur", lambda: upd_prev())
                json_ascii.on("update:model-value", lambda: upd_prev())

                # TXT controls
                txt_spk_incl.on("update:model-value", lambda: upd_prev())
                txt_idx_incl.on("update:model-value", lambda: upd_prev())
                txt_sep_type.on("update:model-value", lambda: upd_prev())
                txt_sep_custom.on("blur", lambda: upd_prev())

                # RTF controls
                rtf_spk_incl.on("update:model-value", lambda: upd_prev())
                rtf_idx_incl.on("update:model-value", lambda: upd_prev())

                upd_prev()

                ui.separator().classes("my-4")

                # Footer
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label(f"File: {filename}.{fmt.value}").classes("text-body2")
                    with ui.row().classes("gap-2"):
                        ui.button("Cancel", on_click=dialog.close).props("outline")

                        def exp():
                            try:
                                c = None

                                def fmt_ts(ts, f):
                                    p = ts.replace(",", ":").split(":")
                                    h, m, s, ms = (
                                        int(p[0]),
                                        int(p[1]),
                                        int(p[2]),
                                        int(p[3]),
                                    )
                                    if f == "seconds":
                                        return f"{h*3600 + m*60 + s + ms/1000:.3f}"
                                    if f == "ms":
                                        return str(
                                            h * 3600000 + m * 60000 + s * 1000 + ms
                                        )
                                    if f == "vtt":
                                        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
                                    return ts

                                def build_ts_str(cap):
                                    """Build timestamp string based on options"""
                                    if not ts_incl.value:
                                        return ""
                                    parts = []
                                    if ts_which.value in ["start", "both"]:
                                        parts.append(
                                            fmt_ts(cap.start_time, ts_fmt.value)
                                        )
                                    if ts_which.value in ["end", "both"]:
                                        parts.append(fmt_ts(cap.end_time, ts_fmt.value))
                                    return " - ".join(parts) if parts else ""

                                if fmt.value == "srt":
                                    c = self.export_srt()
                                elif fmt.value == "vtt":
                                    c = self.export_vtt()
                                elif fmt.value == "rtf":
                                    c = self.export_rtf(
                                        rtf_spk_incl.value,
                                        ts_incl.value,
                                        rtf_idx_incl.value,
                                        ts_which.value,
                                        ts_fmt.value,
                                    )
                                elif fmt.value == "txt":
                                    # TXT format with custom options
                                    parts = []
                                    sep_str = "\n\n"
                                    if txt_sep_type.value == "custom":
                                        sep_str = txt_sep_custom.value.replace(
                                            "\\n", "\n"
                                        )
                                    elif txt_sep_type.value != "\\n\\n":
                                        sep_str = txt_sep_type.value.replace(
                                            "\\n", "\n"
                                        )

                                    for cap in self.captions:
                                        p_parts = []
                                        if txt_idx_incl.value:
                                            p_parts.append(f"[{cap.index}]")

                                        ts_str = build_ts_str(cap)
                                        if ts_str and ts_pos.value == "before":
                                            p_parts.append(f"({ts_str})")

                                        if txt_spk_incl.value:
                                            p_parts.append(f"{cap.speaker}:")

                                        # Add text on new line or same line
                                        if p_parts:
                                            p = " ".join(p_parts) + "\n" + cap.text
                                        else:
                                            p = cap.text

                                        if ts_str and ts_pos.value == "after":
                                            p += f"\n({ts_str})"

                                        parts.append(p)
                                    c = sep_str.join(parts)
                                elif fmt.value == "csv":
                                    # CSV format with custom options
                                    q = csv_qt.value or '"'
                                    d = csv_delim.value or ","
                                    lines = []
                                    if csv_hdr.value:
                                        h = ["index"]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                h.append("start")
                                            if ts_which.value in ["end", "both"]:
                                                h.append("end")
                                        if csv_spk_incl.value:
                                            h.append("speaker")
                                        h.append("text")
                                        lines.append(d.join(f"{q}{x}{q}" for x in h))
                                    for cap in self.captions:
                                        r = [str(cap.index)]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                r.append(
                                                    fmt_ts(cap.start_time, ts_fmt.value)
                                                )
                                            if ts_which.value in ["end", "both"]:
                                                r.append(
                                                    fmt_ts(cap.end_time, ts_fmt.value)
                                                )
                                        if csv_spk_incl.value:
                                            r.append(cap.speaker)
                                        r.append(
                                            cap.text.replace(q, q + q).replace(
                                                "\n", " "
                                            )
                                        )
                                        lines.append(d.join(f"{q}{x}{q}" for x in r))
                                    c = "\n".join(lines)
                                elif fmt.value == "tsv":
                                    # TSV format with custom options
                                    if tsv_tab_type.value == "\\t":
                                        tab_char = "\t"
                                    else:
                                        tab_char = " " * int(tsv_tab_width.value)

                                    lines = []
                                    if tsv_hdr.value:
                                        h = ["index"]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                h.append("start")
                                            if ts_which.value in ["end", "both"]:
                                                h.append("end")
                                        if tsv_spk_incl.value:
                                            h.append("speaker")
                                        h.append("text")
                                        lines.append(tab_char.join(h))
                                    for cap in self.captions:
                                        r = [str(cap.index)]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                r.append(
                                                    fmt_ts(cap.start_time, ts_fmt.value)
                                                )
                                            if ts_which.value in ["end", "both"]:
                                                r.append(
                                                    fmt_ts(cap.end_time, ts_fmt.value)
                                                )
                                        if tsv_spk_incl.value:
                                            r.append(cap.speaker)
                                        r.append(
                                            cap.text.replace("\t", "  ").replace(
                                                "\n", " "
                                            )
                                        )
                                        lines.append(tab_char.join(r))
                                    c = "\n".join(lines)
                                elif fmt.value == "json":
                                    # JSON format with custom options
                                    data = self.export_json()
                                    # Update data based on timestamp options
                                    if ts_incl.value:
                                        for i, cap in enumerate(self.captions):
                                            if i < len(data["segments"]):
                                                seg = data["segments"][i]
                                                # Remove timestamps not selected
                                                if ts_which.value == "start":
                                                    seg["start"] = fmt_ts(
                                                        cap.start_time, ts_fmt.value
                                                    )
                                                    if "end" in seg:
                                                        del seg["end"]
                                                elif ts_which.value == "end":
                                                    seg["end"] = fmt_ts(
                                                        cap.end_time, ts_fmt.value
                                                    )
                                                    if "start" in seg:
                                                        del seg["start"]
                                                else:  # both
                                                    seg["start"] = fmt_ts(
                                                        cap.start_time, ts_fmt.value
                                                    )
                                                    seg["end"] = fmt_ts(
                                                        cap.end_time, ts_fmt.value
                                                    )
                                    else:
                                        # Remove all timestamps
                                        for seg in data["segments"]:
                                            if "start" in seg:
                                                del seg["start"]
                                            if "end" in seg:
                                                del seg["end"]

                                    indent = (
                                        int(json_indent.value)
                                        if json_indent.value
                                        else None
                                    )
                                    c = json.dumps(
                                        data,
                                        indent=indent,
                                        ensure_ascii=json_ascii.value,
                                    )

                                ui.download(
                                    c.encode("utf-8"),
                                    filename=f"{filename}.{fmt.value}",
                                )
                                ui.notify(
                                    f"Exported as {fmt.value.upper()}", type="positive"
                                )
                                dialog.close()
                            except Exception as e:
                                ui.notify(f"Export failed: {str(e)}", type="negative")

                        ui.button("Export", icon="download", on_click=exp).props(
                            "flat color=white"
                        ).classes("button-default-style")

            dialog.open()

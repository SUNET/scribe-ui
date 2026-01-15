import json
import re
import requests

from nicegui import app, events, ui
from typing import Any, Callable, Dict, List, Optional
from utils.common import get_auth_header
from utils.settings import get_settings

CHARACTER_LIMIT_EXCEEDED_COLOR = "text-red"
CHARACTER_LIMIT = 42

settings = get_settings()


class SRTCaption:
    def __init__(
        self,
        index: int,
        start_time: str,
        end_time: str,
        text: str,
        speaker: Optional[str] = "",
    ):
        """
        Initialize a caption with index, start time, end time, and text.
        """

        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
        self.is_selected = False
        self.is_highlighted = False  # For search highlighting
        self.is_valid = True  # For validation
        self.speaker = speaker if speaker else "UNKNOWN"

    def copy(self) -> "SRTCaption":
        """
        Create a deep copy of the caption.
        """

        new_caption = SRTCaption(
            self.index,
            self.start_time,
            self.end_time,
            self.text,
            self.speaker,
        )
        new_caption.is_selected = self.is_selected
        new_caption.is_highlighted = self.is_highlighted
        new_caption.is_valid = self.is_valid
        return new_caption

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start": self.get_start_seconds(),
            "end": self.get_end_seconds(),
            "duration": self.get_end_seconds() - self.get_start_seconds(),
        }

    def to_srt_format(self) -> str:
        return f"{self.index}\n{self.start_time} --> {self.end_time}\n{self.text}\n"

    def get_start_seconds(self) -> float:
        """
        Convert timestamp to seconds for calculations.
        """

        time_parts = self.start_time.replace(",", ".").split(":")
        hours = float(time_parts[0])
        minutes = float(time_parts[1])
        seconds = float(time_parts[2])

        return hours * 3600 + minutes * 60 + seconds

    def get_end_seconds(self) -> float:
        """
        Convert timestamp to seconds for calculations.
        """

        time_parts = str(self.end_time).replace(",", ".").split(":")

        hours = float(time_parts[0])
        minutes = float(time_parts[1])
        seconds = float(time_parts[2])

        return hours * 3600 + minutes * 60 + seconds

    def matches_search(self, search_term: str, case_sensitive: bool = False) -> bool:
        """
        Check if caption matches search term.
        """
        if not search_term:
            return False

        text = self.text if case_sensitive else self.text.lower()
        term = search_term if case_sensitive else search_term.lower()

        return term in text


class UndoRedoManager:
    """
    Manages undo/redo history for the SRT editor.
    """

    def __init__(self, max_history: int = 50):
        self.undo_stack: List[List[SRTCaption]] = []
        self.redo_stack: List[List[SRTCaption]] = []
        self.max_history = max_history

    def save_state(self, captions: List[SRTCaption]) -> None:
        """
        Save the current state to the undo stack.
        """

        # Deep copy the captions list
        state = [caption.copy() for caption in captions]
        self.undo_stack.append(state)

        # Clear redo stack when new action is performed
        self.redo_stack.clear()

        # Limit history size
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)

    def undo(self, current_captions: List[SRTCaption]) -> Optional[List[SRTCaption]]:
        """
        Undo the last action and return the previous state.
        """
        if not self.undo_stack:
            return None

        # Save current state to redo stack
        current_state = [caption.copy() for caption in current_captions]
        self.redo_stack.append(current_state)

        # Pop and return the previous state
        return self.undo_stack.pop()

    def redo(self, current_captions: List[SRTCaption]) -> Optional[List[SRTCaption]]:
        """
        Redo the last undone action and return the next state.
        """

        if not self.redo_stack:
            return None

        # Save current state to undo stack
        current_state = [caption.copy() for caption in current_captions]
        self.undo_stack.append(current_state)

        # Pop and return the next state
        return self.redo_stack.pop()

    def can_undo(self) -> bool:
        """
        Check if undo is available.
        """

        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """
        Check if redo is available.
        """

        return len(self.redo_stack) > 0

    def clear(self) -> None:
        """
        Clear all history.
        """

        self.undo_stack.clear()
        self.redo_stack.clear()


class SRTEditor:
    def __init__(self, uuid: str, srt_format: str):
        """
        Initialize the SRT editor with empty captions and other properties.
        """

        self.uuid = uuid
        self.srt_format = srt_format
        self.captions: List[SRTCaption] = []
        self.selected_caption: Optional[SRTCaption] = None
        self.caption_cards = {}
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
        self.keypresses = 0

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

        if self.has_unsaved_changes():
            self.show_save_confirmation_dialog(
                on_save=do_close,
                on_discard=do_close,
                on_cancel=None,  # Just close the dialog, don't navigate
            )
        else:
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
            self.refresh_display()
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
            self.refresh_display()
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
                data = self.export_json()

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
        self.keypresses += 1

        if self.keypresses > 1:
            self.keypresses = 0
            return

        match event.key:
            # Next block of captions, Ctrl+Down
            case "ArrowDown" if event.modifiers.alt:
                self.select_next_caption()

            # Prev block of captions, Ctrl+Up
            case "ArrowUp" if event.modifiers.alt:
                self.select_prev_caption()

            # Split block, Alt+Enter
            case "Enter" if event.modifiers.alt:
                self.split_caption(self.selected_caption)

            # Merge block with next, Ctrl+M
            case "m" if event.modifiers.ctrl:
                self.merge_with_next(self.selected_caption)

            # Merge block with previous, Ctrl+Shift+M
            case "M" if event.modifiers.ctrl:
                self.merge_with_previous(self.selected_caption)

            # Add caption after, Ctrl+N
            case "n" if event.modifiers.ctrl:
                self.add_caption_after(self.selected_caption)

            # Delete block, Ctrl+Shift+D
            case "d" if event.modifiers.ctrl:
                self.remove_caption(self.selected_caption)

            # Validate captions, Ctrl+Shift+V
            case "v" if event.modifiers.ctrl:
                self.validate_captions()

            # Play/pause video, Ctrl+Space
            case " " if event.modifiers.ctrl:
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
                self.select_caption(self.selected_caption)

            # Open find, Ctrl+F
            case "f" if event.modifiers.ctrl:
                self.create_search_panel(open_window=True)

            # Save file, Ctrl+S / Cmd+S
            case "s" if event.modifiers.ctrl or event.modifiers.meta:
                self.save_srt_changes()

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

        csv_content = ""
        for caption in self.captions:
            escaped_text = caption.text.replace('"', '""')
            csv_content += f'"{caption.start_time}","{caption.end_time}","{caption.speaker}","{escaped_text}"\n'

        return csv_content.strip()

    def export_tsv(self) -> str:
        """
        Export to TSV format.
        Fields: Start time, stop time, speaker, text
        """

        tsv_content = ""
        for caption in self.captions:
            escaped_text = caption.text.replace("\t", "    ").replace("\n", " ")
            tsv_content += f"{caption.start_time}\t{caption.end_time}\t{caption.speaker}\t{escaped_text}\n"

        return tsv_content.strip()

    def export_rtf(self) -> str:
        """
        Export captions to RTF format with proper Unicode handling.
        """

        def to_rtf_unicode(text: str) -> str:
            result = []
            for ch in text:
                code = ord(ch)
                if code < 128:
                    if ch in ["\\", "{", "}"]:
                        result.append("\\" + ch)
                    else:
                        result.append(ch)
                else:
                    signed_code = code if code <= 0x7FFF else code - 0x10000
                    result.append(f"\\u{signed_code}? ")
            return "".join(result)

        rtf_content = (
            r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}" r"\viewkind4\uc1\pard\f0\fs20 "
        )

        for caption in self.captions:
            rtf_content += (
                r"\b "
                + to_rtf_unicode(f"{caption.speaker}: ")
                + r"\b0 "
                + to_rtf_unicode(f"{caption.start_time} - {caption.end_time}")
                + r"\line "
                + to_rtf_unicode(caption.text).replace("\n", r"\line ")
                + r"\line\line "
            )

        rtf_content += "}"

        return rtf_content.strip()

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

        vtt_content = "WEBVTT\n\n"
        for caption in self.captions:
            vtt_content += f"{caption.index}\n"
            vtt_content += f"{caption.start_time. replace(',', '.')} --> {caption.end_time.replace(',', '.')}\n"
            vtt_content += f"{caption.text}\n\n"

        return vtt_content

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

        # Clear previous highlights
        for caption in self.captions:
            caption.is_highlighted = False

        if not search_term.strip():
            self.refresh_display()
            self.update_search_info()
            return

        # Find matching captions
        for i, caption in enumerate(self.captions):
            if caption.matches_search(search_term, self.case_sensitive):
                self.search_results.append(i)
                caption.is_highlighted = True

        self.current_search_index = 0
        self.refresh_display()
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
        self.refresh_display()

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
        self.refresh_display()
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
            self.refresh_display()
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
        self.refresh_display()

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

        self.refresh_display()

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
        self.refresh_display()

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
        self.refresh_display()

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
                    "blur", lambda e: self.update_caption_text(caption, e.sender.value)
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
                # Show text with search highlighting
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

                        character_label = ""
                        for x in caption.text.split("\n"):
                            if len(x) > CHARACTER_LIMIT and self.data_format != "txt":
                                text_color = CHARACTER_LIMIT_EXCEEDED_COLOR
                                tooltip_text = f"Character limit of {CHARACTER_LIMIT} exceeded in one or more lines."
                            character_label += f"{len(x)}/"

                        if character_label.endswith("/"):
                            character_label = character_label[:-1]

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

        return card

    def refresh_display(self) -> None:
        """Refresh the caption display"""
        if self.main_container:
            self.main_container.clear()
            with self.main_container:
                if not self.captions:
                    ui.label("No captions loaded").classes(
                        "text-gray-500 text-center p-8"
                    )
                else:
                    for caption in self.captions:
                        self.create_caption_card(caption)

    def validate_captions(self):
        """
        Validate captions for overlapping times and empty text.
        """
        errors = []
        seen_times = set()
        start_times = {}
        errorenous_captions = []

        for caption in self.captions:
            if not caption.text.strip():
                errors.append(f"Caption #{caption.index} has no text.")
            if (caption.start_time, caption.end_time) in seen_times:
                errors.append(
                    f"Caption #{caption.index} overlaps with another caption."
                )

            seen_times.add((caption.start_time, caption.end_time))

            if caption.start_time in start_times:
                start_times[caption.start_time].append(caption.index)
            else:
                start_times[caption.start_time] = [caption.index]

            if caption.get_end_seconds() < caption.get_start_seconds():
                caption.is_valid = False
                errorenous_captions.append(caption)
                errors.append(
                    f"Caption #{caption.index} has end time before start time."
                )

        # Check for overlapping times
        for i in range(len(self.captions) - 1):
            current = self.captions[i]
            next_caption = self.captions[i + 1]

            if current.get_end_seconds() > next_caption.get_start_seconds():
                current.is_valid = False
                errorenous_captions.append(current)
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
                        errorenous_captions.append(cap)
                        cap.is_valid = False

        with ui.dialog() as dialog:
            with (
                ui.card()
                .style(
                    "background-color: white; align-self: center; border:  0; width: 80%;"
                )
                .classes("w-full no-shadow no-border")
            ):
                ui.label("Subtitles validation").style("width: 100%;").classes(
                    "text-h6 q-mb-xl text-black"
                )

                with ui.row().classes("w-full"):
                    if errors:
                        ui.label(
                            "The following issues were found with the captions:"
                        ).classes("text-bold")
                        ui.html("<br>".join(errors), sanitize=False)
                    else:
                        for caption in self.captions:
                            caption.is_valid = True

                        ui.label("All captions are valid, no errors found!")

                with ui.row().classes("justify-between w-full"):
                    with ui.button(
                        "Close",
                        icon="cancel",
                    ) as cancel:
                        cancel.on("click", lambda: dialog.close())
                        cancel.props("color=black flat")
                        cancel.classes("cancel-style")

            dialog.open()

        self.refresh_display()

    def show_keyboard_shortcuts(self) -> None:
        """
        Show keyboard shortcuts dialog.
        """

        shortcuts = [
            ("Next caption", "Alt/Option + Down Arrow"),
            ("Previous caption", "Alt/Option + Up Arrow"),
            ("Split caption", "Alt + Enter"),
            ("Merge with next caption", "Ctrl + M"),
            ("Merge with previous caption", "Ctrl + Shift + M"),
            ("Add caption after", "Ctrl + N"),
            ("Delete caption", "Ctrl + Shift + D"),
            ("Validate captions", "Ctrl + Shift + V"),
            ("Play/Pause video", "Ctrl + Space"),
            ("Undo", "Ctrl/⌘ + Z"),
            ("Redo", "Ctrl + Y / ⌘ + Shift + Z / ⌘ + Y"),
            ("Find", "Ctrl + F"),
            ("Save", "Ctrl + S / ⌘ + S"),
            ("Close block", "Escape"),
        ]

        with ui.dialog() as dialog:
            with ui.card().classes("w-1/3 max-w-full").style("padding: 16px;"):
                ui.label("Keyboard Shortcuts").classes("text-h6 mb-3")

                with ui.column().classes("w-full gap-2"):
                    for action, keys in shortcuts:
                        with ui.row().classes("justify-between w-full"):
                            ui.label(action).classes("text-body1")
                            ui.label(keys).classes("text-body2 text-gray-600")

                with ui.row().classes("w-full justify-end"):
                    ui.button("Close").props("flat dense color=black").on(
                        "click", dialog.close
                    )

        ui.button("Shortcuts").props("icon=keyboard flat dense color=black").on(
            "click", lambda: dialog.open()
        ).classes("button-open-search")

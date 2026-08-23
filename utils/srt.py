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
    OVERLAY_SHOW_KEY,
    TIMELINE_DOCK_KEY,
    TIMELINE_SHOW_KEY,
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
    "OVERLAY_SHOW_KEY",
    "TIMELINE_DOCK_KEY",
    "TIMELINE_SHOW_KEY",
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

        # Set by the document editor once it is built, so refresh_display has
        # somewhere to send changes; see refresh_display in srt_render.py.
        self.render_override: Optional[Callable] = None
        # Set the same way, for search and autoscroll to say which caption
        # the reader's attention should move to.
        self.on_select: Optional[Callable] = None
        self.words_per_minute_element = None
        # The status line's own figures, by name -- see set_status_elements.
        self.status_elements: dict = {}
        self.speakers = set()

        # Seeded from what the page opened, not left as None until parsing:
        # the toolbar is built before any content is fetched, and everything
        # in it that asks which format is open -- the Shortcuts dialog most
        # of all, which is worded for captions or for paragraphs -- read
        # None and answered as though it were a transcription. parse_srt and
        # parse_txt still set it, and are still the authority once content
        # has actually been read.
        self.data_format = srt_format
        self.filename = filename

        # Per-word timings, empty for results produced before they existed.
        self.words: List[dict] = []
        self._word_midpoints: List[float] = []
        self.has_confidence = False
        self.show_uncertain_words = False
        self.show_my_edits = False
        # The strip under the video. On by default, the same as the overlay
        # and for the same reason: it shows what is already there rather
        # than adding anything to read.
        self.show_timeline = True
        # The caption playing right now, drawn over the video (subtitles
        # only). On by default, unlike the review markings: it shows what a
        # viewer would see rather than adding anything to read.
        self.show_subtitle_overlay = True
        self.review_sensitivity = DEFAULT_REVIEW_SENSITIVITY
        self.flagged_count_element = None

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

        self.undo_redo_manager.save_state(self.captions, self.speakers)
        self._update_undo_redo_buttons()
        # Mark as having unsaved changes
        self.mark_as_changed()
        self.update_beforeunload_state()

    def restore_speakers(self, speakers) -> None:
        """
        Put the speaker list back as a restored state recorded it.

        Mutated in place rather than rebound: the list is read straight off
        the editor by the speaker menu and by refresh(), and a state saved
        before speakers were tracked carries None, which leaves the current
        list alone rather than emptying it.
        """

        if speakers is None:
            return

        self.speakers.clear()
        self.speakers.update(speakers)

    def undo(self) -> None:
        """
        Undo the last action.
        """
        previous_state = self.undo_redo_manager.undo(self.captions, self.speakers)
        if previous_state is not None:
            self.captions = previous_state.captions
            self.restore_speakers(previous_state.speakers)
            self.selected_caption = None
            self.renumber_captions()
            self.update_words_per_minute()
            # The text just moved, so which words are flagged moved with it.
            self.update_flagged_count()
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
        next_state = self.undo_redo_manager.redo(self.captions, self.speakers)
        if next_state is not None:
            self.captions = next_state.captions
            self.restore_speakers(next_state.speakers)
            self.selected_caption = None
            self.renumber_captions()
            self.update_words_per_minute()
            # The text just moved, so which words are flagged moved with it.
            self.update_flagged_count()
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
        with ui.row().classes("editor-toolbar-group"):
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

            # Validate captions, Ctrl+Shift+V. Subtitles only -- there is
            # nothing to validate in a transcription, which has neither a
            # line-length guideline nor a line count to exceed. Ctrl rather
            # than Cmd as well: Cmd+Shift+V is paste-without-formatting on a
            # Mac, which a text editor should not be taking.
            case "v" if (
                event.modifiers.ctrl
                and event.modifiers.shift
                and self.data_format == "srt"
            ):
                self.validate_captions()

            # Everything else
            case _:
                pass

    def set_words_per_minute_element(self, element) -> None:
        """
        Set the element to display words per minute.
        """

        self.words_per_minute_element = element

    def set_status_elements(self, **elements) -> None:
        """
        Register the status line's own figures, by name: "captions",
        "duration" and "wpm". Each is a label of its own rather than one
        line of text, so each can say what it means on hover -- a bare
        number in a row of numbers explains nothing.

        The language is not among them: it never changes, so the page draws
        it once and the editor never touches it again.
        """

        self.status_elements = elements
        self.update_status()

    def status_values(self) -> dict:
        """
        What the status line reports, keyed the same way its elements are.
        """

        count = len(self.captions)

        return {
            "captions": f"{count} caption" if count == 1 else f"{count} captions",
            "duration": (
                self.format_duration(self.captions[-1].get_end_seconds())
                if self.captions
                else ""
            ),
            "wpm": f"{self.get_words_per_minute():.0f} wpm",
        }

    def update_status(self) -> None:
        """
        Redraw the status line: how many captions there are, how far the
        last one runs to, and how fast the result reads.
        """

        elements = getattr(self, "status_elements", None)

        if not elements:
            return

        values = self.status_values()

        for name, element in elements.items():
            element.set_text(values.get(name, ""))

    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        A running time, as a viewer would read it off a player.
        """

        total = max(0, int(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"

        return f"{minutes}:{secs:02d}"

    def update_words_per_minute(self) -> None:
        """
        Update the words per minute display.

        The status line goes with it: the moments the words-per-minute
        figure changes -- an edit, a split, a merge, an undo -- are exactly
        the moments the caption count and the running time change too, and
        every one of them already calls this.
        """

        if self.words_per_minute_element:
            wpm = self.get_words_per_minute()
            # The value alone: the panel names it in a label of its own
            # beside this one, rather than repeating the name in the value.
            self.words_per_minute_element.set_text(f"{wpm:.2f}")

        self.update_status()

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

        Refreshes the status line with them: this runs after parsing and
        after every structural edit, so it is the one place that always
        knows the count has just changed. Without it the line reported the
        editor as empty for the whole session -- the page registers its
        figures while building the toolbar, which is before the captions
        have been parsed at all, and nothing else redrew them until the
        first edit.
        """

        for i, caption in enumerate(self.captions, 1):
            caption.index = i

        self.update_status()

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

    @staticmethod
    def split_point(text: str) -> int:
        """
        Where to halve a caption that has no caret to break at.

        The nearest gap between words to the middle, looking both ways. It
        used to only look backwards and fall back to the bare middle when it
        found nothing, which cut straight through the first word of a caption
        that had no space before its midpoint -- "internationalization
        matters" came out as "internationali" and "zation matters".

        A caption of one long word has no gap to find, and there the middle is
        all there is; every real caption has one.
        """

        middle = len(text) // 2
        gaps = [index for index, character in enumerate(text) if character.isspace()]

        if not gaps:
            return middle

        # Ties go to the earlier gap, so the same text always breaks the same
        # way rather than depending on which side was searched first.
        return min(gaps, key=lambda index: (abs(index - middle), index))

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
                text = caption.text
                mid_point = self.split_point(text)

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
        self, caption: SRTCaption, seek: Optional[bool] = True
    ) -> None:
        """
        Mark a caption as the current one -- what search and autoscroll use
        to say which caption the reader's attention should move to. Every
        caption's text is editable regardless, so this no longer opens or
        closes anything; it seeks the video and asks the editor in use (see
        on_select) to bring the caption into view.
        """

        old_selected = self.selected_caption

        if self.selected_caption:
            self.selected_caption.is_selected = False

        if self.selected_caption == caption:
            self.selected_caption = None
        else:
            caption.is_selected = True
            self.selected_caption = caption

            if self._video_player and seek:
                self._video_player.seek(caption.get_start_seconds())

        # Only update the captions that changed state
        indices_to_update = set()
        if old_selected:
            indices_to_update.add(old_selected.index)
        if caption:
            indices_to_update.add(caption.index)
        self.refresh_display(specific_indices=indices_to_update)

        if self.selected_caption and self.on_select:
            self.on_select(self.selected_caption)

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
        # Only actually joined with a newline when both sides have text --
        # an empty caption (freshly added, then merged straight back away
        # with Backspace) has nothing to separate from the other, and a
        # bare "\n" would show up as a spurious blank line the reader never
        # typed.
        caption.text = "\n".join(
            text for text in (caption.text, next_caption.text) if text
        )
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
        # See the equivalent join in merge_with_next for why this is not
        # always a bare "\n" join.
        previous_caption.text = "\n".join(
            text for text in (previous_caption.text, caption.text) if text
        )
        previous_caption.end_time = caption.end_time

        # Remove current caption
        self.captions.remove(caption)

        self.renumber_captions()
        self.update_words_per_minute()
        self.refresh_display(force_full_refresh=True)








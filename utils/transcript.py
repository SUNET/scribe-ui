import json
from nicegui import ui
from typing import Any
from typing import Dict
from typing import List


class TranscriptSegment:
    def __init__(self, speaker: str, text: str, start: float = 0.0, end: float = 0.0):
        self.speaker = speaker
        self.text = text
        self.start = start
        self.end = end
        self.duration = end - start
        self.is_selected = False
        self.is_highlighted = False
        self.action_col = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "duration": self.duration,
        }


class TranscriptEditor:
    def __init__(self, data: str):
        self.original_data = json.loads(data)
        self.segments: List[TranscriptSegment] = []
        self.speakers = set()
        self.container = None
        self.parse_segments()
        self.video_player = None
        self.autoscroll = False
        self.selected_segment: TranscriptSegment = None

    async def select_segment_from_video(self, autoscroll: bool) -> None:
        if not autoscroll:
            return

        self.autoscroll = autoscroll

        current_time = await ui.run_javascript(
            """(() => { return document.querySelector("video").currentTime })()"""
        )

        caption = self.get_segment_from_time(current_time)

        if caption:
            if self.selected_segment != caption:
                print(f"Selecting segment at time {current_time}")
                self.select_segment(caption, "")

    def select_segment(self, caption: TranscriptSegment, speaker: str) -> None:
        if self.selected_segment:
            self.selected_segment.is_selected = False

        if self.selected_segment == caption:
            self.selected_segment = None
        else:
            caption.is_selected = True
            self.selected_segment = caption

        if speaker:
            caption.speaker = speaker
            self.speakers.add(speaker)

        if self.video_player:
            self.video_player.seek(caption.start)

        self.refresh_ui()

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

    def get_segment_from_time(self, time: float) -> TranscriptSegment:
        for segment in self.segments:
            if segment.start <= time <= segment.end:
                return segment

        return None

    def set_video_player(self, player) -> None:
        self.video_player = player

    def parse_segments(self):
        print("Parsing segments")
        if not self.original_data.get("segments"):
            return

        raw_segments = self.original_data["segments"]

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

        for seg in concatenated:
            if seg.get("text", "").strip():
                self.segments.append(
                    TranscriptSegment(
                        speaker=seg["speaker"],
                        text=seg["text"],
                        start=seg.get("start", 0.0),
                        end=seg.get("end", 0.0),
                    )
                )
                self.speakers.add(seg["speaker"])

    def add_segment(self, speaker: str, text: str, position: int = None):
        if position is None:
            position = len(self.segments)

        new_segment = TranscriptSegment(speaker, text)

        self.segments.insert(position, new_segment)
        self.speakers.add(speaker)
        self.refresh_ui()

    def remove_segment(self, index: int):
        if 0 <= index < len(self.segments):
            self.segments.pop(index)
            self.refresh_ui()

    def update_segment(self, index: int, speaker: str = None, text: str = None):
        if speaker not in self.speakers and speaker is not None:
            self.speakers.add(speaker)

        if 0 <= index < len(self.segments):
            if speaker is not None:
                self.segments[index].speaker = speaker
                self.speakers.add(speaker)
            if text is not None:
                self.segments[index].text = text

    def move_segment(self, from_index: int, to_index: int):
        if 0 <= from_index < len(self.segments) and 0 <= to_index < len(self.segments):
            segment = self.segments.pop(from_index)

            self.segments.insert(to_index, segment)
            self.refresh_ui()

    def get_export_data(self) -> str:
        result = []

        for segment in self.segments:
            result.append(
                f"{segment.start} -> {segment.end}, {segment.speaker}: {segment.text}"
            )

        return "\n\n".join(result)

    def get_json_data(self) -> str:
        return {
            "segments": [seg.to_dict() for seg in self.segments],
            "speaker_count": len(self.speakers),
            "full_transcription": " ".join(seg.text for seg in self.segments),
        }

    def refresh_ui(self):
        if self.container:
            self.container.clear()
            with self.container:
                self._render_segments()

    def _create_segment_ui(self, segment: TranscriptSegment, index: int):
        card_class = "cursor-pointer border-0 transition-all duration-200 w-full"

        if segment.is_selected:
            card_class += " shadow-lg"
        elif segment.is_highlighted:
            card_class += " border-yellow-400 bg-yellow-50 hover:border-yellow-500"
        else:
            card_class += " hover:shadow-md shadow-none"

        with ui.card().classes(card_class) as card:
            if segment.is_selected:
                with ui.row().classes("w-full").classes("justify-between"):
                    speaker_select = ui.select(
                        options=list(self.speakers),
                        value=segment.speaker,
                        with_input=True,
                        label="Speaker",
                        new_value_mode="add",
                    )

                    ui.label(
                        f"{self.seconds_to_timestamp(segment.start)} - {self.seconds_to_timestamp(segment.end)}"
                    ).classes("text-sm text-gray-500")

                text_area = (
                    ui.textarea(value=segment.text)
                    .classes("w-full")
                    .props("outlined input-class=h-16")
                )

                text_area.on_value_change(
                    lambda e, idx=index: self.update_segment(idx, text=e.value)
                )

                text_area.on(
                    "click",
                    lambda e, idx=index: (
                        self.select_segment(segment, speaker_select.value),
                    ),
                )

                with ui.row().classes("w-full items-center justify-between mt-3"):
                    with ui.row().classes("gap-2"):
                        ui.button("Close").props("flat dense").on(
                            "click",
                            lambda: self.select_segment(segment, speaker_select.value),
                        ).classes("button-close")
                        ui.button("Add", color="green").props("flat dense").on(
                            "click", lambda: self._show_insert_dialog(index)
                        )
                        ui.button("Delete", color="red").props("flat dense").on(
                            "click", lambda: self._confirm_delete(index)
                        )
            else:
                if segment.is_highlighted and self.search_term:
                    highlighted_text = self.get_highlighted_text(segment.text)

                    with ui.row().classes("w-full").classes("justify-between"):
                        ui.label(f"{segment.speaker}:").classes(
                            "font-bold text-sm leading-relaxed"
                        )
                        ui.label(
                            f"{self.seconds_to_timestamp(segment.start)} - {self.seconds_to_timestamp(segment.end)}"
                        ).classes("text-sm text-gray-500")
                    ui.html(highlighted_text).classes(
                        "text-sm leading-relaxed whitespace-pre-wrap"
                    )
                else:
                    with ui.row().classes("w-full").classes("justify-between"):
                        ui.label(f"{segment.speaker}:").classes(
                            "font-bold text-sm leading-relaxed"
                        )
                        ui.label(
                            f"{self.seconds_to_timestamp(segment.start)} - {self.seconds_to_timestamp(segment.end)}"
                        ).classes("text-sm text-gray-500")
                    ui.label(segment.text).classes(
                        "text-sm leading-relaxed whitespace-pre-wrap"
                    )

            card.on(
                "click",
                lambda: self.select_segment(segment, "")
                if not segment.is_selected
                else None,
            )

        """
        segment_class = "cursor-pointer border-0 transition-all duration-200 w-full"

        if segment.is_selected:
            segment_class += "  shadow-none"
        elif segment.is_highlighted:
            segment_class += " border-yellow-400 bg-yellow-50 hover:border-yellow-500"
        else:
            segment_class += " hover:border-gray-300 hover:shadow-md shadow-none"

        with ui.column().classes("w-full mb-4 p-4"):
            with ui.row().classes("w-full") as segment_row:
                segment_row.classes(segment_class)

                with ui.column().classes("flex-grow"):
                    with ui.row().classes("items-center gap-2 w-32"):
                        speaker_select = ui.select(
                            options=list(self.speakers),
                            value=segment.speaker,
                            with_input=True,
                        ).style("font-family: verdana; font-size: 10px;")
                        speaker_select.on_value_change(
                            lambda e, idx=index: self.update_segment(
                                idx, speaker=e.value
                            )
                        )

                with ui.row().classes("items-center w-2/3") as text_row:
                    ui.label(f"{segment.start:.2f} - {segment.end:.2f}").classes(
                        "text-sm text-gray-500"
                    ).classes(segment_class)

                    text_editor = (
                        ui.editor(value=segment.text, placeholder="Enter text...")
                        .style("font-family: verdana; border: 0; width: 100%;")
                        .props("min-height=0")
                        .classes(segment_class)
                    )
                    text_editor.on_value_change(
                        lambda e, idx=index: self.update_segment(idx, text=e.value)
                    )

                    text_row.on(
                        "click",
                        lambda e, idx=index: (self.select_segment(segment),),
                    )
                with ui.row().classes("flex-shrink-0 gap-1") as action_col:
                    action_col.visible = segment.is_selected
                    segment.action_col = action_col

                    ui.button(
                        icon="keyboard_arrow_up",
                        on_click=lambda idx=index: self.move_segment(
                            idx, max(0, idx - 1)
                        ),
                    ).props("flat round").set_enabled(index > 0)
                    ui.button(
                        icon="keyboard_arrow_down",
                        on_click=lambda idx=index: self.move_segment(
                            idx, min(len(self.segments) - 1, idx + 1)
                        ),
                    ).props("flat round").set_enabled(index < len(self.segments) - 1)
                    ui.button(
                        icon="add_circle",
                        color="positive",
                        on_click=lambda idx=index: self._show_insert_dialog(idx),
                    ).props("flat round")
                    ui.button(
                        icon="delete",
                        color="negative",
                        on_click=lambda idx=index: self._confirm_delete(idx),
                    ).props("flat round")
        """

    def _add_new_speaker(self, speaker_name: str, speaker_select, segment_index: int):
        if speaker_name and speaker_name not in self.speakers:
            self.speakers.add(speaker_name)
            speaker_select.options = list(self.speakers)
            speaker_select.value = speaker_name
            self.update_segment(segment_index, speaker=speaker_name)

    def _confirm_delete(self, index: int):
        with ui.dialog().props("persistent") as dialog, ui.card():
            ui.label("Are you sure you want to delete this segment?")
            with ui.row():
                ui.button("Cancel", on_click=dialog.close)
                ui.button(
                    "Delete",
                    color="negative",
                    on_click=lambda: (self.remove_segment(index), dialog.close()),
                )

        dialog.open()

    def _show_insert_dialog(self, position: int):
        with ui.dialog().props("persistent") as dialog:
            with ui.card().classes("w-full max-w-2xl"):
                ui.label("Insert New Segment")

                speaker_input = ui.select(
                    options=list(self.speakers), label="Speaker"
                ).classes("w-full")

                text_input = ui.textarea("Text").classes("w-full")

                position_select = ui.select(
                    options=["Before this segment", "After this segment"],
                    value="After this segment",
                    label="Position",
                )

                with ui.row().classes("w-full justify-between"):
                    ui.button("Cancel", on_click=dialog.close)
                    ui.button(
                        "Insert",
                        color="positive",
                        on_click=lambda: self._do_insert(
                            dialog,
                            speaker_input.value,
                            text_input.value,
                            position,
                            position_select.value,
                        ),
                    )
            dialog.open()

    def _do_insert(
        self, dialog, speaker: str, text: str, base_position: int, position_type: str
    ):
        if not speaker or not text:
            ui.notify("Please provide both speaker and text", type="warning")
            return

        insert_pos = (
            base_position
            if position_type == "Before this segment"
            else base_position + 1
        )

        self.add_segment(speaker, text, insert_pos)

        dialog.close()

        ui.notify("Segment inserted successfully", type="positive")

    def _render_segments(self):
        if not self.segments:
            ui.label("No segments found").classes("text-center text-gray-500")
            return

        for i, segment in enumerate(self.segments):
            self._create_segment_ui(segment, i)

    def render(self):
        ui.add_css(
            """
            .q-textarea .q-field__control { 
                font-family: 'Courier New', monospace; 
                font-size: 14px; 
            }
        """
        )

        self.container = ui.column().classes("w-full")

        with self.container:
            self._render_segments()

    def _show_add_segment_dialog(self):
        with ui.dialog() as dialog, ui.card():
            ui.label("Add New Segment")

            speaker_input = ui.select(
                options=list(self.speakers), label="Speaker"
            ).classes("w-full")

            new_speaker_input = ui.input("New Speaker").classes("w-full")
            text_input = ui.textarea("Text").classes("w-full")

            with ui.row():
                ui.button("Cancel", on_click=dialog.close)
                ui.button(
                    "Add",
                    color="positive",
                    on_click=lambda: (
                        self.add_segment(
                            speaker_input.value or new_speaker_input.value,
                            text_input.value,
                        ),
                        dialog.close(),
                        ui.notify("Segment added successfully", type="positive"),
                    ),
                )
        dialog.open()

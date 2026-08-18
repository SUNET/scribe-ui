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
Editor for transcriptions, as opposed to subtitles.

A transcription is read in long stretches and edited in place; it is not a
series of timed cues the user is deliberately shaping. So this presents the
whole thing as one document -- one contenteditable, speakers and timestamps in
the margin -- rather than as a list of caption cards.

It edits the SRTEditor's own captions, so saving, exporting, the review
highlighting and the word data all keep working exactly as they do for
subtitles. The subtitle editor is untouched.
"""

import re

from typing import Callable, List, Optional

from nicegui import ui

from utils.caption import SRTCaption
from utils.srt_review import REVIEW_TOOLTIP


def format_time_label(seconds: float) -> str:
    """
    A timestamp as the transcription editor shows it: HH:MM:SS .mmm, with the
    milliseconds set apart so the eye can skip them when scanning.
    """

    total_milliseconds = max(0, int(round(seconds * 1000)))

    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d} .{milliseconds:03d}"


class TranscriptBody(
    ui.element,
    component="transcript_editor.js",
):
    """
    The contenteditable itself. Structural edits are reported to the server
    rather than performed by the browser; see the comment in the .js file.
    """

    def __init__(self) -> None:
        super().__init__()
        self._props["blocks"] = []
        self._props["activeId"] = -1
        self._props["reviewLabel"] = REVIEW_TOOLTIP
        self._props["highlightWord"] = False
        self._props["follow"] = False
        self._props["revision"] = 0
        self._props["speakers"] = []
        self._props["unused"] = []

    def set_speakers(self, speakers: List[str], unused: List[str]) -> None:
        self._props["speakers"] = speakers
        self._props["unused"] = unused
        self.update()

    def set_blocks(self, blocks: List[dict]) -> None:
        self._props["blocks"] = blocks
        # An update resends every prop, so the client cannot tell a real change
        # from the active-block updates that arrive while playing. This can.
        self._props["revision"] += 1
        self.update()

    def set_active(self, block_id: int) -> None:
        self._props["activeId"] = block_id
        self.update()

    def set_follow(self, follow: bool) -> None:
        self._props["follow"] = follow
        self.update()

    def set_highlight_word(self, highlight: bool) -> None:
        self._props["highlightWord"] = highlight
        self.update()

    def focus_block(self, block_id: int) -> None:
        self.run_method("focusBlock", block_id)


class TranscriptEditor:
    """
    Document view of a transcription, backed by the editor's captions.
    """

    def __init__(self, editor) -> None:
        self.editor = editor
        self.body: Optional[TranscriptBody] = None
        self.on_change: Optional[Callable] = None

    # ── building ────────────────────────────────────────────────────────────

    def build(self) -> None:
        """
        Create the editor and wire the events it reports.
        """

        self.body = TranscriptBody().classes("w-full")

        # Everything that mutates the captions calls refresh_display; send it
        # here so the caption cards are never drawn for a transcription.
        self.editor.render_override = self.refresh

        self.body.on("blocktext", lambda event: self.set_text(event.args))
        self.body.on("splitblock", lambda event: self.split(event.args))
        self.body.on("mergeblock", lambda event: self.merge(event.args))
        self.body.on("blockclick", lambda event: self.seek(event.args))
        self.body.on("assignspeaker", lambda event: self.assign_speaker(event.args))
        self.body.on("addspeaker", lambda event: self.prompt_new_speaker())
        self.body.on("renamespeaker", lambda event: self.prompt_rename(event.args))
        self.body.on("removespeaker", lambda event: self.drop_speaker(event.args))
        self.body.on("timeclick", lambda event: self.edit_time(event.args))

        self.refresh()

    def blocks(self) -> List[dict]:
        """
        The captions as the component wants them.

        The id is the caption's index, which renumber_captions keeps unique and
        in order, so the component can address a block without holding a
        reference to it.
        """

        return [
            {
                "id": caption.index,
                "speaker": caption.speaker,
                "start_label": format_time_label(caption.get_start_seconds()),
                "end_label": format_time_label(caption.get_end_seconds()),
                "runs": self.editor.review_runs(
                    caption, per_word=self.editor.highlight_word
                ),
            }
            for caption in self.editor.captions
        ]

    def refresh(self) -> None:
        """
        Send the current captions to the component.
        """

        if self.body is None:
            return

        self.body.set_blocks(self.blocks())
        self.body.set_speakers(
            sorted(self.editor.speakers),
            [name for name in sorted(self.editor.speakers)
             if not self.speaker_in_use(name)],
        )

    # ── lookup ──────────────────────────────────────────────────────────────

    def caption(self, block_id) -> Optional[SRTCaption]:
        """
        The caption a block id refers to, or None if it has gone.
        """

        if not isinstance(block_id, int):
            return None

        for caption in self.editor.captions:
            if caption.index == block_id:
                return caption

        return None

    @staticmethod
    def block_id(args) -> Optional[int]:
        """
        Pull a block id out of an event payload, which came from the browser
        and so is not trusted.
        """

        if not isinstance(args, dict):
            return None

        block_id = args.get("id")

        return int(block_id) if isinstance(block_id, (int, float)) else None

    # ── editing ─────────────────────────────────────────────────────────────

    def set_text(self, args) -> None:
        """
        Take an edited block's text. Does not re-render: the caret is in that
        block, and replacing its contents underneath the user would move it.
        """

        caption = self.caption(self.block_id(args))
        text = args.get("text") if isinstance(args, dict) else None

        if caption is None or not isinstance(text, str):
            return

        self.editor.update_caption_text(caption, text)
        self.changed()

    def split(self, args) -> None:
        """
        Break a block where the caret was.

        At the end of a block there is nothing to divide, so a new empty block
        is started instead -- the same thing Enter does at the end of a
        paragraph anywhere else. Only the transcription editor behaves this
        way; the subtitle editor's split is unchanged.
        """

        caption = self.caption(self.block_id(args))
        offset = args.get("offset") if isinstance(args, dict) else None

        if caption is None or not isinstance(offset, (int, float)):
            return

        position = max(0, min(int(offset), len(caption.text)))

        if not caption.text[position:].strip():
            added = self.insert_block_after(caption)
            self.focus(added.index)
            return

        self.editor.split_caption(caption, cursor_position=position)
        self.refresh()
        self.changed()

    def insert_block_after(self, caption: SRTCaption) -> SRTCaption:
        """
        Start a new empty block after this one, for the same speaker.

        It begins and ends where the block before it ended, so it claims no
        time of its own: an empty block has nothing to be timed against, and
        guessing a duration would either overlap the next block or invent audio
        that is not there. Widen it from the timestamp editor once it has words.
        """

        captions = self.editor.captions
        position = captions.index(caption)
        boundary = caption.get_end_seconds()

        self.editor.save_state_for_undo()

        added = SRTCaption(
            caption.index + 1,
            self.editor.seconds_to_timestamp(boundary),
            self.editor.seconds_to_timestamp(boundary),
            "",
            speaker=caption.speaker,
        )

        captions.insert(position + 1, added)
        self.editor.renumber_captions()
        self.editor.mark_as_changed()
        self.refresh()
        self.changed()

        return added

    def focus(self, block_id: int) -> None:
        """
        Put the caret in a block, so a new one can be typed into straight away.
        """

        if self.body is not None:
            self.body.focus_block(block_id)

    def merge(self, args) -> None:
        """
        Join a block with the one before or after it.
        """

        caption = self.caption(self.block_id(args))
        direction = args.get("direction") if isinstance(args, dict) else None

        if caption is None:
            return

        position = self.editor.captions.index(caption)

        if direction == "previous" and position > 0:
            self.editor.merge_with_previous(caption)
        elif direction == "next" and position < len(self.editor.captions) - 1:
            self.editor.merge_with_next(caption)
        else:
            return

        self.refresh()
        self.changed()

    def seek(self, args) -> None:
        """
        Move the recording to where the caret was put.
        """

        caption = self.caption(self.block_id(args))

        if caption is None:
            return

        offset = args.get("offset") if isinstance(args, dict) else None

        self.editor.seek_video(self.time_at_offset(caption, offset))

    def time_at_offset(self, caption: SRTCaption, offset) -> float:
        """
        When the word at a character offset into a block was spoken.

        Falls back to the start of the block: without word data, or on a word
        that has been edited since, there is no time to be had -- and the start
        of the block is never wrong, only imprecise.
        """

        start = caption.get_start_seconds()

        if not isinstance(offset, (int, float)):
            return start

        position = max(0, min(int(offset), len(caption.text)))
        spans = [match.span() for match in re.finditer(r"\S+", caption.text)]

        if not spans:
            return start

        # The word the caret is inside or sits at the end of, otherwise the
        # next one along. <= rather than < matters: clicking the right hand
        # edge of a word puts the caret at its end, and that should play that
        # word, not the one after it.
        index = next(
            (i for i, (_, end) in enumerate(spans) if position <= end),
            len(spans) - 1,
        )

        words = self.editor.aligned_words(caption)

        # Nearest word with a timing, looking back first: an edited word has
        # none, and the one before it is the closer guess.
        for candidate in list(range(index, -1, -1)) + list(range(index, len(words))):
            if candidate < len(words) and words[candidate]:
                return words[candidate]["s"]

        return start

    def changed(self) -> None:
        if self.on_change:
            self.on_change()

    # ── speaker ─────────────────────────────────────────────────────────────

    def assign_speaker(self, args) -> None:
        """
        Put this block with a different speaker.

        One block only. Changing who said this is a different act from
        correcting a speaker's name, which the menu keeps separate.
        """

        caption = self.caption(self.block_id(args))
        speaker = args.get("speaker") if isinstance(args, dict) else None

        if caption is None or not isinstance(speaker, str):
            return

        speaker = speaker.strip()

        if not speaker or speaker == caption.speaker:
            return

        self.editor.save_state_for_undo()
        caption.speaker = speaker
        self.editor.speakers.add(speaker)
        self.editor.mark_as_changed()
        self.refresh()
        self.changed()

    def prompt_new_speaker(self) -> None:
        """
        Ask for a name and add it to the list, ready to be assigned.
        """

        self.ask_for_name("Add speaker", "", self.add_speaker)

    def add_speaker(self, name: str) -> None:
        name = (name or "").strip()

        if not name:
            return

        if name in self.editor.speakers:
            ui.notify(f'"{name}" already exists', type="warning")
            return

        self.editor.speakers.add(name)
        self.editor.mark_as_changed()
        self.refresh()
        self.changed()

    def prompt_rename(self, args) -> None:
        """
        Rename a speaker wherever it appears.
        """

        speaker = args.get("speaker") if isinstance(args, dict) else None

        if not isinstance(speaker, str) or speaker not in self.editor.speakers:
            return

        self.ask_for_name(
            f'Rename "{speaker}"',
            speaker,
            lambda name: self.rename_speaker(speaker, name),
        )

    def rename_speaker(self, old: str, new: str) -> None:
        """
        Give a speaker a different name, everywhere it is used.

        This is the operation diarisation labels need: "Speaker 2" is one
        person throughout, so naming them names every block at once.
        """

        new = (new or "").strip()

        if not new or new == old:
            return

        if new in self.editor.speakers and new != old:
            ui.notify(f'"{new}" already exists', type="warning")
            return

        renamed = [
            caption for caption in self.editor.captions if caption.speaker == old
        ]

        self.editor.save_state_for_undo()

        for caption in renamed:
            caption.speaker = new

        self.editor.speakers.discard(old)
        self.editor.speakers.add(new)
        self.editor.mark_as_changed()
        self.refresh()
        self.changed()

        ui.notify(
            f'Renamed to "{new}"'
            + (f" in {len(renamed)} blocks" if len(renamed) > 1 else ""),
            type="positive",
            position="bottom",
        )

    def drop_speaker(self, args) -> None:
        """
        Take an unused speaker off the list.
        """

        speaker = args.get("speaker") if isinstance(args, dict) else None

        if not isinstance(speaker, str):
            return

        if not self.remove_speaker(speaker):
            ui.notify(
                f'"{speaker}" is still used by some blocks', type="warning"
            )
            return

        self.refresh()
        self.changed()
        ui.notify(f'Removed "{speaker}"', type="positive", position="bottom")

    def ask_for_name(self, title: str, value: str, then) -> None:
        """
        A one field prompt, shared by adding and renaming.
        """

        with ui.dialog() as dialog, ui.card().classes("transcript-dialog"):
            ui.label(title).classes("text-subtitle1 font-semibold")

            name = ui.input(label="Name", value=value).classes("w-full")
            name.props("autofocus")

            def confirm() -> None:
                then(name.value)
                dialog.close()

            name.on("keydown.enter", confirm)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Save", on_click=confirm)

        dialog.open()

    def speaker_in_use(self, name: str) -> bool:
        """
        Whether any block is currently attributed to this speaker.
        """

        return any(caption.speaker == name for caption in self.editor.captions)

    def remove_speaker(self, name: str) -> bool:
        """
        Drop an unused speaker from the list of names on offer.

        Refused while any block still carries it: removing it would leave those
        blocks attributed to a speaker the transcription no longer knows about.
        The count of speakers is part of what gets saved, so this is a real
        change rather than a display detail.
        """

        name = (name or "").strip()

        if not name or name not in self.editor.speakers:
            return False

        if self.speaker_in_use(name):
            return False

        self.editor.speakers.discard(name)
        self.editor.mark_as_changed()

        return True

    def edit_time(self, args) -> None:
        """
        Adjust a block's start and end, bounded by its neighbours so blocks
        cannot be dragged through one another.
        """

        caption = self.caption(self.block_id(args))

        if caption is None:
            return

        position = self.editor.captions.index(caption)
        captions = self.editor.captions

        floor = (
            captions[position - 1].get_end_seconds() if position > 0 else 0.0
        )
        ceiling = (
            captions[position + 1].get_start_seconds()
            if position < len(captions) - 1
            else caption.get_end_seconds() + 60.0
        )

        with ui.dialog() as dialog, ui.card().classes("transcript-dialog"):
            ui.label("Timing").classes("text-subtitle1 font-semibold")

            readout = ui.label().classes("transcript-time-readout")

            span = ui.range(
                min=round(floor, 3),
                max=round(ceiling, 3),
                step=0.01,
                value={
                    "min": caption.get_start_seconds(),
                    "max": caption.get_end_seconds(),
                },
            ).props("label-always snap")

            def show() -> None:
                readout.set_text(
                    f"{format_time_label(span.value['min'])}"
                    f"   -   {format_time_label(span.value['max'])}"
                )

            span.on("update:model-value", lambda: show())
            show()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Apply",
                    on_click=lambda: (
                        self.apply_time(
                            caption, span.value["min"], span.value["max"]
                        ),
                        dialog.close(),
                    ),
                )

        dialog.open()

    def apply_time(self, caption: SRTCaption, start: float, end: float) -> None:
        """
        Write adjusted times back to a block.
        """

        if end <= start:
            ui.notify("A block has to end after it starts", type="warning")
            return

        self.editor.save_state_for_undo()
        caption.start_time = self.editor.seconds_to_timestamp(start)
        caption.end_time = self.editor.seconds_to_timestamp(end)
        self.editor.mark_as_changed()
        self.refresh()
        self.changed()

    # ── following the video ─────────────────────────────────────────────────

    def set_follow(self, follow: bool) -> None:
        if self.body is not None:
            self.body.set_follow(follow)

    def set_highlight_word(self, highlight: bool) -> None:
        """
        Turn word-by-word following on or off.

        Re-renders, because following needs one element per word and the
        blocks are otherwise sent as merged runs.
        """

        self.editor.set_highlight_word(highlight)

        if self.body is not None:
            self.body.set_highlight_word(highlight)
            self.refresh()

    async def follow_video(self) -> None:
        """
        Mark the block being played, so the reader can see where they are.

        The time is read from the player rather than passed in, because
        timeupdate carries no position.
        """

        if self.body is None:
            return

        seconds = await ui.run_javascript(
            '(() => { const v = document.querySelector("video");'
            " return v ? v.currentTime : null; })()"
        )

        if not isinstance(seconds, (int, float)):
            return

        for caption in self.editor.captions:
            if caption.get_start_seconds() <= seconds < caption.get_end_seconds():
                self.body.set_active(caption.index)
                return

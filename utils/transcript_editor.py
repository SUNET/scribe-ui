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
The document editor: one contenteditable holding every caption, used for
both transcriptions and subtitles.

A transcription is read in long stretches and edited in place, with speakers
and timestamps in the margin. A subtitle is a short, timed cue meant to fit
on screen in a line or two -- no speakers, and a length guideline instead.
Both are still just a list of timed text blocks, so one editor draws both;
subtitleMode on the component swaps the margin for a character/line count and
turns on the per-caption delete action.

It edits the SRTEditor's own captions, so saving, exporting, the review
highlighting and the word data all keep working exactly as they do today,
whichever format is open.
"""

import re

from typing import Callable, List, Optional

from nicegui import ui

from utils.caption import SRTCaption
from utils.settings import get_settings
from utils.srt_review import EDIT_TOOLTIP, REVIEW_TOOLTIP


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


TIME_LABEL_PATTERN = re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})\s*\.(\d{3})\s*$")

# "Nothing has been drawn yet", which None cannot stand for -- None is a real
# value here, meaning no caption covers the moment being played. Without it the
# first tick that lands between two captions matches the starting value and
# short-circuits before the overlay is ever told to hide.
UNDRAWN = object()


def parse_time_label(text: str) -> Optional[float]:
    """
    The inverse of format_time_label, for editing a subtitle's timing
    directly where it is shown rather than through the slider dialog. None
    for anything that does not match, so a mistyped or partial value leaves
    the timing untouched rather than being guessed at.
    """

    match = TIME_LABEL_PATTERN.match(text or "")

    if not match:
        return None

    hours, minutes, seconds, millis = (int(group) for group in match.groups())

    return hours * 3600 + minutes * 60 + seconds + millis / 1000


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
        self._props["editLabel"] = EDIT_TOOLTIP
        self._props["showEdits"] = False
        self._props["highlightWord"] = False
        self._props["follow"] = False
        self._props["revision"] = 0
        self._props["speakers"] = []
        self._props["unused"] = []
        # Subtitle-only UI: no speaker margin, a length guideline instead, and
        # a delete action per caption. Off for a transcription.
        self._props["subtitleMode"] = False
        # So the client can recompute a caption's own character-count
        # guideline as it is typed into, without a round trip to the server
        # -- see onInput in the .js file for why that round trip is
        # deliberately not taken.
        settings = get_settings()
        self._props["characterLimit"] = settings.CHARACTER_LIMIT
        self._props["maxSubtitleLines"] = settings.MAX_SUBTITLE_LINES

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

    def set_show_edits(self, show: bool) -> None:
        """
        Tell the component whether edited words are being marked, so that a
        word typed into is marked the moment it changes rather than at the next
        render.
        """

        self._props["showEdits"] = show
        self.update()

    def focus_block(self, block_id: int, offset: int = 0) -> None:
        self.run_method("focusBlock", block_id, offset)

    def scroll_to_block(self, block_id: int) -> None:
        self.run_method("scrollToBlock", block_id)

    def set_subtitle_mode(self, subtitle_mode: bool) -> None:
        self._props["subtitleMode"] = subtitle_mode
        self.update()


class TranscriptEditor:
    """
    Document view of a transcription, backed by the editor's captions.
    """

    def __init__(self, editor) -> None:
        self.editor = editor
        self.body: Optional[TranscriptBody] = None
        self.on_change: Optional[Callable] = None
        self.overlay: Optional[ui.element] = None
        self.overlay_enabled = True
        # The caption the video is currently on, remembered so the overlay can
        # be redrawn without one -- turning it back on while paused has no
        # timeupdate coming to rebuild it from.
        self.overlay_text = UNDRAWN
        # Where the player last reported itself to be, so the overlay's own
        # caption can be worked out again after an edit -- see refresh_overlay.
        self.overlay_seconds: Optional[float] = None

    def set_overlay(self, container: ui.element) -> None:
        """
        Where follow_video draws the caption playing right now.

        A container rather than one label: a caption's own line breaks are
        part of it, and the overlay shows the same lines the editor does by
        giving each one its own element -- see draw_overlay.
        """

        self.overlay = container

    def set_overlay_enabled(self, enabled: bool) -> None:
        """
        Turn the overlay on or off, taking effect at once rather than at the
        next timeupdate -- the video may well be paused while this is toggled.
        """

        self.overlay_enabled = bool(enabled)
        self.draw_overlay()

    # ── building ────────────────────────────────────────────────────────────

    def build(self) -> None:
        """
        Create the editor and wire the events it reports.
        """

        self.body = TranscriptBody().classes("w-full")
        self.body.set_subtitle_mode(self.editor.data_format == "srt")
        # "My edits" can already be on when the page loads -- it is a saved
        # preference, restored onto the editor before build() runs (see
        # restore_review_state). TranscriptBody starts every client with it
        # off regardless, so without this the live, while-typing marking
        # (data-changed) stays invisible until some real render happens to
        # call set_show_my_edits and finally sync the two -- an edit right
        # after opening the page looked unmarked for no visible reason.
        self.body.set_show_edits(self.editor.show_my_edits)

        # Everything that mutates the captions calls refresh_display; send it
        # here so there is only ever one place captions get drawn.
        self.editor.render_override = self.refresh
        # And this is what refresh_display's caller, select_caption, uses to
        # say which caption search or autoscroll just moved to.
        self.editor.on_select = self.scroll_to

        self.body.on("blocktext", lambda event: self.set_text(event.args))
        self.body.on("splitblock", lambda event: self.split(event.args))
        self.body.on("mergeblock", lambda event: self.merge(event.args))
        self.body.on("addblock", lambda event: self.add_after(event.args))
        self.body.on("deleteblock", lambda event: self.delete(event.args))
        self.body.on("blockclick", lambda event: self.seek(event.args))
        self.body.on("assignspeaker", lambda event: self.assign_speaker(event.args))
        self.body.on("addspeaker", lambda event: self.prompt_new_speaker())
        self.body.on("renamespeaker", lambda event: self.prompt_rename(event.args))
        self.body.on("removespeaker", lambda event: self.drop_speaker(event.args))
        self.body.on("retime", lambda event: self.retime(event.args))

        self.refresh()

    def blocks(self) -> List[dict]:
        """
        The captions as the component wants them.

        The id is the caption's index, which renumber_captions keeps unique and
        in order, so the component can address a block without holding a
        reference to it.
        """

        subtitles = self.editor.data_format == "srt"

        blocks = []

        for caption in self.editor.captions:
            block = {
                "id": caption.index,
                "speaker": caption.speaker,
                "start_label": format_time_label(caption.get_start_seconds()),
                "end_label": format_time_label(caption.get_end_seconds()),
                "runs": self.editor.review_runs(
                    caption, per_word=self.editor.highlight_word
                ),
                "invalid": not caption.is_valid,
                "highlighted": caption.is_highlighted,
            }

            if subtitles:
                block["line_counts"] = self.editor.caption_line_counts(caption)

            blocks.append(block)

        return blocks

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
        # A split, merge, delete, retime or undo can change which caption
        # covers the moment being played, or what that caption now says.
        self.refresh_overlay()

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

        Refocuses the start of the new second block afterward, the same as
        splitting a paragraph anywhere else leaves the caret at the start of
        the part that just became its own -- not because the caret would
        otherwise end up somewhere broken (the first block keeps its own
        identity and DOM node here, unlike a merge's removal), just because
        that is where a reader who just pressed Enter mid-sentence expects
        to keep typing.
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

        before = len(self.editor.captions)
        list_position = self.editor.captions.index(caption)

        self.editor.split_caption(caption, cursor_position=position)
        self.refresh()
        self.changed()

        # split_caption refuses a split with nothing on one side of the
        # caret (see its own docstring) -- when that happens no second
        # block was ever created, and there is nothing to refocus.
        if len(self.editor.captions) > before:
            second = self.editor.captions[list_position + 1]
            self.focus(second.index)

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

    def focus(self, block_id: int, offset: int = 0) -> None:
        """
        Put the caret in a block, so it can be typed into straight away --
        at the start by default, for a freshly started block, or at a
        specific character offset, for merge() to land it at the seam.
        """

        if self.body is not None:
            self.body.focus_block(block_id, offset)

    def merge(self, args) -> None:
        """
        Join a block with the one before or after it.

        Refocuses the surviving block at the seam between the two texts
        afterward -- merging previous removes the block the caret was in
        (that block's own DOM node goes with it, and the browser does not
        leave the caret anywhere sensible once it has), and even merging
        next, which does not, is more useful landing exactly where the two
        met than wherever the caret already happened to be.
        """

        caption = self.caption(self.block_id(args))
        direction = args.get("direction") if isinstance(args, dict) else None

        if caption is None:
            return

        position = self.editor.captions.index(caption)

        if direction == "previous" and position > 0:
            survivor = self.editor.captions[position - 1]
            # A "\n" only actually lands between the two if caption itself
            # has text to put after it -- merge_with_previous does not add
            # a separator for nothing, see its own comment -- so the seam
            # is the survivor's own end when it is empty.
            offset = len(survivor.text) + (len("\n") if caption.text else 0)
            self.editor.merge_with_previous(caption)
        elif direction == "next" and position < len(self.editor.captions) - 1:
            survivor = caption
            offset = len(caption.text)
            self.editor.merge_with_next(caption)
        else:
            return

        self.refresh()
        self.changed()
        self.focus(survivor.index, offset)

    def delete(self, args) -> None:
        """
        Drop a caption outright, rather than merging its text into a
        neighbour. Subtitle-only: the click that reaches this only exists
        when the component is in subtitle mode, see transcript_editor.js.

        Refocuses a neighbour afterward, the same as add_after does for the
        caption it starts -- refresh() removes the deleted caption's own
        DOM node, and a caret that was inside it does not survive that: the
        browser collapses the now-invalid selection to the start of the
        contenteditable rather than anywhere near where it just was, which
        reads as the cursor jumping to the top of the page.
        """

        caption = self.caption(self.block_id(args))

        if caption is None:
            return

        position = self.editor.captions.index(caption)

        self.editor.remove_caption(caption)
        self.refresh()
        self.changed()

        remaining = self.editor.captions
        if remaining:
            neighbor = remaining[min(position, len(remaining) - 1)]
            self.focus(neighbor.index)

    def add_after(self, args) -> None:
        """
        Insert a new empty caption after this one and focus it. The "+" next
        to delete; subtitle-only, same reasoning as delete above.
        """

        caption = self.caption(self.block_id(args))

        if caption is None:
            return

        added = self.insert_block_after(caption)
        self.focus(added.index)

    def seek(self, args) -> None:
        """
        Move the recording to where the caret was put, when that can be said.
        """

        caption = self.caption(self.block_id(args))

        if caption is None:
            return

        offset = args.get("offset") if isinstance(args, dict) else None
        seconds = self.time_at_offset(caption, offset)

        if seconds is None:
            return

        self.editor.seek_video(seconds)

    def time_at_offset(self, caption: SRTCaption, offset) -> Optional[float]:
        """
        When the word at a character offset into a block was spoken.

        None for a word that has been edited: nothing in the recording
        corresponds to it, so the recording stays where it is. It used to move
        to the nearest word that did have a timing, which meant clicking a word
        you had changed jumped the recording to the word before it -- and with
        the audio being followed, lit that word up as though it were the one
        clicked.

        Without any word data at all there is nothing better than the start of
        the block, which is never wrong, only imprecise.
        """

        start = caption.get_start_seconds()

        if not self.editor.words:
            return start

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
        word = words[index] if index < len(words) else None

        # Nor has a word that was transcribed without a timing of its own.
        return word["s"] if self.editor.word_is_timed(word) else None

    def changed(self) -> None:
        # Typing is reported without a re-render (set_text leaves the block
        # the caret is in alone), so this is the only chance the overlay gets
        # to follow an edit to the caption it is showing.
        self.refresh_overlay()

        if self.on_change:
            self.on_change()

    def scroll_to(self, caption: SRTCaption) -> None:
        """
        Bring a caption into view -- what search and autoscroll ask for via
        editor.on_select once they have picked which caption that is.
        """

        if self.body is not None:
            self.body.scroll_to_block(caption.index)

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

        # A history entry of its own. The speaker list rides the undo snapshot
        # (see UndoRedoManager), so without one this change is not undoable
        # itself *and* the next unrelated undo silently takes it back.
        self.editor.save_state_for_undo()
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

        # Saved for the same reason add_speaker is -- see there.
        self.editor.save_state_for_undo()
        self.editor.speakers.discard(name)
        self.editor.mark_as_changed()

        return True

    def apply_time(self, caption: SRTCaption, start: float, end: float) -> bool:
        """
        Write adjusted times back to a block. Returns whether it did, since
        retime() below has an input to revert if it did not.
        """

        if end <= start:
            ui.notify("A block has to end after it starts", type="warning")
            return False

        self.editor.save_state_for_undo()
        caption.start_time = self.editor.seconds_to_timestamp(start)
        caption.end_time = self.editor.seconds_to_timestamp(end)
        self.editor.mark_as_changed()
        self.refresh()
        self.changed()

        return True

    def retime(self, args) -> None:
        """
        A start or end time typed directly where it is shown, in either
        mode -- no dialog.
        """

        caption = self.caption(self.block_id(args))

        if caption is None:
            return

        edge = args.get("edge") if isinstance(args, dict) else None
        text = args.get("value") if isinstance(args, dict) else None

        if edge not in ("start", "end"):
            return

        seconds = parse_time_label(text)

        if seconds is not None:
            start = seconds if edge == "start" else caption.get_start_seconds()
            end = seconds if edge == "end" else caption.get_end_seconds()

            if self.apply_time(caption, start, end):
                return

        # Nothing usable was typed, or applying it was refused: put the real
        # value back rather than leave the input showing text that was never
        # saved.
        self.refresh()

    # ── following the video ─────────────────────────────────────────────────

    def set_follow(self, follow: bool) -> None:
        if self.body is not None:
            self.body.set_follow(follow)

    def set_show_my_edits(self, show: bool) -> None:
        """
        Turn the marking of the reader's own words on or off.

        Re-renders: which words count as edited is worked out on the server,
        from the transcription the model produced.
        """

        self.editor.set_show_my_edits(show)

        if self.body is not None:
            self.body.set_show_edits(bool(show))

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
        Mark the block being played, so the reader can see where they are,
        and draw its text over the video itself -- a preview of what a
        viewer would see, independent of whether the editor is also
        following along (see set_active's own gate below): a reader with
        autoscroll off still typing elsewhere still wants to see what is
        playing.

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

        # Kept so the overlay can be worked out again without the player --
        # see refresh_overlay, which is what an edit goes through.
        self.overlay_seconds = seconds

        playing = self.caption_at(seconds)

        if playing is not None and self.editor.autoscroll:
            self.body.set_active(playing.index)

        # None between two captions, or past the last one -- nothing playing
        # right now is what a real subtitle track would also show.
        self._set_overlay_text(None if playing is None else playing.text)

    def caption_at(self, seconds: float) -> Optional[SRTCaption]:
        """
        The caption covering a moment, or None if none does.
        """

        for caption in self.editor.captions:
            if caption.get_start_seconds() <= seconds < caption.get_end_seconds():
                return caption

        return None

    def refresh_overlay(self) -> None:
        """
        Work the overlay's caption out again and redraw if it has moved on.

        Editing the caption being shown has to take the overlay with it: the
        reader is very often paused while editing, and timeupdate -- the only
        other thing that ever redraws it -- does not fire then.

        Re-derived from the time the player was last reported at rather than
        held as a reference to the caption itself, so a split, merge, delete
        or undo swapping the caption objects out from under it cannot leave
        this pointing at one that is no longer in the list.
        """

        if self.overlay_seconds is None:
            return

        playing = self.caption_at(self.overlay_seconds)
        self._set_overlay_text(None if playing is None else playing.text)

    def _set_overlay_text(self, text: Optional[str]) -> None:
        """
        Remember the caption the video is on, and redraw if it changed.

        timeupdate fires several times a second and mostly lands on the same
        caption, so the DOM is only rebuilt when the text actually moves on.
        """

        if text == self.overlay_text:
            return

        self.overlay_text = text
        self.draw_overlay()

    def draw_overlay(self) -> None:
        """
        Draw the remembered caption, one element per line.

        Split on the caption's own line breaks rather than left to CSS, so
        the overlay shows exactly the lines the editor does -- the same
        split caption_line_counts uses for the character guideline. Each
        line is a ui.label, so the text stays text: a caption is user
        content and never becomes markup.
        """

        if self.overlay is None:
            return

        text = self.overlay_text if self.overlay_enabled else None
        if text is UNDRAWN:
            text = None

        self.overlay.clear()

        if not text:
            self.overlay.set_visibility(False)
            return

        with self.overlay:
            for line in text.split("\n"):
                # A blank line still has to take up a line's height, or the
                # lines below it move up and stop matching the editor.
                ui.label(line or " ").classes("video-subtitle-line")

        self.overlay.set_visibility(True)

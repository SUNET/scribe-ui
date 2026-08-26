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

settings = get_settings()


def format_time_label(seconds: float) -> str:
    """
    A timestamp as the transcription editor shows it: HH:MM:SS.mmm.
    """

    total_milliseconds = max(0, int(round(seconds * 1000)))

    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


# What a reader may type into a timestamp. Deliberately more forgiving than
# what the editor draws: a comma for the decimal point (which is what SRT
# itself uses, and what a Swedish keyboard offers first), and one to three
# decimals rather than exactly three -- "00:00:23,4" means 23.4 seconds and
# refusing it, as this once did, reverted the whole edit with no explanation.
# The space the editor used to draw before the decimals is still tolerated.
TIME_LABEL_PATTERN = re.compile(
    r"^\s*(\d{1,2}):(\d{2}):(\d{2})\s*[.,](\d{1,3})\s*$"
)

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

    hours, minutes, seconds = (int(group) for group in match.groups()[:3])
    # Decimals, not a count of milliseconds: ".4" is four tenths of a second,
    # so a short fraction is padded out rather than read as 4 ms.
    millis = int(match.group(4).ljust(3, "0"))

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
        # The speech strip under the video, when there are word timings to
        # draw one from -- see set_timeline.
        self.timeline = None
        self.overlay_enabled = True
        # The caption the video is currently on, remembered so the overlay can
        # be redrawn without one -- turning it back on while paused has no
        # timeupdate coming to rebuild it from.
        self.overlay_text = UNDRAWN
        # Where the player last reported itself to be, so the overlay's own
        # caption can be worked out again after an edit -- see refresh_overlay.
        self.overlay_seconds: Optional[float] = None

    def set_timeline(self, timeline) -> None:
        """
        Register the speech strip under the video and fill it in.

        Its caption boundaries move with every structural edit, so refresh()
        redraws them the same way it redraws the overlay -- the speech runs
        themselves come from the word timings and never change.
        """

        self.timeline = timeline
        timeline.set_speech(
            self.editor.speech_runs(), self.editor.speech_duration()
        )
        timeline.on("retimespan", lambda event: self.retime_span(event.args))
        timeline.on("createcaption", lambda event: self.create_caption(event.args))
        timeline.on("selectcaption", lambda event: self.select_from_timeline(event.args))
        self.refresh_timeline()

    def refresh_timeline(self) -> None:
        if self.timeline is None:
            return

        self.timeline.set_captions(
            [
                {
                    "id": caption.index,
                    "start": caption.get_start_seconds(),
                    "end": caption.get_end_seconds(),
                }
                for caption in self.editor.captions
            ]
        )

    def select_from_timeline(self, args) -> None:
        """
        A caption clicked on the strip: the text editor moves to it and the
        recording follows.

        The strip is a second view of the same captions, not a separate
        thing to keep in step by hand -- so clicking one there does what
        clicking one in the text does, rather than only seeking.

        To the caption's own start. It once went to the middle, on the
        reasoning that the frame where a cue begins shows what is about to
        be said rather than what the cue covers -- but a reader clicking a
        caption is asking to play it, and landing halfway through means the
        first half of it is never heard without seeking back by hand. A
        click on the strip *itself* still means the moment it landed on, to
        the pixel; that one never reaches here.
        """

        caption = self.caption(self.block_id(args))

        if caption is None:
            return

        start = caption.get_start_seconds()

        self.editor.seek_video(start)
        self.moved_to(start)
        self.focus(caption.index)
        self.mark_current(caption.index)

    def mark_current(self, caption_index: int) -> None:
        """
        Tell the strip which caption the text editor is on.
        """

        if self.timeline is not None:
            self.timeline.set_current(caption_index)

    def retime_span(self, args) -> None:
        """
        A caption dragged on the strip under the video: both ends at once.

        One call rather than a retime per edge, so dragging a caption across
        is a single undo step -- apply_time takes the snapshot, and taking
        two would mean pressing undo twice to put back one gesture.
        """

        caption = self.caption(self.block_id(args))

        if caption is None or not isinstance(args, dict):
            return

        start = args.get("start")
        end = args.get("end")

        if start is None or end is None:
            return

        try:
            start = float(start)
            end = float(end)
        except (TypeError, ValueError):
            return

        if not self.apply_time(caption, start, end):
            # Refused (an end before its start): put the caption back where
            # it was, since the strip is already drawing it where it was
            # dropped.
            self.refresh()

    def create_caption(self, args) -> None:
        """
        An empty stretch of the strip dragged out: a new caption covering
        exactly it.

        The strip is where a reader can see that nothing covers a passage of
        speech, so it is where they should be able to say that something now
        does -- rather than adding a caption after some other one and
        dragging it across. It starts empty and takes the caret, the same as
        "Add caption after", since the next thing wanted is its text.

        The client keeps the drag inside the gap it was started in, so the
        overlap check below is a guard rather than the rule: captions can
        have moved since the strip was last drawn.
        """

        if not isinstance(args, dict):
            return

        try:
            start = float(args.get("start"))
            end = float(args.get("end"))
        except (TypeError, ValueError):
            return

        if end <= start:
            return

        overlaps = any(
            start < caption.get_end_seconds() and end > caption.get_start_seconds()
            for caption in self.editor.captions
        )

        if overlaps:
            # The strip is already drawing the caption it thought it was
            # making; nothing else would take it back off.
            self.refresh()
            ui.notify("A caption already covers part of that", type="warning")

            return

        self.editor.save_state_for_undo()

        added = SRTCaption(
            len(self.editor.captions) + 1,
            self.editor.seconds_to_timestamp(start),
            self.editor.seconds_to_timestamp(end),
            "",
        )

        self.editor.captions.append(added)
        # A caption's number is its position in the list, and this one was
        # appended rather than inserted -- sort_captions renumbers as it
        # goes, so `added.index` is only right after this.
        self.editor.sort_captions()
        self.editor.mark_as_changed()
        self.refresh()
        self.changed()

        # Everything a click on the strip does, because making a caption is
        # asking for it as much as clicking one is: the recording moves to
        # it, the caret goes into it, and the strip marks it as current.
        #
        # The seek is what keeps the frame under the subtitle overlay
        # honest. The overlay draws whatever caption covers the play
        # position, and a caption dragged out of the empty stretch around
        # the playhead -- which is fixed at the centre of the strip, so that
        # is where the empty stretch usually is -- covers it: the text
        # appeared over a frame from somewhere else entirely as it was
        # typed. Moving the recording to the caption makes what is shown and
        # what is under it the same moment.
        #
        # To the middle of it rather than its start: the start is the edge
        # the reader has just placed, and a frame from the very instant a
        # cue begins shows what is about to be said rather than what it
        # covers. The middle is the frame the caption is about.
        middle = (start + end) / 2

        self.editor.seek_video(middle)
        self.moved_to(middle)
        self.focus(added.index)
        self.mark_current(added.index)

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
        self.body.on("moveword", lambda event: self.move_word(event.args))
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
        # And where the captions divide the recording, which the strip under
        # the video draws.
        self.refresh_timeline()

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
        Break a block where the caret was, or halve it when there was no
        caret in it to break at -- see the offset check below.

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

        if caption is None:
            return

        before = len(self.editor.captions)
        list_position = self.editor.captions.index(caption)

        # The split icon clicked while the caret is somewhere else entirely:
        # there is no position the reader chose, so halve the caption rather
        # than inventing one. splitAt used to send the middle of the text as
        # if it were a caret, and a caret is honoured to the character --
        # which cut straight through whatever word the middle landed in.
        # split_caption's own halving keeps the break between words.
        if offset is None:
            self.editor.split_caption(caption)
            self.refresh()
            self.changed()

            if len(self.editor.captions) > before:
                self.focus(self.editor.captions[list_position + 1].index)

            return

        if not isinstance(offset, (int, float)):
            return

        position = max(0, min(int(offset), len(caption.text)))

        if not caption.text[position:].strip():
            added = self.insert_block_after(caption)
            self.focus(added.index)
            return

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

        It begins where the block before it ended and runs for
        NEW_CAPTION_SECONDS -- or up to the next block's start, whichever
        comes first, so a new caption never overlaps the one it was inserted
        before. Inserted into a run of back-to-back captions there is no room
        at all, and it keeps the zero length it used to always have; it can
        be widened by dragging it on the timeline or typing its timing.

        A zero-length caption everywhere was the safe answer before there was
        anywhere to see it: it is invisible on the timeline, has nothing to
        take hold of, and "Validate" objects to it. A second of room is a
        better starting point when there is a second to give.
        """

        captions = self.editor.captions
        position = captions.index(caption)
        boundary = caption.get_end_seconds()

        room = settings.NEW_CAPTION_SECONDS

        if position + 1 < len(captions):
            room = min(room, captions[position + 1].get_start_seconds() - boundary)

        self.editor.save_state_for_undo()

        added = SRTCaption(
            caption.index + 1,
            self.editor.seconds_to_timestamp(boundary),
            self.editor.seconds_to_timestamp(boundary + max(0.0, room)),
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

    def move_word(self, args) -> None:
        """
        Hand one word across the boundary to the caption either side.

        The editor's own methods refuse the cases that have nowhere to go --
        the first caption has no previous, the last has no next, and neither
        will empty a caption outright -- so this only has to say which way,
        and re-render whatever came back. Both captions are re-timed from the
        word data by those methods, not here.

        The caret is put back in the caption the reader is working in rather
        than following the word across: they are trimming this caption's
        edges, and a caret that jumped to the neighbour on every keystroke
        would make a second press mean something different from the first.
        """

        caption = self.caption(self.block_id(args))
        direction = args.get("direction") if isinstance(args, dict) else None

        if caption is None:
            return

        if direction == "previous":
            self.editor.move_first_word_to_previous(caption)
        elif direction == "next":
            self.editor.move_last_word_to_next(caption)
        else:
            return

        self.refresh()
        self.changed()
        self.focus(caption.index)

    def delete(self, args) -> None:
        """
        Drop a caption outright, rather than merging its text into a
        neighbour. Reached by Ctrl+D in either format, and by the trash icon
        on the caption row, which subtitles alone have.

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
        to delete on the caption row, and Ctrl/Cmd+Shift+Enter -- both
        subtitles only, since that row is what either one is the half of.
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

        self.mark_current(caption.index)

        offset = args.get("offset") if isinstance(args, dict) else None
        seconds = self.time_at_offset(caption, offset)

        if seconds is None:
            # The word under the caret cannot be placed in the recording --
            # the reader wrote it, or the model transcribed it without a
            # timing. Refusing to move is right only while the recording is
            # inside this caption already: that is the case the rule was
            # written for, a reader listening to a caption and clicking a
            # word in it, where jumping back to its first word is worse than
            # staying put.
            #
            # Coming from somewhere else, though, the click is asking for
            # the caption itself, and there is no position within it to
            # refine. Doing nothing there means clicking a caption is
            # silently ignored -- no seek, no overlay, no active block --
            # which is what a reader sees as the editor having missed the
            # click entirely.
            # Only when the recording is known to be elsewhere. Before the
            # player has reported itself even once there is nothing saying
            # it has left this caption, so the rule stands as written.
            playing = (
                caption
                if self.overlay_seconds is None
                else self.caption_at(self.overlay_seconds)
            )

            if playing is caption:
                return

            seconds = caption.get_start_seconds()

        self.editor.seek_video(seconds)
        self.moved_to(seconds)

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

        # Nothing in this caption can be placed in the recording at all. A
        # caption dragged out on the timeline is exactly that: it covers
        # whatever words are under it, but its text was typed by hand and so
        # aligns with none of them, leaving every entry None -- and a
        # caption in a silent stretch has no words under it to begin with.
        # Its own start is the answer, the same as for a job with no word
        # data; the rule below is about telling one edited word apart from
        # the timed ones around it, and needs there to be timed ones.
        #
        # Without this, clicking such a caption in the text moved the
        # recording nowhere, so the subtitle overlay went on showing
        # whatever the player was still parked in -- or nothing at all, when
        # that was a stretch no caption covers.
        if not any(self.editor.word_is_timed(word) for word in words):
            return start

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

        # Search and autoscroll both move the reader to a caption, which is
        # exactly what the strip means by "current".
        self.mark_current(caption.index)

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
        # A retime can move a caption past a neighbour, and a caption's
        # number is its position in the list -- so the list has to follow the
        # clock, or the text editor keeps showing it where it used to be
        # under a number that matches neither its own timing nor the strip.
        self.editor.sort_captions()
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

        self.moved_to(seconds)

    def moved_to(self, seconds: float) -> None:
        """
        The recording is at this moment now: mark the block being played and
        draw its text over the video.

        Called both by follow_video, when the player reports itself, and by
        whatever asked the player to move -- a click in the text, a caption
        on the strip, a caption just dragged out. Waiting for the report was
        not enough: setting currentTime to the value it already holds moves
        nothing and so fires no timeupdate at all, and the first caption of
        a recording usually starts at 0, exactly where a freshly opened
        player already sits. Clicking it drew no overlay and lit no block,
        while every other caption worked.
        """

        # Kept so the overlay can be worked out again without the player --
        # see refresh_overlay, which is what an edit goes through.
        self.overlay_seconds = seconds

        playing = self.caption_at(seconds)

        if playing is not None and self.editor.autoscroll and self.body is not None:
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

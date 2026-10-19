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
The reader's comments: notes attached to a stretch of words.

A comment never changes the text. It is kept as word positions plus its own
text (see caption.WordComment) and follows its words through every edit the
way a highlight does. The rules that differ from a highlight's:

- A comment belongs to one caption. A selection reaching across captions is
  refused, so a stretch of words and the note about it cannot be torn apart by
  a split or a merge that nobody asked about.
- A word has at most one comment. Asking to comment on words that already have
  one opens that comment for editing instead of laying a second over it.
- When the last of a comment's words is gone, so is the comment.
"""

import re
from typing import List, Optional, Tuple

from nicegui import ui

from utils.caption import SRTCaption, WordComment

# Long enough for a thought, short enough that a saved transcription is not
# bloated by a pasted page.
COMMENT_MAX_LENGTH = 1000


class CommentsMixin:
    """
    Adding, editing, removing and carrying the reader's comments.
    """

    @staticmethod
    def clean_comment(text) -> str:
        """
        A comment's text as it is kept: no blank edges, line breaks as typed.
        """

        return text.strip() if isinstance(text, str) else ""

    @staticmethod
    def restore_comments(saved, text: str = "") -> List[WordComment]:
        """
        Comments as a saved transcription holds them. Anything that is not a
        usable comment is skipped rather than failing the whole file: a note
        with no words or no text, positions that are not whole numbers, and a
        word already taken by an earlier comment (a word has only one).
        """

        if not isinstance(saved, list):
            return []

        restored: List[WordComment] = []
        taken: set = set()
        count = len(text.split()) if text else None

        for item in saved:
            if not isinstance(item, dict):
                continue

            note = item.get("text")
            positions = item.get("words")

            if not isinstance(note, str) or not note.strip():
                continue

            if not isinstance(positions, list):
                continue

            words = {
                position
                for position in positions
                if isinstance(position, int)
                and not isinstance(position, bool)
                and position >= 0
                and (count is None or position < count)
                and position not in taken
            }

            if not words:
                continue

            taken |= words
            restored.append(WordComment(words, note.strip()[:COMMENT_MAX_LENGTH]))

        restored.sort(key=lambda comment: min(comment.words))

        return restored

    def carry_comments(
        self, previous: str, current: str, comments: List[WordComment]
    ) -> List[WordComment]:
        """
        Carry a caption's comments across a change to its text.

        Each comment's words move by the same rules as a highlight's (see
        carry_highlights, where they are explained), so the two kinds of note
        cannot drift apart. A comment none of whose words are left is dropped
        with them.
        """

        carried = []

        for comment in comments:
            words = self.carry_highlights(previous, current, comment.words)

            if words:
                carried.append(WordComment(words, comment.text))

        return carried

    @staticmethod
    def split_comments(
        comments: List[WordComment], at: int
    ) -> Tuple[List[WordComment], List[WordComment]]:
        """
        Divide a caption's comments where its text is split, the second half
        counted from its own first word.

        A comment whose words lie on both sides is kept on both, with the same
        text: the note was about all of those words, and each half still holds
        some of them.
        """

        first, second = [], []

        for comment in comments:
            before = {index for index in comment.words if index < at}
            after = {index - at for index in comment.words if index >= at}

            if before:
                first.append(WordComment(before, comment.text))
            if after:
                second.append(WordComment(after, comment.text))

        return first, second

    @staticmethod
    def join_comments(
        first: List[WordComment], second: List[WordComment], offset: int
    ) -> List[WordComment]:
        """
        Combine two captions' comments when their text is joined, the second
        caption's moved along by however many words now precede it. Comments
        stay separate notes, even where one ends and the next begins.
        """

        return [comment.copy() for comment in first] + [
            WordComment({index + offset for index in comment.words}, comment.text)
            for comment in second
        ]

    @staticmethod
    def comment_index_at(caption: SRTCaption, word: int) -> Optional[int]:
        """
        Which of the caption's comments the word at this position is in.
        """

        for at, comment in enumerate(caption.comments):
            if word in comment.words:
                return at

        return None

    @staticmethod
    def word_range(text: str, first: int, last: int) -> Optional[Tuple[int, int]]:
        """
        The character offsets, in the caption's text, of the stretch from the
        word at position `first` to the one at `last`, both included. None when
        the text has no such words.
        """

        matches = list(re.finditer(r"\S+", text))

        if not matches or first < 0 or last >= len(matches) or first > last:
            return None

        return matches[first].start(), matches[last].end()

    def comment_target(
        self, caption: SRTCaption, start: int, end: int
    ) -> Optional[dict]:
        """
        What a request to comment on the words around a selection is about.

        If any word taken already has a comment, that comment: the request
        becomes a request to edit it, since a word has only one. Otherwise a
        new comment on the words taken. None when the selection takes no word.
        """

        touched = self.words_in_selection(caption.text, start, end)

        if not touched:
            return None

        existing = None

        for position in touched:
            existing = self.comment_index_at(caption, position)

            if existing is not None:
                break

        if existing is not None:
            words = caption.comments[existing].words
            text = caption.comments[existing].text
        else:
            words = set(range(min(touched), max(touched) + 1))
            text = ""

        span = self.word_range(caption.text, min(words), max(words))

        if span is None:
            return None

        return {
            "index": existing,
            "text": text,
            "start": span[0],
            "end": span[1],
        }

    def set_comment(
        self, caption: SRTCaption, start: int, end: int, text: str
    ) -> str:
        """
        Put a comment on the words a selection takes, or change the text of the
        one they already have.

        Returns "added", "changed", or "" when nothing was done: nothing to
        comment on, an empty or over-long text, or a text the comment already
        has. Refused for subtitles, which are saved as plain SRT and have
        nowhere to keep a comment.
        """

        if self.data_format == "srt":
            return ""

        text = self.clean_comment(text)

        if not text:
            return ""

        if len(text) > COMMENT_MAX_LENGTH:
            ui.notify(
                f"A comment can be at most {COMMENT_MAX_LENGTH} characters",
                type="warning",
                timeout=None,
                close_button="Close",
            )
            return ""

        target = self.comment_target(caption, start, end)

        if target is None:
            ui.notify(
                "Select the words to comment on first",
                type="warning",
                timeout=None,
                close_button="Close",
            )
            return ""

        if target["index"] is not None:
            if caption.comments[target["index"]].text == text:
                return ""

            self.save_state_for_undo()
            caption.comments[target["index"]].text = text
            self.mark_as_changed()
            return "changed"

        touched = self.words_in_selection(caption.text, start, end)

        self.save_state_for_undo()
        caption.comments.append(
            WordComment(range(min(touched), max(touched) + 1), text)
        )
        caption.comments.sort(key=lambda comment: min(comment.words))
        self.mark_as_changed()
        return "added"

    def remove_comment(self, caption: SRTCaption, start: int, end: int) -> bool:
        """
        Take away the comment on the words a selection takes. Says whether
        there was one.
        """

        if self.data_format == "srt":
            return False

        for position in self.words_in_selection(caption.text, start, end):
            at = self.comment_index_at(caption, position)

            if at is not None:
                self.save_state_for_undo()
                del caption.comments[at]
                self.mark_as_changed()
                return True

        return False

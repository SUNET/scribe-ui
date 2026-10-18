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

from typing import Any, Dict, List, Optional, Set


class WordComment:
    """
    A note the reader has attached to a stretch of words.

    Like a highlight it is for the reader and never changes the text: it is
    kept as word positions, counted in whitespace separated words from the
    start of its caption, and moves with those words through every edit.
    Unlike a highlight it carries a text of its own, so each comment is a
    separate object -- two neighbouring comments are two notes, not one.
    """

    def __init__(self, words, text: str) -> None:
        self.words: Set[int] = set(words)
        self.text: str = text

    def copy(self) -> "WordComment":
        return WordComment(self.words, self.text)

    def to_dict(self) -> Dict[str, Any]:
        return {"words": sorted(self.words), "text": self.text}


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
        # Whether any issue Validate found is an error rather than a warning;
        # decides the colour the caption is marked in. Only means anything
        # while is_valid is False.
        self.has_error = False
        self.speaker = speaker if speaker else "UNKNOWN"

        # Word positions the reader has changed, counted in whitespace
        # separated words from the start of this caption. Recorded as the edit
        # happens rather than worked out afterwards by comparing the text
        # against the words the model transcribed: that comparison cannot tell
        # a word the reader wrote from one the transcription has no entry for,
        # and marked untouched words as edited.
        self.edited_words: Set[int] = set()

        # Word positions the reader has highlighted for themselves, counted the
        # same way. A note to self made while reviewing against the recording:
        # it never changes the text, and it is kept apart from edited_words
        # because the two mean different things and move differently when the
        # text changes (see carry_highlights).
        self.highlighted_words: Set[int] = set()

        # The reader's comments on stretches of this caption's words. Never
        # overlapping: a word belongs to at most one comment.
        self.comments: List[WordComment] = []

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
        new_caption.has_error = self.has_error
        # Copied rather than shared: the undo stack holds these snapshots, so
        # undoing a change has to take its marks back with it.
        new_caption.edited_words = set(self.edited_words)
        new_caption.highlighted_words = set(self.highlighted_words)
        new_caption.comments = [comment.copy() for comment in self.comments]
        return new_caption

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start": self.get_start_seconds(),
            "end": self.get_end_seconds(),
            "duration": self.get_end_seconds() - self.get_start_seconds(),
            # Only when there are any, so a transcription nobody has touched
            # exports exactly as it did before this was recorded.
            **({"edited": sorted(self.edited_words)} if self.edited_words else {}),
            **(
                {"highlighted": sorted(self.highlighted_words)}
                if self.highlighted_words
                else {}
            ),
            **(
                {"comments": [comment.to_dict() for comment in self.comments]}
                if self.comments
                else {}
            ),
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

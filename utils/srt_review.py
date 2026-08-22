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
Word level review: which words the model was unsure of, and which of those
the reader has since confirmed.

Mixed into SRTEditor rather than kept as a separate object, so that call
sites stay `editor.get_review_html(...)`. Everything here reads the editor's
own captions and word list.
"""

import bisect
import json
import re

from difflib import SequenceMatcher
from html import escape as html_escape
from typing import List, Optional

from utils.caption import SRTCaption
from utils.settings import get_settings

settings = get_settings()

# Word timing payload version this editor understands. A wire format constant,
# deliberately not a setting: anything with a different version is treated as
# absent rather than guessed at.
WORDS_FORMAT_VERSION = 1

# How far up the confidence range each sensitivity flags. Words are marked
# identically whichever setting is in force -- the setting decides how many
# are marked, not how alarming any one of them looks. The raw score is never
# surfaced: it is not a calibrated probability, so a number would read as odds
# it cannot back up, and its absolute value shifts between models.
REVIEW_SENSITIVITIES = ("low", "medium", "high")
DEFAULT_REVIEW_SENSITIVITY = "low"

REVIEW_TOOLTIP = "This word may need review"
EDIT_TOOLTIP = "You changed this word"

# Where the review preferences live in app.storage.user, so a reload does not
# reset them. Plain values: they are display preferences, not secrets, so they
# do not go through storage_encrypt the way tokens and passwords do.
REVIEW_SHOW_KEY = "srt_show_uncertain_words"
REVIEW_SENSITIVITY_KEY = "srt_review_sensitivity"
EDITS_SHOW_KEY = "srt_show_my_edits"
AUTOSCROLL_KEY = "srt_autoscroll"
OVERLAY_SHOW_KEY = "srt_show_subtitle_overlay"



class ReviewMixin:
    """
    Word level confidence, review marking and the flagged-word counter.
    """

    def load_words(self, payload) -> None:
        """
        Load the per-word timing payload returned by the backend.

        Anything unrecognised is discarded silently: word data is an optional
        enhancement, and an editor that cannot read it must still open the
        transcription normally.
        """

        self.words = []
        self._word_midpoints = []
        self.has_confidence = False

        if not payload:
            return

        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                return

        if not isinstance(payload, dict):
            return

        if payload.get("version") != WORDS_FORMAT_VERSION:
            return

        words = payload.get("words")

        if not isinstance(words, list):
            return

        loaded = []

        for word in words:
            if not isinstance(word, dict):
                continue

            text = word.get("t")

            if not text:
                continue

            entry = {"t": str(text)}
            start = word.get("s")
            end = word.get("e")

            # A timing is optional. A word can be transcribed without one and
            # is still part of the transcript, still carrying its confidence
            # score; only seeking to it and following it are unavailable.
            # Discarding it left a hole that read as a word the reader had
            # written, and took its review flag out with it.
            if start is not None and end is not None:
                try:
                    entry["s"] = float(start)
                    entry["e"] = float(end)
                except (TypeError, ValueError):
                    pass

            confidence = word.get("c")

            if confidence is not None:
                try:
                    entry["c"] = float(confidence)
                    self.has_confidence = True
                except (TypeError, ValueError):
                    pass

            loaded.append(entry)

        # Ordered and located by midpoint -- the same value words_in_range
        # searches on, so the list it bisects is sorted by the key it is
        # searched with. A word with no timing takes the midpoint of the last
        # word that had one: it was spoken after that word, which is enough to
        # put it in the same caption rather than outside every range. The sort
        # is stable, so words sharing a midpoint keep the order they arrived in.
        midpoints = []
        carried = 0.0

        for word in loaded:
            if "s" in word:
                carried = (word["s"] + word["e"]) / 2

            midpoints.append(carried)

        order = sorted(range(len(loaded)), key=lambda position: midpoints[position])

        self.words = [loaded[position] for position in order]
        self._word_midpoints = [midpoints[position] for position in order]


    def words_in_range(self, start: float, end: float) -> List[dict]:
        """
        Words spoken inside a time range, matched on their midpoint so a word
        straddling a caption boundary belongs to exactly one caption.
        """

        if not self.words or end < start:
            return []

        first = bisect.bisect_left(self._word_midpoints, start)
        last = bisect.bisect_right(self._word_midpoints, end)

        return self.words[first:last]


    def caption_words(self, caption: SRTCaption) -> List[dict]:
        """
        Words belonging to a caption.

        Claimed from where the previous caption ended rather than from this
        one's own start, and to the end of the recording for the last one, so
        that the captions divide the whole of it and leave no gaps to fall into.

        A word's own timing cannot be relied on to sit inside the segment it was
        transcribed in: whisper dates a leading word from the silence before it,
        so a caption starting at 2.32 has been seen holding a word timed from
        0.00. Matching each caption only against its own range left that word
        claimed by nobody -- invisible to the review marking, and, back when
        edits were inferred rather than recorded, looking like a word the reader
        had written.
        """

        if not caption:
            return []

        captions = getattr(self, "captions", None) or []
        position = next(
            (
                index
                for index, candidate in enumerate(captions)
                if candidate is caption
            ),
            None,
        )

        if position is None:
            # Not one of ours -- an uncommitted copy, say. Nothing to bound it
            # against, so it answers for its own range as it always did.
            return self.words_in_range(
                caption.get_start_seconds(), caption.get_end_seconds()
            )

        floor = (
            captions[position - 1].get_end_seconds() if position > 0 else 0.0
        )
        ceiling = (
            caption.get_end_seconds()
            if position < len(captions) - 1
            else float("inf")
        )

        return self.words_in_range(floor, ceiling)


    def review_threshold(self) -> float:
        """
        Confidence below which a word is flagged, for the current sensitivity.
        """

        return {
            "low": settings.REVIEW_SENSITIVITY_LOW,
            "medium": settings.REVIEW_SENSITIVITY_MEDIUM,
            "high": settings.REVIEW_SENSITIVITY_HIGH,
        }.get(self.review_sensitivity, settings.REVIEW_SENSITIVITY_LOW)


    def is_flagged(self, score: Optional[float]) -> bool:
        """
        Whether a word scoring this low is worth a second look.
        """

        return score is not None and score < self.review_threshold()


    @staticmethod
    def word_is_timed(word: Optional[dict]) -> bool:
        """
        Whether a word can be placed in the recording.

        A word can be transcribed without a timing. It still belongs to the
        transcript and can still be uncertain; what it cannot do is be sought
        to, or be followed as the audio plays.
        """

        return bool(word) and "s" in word and "e" in word


    def word_needs_review(self, word: Optional[dict]) -> bool:
        """
        Whether a word should carry a flag.
        """

        if not word or "c" not in word:
            return False

        return self.is_flagged(word["c"])


    @staticmethod
    def token_is_edit(caption: SRTCaption, index: int) -> bool:
        """
        Whether the word at this position is one the reader changed.

        Read from what the caption recorded as it was edited. This used to be
        inferred instead, from a word failing to align against the words the
        model transcribed -- but a word fails to align for several reasons, only
        one of which is the reader having written it, so untouched words came
        out marked.
        """

        return index in caption.edited_words


    @staticmethod
    def retag_edits(previous: str, current: str, edited: set) -> set:
        """
        Carry a caption's marks across a change to its text.

        Marks are word positions, so they move when words are added or removed
        ahead of them, and words the change itself brought in take marks of
        their own -- that is precisely what the reader just did.

        Compared word for word without normalising, unlike the alignment used
        for confidence: changing only a word's capitalisation is still the
        reader changing it.
        """

        before = previous.split()
        after = current.split()
        carried = set()

        matcher = SequenceMatcher(None, before, after, autojunk=False)

        for tag, before_start, before_end, after_start, after_end in (
            matcher.get_opcodes()
        ):
            if tag == "equal":
                # The same words, possibly at new positions: their marks move
                # with them.
                for offset in range(before_end - before_start):
                    if before_start + offset in edited:
                        carried.add(after_start + offset)
            elif tag in ("replace", "insert"):
                carried.update(range(after_start, after_end))

            # "delete" contributes nothing: those words are gone, and so is
            # anything that was marked about them.

        return carried


    @staticmethod
    def split_edits(edited: set, at: int) -> tuple:
        """
        Divide a caption's marks where its text is split, the second half
        counted from its own first word.
        """

        return (
            {index for index in edited if index < at},
            {index - at for index in edited if index >= at},
        )


    @staticmethod
    def joined_edits(first: set, second: set, offset: int) -> set:
        """
        Combine two captions' marks when their text is joined, the second half
        moved along by however many words now precede it.
        """

        return set(first) | {index + offset for index in second}


    def flagged_word_count(self) -> int:
        """
        How many words are flagged across the whole transcription.

        Counts what is actually marked in the captions rather than scanning
        the raw word list, so the number tracks edits: fixing a flagged word
        takes it off the count.
        """

        return sum(
            1
            for caption in self.captions
            for word in self.aligned_words(caption)
            if self.word_needs_review(word)
        )


    def restore_review_state(
        self, show, sensitivity, edits=False, overlay=True
    ) -> None:
        """
        Apply persisted review preferences before the first render.

        Assigns rather than going through the setters, which refresh a caption
        list that does not exist yet. A sensitivity that is not recognised is
        ignored, so a value left behind by an older version of the editor
        falls back to the default instead of flagging nothing.

        overlay defaults to True, unlike the markings: nothing stored yet
        means a reader who has never touched the switch gets it on.
        """

        self.show_uncertain_words = bool(show)
        self.show_my_edits = bool(edits)
        self.show_subtitle_overlay = bool(overlay)

        if sensitivity in REVIEW_SENSITIVITIES:
            self.review_sensitivity = sensitivity


    def set_show_uncertain_words(self, show: bool) -> None:
        """
        Toggle the review marking on the caption list.
        """

        self.show_uncertain_words = bool(show)
        self.refresh_display(force_full_refresh=True)
        self.update_flagged_count()


    def set_show_my_edits(self, show: bool) -> None:
        """
        Toggle the marking of words the reader has changed.

        No effect on the flagged count: an edited word carries no confidence
        score, so it was never part of that number.
        """

        self.show_my_edits = bool(show)
        self.refresh_display(force_full_refresh=True)


    def set_review_sensitivity(self, sensitivity: str) -> None:
        """
        Choose how far up the confidence range to flag words.
        """

        if sensitivity not in REVIEW_SENSITIVITIES:
            return

        self.review_sensitivity = sensitivity

        if self.show_uncertain_words:
            self.refresh_display(force_full_refresh=True)

        self.update_flagged_count()


    def set_flagged_count_element(self, element) -> None:
        """
        Register the label that reports how many words are flagged.
        """

        self.flagged_count_element = element
        self.update_flagged_count()


    def update_flagged_count(self) -> None:
        """
        Refresh the flagged-word counter.

        Hidden outright while the marking is off rather than reporting zero:
        nothing is flagged by definition then, so the number says nothing
        and only adds another thing to read in the controls.
        """

        if self.flagged_count_element is None:
            return

        self.flagged_count_element.set_visibility(self.show_uncertain_words)

        if not self.show_uncertain_words:
            return

        self.flagged_count_element.set_text(f"{self.flagged_word_count()} flagged")


    @staticmethod
    def match_key(text: str) -> str:
        """
        Normalised form used to decide whether a token is still the word the
        model transcribed. Case and surrounding punctuation are ignored, so
        recasing a word or adding a comma does not discard its score.
        """

        return re.sub(r"^\W+|\W+$", "", text).casefold()


    def aligned_words(
        self, caption: SRTCaption, text: Optional[str] = None
    ) -> List[Optional[dict]]:
        """
        The transcribed word behind each word of a caption, in order.

        The caption text is aligned against the words the model actually
        transcribed, rather than paired off by position. Position alone breaks
        as soon as the text is edited: replacing a word would keep the entry
        that belonged to the old one, and inserting a word would shift every
        entry after it onto the wrong word.

        A token that no longer matches the word it came from returns None --
        it has no timing or confidence we can honestly attribute to it.

        Pass text to align something other than what the caption currently
        holds, such as the uncommitted value of an open text area.
        """

        source = caption.text if text is None else text
        tokens = [token for token in re.split(r"\s+", source) if token]
        aligned: List[Optional[dict]] = [None] * len(tokens)
        words = self.caption_words(caption)

        if not words or not tokens:
            return aligned

        # autojunk would treat repeated words as noise in long captions and
        # silently drop them from the alignment.
        matcher = SequenceMatcher(
            None,
            [self.match_key(token) for token in tokens],
            [self.match_key(word["t"]) for word in words],
            autojunk=False,
        )

        for tag, token_start, token_end, word_start, _ in matcher.get_opcodes():
            if tag != "equal":
                continue

            for offset in range(token_end - token_start):
                aligned[token_start + offset] = words[word_start + offset]

        return aligned


    def get_review_html(
        self, caption: SRTCaption, text: Optional[str] = None
    ) -> Optional[str]:
        """
        Caption text with the words worth reviewing, and the ones the reader
        has changed, marked up.

        Returns None when neither applies to anything in this caption.

        Both toggles are honoured here rather than at the call site, so that
        turning one on cannot bring the other's marking with it.
        """

        source = caption.text if text is None else text
        words = self.aligned_words(caption, source)

        if not words:
            return None

        # Keep the separators so line breaks and spacing survive the round trip.
        tokens = re.split(r"(\s+)", source)
        marked = False
        parts = []
        index = 0

        for token in tokens:
            if not token.strip():
                parts.append(html_escape(token).replace("\n", "<br>"))
                continue

            word = words[index] if index < len(words) else None
            index += 1

            flagged = self.show_uncertain_words and self.word_needs_review(word)
            edited = self.show_my_edits and self.token_is_edit(caption, index - 1)

            if not flagged and not edited:
                parts.append(html_escape(token))
                continue

            marked = True

            # One marking and one message per word: the score behind a flag is
            # not precise enough to grade flags against each other. The message
            # rides on a data attribute rather than title= so the tooltip is a
            # CSS box we can style; aria-label keeps it reachable for screen
            # readers.
            #
            # Flagged wins if a word is somehow both. They are no longer
            # exclusive by construction: one comes from the score the model gave
            # the word here, the other from the reader having changed it, and a
            # word worth a second look is the more useful thing to say.
            css, message = (
                ("review-word", REVIEW_TOOLTIP)
                if flagged
                else ("edit-word", EDIT_TOOLTIP)
            )
            attribute = "data-review" if flagged else "data-edit"

            parts.append(
                f'<span class="{css}" '
                f'{attribute}="{message}" '
                f'aria-label="{message}">{html_escape(token)}</span>'
            )

        return "".join(parts) if marked else None


    def review_runs(
        self,
        caption: SRTCaption,
        text: Optional[str] = None,
        per_word: bool = False,
    ) -> list:
        """
        A block's text split into runs, marking the words worth reviewing.

        Structured rather than marked up, so a client can render the marking
        itself. Nothing has to escape or unescape anything, and no HTML string
        built here can end up interpreted somewhere it should not be.

        Runs of unmarked text are merged by default, so a block with two
        flagged words is five runs rather than one per word.

        Every word becomes a run of its own in two cases. With per_word each
        one also carries its start and end, which is what lets a client follow
        the audio word by word. While the reader's own words are being marked,
        the split alone is needed: a word cannot be marked as changed part way
        through being typed unless it is already a run by itself.

        Either way it costs one element per word, so neither is done unless
        something needs it.
        """

        source = caption.text if text is None else text

        if not source:
            return []

        if (
            not self.show_uncertain_words
            and not self.show_my_edits
            and not per_word
        ):
            return [{"t": source, "flag": False}]

        # A word has to be a run of its own before it can be marked at all, so
        # marking the reader's words needs the same split that following the
        # audio does.
        one_run_per_word = per_word or self.show_my_edits

        words = self.aligned_words(caption, source)
        runs: list = []
        plain: list = []
        index = 0

        def flush() -> None:
            if plain:
                runs.append({"t": "".join(plain), "flag": False})
                plain.clear()

        for token in re.split(r"(\s+)", source):
            if not token:
                continue

            if not token.strip():
                plain.append(token)
                continue

            word = words[index] if index < len(words) else None
            index += 1
            # per_word bypasses the early return above, so the toggles have to
            # be honoured here too or words stay marked with them switched off.
            flagged = self.show_uncertain_words and self.word_needs_review(word)
            edited = self.show_my_edits and self.token_is_edit(caption, index - 1)

            if not one_run_per_word and not flagged and not edited:
                plain.append(token)
                continue

            flush()
            run = {"t": token, "flag": flagged}

            # Only carried when true, so a run reads the same as it always did
            # wherever nothing has been edited.
            if edited:
                run["edit"] = True

            # Only a word still matching what the model transcribed has a
            # timing we can attribute to it; an edited word has none, and nor
            # has a word transcribed without one. Neither is ever highlighted.
            if per_word and self.word_is_timed(word):
                run["s"] = word["s"]
                run["e"] = word["e"]

            runs.append(run)

        flush()

        return runs

    def review_backdrop_html(self, caption: SRTCaption, text: str) -> str:
        """
        Markup for the highlight layer behind an open text area.

        Always returns markup, even with nothing flagged: the layer has to
        mirror the text area character for character or the highlight boxes
        drift off their words.
        """

        markup = None

        if self.show_uncertain_words or self.show_my_edits:
            markup = self.get_review_html(caption, text)

        if markup is None:
            markup = html_escape(text).replace("\n", "<br>")

        # A trailing newline opens no line box, so without this the layer comes
        # up one line short of the text area.
        return f"{markup}<br>" if text.endswith("\n") else markup


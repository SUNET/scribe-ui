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
The review assistant: possible corrections, one at a time, never applied on
its own.

See SUNET/scribe-ui#74, which is where the shape of this comes from. The
one rule underneath all of it is that this is a *review* tool and not an
editor: it proposes, the reader disposes, and nothing reaches the captions
that the reader has not pressed Accept on. A transcript that has been
silently rewritten by a model is worth less than one that has not been
touched, because nobody can any longer say which parts of it are what was
said.

Three things follow from that and should stay:

  * The domain is confirmed by the reader before a single suggestion is
    asked for. A model reviewing a law seminar as though it were cardiology
    suggests confident nonsense, and the reader knows the material better
    than the classifier does.

  * A suggestion carries the exact text it would replace, and is dropped if
    that text is no longer there. Accepting one changes the transcript, and
    the ones queued behind it were written against the transcript as it was.

  * Accepting is one undo step and saves nothing. The reader leaves the
    review with unsaved changes, and is told so.

The assistant's own sentences are in the language of the recording (the
hub is told which); every label, button and heading here stays in English,
like the rest of the product.
"""

import json
import re

from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Callable, Optional

from nicegui import ui

from utils.inference import add_usage, answer_language, transcript_text, usage_line

# The hub's two review tasks. Not offered in the Analyse strip -- they are
# asked for here, in this order.
DOMAIN_TASK = "review_domain"
SUGGEST_TASK = "review_suggestions"

# What a suggestion is about, in the reader's own language -- which is
# English, unlike the sentence the model writes underneath it.
KIND_LABELS = {
    "terminology": "Terminology",
    "name": "Name",
    "consistency": "Consistency",
    "wording": "Word choice",
}

# More than this from one review is not a review any more. The prompt asks
# for restraint; this is what happens when it is not shown any.
MAX_SUGGESTIONS = 40

# How much of the caption to show either side of the words a suggestion
# would change. Enough to judge it by; not so much that the card scrolls.
CONTEXT_CHARS = 90

# What the reader is told, in English.
ANALYSING = "Reading the transcription..."
DOMAIN_LEAD = "This looks like a recording in:"
DOMAIN_UNKNOWN = "The domain could not be worked out from the transcription. Pick one."
DOMAIN_NOTE = (
    "The domain decides which terms the assistant treats as normal and which "
    "it questions. Change it if this is wrong -- you know the material."
)
REVIEWING = "Looking for possible corrections..."
NOTHING_FOUND = "No corrections to suggest. The transcription looks sound."
NOT_SAVED = "Nothing has been saved. Press Save in the toolbar to keep what you accepted."
STALE_NOTE = "This text is no longer in the transcription -- it was probably changed by an earlier suggestion."


@dataclass
class Suggestion:
    """
    One possible correction, as the model proposed it.

    Parameters:
        find (str): The text to replace, copied from the transcription.
        replace (str): What it would say instead. The reader can change
            this on the card before accepting, so it is what is applied,
            not necessarily what the model proposed.
        suggested (str): What the model proposed, kept as it was written so
            an edited suggestion can be told from an untouched one. Filled
            in from replace when the suggestion is made.
        why (str): One sentence saying why, in the language of the
            recording.
        kind (str): terminology, name, consistency or wording.
        state (str): pending, accepted, dismissed, skipped or stale.
    """

    find: str
    replace: str
    suggested: str = ""
    why: str = ""
    kind: str = "wording"
    state: str = "pending"

    def __post_init__(self) -> None:
        """
        Note the model's own wording, before the reader can change it.

        Returns:
            None
        """

        if not self.suggested:
            self.suggested = self.replace

    @property
    def edited(self) -> bool:
        """
        Whether the reader reworded the replacement themselves.

        Returns:
            bool: True when what would be applied is no longer what the
                model proposed.
        """

        return self.replace.strip() != self.suggested.strip()

    @property
    def applicable(self) -> bool:
        """
        Whether accepting this would change anything.

        A reader who empties the box, or types the transcribed text back
        into it, has asked for no change -- which is Dismiss, not Accept.

        Returns:
            bool: True when there is a replacement, and it differs from
                the text being replaced.
        """

        replacement = self.replace.strip()

        return bool(replacement) and replacement != self.find

    @property
    def kind_label(self) -> str:
        """
        What kind of suggestion this is, in English.

        Returns:
            str: A label for the chip on the card.
        """

        return KIND_LABELS.get(self.kind, "Suggestion")


@dataclass
class Outcome:
    """
    What a review came to, for the line at the end of it.
    """

    accepted: int = 0
    edited: int = 0
    dismissed: int = 0
    skipped: int = 0
    stale: int = 0
    changed: int = 0
    applied: list = field(default_factory=list)


def parse_suggestions(text: str) -> list[Suggestion]:
    """
    The suggestions in a model's answer.

    JSON Lines, because the answer arrives a few words at a time and a
    finished line can be read while the rest is still coming -- and because
    one malformed line costs one suggestion rather than all of them. A
    model that wraps them in a code fence anyway, or numbers them, or writes
    a sentence first, loses only the lines that are not objects.

    Parameters:
        text (str): The answer as it stands.

    Returns:
        list[Suggestion]: Everything readable in it, in order.
    """

    found: list[Suggestion] = []

    for line in (text or "").splitlines():
        line = line.strip().lstrip("-*0123456789. ").strip()

        if not line.startswith("{") or not line.endswith("}"):
            continue

        try:
            entry = json.loads(line)
        except ValueError:
            continue

        if not isinstance(entry, dict):
            continue

        find = str(entry.get("find") or "").strip()
        replace = str(entry.get("replace") or "").strip()

        # A suggestion that changes nothing, or has nothing to change, is
        # not a suggestion. Neither is one that only differs in the spaces
        # around it.
        if not find or not replace or find == replace:
            continue

        found.append(
            Suggestion(
                find=find,
                replace=replace,
                why=str(entry.get("why") or "").strip(),
                kind=str(entry.get("kind") or "wording").strip().lower(),
            )
        )

        if len(found) >= MAX_SUGGESTIONS:
            break

    return found


def match_pattern(find: str) -> re.Pattern:
    """
    How a suggestion's text is looked for in the captions.

    Word boundaries where the text itself begins or ends with a word
    character, so replacing "dos" does not reach into "dosering"; none where
    it does not, since \\b next to a comma or a bracket means the opposite
    of what it does next to a letter.

    Parameters:
        find (str): The text to look for.

    Returns:
        re.Pattern: The compiled pattern.
    """

    pattern = re.escape(find)

    if find[:1].isalnum() or find[:1] == "_":
        pattern = r"\b" + pattern

    if find[-1:].isalnum() or find[-1:] == "_":
        pattern = pattern + r"\b"

    return re.compile(pattern)


def matching_captions(captions: list, find: str) -> list:
    """
    The captions a suggestion applies to.

    Parameters:
        captions (list[SRTCaption]): The transcription as it stands.
        find (str): The text the suggestion replaces.

    Returns:
        list[SRTCaption]: Every caption containing it, in order.
    """

    if not find:
        return []

    pattern = match_pattern(find)

    return [caption for caption in captions if pattern.search(caption.text)]


def occurrences(captions: list, find: str) -> int:
    """
    How many times a suggestion's text appears in the transcription.

    Parameters:
        captions (list[SRTCaption]): The transcription as it stands.
        find (str): The text the suggestion replaces.

    Returns:
        int: The number of matches across every caption.
    """

    if not find:
        return 0

    pattern = match_pattern(find)

    return sum(len(pattern.findall(caption.text)) for caption in captions)


def excerpt(
    text: str, start: int, end: int, width: int = CONTEXT_CHARS
) -> tuple[str, str, str]:
    """
    A match with enough of its sentence around it to be judged.

    Parameters:
        text (str): The caption's text.
        start (int): Where the match begins.
        end (int): Where it ends.
        width (int): How many characters to keep either side.

    Returns:
        tuple[str, str, str]: What comes before, the match itself, and what
            comes after -- the outer two cut back to `width` with an
            ellipsis, and every line break flattened to a space, since this
            is one line of a card and not the caption being edited.
    """

    def flat(part: str) -> str:
        return part.replace("\n", " ")

    before = flat(text[:start])
    hit = flat(text[start:end])
    after = flat(text[end:])

    if len(before) > width:
        before = "…" + before[-width:]

    if len(after) > width:
        after = after[:width] + "…"

    return before, hit, after


def apply_suggestion(editor, suggestion: Suggestion) -> int:
    """
    Accept a suggestion: change every place it applies to, once.

    Every occurrence, not only the first: a name spelled two ways through a
    recording is the case the feature exists for, and accepting a
    suggestion caption by caption would mean pressing Accept a dozen times
    for one decision. It is one undo step for the same reason Replace All
    is -- one decision, one press of undo to take it back -- which is why
    the snapshot is taken here rather than through update_caption_text,
    which would take one per caption.

    Parameters:
        editor (SRTEditor): The open editor.
        suggestion (Suggestion): What the reader accepted.

    Returns:
        int: How many captions were changed.
    """

    targets = matching_captions(editor.captions, suggestion.find)

    if not targets:
        return 0

    editor.save_state_for_undo()
    pattern = match_pattern(suggestion.find)

    for caption in targets:
        # A function rather than a replacement string: a replacement
        # string is not literal text -- a backslash or a \g in it is an
        # instruction to re, and the model's suggestion is neither ours nor
        # written with that in mind.
        new_text = pattern.sub(lambda _: suggestion.replace, caption.text)

        # The reader accepted this, so it is their edit, marked as one --
        # and a replacement of a different length moves every mark after it
        # along, which is what retag_edits works out.
        caption.edited_words = editor.retag_edits(
            caption.text, new_text, caption.edited_words
        )
        caption.text = new_text

    editor.update_flagged_count()
    editor.refresh_display()

    return len(targets)


def read_domain_code(answer: str, codes: list[str]) -> Optional[str]:
    """
    The domain code in the classifier's answer.

    The codes come from the hub rather than from a copy of the table kept
    here: the list is the hub's to extend, and a frontend holding a stale
    copy of it would refuse a domain the server understands perfectly well.

    Nothing is guessed from the words. A model that answered with a label
    instead of a code has not answered the question, and the reader is
    shown an empty picker rather than a confident wrong classification.

    Parameters:
        answer (str): Whatever the model wrote.
        codes (list[str]): The codes the hub offers.

    Returns:
        Optional[str]: One of the codes, or None.
    """

    for code in sorted(codes, key=len, reverse=True):
        if re.search(rf"(?<![\d.]){re.escape(code)}(?![\d])", answer or ""):
            return code

    return None


class ReviewAssistant:
    """
    Work out the domain, let the reader confirm it, then go through the
    suggestions one at a time.

    It is drawn in the Analyse strip's own answer area rather than in a
    dialog of its own: a review is another thing to ask of the same
    recording, so it is asked for from the same row of pills, and it is
    read where an answer is read. That is also what settles the problem the
    dialog had -- a card over the transcription is a card over the very
    text a suggestion is judged against, which is why it had to be
    seamless, and draggable, and kept inside the window. In the strip
    nothing covers the text, and the card cannot be in the way of it.

    Parameters:
        editor (SRTEditor): The open editor. Its captions are what is
            reviewed and what an accepted suggestion changes.
        language (str): The language the transcription was made in, so the
            assistant's own sentences come back in it.
        client (InferenceClient): The page's connection to the hub, shared
            with the Analyse strip -- one socket per open editor.
        on_jump (Optional[Callable]): Called with a caption to move the
            transcription to it, so a suggestion can be seen in place.
        container: The slot to draw into -- the strip's own review slot.
            Assigned after the strip is built, alongside the client, since
            neither exists until then.
        on_close (Optional[Callable]): Called when the review ends, so the
            strip can have its answer area back.
    """

    def __init__(
        self,
        editor,
        language: str = "",
        client=None,
        on_jump: Optional[Callable] = None,
        container=None,
        on_close: Optional[Callable] = None,
    ) -> None:
        self.editor = editor
        self.language = language
        self.client = client
        self.on_jump = on_jump
        self.container = container
        self.on_close = on_close

        self.domains: list[dict] = []
        self.domain: Optional[str] = None

        self.body = None
        self.footer = None
        self.continue_button = None
        # Whether the footer already carries Accept/Dismiss/Skip. They are
        # drawn once and left alone for the whole review.
        self.deciding = False

        self.answer = ""
        self.request_id: Optional[str] = None

        # What the review cost: two requests, the classification and the
        # review itself, added together. Shown at the end rather than
        # between the suggestions, where it would be one more thing to read
        # on a card that is being decided on.
        self.spent: dict = {"input_tokens": 0, "output_tokens": 0, "gpu_seconds": 0.0}

        self.queue: list[Suggestion] = []
        self.position = 0
        self.skips = 0
        self.outcome = Outcome()

        # How many suggestions have been read out of the answer so far.
        # The answer arrives a line at a time and each line is a whole
        # suggestion, so the reader starts deciding while the rest is still
        # being written -- see _collect.
        self.parsed = 0
        self.streaming = False

        # The counter on the card, kept as a reference so an arriving
        # suggestion can update it without the card being redrawn under a
        # reader who is reading it.
        self.progress_label = None

        # The last suggestion accepted, and the button that takes it back.
        # Accepting is one undo step, so the editor's own undo is what
        # undoes it -- there is nothing to remember here but which
        # suggestion to offer again.
        self.last_accepted: Optional[Suggestion] = None
        self.last_changed = 0
        self.undo_button = None

        # Accept, kept as a reference for the same reason the counter is:
        # the footer is drawn once for the whole review, and the reader can
        # edit the replacement on the card -- emptying the box, or typing
        # the transcribed text back into it, leaves nothing to accept.
        self.accept_button = None

    # ------------------------------------------------------------------
    # What the hub offers
    # ------------------------------------------------------------------

    def set_catalogue(self, catalogue: dict) -> None:
        """
        Take the domain list from the hub's own menu.

        Parameters:
            catalogue (dict): What /inference/tasks answered with.

        Returns:
            None
        """

        self.domains = list(catalogue.get("domains") or [])

    @property
    def available(self) -> bool:
        """
        Whether the assistant can be offered at all.

        Returns:
            bool: True when the hub named some domains to review against,
                and the strip has given the assistant a socket and
                somewhere to draw.
        """

        return (
            bool(self.domains)
            and self.client is not None
            and self.container is not None
        )

    def domain_label(self, code: Optional[str]) -> str:
        """
        A domain's name, as the hub gave it.

        Parameters:
            code (Optional[str]): The domain code.

        Returns:
            str: "Field — Domain", or an empty string for an unknown code.
        """

        for domain in self.domains:
            if domain["code"] == code:
                return f"{domain['group_label']} — {domain['label']}"

        return ""

    # ------------------------------------------------------------------
    # Opening
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """
        Start a review: draw the panel and ask what the recording is about.

        Returns:
            None
        """

        if not self.available:
            ui.notify("The review assistant is not available right now.")
            return

        self.answer = ""
        self.domain = None
        self.queue = []
        self.position = 0
        self.skips = 0
        self.parsed = 0
        self.streaming = False
        self.last_accepted = None
        self.spent = {"input_tokens": 0, "output_tokens": 0, "gpu_seconds": 0.0}
        self.outcome = Outcome()

        self._build()

        await self._ask_domain()

    def _build(self) -> None:
        """
        Draw the panel, empty, in the strip's own review slot.

        Returns:
            None
        """

        self.container.clear()

        with self.container:
            # A heading, because the slot it is drawn in is where an
            # answer to one of the pills beside Review normally appears --
            # so it says which of them produced what is in it.
            with ui.row().classes("review-header items-center w-full"):
                ui.icon("rate_review").classes("review-mark")
                ui.label("Review assistant").classes("review-title")

            self.body = ui.column().classes("review-body w-full")
            self.footer = ui.row().classes("review-footer items-center w-full")

    def _open(self) -> bool:
        """
        Whether there is still a review on the page to draw into.

        The hub can answer after the review has been closed -- a cancel
        races whatever is already on the wire -- and close() empties the
        slot on the way out. Nothing that draws may assume the panel it was
        called about is still there.

        Returns:
            bool: True while the panel is built and on the page.
        """

        return self.body is not None and self.footer is not None

    async def close(self) -> None:
        """
        End the review, stopping anything still generating.

        The slot is emptied and handed back: the strip's answer area lives
        in the same place, and a finished review left standing there would
        keep it hidden.

        Returns:
            None
        """

        if self.request_id is not None and self.client is not None:
            await self.client.cancel(self.request_id)
            self.request_id = None

        if self.container is not None:
            self.container.clear()

        self.body = None
        self.footer = None
        self.deciding = False
        self.accept_button = None

        if self.on_close is not None:
            self.on_close()

    # ------------------------------------------------------------------
    # Step one: what is this recording about
    # ------------------------------------------------------------------

    async def _ask_domain(self) -> None:
        """
        Ask the hub to classify the transcription.

        Returns:
            None
        """

        text = transcript_text(self.editor)

        if not text.strip():
            self._say(ANALYSING, "There is nothing to review yet.")
            return

        self.answer = ""
        self._working(ANALYSING)

        self.request_id = await self.client.ask(
            task=DOMAIN_TASK,
            text=text,
            language=None,
            model=None,
            on_delta=self._collect,
            on_done=self._domain_ready,
            on_error=self._failed,
        )

    def _collect(self, text: str) -> None:
        """
        Keep a piece of an answer, and show a suggestion the moment there is
        one.

        The answer is JSON Lines precisely so that a finished line can be
        read while the rest is still being written: a review of a long
        recording takes a model a while, and there is no reason for the
        reader to watch a spinner through all of it when the first
        suggestion was ready in the first second. A partial last line is
        not an object yet and parse_suggestions ignores it, so nothing
        half-arrived is ever offered.

        Parameters:
            text (str): The piece.

        Returns:
            None
        """

        self.answer += text

        if not self.streaming:
            return

        with self._on_the_page():
            self._take_new_suggestions()

    def _take_new_suggestions(self) -> None:
        """
        Put whatever has arrived since the last look on the queue.

        Returns:
            None
        """

        found = parse_suggestions(self.answer)

        if len(found) <= self.parsed:
            return

        # Appended, never re-ordered: Skip moves a suggestion to the back of
        # this same list, so rebuilding it from the answer would undo the
        # reader's own decisions.
        self.queue.extend(found[self.parsed :])
        self.parsed = len(found)

        if not self.deciding:
            # The first one to arrive is what takes the spinner away.
            self._draw_current()
        else:
            self._update_progress()

    def _update_progress(self) -> None:
        """
        Say how many suggestions are still waiting, without redrawing the
        card.

        Redrawing it would move what the reader is reading, and while the
        answer is still arriving that would happen several times a second.

        Returns:
            None
        """

        if self.progress_label is not None:
            self.progress_label.set_text(self._progress_text())

    def _progress_text(self) -> str:
        """
        The counter in the corner of the card.

        Returns:
            str: How many are left, and whether more are still coming.
        """

        left = sum(entry.state == "pending" for entry in self.queue)

        if self.streaming:
            return f"{left} so far, still looking..."

        return f"{left} left to decide" if left > 1 else "Last suggestion"

    def _domain_ready(self, usage: Optional[dict] = None) -> None:
        """
        Show the domain the model settled on, for the reader to confirm.

        Parameters:
            usage (Optional[dict]): What the classification cost.

        Returns:
            None
        """

        self.request_id = None
        self.spent = add_usage(self.spent, usage or {})
        self.domain = read_domain_code(
            self.answer, [domain["code"] for domain in self.domains]
        )

        with self._on_the_page():
            self._draw_domain()

    def _draw_domain(self) -> None:
        """
        The domain step: a suggestion, and everything else to choose from.

        Returns:
            None
        """

        if not self._open():
            return

        self.body.clear()
        self.footer.clear()
        self.deciding = False
        self.accept_button = None

        with self.body:
            if self.domain:
                ui.label(DOMAIN_LEAD).classes("review-lead")
                ui.label(self.domain_label(self.domain)).classes("review-domain")
            else:
                ui.label(DOMAIN_UNKNOWN).classes("review-lead")

            ui.label(DOMAIN_NOTE).classes("review-note")

            # Every domain, not only the suggested one: "Change domain" is
            # a step in the flow, not an escape hatch, and a reader who
            # knows the material should not have to accept a guess first.
            options = {
                domain["code"]: f"{domain['group_label']} — {domain['label']}"
                for domain in self.domains
            }

            select = (
                ui.select(
                    options,
                    value=self.domain,
                    label="Domain",
                    with_input=True,
                )
                .props("outlined dense")
                .classes("review-select")
            )
            select.on_value_change(lambda event: self._domain_chosen(event.value))

        with self.footer:
            ui.space()
            ui.button("Cancel", on_click=self.close, color=None).props(
                "flat no-caps"
            ).classes("review-action")
            self.continue_button = (
                ui.button("Continue", on_click=self._start_review, color=None)
                .props("unelevated no-caps")
                .classes("review-primary")
            )
            self.continue_button.set_enabled(bool(self.domain))

    def _domain_chosen(self, code) -> None:
        """
        The reader picked a domain of their own.

        Parameters:
            code: The code they picked.

        Returns:
            None
        """

        self.domain = str(code) if code else None

        if self.continue_button is not None:
            self.continue_button.set_enabled(bool(self.domain))

    # ------------------------------------------------------------------
    # Step two: the suggestions
    # ------------------------------------------------------------------

    async def _start_review(self) -> None:
        """
        Ask for corrections, now that the domain is settled.

        Returns:
            None
        """

        if not self.domain:
            return

        self.answer = ""
        self.parsed = 0
        self.queue = []
        self.position = 0
        self.skips = 0
        self.streaming = True
        self._working(REVIEWING)

        self.request_id = await self.client.ask(
            task=SUGGEST_TASK,
            text=transcript_text(self.editor),
            # The sentence explaining each suggestion is written for the
            # people who were recorded, not for the prompt's own language.
            language=answer_language(self.language),
            model=None,
            on_delta=self._collect,
            on_done=self._suggestions_ready,
            on_error=self._failed,
            domain=self.domain,
        )

    def _suggestions_ready(self, usage: Optional[dict] = None) -> None:
        """
        Start stepping through what came back.

        Parameters:
            usage (Optional[dict]): What the review itself cost, on top of
                the classification.

        Returns:
            None
        """

        self.request_id = None
        self.spent = add_usage(self.spent, usage or {})

        with self._on_the_page():
            # Everything that arrived in the last batch, and then the
            # counter stops saying "still looking".
            self._take_new_suggestions()
            self.streaming = False

            if self.deciding:
                self._update_progress()
            else:
                # Nothing was ever drawn: either the answer held no
                # suggestion at all, or none of them survived parsing.
                self._draw_current()

    def _current(self) -> Optional[Suggestion]:
        """
        The suggestion being shown, skipping any that no longer apply.

        A suggestion is written against the transcription as it was when the
        review started. Accepting one changes that transcription, and a
        later suggestion may be about text that is no longer there -- the
        same word, corrected already, or a phrase that has been replaced
        wholesale. Such a suggestion is dropped rather than offered against
        text nobody can see.

        Returns:
            Optional[Suggestion]: What to show, or None when the review is
                over.
        """

        while self.position < len(self.queue):
            suggestion = self.queue[self.position]

            if suggestion.state != "pending":
                self.position += 1
                continue

            if occurrences(self.editor.captions, suggestion.find):
                return suggestion

            suggestion.state = "stale"
            self.outcome.stale += 1
            self.position += 1

        return None

    def _draw_current(self) -> None:
        """
        Show the suggestion being decided on, or finish.

        Returns:
            None
        """

        if not self._open():
            return

        suggestion = self._current()

        if suggestion is None:
            self._finish()
            return

        places = occurrences(self.editor.captions, suggestion.find)

        self.body.clear()

        with self.body:
            with ui.row().classes("review-meta items-center w-full"):
                ui.label(suggestion.kind_label).classes("review-kind")
                self.progress_label = ui.label(self._progress_text()).classes(
                    "review-progress"
                )

            with ui.column().classes("review-change w-full"):
                with ui.row().classes("review-change-row items-center"):
                    ui.label("Transcribed as").classes("review-change-label")
                    ui.label(suggestion.find).classes("review-original")

                # The replacement is the reader's to change. A model that
                # has heard "halvsats" for "halstabletter" has usually
                # heard the right *kind* of thing and the wrong word, and
                # a reader who can see what was meant should not have to
                # dismiss the suggestion and go and find the caption to
                # type one word into it. Editing it here keeps the rest of
                # what the card is worth -- every occurrence changed at
                # once, as one undo step, with the sentence it came out of
                # in front of them.
                with ui.row().classes("review-change-row items-center"):
                    ui.label("Suggested").classes("review-change-label")

                    replacement = ui.input(
                        value=suggestion.replace,
                        on_change=lambda event, s=suggestion: self._reword(s, event),
                    ).props("dense borderless").classes("review-replacement-input")

                    with replacement:
                        ui.tooltip("Change the wording before accepting it.")

            # The model's own sentence, in the language of the recording.
            # A label, never markdown or HTML: it is generated text about
            # somebody's speech, and neither is trusted here.
            if suggestion.why:
                ui.label(suggestion.why).classes("review-why")

            self._draw_context(suggestion)

            with ui.row().classes("review-where items-center"):
                ui.label(
                    f"Found in {places} places"
                    if places > 1
                    else "Found in one place"
                ).classes("review-note")

                if self.on_jump is not None:
                    ui.button(
                        "Show in transcription",
                        icon="my_location",
                        on_click=lambda _=None, s=suggestion: self._show(s),
                        color=None,
                    ).props("flat dense no-caps").classes("review-show review-action")

        # The footer is not redrawn between suggestions. Accept, Dismiss
        # and Skip are pressed dozens of times in a row, and a button that
        # is rebuilt -- or that moves because the card above it grew -- is
        # a button the reader has to find again every time. See
        # _review_footer, and .review-body, which takes its height from the
        # pane rather than from what is in it for the same reason.
        if not self.deciding:
            self._review_footer()

        self._sync_accept(suggestion)

    def _reword(self, suggestion: Suggestion, event) -> None:
        """
        Take what the reader typed into the replacement box.

        Parameters:
            suggestion (Suggestion): The one being decided on.
            event: The input's own change event.

        Returns:
            None
        """

        suggestion.replace = str(event.value or "")

        self._sync_accept(suggestion)

    def _sync_accept(self, suggestion: Optional[Suggestion]) -> None:
        """
        Let Accept be pressed only while there is a change to make.

        Parameters:
            suggestion (Optional[Suggestion]): The one being decided on.

        Returns:
            None
        """

        if self.accept_button is not None:
            self.accept_button.set_enabled(
                suggestion is not None and suggestion.applicable
            )

    def _draw_context(self, suggestion: Suggestion) -> None:
        """
        The sentence the suggestion is about, with the words it would change
        picked out.

        "dos" against "dose" cannot be judged on its own -- whether it is a
        mishearing or a word the speaker meant is decided by what is around
        it, and asking the reader to go and look it up in the transcription
        for every suggestion is asking them not to bother.

        Three labels rather than one piece of HTML: a caption is somebody's
        speech and a suggestion is a model's writing, and neither is markup
        to be trusted here. They are laid out inline (see .review-context)
        so the three read as one wrapping sentence.

        Parameters:
            suggestion (Suggestion): The one being decided on.

        Returns:
            None
        """

        found = matching_captions(self.editor.captions, suggestion.find)

        if not found:
            return

        caption = found[0]
        match = match_pattern(suggestion.find).search(caption.text)

        if match is None:
            return

        before, hit, after = excerpt(caption.text, match.start(), match.end())

        with ui.column().classes("review-context-block w-full"):
            ui.label(f"In caption #{caption.index}").classes("review-change-label")

            with ui.element("div").classes("review-context"):
                ui.label(before).classes("review-context-text")
                ui.label(hit).classes("review-context-hit")
                ui.label(after).classes("review-context-text")

    def _review_footer(self) -> None:
        """
        The three answers, drawn once for the whole review.

        Dismiss and Skip are different answers and the issue asks for both:
        dismissing is a decision -- no, not this one -- and it is final,
        while skipping is the absence of one, so the suggestion comes round
        again. The tooltips say so, since two greyed words side by side do
        not.

        Returns:
            None
        """

        self.footer.clear()
        self.deciding = True

        # color=None on every button here, and everywhere else in this
        # panel. NiceGUI colours a button "primary" unless told otherwise,
        # which puts Quasar's own text-primary class on it -- and that
        # class carries !important, so a stylesheet rule of ours is not a
        # reliable way to take it off again. Asking for no colour at all
        # leaves the button inheriting the page's text colour, which is
        # what these should have been all along: three blue words in a row
        # read as three links, and Accept is the only one of the three that
        # changes anything.
        with self.footer:
            stop = ui.button("Stop review", on_click=self.close, color=None).props(
                "flat no-caps"
            ).classes("review-action")

            with stop:
                ui.tooltip("End the review. What you accepted stays.")

            self.undo_button = ui.button(
                "Undo last accept", icon="undo", on_click=self._undo, color=None
            ).props("flat no-caps").classes("review-action")
            self.undo_button.set_enabled(self.last_accepted is not None)

            with self.undo_button:
                ui.tooltip("Put the last accepted change back as it was.")

            ui.space()

            skip = ui.button("Skip", on_click=self._skip, color=None).props(
                "flat no-caps"
            ).classes("review-action")

            with skip:
                ui.tooltip("Decide later. This comes round again at the end.")

            dismiss = ui.button("Dismiss", on_click=self._dismiss, color=None).props(
                "flat no-caps"
            ).classes("review-action")

            with dismiss:
                ui.tooltip("No. This suggestion does not come back.")

            accept = ui.button(
                "Accept", icon="check", on_click=self._accept, color=None
            ).props("unelevated no-caps").classes("review-primary")

            self.accept_button = accept

            with accept:
                ui.tooltip("Change the transcription here. Nothing is saved yet.")

    def _show(self, suggestion: Suggestion) -> None:
        """
        Move the transcription to the first place a suggestion applies.

        Parameters:
            suggestion (Suggestion): The one being decided on.

        Returns:
            None
        """

        found = matching_captions(self.editor.captions, suggestion.find)

        if found and self.on_jump is not None:
            self.on_jump(found[0])

    def _accept(self) -> None:
        """
        Apply the suggestion being shown and move on.

        Returns:
            None
        """

        suggestion = self._current()

        # Accept is disabled while there is nothing to apply, but the
        # check belongs here too: a suggestion emptied on the card must
        # never reach the captions as a deletion nobody asked for.
        if suggestion is None or not suggestion.applicable:
            return

        # What was typed, not what was typed plus whatever spaces came with
        # it -- the replacement goes straight into a caption.
        suggestion.replace = suggestion.replace.strip()

        changed = apply_suggestion(self.editor, suggestion)

        suggestion.state = "accepted"
        self.outcome.accepted += 1

        if suggestion.edited:
            self.outcome.edited += 1

        self.outcome.changed += changed
        self.outcome.applied.append(suggestion)

        self.position += 1
        self.skips = 0
        self.last_changed = changed
        self._remember_accept(suggestion)

        self._draw_current()

    def _remember_accept(self, suggestion: Optional[Suggestion]) -> None:
        """
        Note which suggestion Undo would take back.

        Parameters:
            suggestion (Optional[Suggestion]): The one just accepted, or
                None once there is nothing to undo.

        Returns:
            None
        """

        self.last_accepted = suggestion

        if self.undo_button is not None:
            self.undo_button.set_enabled(suggestion is not None)

    def _undo(self) -> None:
        """
        Take back the last accepted suggestion, and offer it again.

        Accepting is one undo step, so the editor's own history is what
        puts the text back -- nothing is remembered here but which
        suggestion to put back on the queue. Only the most recent accept
        can be taken back: further undo is the editor's own business, and
        an assistant reaching further into that history than the change it
        made itself would be undoing the reader's typing.

        Returns:
            None
        """

        suggestion = self.last_accepted

        if suggestion is None:
            return

        self.editor.undo()

        suggestion.state = "pending"
        self.outcome.accepted = max(0, self.outcome.accepted - 1)

        if suggestion.edited:
            self.outcome.edited = max(0, self.outcome.edited - 1)

        self.outcome.changed = max(0, self.outcome.changed - self.last_changed)
        self.last_changed = 0

        if suggestion in self.outcome.applied:
            self.outcome.applied.remove(suggestion)

        # Back to it, so the reader lands on the suggestion they just took
        # back rather than having to find it again.
        if 0 <= self.position - 1 < len(self.queue):
            if self.queue[self.position - 1] is suggestion:
                self.position -= 1

        self._remember_accept(None)
        self._draw_current()

    def _dismiss(self) -> None:
        """
        Turn the suggestion down. It does not come back.

        Returns:
            None
        """

        suggestion = self._current()

        if suggestion is None:
            return

        suggestion.state = "dismissed"
        self.outcome.dismissed += 1

        self.position += 1
        self.skips = 0

        self._draw_current()

    def _skip(self) -> None:
        """
        Decide later: the suggestion goes to the back of the queue.

        Dismiss and Skip are different answers and the issue asks for both.
        Dismissing is a decision -- no, not this one -- and it is final.
        Skipping is the absence of one, so the suggestion comes round again
        once the rest have been dealt with. Skipping everything ends the
        review rather than looping forever.

        Returns:
            None
        """

        suggestion = self._current()

        if suggestion is None:
            return

        pending = sum(entry.state == "pending" for entry in self.queue)

        self.queue.append(self.queue.pop(self.position))
        self.skips += 1

        if self.skips >= pending:
            self._finish()
            return

        self._draw_current()

    def _finish(self) -> None:
        """
        Say what the review came to, and remind the reader to save.

        Returns:
            None
        """

        self.outcome.skipped = sum(
            entry.state == "pending" for entry in self.queue
        )

        if not self._open():
            return

        self.body.clear()
        self.footer.clear()
        self.deciding = False
        self.accept_button = None

        with self.body:
            if not self.queue:
                ui.label(NOTHING_FOUND).classes("review-lead")
            else:
                ui.label("Review finished").classes("review-lead")

                with ui.column().classes("review-summary"):
                    ui.label(
                        f"{self.outcome.accepted} accepted"
                        + (
                            f", changing {self.outcome.changed} "
                            + ("caption" if self.outcome.changed == 1 else "captions")
                            if self.outcome.accepted
                            else ""
                        )
                    )
                    if self.outcome.edited:
                        # Worth saying: those are the reader's own words,
                        # not the model's, and the count is the only place
                        # that distinction survives the review.
                        ui.label(
                            f"{self.outcome.edited} of them reworded before "
                            "accepting"
                        )

                    ui.label(f"{self.outcome.dismissed} dismissed")

                    if self.outcome.skipped:
                        ui.label(f"{self.outcome.skipped} left undecided")

                    if self.outcome.stale:
                        # Worth saying rather than quietly dropping: the
                        # reader saw a count when the review started.
                        ui.label(
                            f"{self.outcome.stale} no longer applied to the "
                            "transcription"
                        )

            if self.outcome.accepted:
                ui.label(NOT_SAVED).classes("review-note")

            # What the review cost: both requests, the classification and
            # the review itself. Said at the end, where there is nothing
            # left to decide, rather than on a card being read.
            if line := usage_line(self.spent):
                ui.label(line).classes("review-note review-usage")

        with self.footer:
            ui.space()
            ui.button("Close", on_click=self.close, color=None).props(
                "unelevated no-caps"
            ).classes("review-primary")

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _working(self, message: str) -> None:
        """
        Show that something is being generated.

        Parameters:
            message (str): What is being done, in English.

        Returns:
            None
        """

        if not self._open():
            return

        self.body.clear()
        self.footer.clear()
        self.deciding = False
        self.accept_button = None

        # Centred in the card rather than sitting in its top corner: while
        # this is up there is nothing else on it, and a spinner tucked into
        # a corner of an otherwise empty box reads as something having gone
        # wrong rather than as work in progress.
        with self.body:
            with ui.column().classes("review-working items-center"):
                ui.spinner(size="2rem")
                ui.label(message).classes("review-lead")

                ui.label(
                    "The transcription is sent as it stands, including edits "
                    "you have not saved. Nothing is stored."
                ).classes("review-note review-working-note")

        with self.footer:
            ui.space()
            ui.button("Cancel", on_click=self.close, color=None).props(
                "flat no-caps"
            ).classes("review-action")

    def _say(self, heading: str, note: str) -> None:
        """
        Show a message and nothing else.

        Parameters:
            heading (str): The line in normal type.
            note (str): The quieter line under it.

        Returns:
            None
        """

        if not self._open():
            return

        self.body.clear()
        self.footer.clear()
        self.deciding = False
        self.accept_button = None

        with self.body:
            ui.label(heading).classes("review-lead")
            ui.label(note).classes("review-note")

        with self.footer:
            ui.space()
            ui.button("Close", on_click=self.close, color=None).props(
                "flat no-caps"
            ).classes("review-action")

    def _failed(self, message: str) -> None:
        """
        Report a request that did not finish.

        Parameters:
            message (str): What went wrong, as the hub put it.

        Returns:
            None
        """

        self.request_id = None

        with self._on_the_page():
            self._say("The review could not be completed.", message)

    def _on_the_page(self):
        """
        Enter the review's own slot.

        Everything the hub sends back arrives on a background task, which
        has no slot stack -- NiceGUI cannot tell which client an element
        belongs to and raises rather than guessing. The slot the review is
        drawn in answers both questions, since the client is read from its
        parent.

        Returns:
            The slot, as a context manager.
        """

        return self.container if self.container is not None else nullcontext()

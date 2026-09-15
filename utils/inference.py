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
Asking a language model about what was transcribed.

The socket is held by this process -- the NiceGUI server -- and not by the
browser: the editor already lives here, so the browser needs no Javascript
of its own, and the reader's token never has to be handed to a page script.

Nothing on this path is stored. The text sent is whatever the editor holds
at that moment, edits and all, and the answer that comes back lives in the
page until it is closed. That is deliberate -- a transcript is never
written down for the sake of summarising it -- and it is why the dialog
says so and offers a download.
"""

import asyncio
import json
import logging
import math
import re
import uuid

from typing import Callable, Optional

import httpx
import websockets

from nicegui import app, background_tasks

from utils.docx_export import build_docx
from utils.latex_export import build_latex
from utils.markdown_blocks import BREAK, TAGS, plain
from utils.settings import get_settings
from utils.token import get_auth_header

settings = get_settings()
log = logging.getLogger(__name__)

# What the transcript is called in the download the reader gets.
NOTES_SUFFIX = {
    "summary": "summary",
    "key_points": "key-points",
    "action_items": "action-items",
    "study_notes": "study-notes",
}

# Said at the top of every exported file. The export is a derived thing and
# has to say so on its own, away from the page that produced it: a file
# called "lecture-summary.txt" sitting beside "lecture.txt" is otherwise
# indistinguishable from a transcript someone edited down by hand.
EXPORT_NOTE = "Generated from the transcription by {product}. Not part of the transcript."


def hub_base() -> str:
    """
    The HTTP address of the inference hub.

    The hub is its own application, not part of the API: behind a reverse
    proxy the two share a name, which is what an empty INFERENCE_URL means,
    but in development they are two ports and the API answers 404 for
    anything inference asks it.

    Returns:
        str: The base URL, without a trailing slash.
    """

    return (settings.INFERENCE_URL or settings.API_URL).rstrip("/")


def hub_url() -> str:
    """
    The websocket address of the inference hub.

    Returns:
        str: The configured address, or one derived from the hub's base URL.
    """

    if settings.INFERENCE_WS_URL:
        return settings.INFERENCE_WS_URL

    base = hub_base()

    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]

    return f"{base.rstrip('/')}/api/v1/ws/inference"


def answer_language(name: str) -> Optional[str]:
    """
    The language an answer should be written in, from the job's own.

    An answer is always written in the language that was spoken -- a Swedish
    lecture summarised in English is of no use to the person who recorded
    it, and a small model asked to work in "the same language as the
    transcript" will happily answer in the language its instructions
    happen to be written in. Naming the language outright is what makes it
    reliable.

    The job's language carries qualifiers the model has no use for:
    "Swedish (verbatim)" is a transcription mode, and "Northern Sámi
    (Experimental)" says something about our support for it, not about the
    language. Both are cut back to the language itself.

    Parameters:
        name (str): The language the transcription was made in.

    Returns:
        Optional[str]: The language to answer in, or None when the job does
            not say -- the hub then falls back to asking for the
            transcript's own language.
    """

    cleaned = re.sub(r"\s*\([^)]*\)", "", name or "").strip()

    return cleaned or None


def usage_of(message: dict) -> dict:
    """
    What an answer cost, out of the hub's own "done".

    The same figures the hub writes to its usage row, so the number a
    reader is shown and the number that gets billed cannot drift apart.
    A worker that reports none of them leaves zeros rather than nothing:
    the caller then has one shape to deal with.

    Parameters:
        message (dict): The "done" message.

    Returns:
        dict: input_tokens, output_tokens and gpu_seconds.
    """

    def number(name, kind):
        try:
            return kind(message.get(name, 0) or 0)
        except (TypeError, ValueError):
            return kind(0)

    return {
        "input_tokens": number("input_tokens", int),
        "output_tokens": number("output_tokens", int),
        "gpu_seconds": number("gpu_seconds", float),
    }


def add_usage(total: dict, more: dict) -> dict:
    """
    Two answers' cost, added up.

    Parameters:
        total (dict): What has been spent so far.
        more (dict): What the latest answer cost.

    Returns:
        dict: The sum, as a new dict.
    """

    return {
        key: total.get(key, 0) + more.get(key, 0)
        for key in ("input_tokens", "output_tokens", "gpu_seconds")
    }


def usage_line(usage: dict) -> str:
    """
    What an answer cost, in one line for the page.

    Tokens in, tokens out, and the GPU time behind them -- the three
    figures that say what a question actually cost, which is otherwise
    invisible to everyone but an operator reading the usage table. Thin
    spaces group the thousands, since a five-figure token count is
    unreadable without them.

    Parameters:
        usage (dict): As usage_of() returns it.

    Returns:
        str: The line, or an empty string when the worker reported nothing
            at all -- a row of zeros says less than no row.
    """

    if not usage or not any(usage.get(key) for key in usage):
        return ""

    def grouped(value: int) -> str:
        return f"{value:,}".replace(",", "\u2009")

    parts = [
        f"{grouped(int(usage.get('input_tokens', 0)))} tokens in",
        f"{grouped(int(usage.get('output_tokens', 0)))} out",
    ]

    if seconds := float(usage.get("gpu_seconds", 0)):
        parts.append(f"{seconds:.1f}\u2009s on the GPU")

    return " · ".join(parts)


def transcript_text(editor) -> str:
    """
    The text to reason about, taken from the editor as it stands now.

    Timings are left out on purpose: they cost tokens and say nothing about
    what was said. Speakers are kept when there are any, because who said
    what is most of the meaning in a meeting or an interview.

    Parameters:
        editor (SRTEditor): The open editor.

    Returns:
        str: The transcript as plain text.
    """

    if editor.data_format == "srt":
        # Subtitles are cut to fit a screen, not into sentences. Joining the
        # lines back up gives the model prose rather than a column of
        # fragments.
        return " ".join(
            caption.text.replace("\n", " ").strip()
            for caption in editor.captions
            if caption.text.strip()
        )

    blocks = []

    for caption in editor.captions:
        if not caption.text.strip():
            continue

        speaker = (caption.speaker or "").strip()

        if speaker and speaker != "UNKNOWN":
            blocks.append(f"{speaker}: {caption.text.strip()}")
        else:
            blocks.append(caption.text.strip())

    return "\n\n".join(blocks)


# Finding a passage again in the transcription.
#
# The answer is prose a model wrote about the transcript, not a quotation
# of it, so there is no marker to follow back -- what is left is the words
# the two have in common. A rare word ("photosynthesis", a name, a figure)
# says a great deal about where a sentence came from and a common one
# ("and", "the") says nothing, which is what the inverse document
# frequency below weighs: a caption is scored by how much of the clicked
# text's *weight* it accounts for, not by how many words it happens to
# share.
WORD = re.compile(r"\w+", re.UNICODE)

# How much of that weight has to land in one place before the jump is
# offered, and how many separate words have to be behind it. A single
# shared word is a coincidence however rare it is, and moving the reader
# somewhere on the strength of one is worse than telling them the passage
# could not be placed.
JUMP_MIN_SCORE = 0.3
JUMP_MIN_TERMS = 2

# How many captions in a row a passage is allowed to have come out of. A
# bullet in a set of study notes summarises a stretch of speech, not one
# sentence of it, and in a transcription a caption is one speaker turn --
# so the words behind a single line of the answer are routinely spread over
# two or three of them, and scoring each caption alone means no single one
# ever accounts for enough of the passage to clear the threshold. That was
# the common way for a jump to miss: not a wrong caption, but no caption at
# all for a line that plainly came from somewhere.
JUMP_WINDOW = 3

# How much of the run's best caption a caption has to carry before it
# counts as where the passage started, rather than a caption that happens
# to share a word with it.
LEAD_SHARE = 0.35

# A longer window covers more of any passage simply by being longer, so
# each caption past the first costs a little: a run of three only wins when
# it genuinely accounts for more than the best single caption in it does.
WINDOW_DISCOUNT = 0.92

# A word used in more than this much of the transcription is not evidence
# of anything: it still counts for what it weighs, but it cannot be one of
# the words a jump rests on. Without this, a sentence of the model's own --
# "This answer was generated from the transcription." -- shares "the" and
# "was" with some caption and, since those are the only terms in it the
# transcription uses at all, accounts for its whole weight and is placed
# with confidence somewhere arbitrary.
COMMON_SHARE = 0.5

# What a word counts for at least, even when every caption uses it. Without
# a floor the whole reckoning collapses on a short transcription, where a
# word in every caption weighs exactly nothing and a passage made of such
# words weighs nothing at all.
TERM_FLOOR = 0.05

# Endings stripped, longest first, to compare a word with the same word
# inflected. The recordings are mostly Swedish, where the definite article
# is a suffix ("budget" is "budgeten" the second time it is mentioned) and
# a model writing about the transcript reaches for whichever form its own
# sentence wants -- so an exact match on the surface form misses most of
# what the two texts really have in common. Cheap and blunt on purpose:
# the same folding is applied to both sides, so over-folding merges words
# rather than losing them.
ENDINGS = (
    "arna", "erna", "orna", "ande", "ende", "aren", "arne",
    "ade", "are", "ast", "ing", "ens", "ans", "ets",
    "ar", "er", "en", "et", "es", "an", "na", "ns", "or", "ur",
    "a", "e", "n", "s", "t",
)

# Nothing is folded below this, and nothing is compared past it: a stem of
# three letters is not a word any more, and two long words that agree for
# eight letters are the same word for this purpose.
MIN_STEM = 4
MAX_STEM = 8


def fold(word: str) -> str:
    """
    A word as something an inflected form of it also folds to.

    Parameters:
        word (str): One word, lower case.

    Returns:
        str: Its stem, as far as this can be taken without a dictionary.
    """

    stem = word

    # Repeatedly, since one ending routinely sits on another: "budgeten"
    # is "budget" is "budg", and "budget" itself has to reach the same
    # place or the two would not compare equal.
    while True:
        for ending in ENDINGS:
            if stem.endswith(ending) and len(stem) - len(ending) >= MIN_STEM:
                stem = stem[: -len(ending)]
                break
        else:
            break

    return stem[:MAX_STEM]


def terms(text: str) -> list[str]:
    """
    The words of a piece of text, as something comparable.

    Case, punctuation and inflection are dropped, which also takes the
    Markdown marks the answer is written with -- a bullet's `**heading**`
    compares as the word inside it.

    Parameters:
        text (str): Any text.

    Returns:
        list[str]: Its words, folded.
    """

    return [fold(word) for word in WORD.findall(text.lower())]


def locate_caption(text: str, captions: list) -> Optional[object]:
    """
    The caption a passage of the answer most likely came from.

    Words the transcription never uses are left out of the reckoning
    altogether rather than counted as misses: the answer is a paraphrase,
    and half of any sentence in it is the model's own wording. What is
    scored is how much of the shared vocabulary's weight one *run* of
    captions accounts for -- a run rather than a single caption because a
    line of an answer summarises a stretch of speech, and the words behind
    it are normally spread over more than one of them.

    The reader is put down at the *start* of that run rather than at its
    strongest caption: a line of an answer is about a stretch of speech,
    and landing halfway through it means the first half is never heard
    without seeking back by hand -- the same reason clicking a caption on
    the timeline seeks to its start. "The start" is the first caption in
    the run actually carrying some of the passage, so a run that opens on a
    caption sharing nothing but a common word does not send the reader a
    caption early.

    Parameters:
        text (str): The passage the reader clicked.
        captions (list[SRTCaption]): The transcription, as it stands.

    Returns:
        Optional[SRTCaption]: The best match, or None when nothing is close
            enough to be worth moving the reader for.
    """

    query = set(terms(text))

    if not query or not captions:
        return None

    spoken = [set(terms(caption.text)) for caption in captions]
    total = len(spoken)

    weights = {}
    common = set()

    for term in query:
        appears = sum(1 for words in spoken if term in words)

        if appears > total * COMMON_SHARE:
            common.add(term)

        if appears:
            # Smoothed inverse document frequency: a word every caption
            # uses says nothing about which one a line came from, and
            # counting it dilutes the words that do -- half a summary is
            # made of such words. TERM_FLOOR keeps it from being nothing
            # at all, which would leave a short transcription unplaceable.
            weights[term] = (
                math.log((1 + total) / (1 + appears)) + TERM_FLOOR
            )

    weight = sum(weights.values())

    if not weight:
        return None

    # What each caption accounts for on its own, worked out once: it is
    # both the score of a one-caption run and, inside a winning run, what
    # decides where the reader is put down.
    shares = []

    for words in spoken:
        shared = [term for term in weights if term in words]
        shares.append((shared, sum(weights[term] for term in shared)))

    best = None
    best_score = 0.0

    for start in range(total):
        covered: set = set()
        found = 0.0

        for length in range(1, JUMP_WINDOW + 1):
            index = start + length - 1

            if index >= total:
                break

            for term in shares[index][0]:
                if term not in covered:
                    covered.add(term)
                    found += weights[term]

            # The minimum is a minimum of *telling* words. A run sharing
            # nothing but words the whole transcription uses has not been
            # found, however much of the passage's weight those words
            # happen to be.
            if len(covered - common) < JUMP_MIN_TERMS:
                continue

            score = (found / weight) * (WINDOW_DISCOUNT ** (length - 1))

            # Strictly greater, so a passage that fits two runs equally
            # well lands in the earlier one -- which is where it was said
            # first.
            if score > best_score:
                best_score = score
                best = _landing(shares, start, index)

    if best is None or best_score < JUMP_MIN_SCORE:
        return None

    return captions[best]


def _landing(shares: list, start: int, end: int) -> int:
    """
    Where in a run of captions to put the reader down.

    Parameters:
        shares (list[tuple]): Per caption, the passage's terms it carries
            and what they weigh.
        start (int): First caption of the run.
        end (int): Last caption of the run, inclusive.

    Returns:
        int: The caption to move to.
    """

    strongest = max(shares[at][1] for at in range(start, end + 1))

    for at in range(start, end + 1):
        # A caption sharing a word or two of the common kind is not where
        # the passage began; one carrying a real part of it is.
        if shares[at][1] >= LEAD_SHARE * strongest:
            return at

    return start


# What a sub- or superscript becomes with no typesetting to do it with,
# and the tags that are worth nothing at all here.
SUBSCRIPT = re.compile(r"<sub>(.+?)</sub>", re.DOTALL)
SUPERSCRIPT = re.compile(r"<sup>(.+?)</sup>", re.DOTALL)
STRAY_TAG = re.compile(rf"</?(?:b|strong|i|em|{'|'.join(TAGS)})\s*/?>")


def plain_text(text: str) -> str:
    """
    A model's Markdown answer as plain text.

    The export is offered as a text file, and a text file full of `##` and
    `**` is a worse read than the page it came from -- the marks are
    instructions to a renderer, not something anyone wants to see. Headings
    keep their words, emphasis loses its asterisks, and bullets are
    normalised to one dash so a list still reads as a list.

    The inline HTML a model writes among its Markdown is read here too:
    plain text has no subscript to fall back on, so a sub or a
    superscript is written the way it would be typed on one line --
    `R_H`, `10^-18` -- which is how anybody reading it would have written
    it themselves. The rest of the tags carry nothing plain text can act
    on and are dropped rather than printed.

    Parameters:
        text (str): The answer, in Markdown.

    Returns:
        str: The same answer as plain text.
    """

    lines = []
    fenced = False

    for line in text.splitlines():
        # A code fence, and everything inside it, is left exactly as it
        # was: stripping what looks like markup out of a program exports
        # something that no longer runs, and its blank lines are part of
        # it.
        if line.lstrip().startswith("```"):
            fenced = not fenced
            lines.append(line.rstrip())
            continue

        if fenced:
            lines.append(line.rstrip())
            continue

        line = SUBSCRIPT.sub(r"_\1", line)
        line = SUPERSCRIPT.sub(r"^\1", line)
        line = BREAK.sub(" ", line)
        line = STRAY_TAG.sub("", line)
        line = plain(line)

        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^(\s*)[-*+]\s+", r"\1- ", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"\*(\S.*?\S|\S)\*", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)

        lines.append(line.rstrip())

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def export_title(task_label: str, filename: str) -> str:
    """
    What an exported file calls itself, at the top of its first page.

    Parameters:
        task_label (str): What was asked for, e.g. "Study notes".
        filename (str): The media file the transcription came from.

    Returns:
        str: The title.
    """

    return f"{task_label} — {filename}" if filename else task_label


def export_word(task_label: str, filename: str, answer: str) -> bytes:
    """
    The same file as a Word document, formulae and all.

    Notes and summaries are handed in, pasted into a course page or marked
    up by somebody who does not have Scribe open, and .docx is what those
    readers have. It is the one export that keeps a formula *as* a formula
    -- an OMML equation Word draws, edits and searches -- rather than as a
    line of LaTeX nobody outside a physics department reads.

    Parameters:
        task_label (str): What was asked for, e.g. "Study notes".
        filename (str): The media file the transcription came from.
        answer (str): The model's answer, in Markdown.

    Returns:
        bytes: The .docx file.
    """

    return build_docx(
        title=export_title(task_label, filename),
        note=EXPORT_NOTE.format(product=settings.TAB_TITLE),
        answer=answer,
    )


def export_latex(task_label: str, filename: str, answer: str) -> str:
    """
    The same file as LaTeX source.

    For the reader at the other end from the Word one: notes going into a
    document somebody is already writing in LaTeX, or formulae to be
    typeset rather than read on a screen. The mathematics needs no
    conversion here -- the model writes it in LaTeX already -- but the
    prose around it does, since a single unescaped per cent sign is a
    document that will not build.

    Parameters:
        task_label (str): What was asked for, e.g. "Study notes".
        filename (str): The media file the transcription came from.
        answer (str): The model's answer, in Markdown.

    Returns:
        str: A whole .tex document.
    """

    return build_latex(
        title=export_title(task_label, filename),
        note=EXPORT_NOTE.format(product=settings.TAB_TITLE),
        answer=answer,
    )


def export_document(
    task_label: str, filename: str, answer: str, plain: bool
) -> str:
    """
    The file a reader downloads: the answer, with a line saying what it is.

    Parameters:
        task_label (str): What was asked for, e.g. "Study notes".
        filename (str): The media file the transcription came from.
        answer (str): The model's answer, in Markdown.
        plain (bool): Whether to write plain text rather than Markdown.

    Returns:
        str: The file's contents.
    """

    title = export_title(task_label, filename)
    note = EXPORT_NOTE.format(product=settings.TAB_TITLE)

    if plain:
        return f"{title}\n{note}\n\n{plain_text(answer)}"

    return f"# {title}\n\n*{note}*\n\n{answer.strip()}\n"


async def fetch_tasks() -> dict:
    """
    The tasks and models the hub is offering right now.

    Returns:
        dict: The hub's answer, or an empty dict when it cannot be reached.
    """

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{hub_base()}/api/v1/inference/tasks",
                headers=get_auth_header(),
            )
            response.raise_for_status()

            return response.json().get("result", {})
    except (httpx.HTTPError, ValueError):
        return {}


class InferenceClient:
    """
    One connection to the hub, belonging to one open editor page.

    Opened when the reader first asks for something and kept for as long as
    the page is, since a second request is common and reconnecting costs a
    round trip through the proxy.
    """

    def __init__(self) -> None:
        self.socket = None
        self.reader: Optional[asyncio.Task] = None
        self.handlers: dict[str, dict[str, Callable]] = {}

    @property
    def connected(self) -> bool:
        """
        Whether the socket is open.

        Returns:
            bool: True when requests can be sent.
        """

        return self.socket is not None

    async def connect(self) -> Optional[str]:
        """
        Open the socket, if it is not open already.

        Returns:
            Optional[str]: None on success, otherwise a message for the
                reader.
        """

        if self.socket is not None:
            return None

        if not (header := get_auth_header()):
            return "Your session has expired. Reload the page."

        try:
            self.socket = await websockets.connect(
                hub_url(),
                additional_headers=header,
                max_size=None,
                open_timeout=15,
            )
        except Exception:
            self.socket = None
            return "The service that answers these questions is unavailable."

        self.reader = background_tasks.create(self._read())

        return None

    async def close(self) -> None:
        """
        Close the socket and forget anything still running on it.

        Called when the page goes away: the hub cancels whatever this
        connection asked for as soon as it closes, so a reader who leaves
        does not leave a GPU generating for nobody.

        Returns:
            None
        """

        if self.reader is not None:
            self.reader.cancel()
            self.reader = None

        if self.socket is not None:
            try:
                await self.socket.close()
            except Exception:
                pass

            self.socket = None

        self.handlers.clear()

    async def _read(self) -> None:
        """
        Deliver what comes back to whoever asked for it.

        Returns:
            None
        """

        try:
            async for raw in self.socket:
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue

                req_id = str(message.get("req_id", ""))
                handlers = self.handlers.get(req_id, {})

                match message.get("type"):
                    case "accepted":
                        self._deliver(handlers, "on_accepted", message.get("model", ""))
                    case "delta":
                        self._deliver(handlers, "on_delta", message.get("text", ""))
                    case "done":
                        self._deliver(handlers, "on_done", usage_of(message))
                        self.handlers.pop(req_id, None)
                    case "error":
                        self._deliver(
                            handlers,
                            "on_error",
                            message.get("message", "The request failed."),
                        )
                        self.handlers.pop(req_id, None)
                    case _:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception:
            # The socket dropped. Logged with the reason, because "the
            # connection was lost" is all the page can honestly say and it
            # is not enough to work out why. Nothing here carries what was
            # being worked on.
            log.warning("Inference socket closed unexpectedly", exc_info=True)

            # Everything waiting on it is told, rather than left spinning.
            for handlers in list(self.handlers.values()):
                self._deliver(
                    handlers, "on_error", "The connection to the service was lost."
                )

            self.handlers.clear()
            self.socket = None

    @staticmethod
    def _deliver(handlers: dict, name: str, *args) -> None:
        """
        Hand one message to the page, without letting it take the socket down.

        A callback draws into the page, and drawing can fail for reasons
        that have nothing to do with the connection. Left unguarded, one
        such failure ends the read loop and every later message with it.

        Parameters:
            handlers (dict): The callbacks registered for this request.
            name (str): Which one to call.
            *args: What to call it with.

        Returns:
            None
        """

        if (callback := handlers.get(name)) is None:
            return

        try:
            callback(*args)
        except Exception:
            log.warning(f"Inference {name} handler failed", exc_info=True)

    async def ask(
        self,
        task: str,
        text: str,
        language: Optional[str],
        model: Optional[str],
        on_delta: Callable[[str], None],
        on_done: Callable[[dict], None],
        on_error: Callable[[str], None],
        on_accepted: Optional[Callable[[str], None]] = None,
        domain: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send one request and route its answer back to the page.

        Parameters:
            task (str): Task name, as offered by the hub.
            text (str): The transcript to work on.
            language (Optional[str]): Language to answer in.
            model (Optional[str]): Model alias, or None for the default.
            on_delta (Callable): Called with each piece of the answer.
            on_done (Callable): Called with what the answer cost when it is
                complete -- see usage_of().
            on_error (Callable): Called with a message when it is not.
            on_accepted (Optional[Callable]): Called with the model that
                took the request.
            domain (Optional[str]): Subject domain code, for the review
                assistant's own tasks. A code from the hub's own list -- it
                is looked up there and only the hub's label for it reaches
                a prompt.

        Returns:
            Optional[str]: The request identifier, or None when it could not
                be sent -- on_error has been called in that case.
        """

        if (problem := await self.connect()) is not None:
            on_error(problem)
            return None

        req_id = str(uuid.uuid4())

        self.handlers[req_id] = {
            "on_delta": on_delta,
            "on_done": on_done,
            "on_error": on_error,
            "on_accepted": on_accepted,
        }

        try:
            await self.socket.send(
                json.dumps(
                    {
                        "type": "request",
                        "req_id": req_id,
                        "task": task,
                        "text": text,
                        "language": language,
                        "model": model,
                        "domain": domain,
                        # The socket outlives the token it was opened with,
                        # so every request carries the current one and the
                        # hub checks it again.
                        "token": app.storage.user.get("token"),
                    }
                )
            )
        except Exception:
            self.handlers.pop(req_id, None)
            self.socket = None
            on_error("The connection to the service was lost.")
            return None

        return req_id

    async def cancel(self, req_id: str) -> None:
        """
        Stop a request that is still running.

        Parameters:
            req_id (str): The identifier ask() returned.

        Returns:
            None
        """

        self.handlers.pop(req_id, None)

        if self.socket is None:
            return

        try:
            await self.socket.send(json.dumps({"type": "cancel", "req_id": req_id}))
        except Exception:
            pass

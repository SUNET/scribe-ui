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
import re
import uuid

from typing import Callable, Optional

import httpx
import websockets

from nicegui import app, background_tasks

from utils.settings import get_settings
from utils.token import get_auth_header

settings = get_settings()

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


def plain_text(text: str) -> str:
    """
    A model's Markdown answer as plain text.

    The export is offered as a text file, and a text file full of `##` and
    `**` is a worse read than the page it came from -- the marks are
    instructions to a renderer, not something anyone wants to see. Headings
    keep their words, emphasis loses its asterisks, and bullets are
    normalised to one dash so a list still reads as a list.

    Parameters:
        text (str): The answer, in Markdown.

    Returns:
        str: The same answer as plain text.
    """

    lines = []

    for line in text.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^(\s*)[-*+]\s+", r"\1- ", line)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"\*(\S.*?\S|\S)\*", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)

        lines.append(line.rstrip())

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


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

    title = f"{task_label} — {filename}" if filename else task_label
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

                handlers = self.handlers.get(str(message.get("req_id", "")), {})

                match message.get("type"):
                    case "accepted":
                        if callback := handlers.get("on_accepted"):
                            callback(message.get("model", ""))
                    case "delta":
                        if callback := handlers.get("on_delta"):
                            callback(message.get("text", ""))
                    case "done":
                        if callback := handlers.get("on_done"):
                            callback()
                        self.handlers.pop(str(message.get("req_id", "")), None)
                    case "error":
                        if callback := handlers.get("on_error"):
                            callback(message.get("message", "The request failed."))
                        self.handlers.pop(str(message.get("req_id", "")), None)
                    case _:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception:
            # The socket dropped. Everything waiting on it is told, rather
            # than left spinning.
            for handlers in list(self.handlers.values()):
                if callback := handlers.get("on_error"):
                    callback("The connection to the service was lost.")

            self.handlers.clear()
            self.socket = None

    async def ask(
        self,
        task: str,
        text: str,
        language: Optional[str],
        model: Optional[str],
        on_delta: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        on_accepted: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """
        Send one request and route its answer back to the page.

        Parameters:
            task (str): Task name, as offered by the hub.
            text (str): The transcript to work on.
            language (Optional[str]): Language to answer in.
            model (Optional[str]): Model alias, or None for the default.
            on_delta (Callable): Called with each piece of the answer.
            on_done (Callable): Called when the answer is complete.
            on_error (Callable): Called with a message when it is not.
            on_accepted (Optional[Callable]): Called with the model that
                took the request.

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

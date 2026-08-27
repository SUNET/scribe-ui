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
The Analyse strip under the video: pick what to ask for, watch the answer
arrive.

Two things about it are deliberate and should stay.

The answer is not saved. It is generated from whatever the editor holds at
that moment and lives in the page until it is closed -- no row, no file, no
second copy of somebody's recording anywhere. The dialog says so, and
offers a download, because a reader who wants to keep it has to be the one
who keeps it.

The answer is never trusted as markup. What comes back is a model's reading
of a transcript, and a transcript is other people's speech: it can contain
anything, including an attempt to get something rendered into this page.
It is `ui.markdown`'s own sanitiser that stops that -- `sanitize=True` runs
the browser's `setHTML`, or DOMPurify where that is missing, over the
rendered HTML before it is inserted. That is a real sanitiser rather than
the character escaping this used to do, which is why maths and diagrams can
be shown at all: escaping every `<` and `&` made a formula and a mermaid
arrow (`-->`) unrenderable along with the markup it was defending against.
"""

import re

from contextlib import contextmanager
from typing import Optional

from nicegui import ui

from utils.helpers import sanitize_filename
from utils.inference import (
    InferenceClient,
    NOTES_SUFFIX,
    answer_language,
    export_document,
    fetch_tasks,
    transcript_text,
)
from utils.settings import get_settings

settings = get_settings()

# What the reader is told, in the line under the buttons.
NOT_SAVED = "Generated from the transcription as it stands now. Not saved — download it to keep it."
IDLE_HINT = "Ask about this transcription. Answers are not saved."
NO_WORKER = "No model is available right now. Try again in a moment."

# An icon per task, so the row reads at a glance rather than as four
# similar words. Anything the hub offers that is not listed here still gets
# a button; it just gets the generic mark.
TASK_ICONS = {
    "summary": "subject",
    "key_points": "format_list_bulleted",
    "action_items": "checklist",
    "study_notes": "school",
}


# What the answer may contain. Mathematics is turned into MathML on this
# side (markdown2's latex extra, via latex2mathml) and drawn by the browser
# itself; mermaid fences become diagrams drawn by the copy of mermaid
# NiceGUI already ships. Neither costs us a line of Javascript.
MARKDOWN_EXTRAS = ["fenced-code-blocks", "tables", "latex", "mermaid"]

# A mermaid diagram can bind a click on a node to a Javascript call. It only
# works when mermaid is initialised with securityLevel "loose" -- which it
# is not here -- but the answer is written by a model reading somebody
# else's speech, and a directive that only fails to run because of a
# setting elsewhere is not a defence. They are dropped.
MERMAID_CLICK = re.compile(r"^\s*click\s+\S+.*$", re.MULTILINE)

# A fenced mermaid block in the answer.
MERMAID_FENCE = re.compile(r"```mermaid[ \t]*\n(.*?)(?:```|\Z)", re.DOTALL)

# What a mermaid diagram may start with. Anything else is a model writing
# prose into a mermaid fence, and mermaid answers that with an error box
# where the diagram should be -- so it is shown as the code block it really
# is instead.
MERMAID_KINDS = (
    "architecture",
    "block",
    "c4context",
    "classDiagram",
    "erDiagram",
    "flowchart",
    "gantt",
    "gitGraph",
    "graph",
    "journey",
    "mindmap",
    "pie",
    "quadrantChart",
    "requirementDiagram",
    "sankey",
    "sequenceDiagram",
    "stateDiagram",
    "timeline",
    "xychart",
)


def is_diagram(source: str) -> bool:
    """
    Whether a mermaid fence holds something mermaid can actually draw.

    Parameters:
        source (str): The contents of the fence.

    Returns:
        bool: True when it opens with a diagram type mermaid knows.
    """

    for line in source.strip().splitlines():
        line = line.strip()

        if not line or line.startswith("%%"):
            continue

        return line.lower().startswith(tuple(k.lower() for k in MERMAID_KINDS))

    return False


def split_answer(text: str) -> list[tuple[str, str]]:
    """
    An answer broken into prose and diagrams, in order.

    They are drawn by different things. Prose goes through ui.markdown,
    which sanitises the HTML it produces before the browser inserts it; a
    diagram goes to ui.mermaid, which takes the source as a prop and never
    becomes HTML on this side at all. They cannot be one element: the
    sanitiser strips the class attribute that markdown's own mermaid
    support looks for, so a diagram written inside markdown is rendered as
    its own source code and nothing else.

    Parameters:
        text (str): The model's answer.

    Returns:
        list[tuple[str, str]]: ("text", markdown) and ("mermaid", source)
            pairs, in the order they appeared.
    """

    parts: list[tuple[str, str]] = []
    position = 0

    for match in MERMAID_FENCE.finditer(text):
        source = match.group(1).strip()

        if not is_diagram(source):
            continue

        if before := text[position:match.start()].strip():
            parts.append(("text", before))

        parts.append(("mermaid", source))
        position = match.end()

    if rest := text[position:].strip():
        parts.append(("text", rest))

    return parts


def prepare_answer(text: str) -> str:
    """
    A model's answer, ready to be rendered.

    The rendering itself is what is defended: ui.markdown sanitises the HTML
    it produces in the browser before inserting it, which is why nothing is
    escaped here. What this does remove is the one construct a sanitiser
    would let through because it is legitimate mermaid -- a click directive
    binding a node to a script.

    Parameters:
        text (str): The model's answer.

    Returns:
        str: The answer, ready for ui.markdown.
    """

    return MERMAID_CLICK.sub("", text)


class InferencePanel:
    """
    The Analyse strip: one row of controls, and the answer under it.

    It lives below the video rather than behind a button because it is read
    alongside the transcription, not instead of it -- a reader compares the
    summary against what was said. At rest it is a single row; the answer
    appears under it only once there is one, so it costs almost nothing
    while it is not being used.

    Parameters:
        editor (SRTEditor): The open editor. Its captions are what gets
            sent, so edits made and not yet saved are included -- which is
            what a reader means by "summarise this".
        filename (str): Name of the media file, used for the download.
        language (str): The language the transcription was made in.
    """

    def __init__(
        self,
        editor,
        filename: str,
        language: str = "",
        on_expand=None,
    ) -> None:
        self.editor = editor
        self.filename = filename
        self.language = language

        # Called with False to fold the video, the timeline and the
        # playback switches away, and True to bring them back. The strip
        # does not own those, so the page hands it a way to ask -- and the
        # page knows the awkward one: the timeline is a custom component
        # rooted in a Teleport, where set_visibility() has nothing to land
        # on and does nothing at all.
        self.on_expand = on_expand
        self.expanded = False

        self.client = InferenceClient()
        self.catalogue: dict = {}
        self.answer = ""
        self.request_id: Optional[str] = None

        self.current_task = ""
        self.available = True
        self.panel = None
        self.actions = None
        self.buttons: dict = {}
        self.output = None
        self.parts = None
        self.body = None
        self.status = None
        self.stop_button = None
        self.copy_button = None
        self.download_button = None

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def build(self) -> None:
        """
        Draw the strip in the current slot.

        It starts hidden and stays hidden unless the hub answers with
        something to offer: a row of dead controls explaining that nothing
        is available is worse than no row at all.

        Returns:
            None
        """

        with ui.column().classes("inference-panel w-full") as panel:
            self.panel = panel
            panel.set_visibility(False)

            with ui.row().classes("inference-bar w-full items-center"):
                ui.icon("auto_awesome").classes("inference-mark")

                # One button per task, filled in once the hub says which
                # tasks exist. A reader picks what they want in one click
                # rather than choosing from a menu and then confirming.
                self.actions = ui.row().classes("inference-actions")

                # Grouped so the row is three cells rather than six: the
                # pills can then be centred on the row's true middle, with
                # these held to the right of it.
                with ui.row().classes("inference-tools"):
                    # An answer is read, and the pane it shares with the
                    # video leaves it a few lines. This gives it the whole
                    # pane and puts everything back afterwards. The video
                    # keeps playing while it is folded away -- a reader
                    # listening to the recording and reading the notes at
                    # the same time is the point of it being here.
                    self.expand_button = (
                        ui.button(icon="open_in_full")
                        .props("flat dense round")
                        .classes("inference-icon-btn")
                        .on("click", self.toggle_expand)
                    )
                    with self.expand_button:
                        self.expand_tooltip = ui.tooltip("Fill the pane")

                    self.stop_button = (
                        ui.button(icon="stop")
                        .props("flat dense round")
                        .classes("inference-icon-btn")
                        .on("click", self.stop)
                    )
                    with self.stop_button:
                        ui.tooltip("Stop generating")

                    self.copy_button = (
                        ui.button(icon="content_copy")
                        .props("flat dense round")
                        .classes("inference-icon-btn")
                        .on("click", self.copy)
                    )
                    with self.copy_button:
                        ui.tooltip("Copy")

                    # Two formats behind the one button. Plain text is what
                    # the feature request asks for and what opens anywhere;
                    # Markdown keeps the headings and lists for anyone pasting
                    # it somewhere that renders them.
                    self.download_button = (
                        ui.button(icon="download")
                        .props("flat dense round")
                        .classes("inference-icon-btn")
                    )
                    with self.download_button:
                        ui.tooltip("Download")

                        with ui.menu():
                            ui.menu_item(
                                "Text (.txt)", lambda: self.download("txt")
                            )
                            ui.menu_item(
                                "Markdown (.md)", lambda: self.download("md")
                            )

            self.status = ui.label(IDLE_HINT).classes("inference-status-line")

            with ui.scroll_area().classes("inference-output") as body:
                self.body = body

                # A container rather than one element: a finished answer is
                # rebuilt into prose and diagrams (see split_answer), and
                # while it is still arriving it is a single markdown element
                # being appended to, which is far cheaper than rebuilding a
                # tree several times a second.
                self.parts = ui.column().classes("inference-answer w-full")

                with self.parts:
                    self.output = ui.markdown("", extras=MARKDOWN_EXTRAS)

        self._set_running(False)
        self._show_answer(False)

        # The page handler is synchronous, so the hub is asked for its menu
        # on the first tick instead.
        ui.timer(0.1, self.load, once=True)

    async def load(self) -> None:
        """
        Ask the hub what it can do, and draw a button for each task.

        Which model answers is not offered as a choice. The hub picks a
        worker that has one, readers have no way to tell the models apart
        from the names, and the choice would be recorded against their
        usage as though they had meant it. Comparing models is an operator's
        job, done by changing the registry.

        Returns:
            None
        """

        self.catalogue = await fetch_tasks()

        tasks = self.catalogue.get("tasks", [])

        # Nothing at all when the deployment has no assistant: a row that
        # only apologises is worse than no row. A hub that is there but has
        # no worker connected is a different case -- the buttons are drawn
        # and disabled, with the reason on the line under them, because a
        # feature that silently vanishes reads as a fault in the page.
        if not self.catalogue.get("enabled") or not tasks:
            return

        with self.actions:
            for task in tasks:
                name = task["name"]

                button = (
                    ui.button(
                        task["label"],
                        icon=TASK_ICONS.get(name, "auto_awesome"),
                        on_click=lambda _, task_name=name: self.start(task_name),
                    )
                    .props("flat dense no-caps")
                    .classes("inference-chip")
                )

                with button:
                    ui.tooltip(task["description"])

                self.buttons[name] = button

        self.panel.set_visibility(True)

        if not self.catalogue.get("models"):
            self.available = False
            self.status.set_text(NO_WORKER)

            for button in self.buttons.values():
                button.set_enabled(False)

    def _show_answer(self, showing: bool) -> None:
        """
        Show or hide the answer area.

        Hidden while empty, so the strip is one row at rest.

        Parameters:
            showing (bool): Whether there is something to show.

        Returns:
            None
        """

        if self.body is not None:
            self.body.set_visibility(showing)

    def _set_running(self, running: bool) -> None:
        """
        Put the strip into or out of its working state.

        The button that was pressed carries the spinner, so it is obvious
        which answer is on its way; the others are disabled rather than
        hidden, so the row does not reflow under the pointer.

        Parameters:
            running (bool): Whether a request is in flight.

        Returns:
            None
        """

        for name, button in self.buttons.items():
            button.set_enabled(self.available and not running)

            if running and name == self.current_task:
                button.props("loading")
            else:
                button.props(remove="loading")

        self.stop_button.set_visibility(running)

        has_answer = bool(self.answer) and not running
        self.copy_button.set_visibility(has_answer)
        self.download_button.set_visibility(has_answer)

        if self.body is not None:
            if running:
                self.body.classes(add="is-generating")
            else:
                self.body.classes(remove="is-generating")

    def toggle_expand(self) -> None:
        """
        Give the answer the whole pane, or hand the pane back.

        Returns:
            None
        """

        self.expanded = not self.expanded

        if self.on_expand is not None:
            self.on_expand(not self.expanded)

        self.expand_button.props(
            f'icon={"close_fullscreen" if self.expanded else "open_in_full"}'
        )
        self.expand_tooltip.set_text(
            "Show the video again" if self.expanded else "Fill the pane"
        )

    async def start(self, task: str) -> None:
        """
        Send the current transcription off to be worked on.

        Parameters:
            task (str): The task whose button was pressed.

        Returns:
            None
        """

        if self.request_id is not None:
            return

        text = transcript_text(self.editor)

        if not text.strip():
            ui.notify("There is nothing to analyse yet.")
            return

        limit = self.catalogue.get("max_input_chars", 0)

        if limit and len(text) > limit:
            ui.notify(
                "This transcription is too long to analyse in one go "
                f"({len(text)} characters, limit {limit})."
            )
            return

        self.answer = ""
        self.current_task = task

        # The previous answer may have been rebuilt into several elements.
        self.parts.clear()

        with self.parts:
            self.output = ui.markdown("", extras=MARKDOWN_EXTRAS)

        self.status.set_text("Waiting for a free worker...")
        self._show_answer(True)
        self._set_running(True)

        self.request_id = await self.client.ask(
            task=task,
            text=text,
            # Always the language that was spoken. Named outright rather
            # than left to the model to infer from the transcript -- see
            # answer_language().
            language=answer_language(self.language),
            # No model is named: the hub picks a worker that has one.
            model=None,
            on_accepted=self._accepted,
            on_delta=self._delta,
            on_done=self._done,
            on_error=self._error,
        )

    @contextmanager
    def _on_the_page(self):
        """
        Enter the strip's own slot.

        Everything the hub sends back arrives on a background task, and a
        background task has no slot stack: NiceGUI cannot tell which client
        an element or a notification belongs to, and raises rather than
        guessing. Entering the panel's slot answers both questions at once,
        since the client is read from the slot's parent.

        Yields:
            None
        """

        if self.panel is None:
            yield
            return

        with self.panel:
            yield

    def _accepted(self, model: str) -> None:
        """
        Note that a worker took the request.

        The model's name is not shown: it is an operator's detail, and the
        reader was not offered a choice about it.

        Parameters:
            model (str): The model alias, for the log rather than the page.

        Returns:
            None
        """

        with self._on_the_page():
            self.status.set_text(f"{self._task_label()} — generating...")

    def _delta(self, text: str) -> None:
        """
        Add a piece of the answer as it arrives.

        Parameters:
            text (str): The piece.

        Returns:
            None
        """

        self.answer += text

        with self._on_the_page():
            if self.output is not None:
                self.output.set_content(prepare_answer(self.answer))

    def _render_answer(self) -> None:
        """
        Draw the finished answer: prose as markdown, diagrams as diagrams.

        Only once it is finished. A fence half-arrived is not a diagram
        yet, and redrawing the tree on every batch would flicker for the
        whole length of an answer.

        Returns:
            None
        """

        parts = split_answer(prepare_answer(self.answer))

        if not any(kind == "mermaid" for kind, _ in parts):
            return

        self.parts.clear()

        with self.parts:
            for kind, payload in parts:
                if kind == "mermaid":
                    ui.mermaid(payload).classes("inference-diagram")
                else:
                    ui.markdown(payload, extras=MARKDOWN_EXTRAS)

        self.output = None

    def _done(self) -> None:
        """
        Finish a completed answer.

        Returns:
            None
        """

        self.request_id = None

        with self._on_the_page():
            self._render_answer()
            self.status.set_text(NOT_SAVED)
            self._set_running(False)

    def _error(self, message: str) -> None:
        """
        Report a request that did not finish.

        Parameters:
            message (str): What went wrong, as the hub put it.

        Returns:
            None
        """

        self.request_id = None

        with self._on_the_page():
            self.status.set_text(IDLE_HINT)
            self._set_running(False)
            self._show_answer(bool(self.answer))
            ui.notify(message)

    async def stop(self) -> None:
        """
        Stop a request that is still generating.

        Whatever has arrived so far is kept -- half an answer is often
        enough, and throwing it away would mean generating it again.

        Returns:
            None
        """

        if self.request_id is not None:
            await self.client.cancel(self.request_id)
            self.request_id = None

        self._render_answer()
        self.status.set_text(NOT_SAVED if self.answer else IDLE_HINT)
        self._set_running(False)

    # ------------------------------------------------------------------
    # Keeping the answer
    # ------------------------------------------------------------------

    def _task_label(self) -> str:
        """
        The label of the task being worked on.

        Returns:
            str: What the button that started it says.
        """

        for task in self.catalogue.get("tasks", []):
            if task["name"] == self.current_task:
                return task["label"]

        return "Answer"

    def _download_name(self, extension: str) -> str:
        """
        What the downloaded file is called.

        Named after the media file and the task, never after the
        transcription's own export: the two sit in the same downloads
        folder, and an assistant's summary must not be mistakable for the
        transcript itself.

        Parameters:
            extension (str): "txt" or "md".

        Returns:
            str: A filename based on the media file and the task.
        """

        base = sanitize_filename(self.filename or "transcription")

        if "." in base:
            base = base.rsplit(".", 1)[0]

        suffix = NOTES_SUFFIX.get(self.current_task, "notes")

        return f"{base}-{suffix}.{extension}"

    def copy(self) -> None:
        """
        Put the answer on the clipboard.

        Returns:
            None
        """

        if not self.answer:
            return

        ui.clipboard.write(self.answer)
        ui.notify("Copied.")

    def download(self, extension: str = "txt") -> None:
        """
        Hand the answer to the reader as a file.

        Parameters:
            extension (str): "txt" for plain text, "md" for Markdown.

        Returns:
            None
        """

        if not self.answer:
            return

        document = export_document(
            task_label=self._task_label(),
            filename=self.filename,
            answer=self.answer,
            plain=extension == "txt",
        )

        ui.download.content(document, filename=self._download_name(extension))

    async def close(self) -> None:
        """
        Drop the connection when the page goes away.

        The hub cancels anything this connection asked for as soon as it
        closes, so a reader who leaves mid-answer does not leave a GPU
        generating for nobody.

        Returns:
            None
        """

        await self.client.close()

    def register_cleanup(self) -> None:
        """
        Arrange for close() to run when the page is gone.

        Returns:
            None
        """

        ui.context.client.on_disconnect(self.close)

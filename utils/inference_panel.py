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
The assistants under the video: pick what to ask for, watch the answer
arrive.

At rest there is nothing here at all -- two quiet icons in the corner of
the video frame, and no row of anything. Press one and its panel opens in
the space under the video, filling the rest of the pane; close it and the
space goes back to the recording. The two share that space, so one is open
at a time.

It was a permanent row: a mark, a pill per task, Review, and a status line
under them, all on screen whether or not anybody was using them. That cost
two rows of a pane the answer itself is trying to grow into, and the pills
were the busiest thing in the editor. The tasks did not go away -- they are
the row at the top of the assistant's own panel now, where they are read
when they are wanted.

Two more things about it are deliberate and should stay.

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
    add_usage,
    answer_language,
    export_document,
    export_latex,
    export_word,
    fetch_tasks,
    locate_caption,
    transcript_text,
    usage_line,
)
from utils.settings import get_settings

settings = get_settings()

# What the reader is told, in the line under the buttons.
NOT_SAVED = "Generated from the transcription as it stands now. Not saved — download it to keep it."
# Said only once there is an answer to click on, and only where the page
# has given the strip somewhere to jump to.
JUMP_HINT = "Click a line to go to where it was said."
# What the reader is told when a line cannot be placed. A heading the model
# wrote, or a sentence in its own words, belongs to no single caption.
NOT_FOUND = "That line could not be placed in the transcription."
IDLE_HINT = "Ask about this transcription. Answers are not saved."
NO_WORKER = "No model is available right now. Try again in a moment."
# While the review is up. It is drawn in the answer area, so the line above
# it has to say what is going on there instead of offering the answer's own
# note about not being saved -- the review says that itself, at the end.
REVIEW_HINT = "Going through the transcription. Nothing is changed unless you accept it."

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


# A line of Markdown that stands on its own: a heading, or an item of a
# list. Either one starts a new passage even without a blank line before
# it, because either one is a separate thing to click.
HEADING = re.compile(r"^\s*#{1,6}\s+")
BULLET = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")


def text_blocks(text: str) -> list[str]:
    """
    A stretch of the answer's prose cut into the passages a reader clicks.

    Not one element for the whole answer: a bullet in a set of study notes
    is about one moment in the recording, and clicking the notes as a whole
    could only ever mean one of them. Paragraphs, headings and list items
    each become a passage of their own; a fenced code block stays whole,
    since its blank lines are part of it.

    Parameters:
        text (str): Markdown, with no diagram fences left in it.

    Returns:
        list[str]: The passages, in order, as Markdown.
    """

    blocks: list[str] = []
    current: list[str] = []
    fenced = False

    def flush() -> None:
        if block := "\n".join(current).strip():
            blocks.append(block)

        current.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            if fenced:
                current.append(line)
                flush()
                fenced = False
            else:
                flush()
                current.append(line)
                fenced = True

            continue

        if fenced:
            current.append(line)
            continue

        if not line.strip():
            flush()
            continue

        if HEADING.match(line):
            flush()
            blocks.append(line.strip())
            continue

        if BULLET.match(line):
            flush()

        current.append(line)

    flush()

    return blocks


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
        on_jump=None,
        on_catalogue=None,
        on_review=None,
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

        # Called with the caption a clicked passage was traced back to, so
        # the transcription moves to where the answer came from. The strip
        # does not own the text editor or the player, so the page hands it
        # a way to ask. Without one the passages are still drawn, just not
        # clickable -- there is nowhere to go.
        self.on_jump = on_jump

        # The passages of the finished answer, and the one last followed --
        # kept marked, since it is the only thing on the page saying which
        # of a dozen similar bullets the transcription was moved for.
        self.passages: list = []
        self.followed = None

        # Called once with what the hub offers. The strip is what asks for
        # that menu, and the review assistant needs the same answer -- the
        # domain list rides along in it -- so it is handed on rather than
        # fetched a second time.
        self.on_catalogue = on_catalogue

        # Called when the Review pill is pressed. The review assistant is
        # another thing to ask of the same recording, so it is asked for
        # from this row rather than from the toolbar, and it is drawn in
        # this strip's own answer area rather than in a dialog over the
        # transcription -- see utils/review_assistant.py. The strip does
        # not own it: it lends it the slot and its socket, and the page
        # puts the two together.
        self.on_review = on_review
        self.review_button = None
        self.review_slot = None
        self.review_available = False
        self.reviewing = False

        # Whether a request of the strip's own is in flight, remembered so
        # the Review pill can be enabled on the same terms as the others
        # without _set_running having to reach it separately.
        self.running = False

        self.client = InferenceClient()
        self.catalogue: dict = {}
        self.answer = ""
        self.request_id: Optional[str] = None

        # What the last answer cost, and what this page has spent
        # altogether -- see the line under the answer.
        self.usage: dict = {}
        self.spent: dict = {"input_tokens": 0, "output_tokens": 0, "gpu_seconds": 0.0}

        self.current_task = ""
        self.available = True
        self.panel = None
        self.actions = None
        self.buttons: dict = {}
        self.output = None
        self.parts = None
        self.body = None
        self.status = None
        self.usage_label = None
        self.stop_button = None
        self.copy_button = None
        self.download_button = None

        # The two icons in the corner of the video frame, and the panel
        # each of them opens. Which one is open -- None, "analyse" or
        # "review" -- is the whole of the strip's state: they are drawn in
        # the same space under the video, so it cannot be both.
        self.launchers = None
        self.analyse_button = None
        self.analyse_slot = None
        self.open_panel: Optional[str] = None

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def build(self) -> None:
        """
        Draw the panels in the current slot, both closed.

        Nothing is on screen until one of the launchers is pressed -- see
        build_launchers, which the page calls inside the video frame.

        Returns:
            None
        """

        # Subtitles are not analysed. A caption is a line cut to fit a
        # screen, and a subtitle file is the same speech the transcription
        # already holds -- summarising one is asking a model to read a
        # column of fragments. The page does not build the strip there at
        # all; this is the same rule stated where the strip itself is.
        if getattr(self.editor, "data_format", "") == "srt":
            return

        with ui.column().classes("inference-panel w-full") as panel:
            self.panel = panel

            # The assistant's own panel: everything that used to be the
            # permanent row, now inside the thing it belongs to.
            with ui.column().classes("inference-open w-full") as slot:
                self.analyse_slot = slot
                slot.set_visibility(False)

                with ui.row().classes("inference-head w-full items-center"):
                    ui.icon("auto_awesome").classes("inference-mark")
                    ui.label("AI assistant").classes("inference-title")

                    ui.space()

                    self.stop_button = (
                        ui.button(icon="stop", color=None)
                        .props("flat dense round")
                        .classes("inference-icon-btn")
                        .on("click", self.stop)
                    )
                    with self.stop_button:
                        ui.tooltip("Stop generating")

                    self.copy_button = (
                        ui.button(icon="content_copy", color=None)
                        .props("flat dense round")
                        .classes("inference-icon-btn")
                        .on("click", self.copy)
                    )
                    with self.copy_button:
                        ui.tooltip("Copy")

                    # Four formats behind the one button. Plain text is
                    # what the feature request asks for and what opens
                    # anywhere; Markdown keeps the headings and lists for
                    # anyone pasting it somewhere that renders them; Word
                    # is what an answer handed to somebody else arrives
                    # as; and LaTeX is for the reader who is going to
                    # typeset it. The last two are the ones that keep a
                    # formula a formula -- Word as an equation it can
                    # edit, LaTeX as the source the model wrote.
                    self.download_button = (
                        ui.button(icon="download", color=None)
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
                            ui.menu_item(
                                "Word (.docx)", lambda: self.download("docx")
                            )
                            ui.menu_item(
                                "LaTeX (.tex)", lambda: self.download("tex")
                            )

                    # An answer is read, and the pane it shares with the
                    # video leaves it a few lines. This gives it the whole
                    # pane and puts everything back afterwards. The video
                    # keeps playing while it is folded away -- a reader
                    # listening to the recording and reading the notes at
                    # the same time is the point of it being here.
                    self.expand_button = (
                        ui.button(icon="open_in_full", color=None)
                        .props("flat dense round")
                        .classes("inference-icon-btn")
                        .on("click", self.toggle_expand)
                    )
                    with self.expand_button:
                        self.expand_tooltip = ui.tooltip("Fill the pane")

                    ui.button(icon="close", on_click=self.close_analyse, color=None).props(
                        "flat dense round"
                    ).classes("inference-icon-btn")

                # One button per task, filled in once the hub says which
                # tasks exist. A reader picks what they want in one click
                # rather than choosing from a menu and then confirming --
                # inside the panel now, not in a row of the pane.
                self.actions = ui.row().classes("inference-actions")

                with ui.row().classes("inference-status w-full items-baseline"):
                    self.status = ui.label(IDLE_HINT).classes(
                        "inference-status-line"
                    )

                    # What the answer cost. Otherwise invisible to everyone
                    # but an operator reading the usage table, and it is
                    # the reader's own question that ran the GPU.
                    self.usage_label = ui.label().classes("inference-usage")

                with ui.scroll_area().classes("inference-output") as body:
                    self.body = body

                    # A container rather than one element: a finished
                    # answer is rebuilt into prose and diagrams (see
                    # split_answer), and while it is still arriving it is a
                    # single markdown element being appended to, which is
                    # far cheaper than rebuilding a tree several times a
                    # second.
                    self.parts = ui.column().classes("inference-answer w-full")

                    with self.parts:
                        self.output = ui.markdown("", extras=MARKDOWN_EXTRAS)

            # Where the review assistant draws itself: the same space, so
            # only one of the two is ever open. Empty and hidden until the
            # Review launcher is pressed.
            self.review_slot = ui.column().classes("review-panel w-full")
            self.review_slot.set_visibility(False)

        self._set_running(False)
        self._show_answer(False)

        # The page handler is synchronous, so the hub is asked for its menu
        # on the first tick instead.
        ui.timer(0.1, self.load, once=True)

    def build_launchers(self) -> None:
        """
        Draw the two icons that open the panels, in the current slot.

        The page calls this inside the video frame, so they sit in its
        corner: at rest that is the whole of this feature on screen, which
        is the point -- a row of controls for something nobody is using
        costs a row of a pane the answer itself wants. They are hidden
        until the hub says what it can do.

        Returns:
            None
        """

        if getattr(self.editor, "data_format", "") == "srt":
            return

        with ui.row().classes("inference-launchers") as launchers:
            self.launchers = launchers
            launchers.set_visibility(False)

            self.analyse_button = (
                ui.button(icon="auto_awesome", on_click=self.open_analyse, color=None)
                .props("flat dense round")
                .classes("inference-launcher")
            )

            with self.analyse_button:
                ui.tooltip("AI assistant — summary, key points and more")

            self.review_button = (
                ui.button(icon="rate_review", on_click=self.start_review, color=None)
                .props("flat dense round")
                .classes("inference-launcher")
            )

            with self.review_button:
                ui.tooltip(
                    "Review assistant — go through the transcription for "
                    "likely mishearings"
                )

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

        # Handed on before anything is drawn, and whatever the answer says:
        # a hub with no worker connected still names its domains, and what
        # depends on this menu is not only this strip.
        if self.on_catalogue is not None:
            self.on_catalogue(self.catalogue)

        tasks = self.catalogue.get("tasks", [])

        # Nothing at all when the deployment has no assistant: a row that
        # only apologises is worse than no row. A hub that is there but has
        # no worker connected is a different case -- the buttons are drawn
        # and disabled, with the reason on the line under them, because a
        # feature that silently vanishes reads as a fault in the page.
        if not self.catalogue.get("enabled"):
            return

        with self.actions:
            for task in tasks:
                name = task["name"]

                button = (
                    ui.button(
                        task["label"],
                        icon=TASK_ICONS.get(name, "auto_awesome"),
                        on_click=lambda _, task_name=name: self.start(task_name),
                        # No colour asked for, deliberately. NiceGUI
                        # colours a button "primary" unless told
                        # otherwise, which puts Quasar's own .text-primary
                        # on it -- and that carries !important, so a
                        # stylesheet rule of ours is not a reliable way to
                        # take it back off: the pills came out in the
                        # brand blue whatever .inference-chip said.
                        # Asking for no colour leaves them inheriting the
                        # page's own text colour, which is what they want.
                        color=None,
                    )
                    .props("flat dense no-caps")
                    .classes("inference-chip")
                )

                with button:
                    ui.tooltip(task["description"])

                self.buttons[name] = button

        self._sync_launchers()

        # A hub with no tasks can still have domains to review against, so
        # the review launcher alone is reason enough to show them.
        if not tasks and not self.review_available:
            return

        if self.launchers is not None:
            self.launchers.set_visibility(True)

        if not self.catalogue.get("models"):
            self.available = False
            self.status.set_text(NO_WORKER)

            for button in self.buttons.values():
                button.set_enabled(False)

            self._sync_launchers()

            # Nothing on screen at rest says this, so the icons do: a
            # disabled icon with no reason on it reads as a fault.
            for launcher in (self.analyse_button, self.review_button):
                if launcher is not None:
                    with launcher:
                        ui.tooltip(NO_WORKER)

    def _show_answer(self, showing: bool) -> None:
        """
        Show or hide the answer area.

        Hidden while empty, so an assistant nobody has asked anything of
        yet is its task row and a line, not an empty box.

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

        self.running = running

        for name, button in self.buttons.items():
            button.set_enabled(self.available and not running)

            if running and name == self.current_task:
                button.props("loading")
            else:
                button.props(remove="loading")

        self._sync_launchers()

        self.stop_button.set_visibility(running)

        has_answer = bool(self.answer) and not running
        self.copy_button.set_visibility(has_answer)
        self.download_button.set_visibility(has_answer)

        if self.body is not None:
            if running:
                self.body.classes(add="is-generating")
            else:
                self.body.classes(remove="is-generating")

    def set_review_available(self, available: bool) -> None:
        """
        Say whether the review launcher is worth offering.

        Decided by the page, which is what holds the assistant: the hub has
        to have named domains to review against *and* have a worker
        connected, since an icon that apologises one click later is worse
        than no icon.

        Parameters:
            available (bool): Whether a review can actually be run.

        Returns:
            None
        """

        self.review_available = available

        self._sync_launchers()

        # Called from the catalogue handler, which runs before the
        # launchers are wired up -- so the flag is remembered and load()
        # reveals them once it knows there is something behind them.
        if available and self.launchers is not None:
            self.launchers.set_visibility(True)

    def _sync_launchers(self) -> None:
        """
        Show and enable the two icons on the frame.

        Returns:
            None
        """

        if self.review_button is not None:
            self.review_button.set_visibility(self.review_available)
            self.review_button.set_enabled(self.available and not self.running)

        if self.analyse_button is not None:
            self.analyse_button.set_enabled(self.available)

    # ------------------------------------------------------------------
    # Opening and closing. Both panels are drawn in the same space under
    # the video, so opening one closes the other.
    # ------------------------------------------------------------------

    def _set_open(self, which: Optional[str]) -> None:
        """
        Show one panel, or neither.

        Parameters:
            which (Optional[str]): "analyse", "review", or None for
                closed.

        Returns:
            None
        """

        self.open_panel = which

        if self.analyse_slot is not None:
            self.analyse_slot.set_visibility(which == "analyse")

        if self.review_slot is not None:
            self.review_slot.set_visibility(which == "review")

        # Closed, the strip must take no room at all: it is a flex item of
        # the pane, and left to grow it would hold the space it is not
        # using away from the video.
        if self.panel is not None:
            if which is None:
                self.panel.classes(remove="is-open")
            else:
                self.panel.classes(add="is-open")

    def open_analyse(self) -> None:
        """
        Open the assistant's own panel.

        Returns:
            None
        """

        if self.panel is None:
            return

        # The review is drawn in the same space. Ending it properly is the
        # assistant's own business -- it has a request in flight and a
        # queue of decisions -- so this only ever opens over a review that
        # is already finished with; while one is up, the launcher for it is
        # what is pressed to come back.
        if self.reviewing:
            return

        self._set_open("analyse")
        self._show_answer(bool(self.answer))
        self._set_running(self.running)

    def close_analyse(self) -> None:
        """
        Close the assistant's panel, keeping whatever answer is in it.

        Reopening shows the same answer again: generating it cost a GPU
        somebody paid for, and closing a panel is not asking for it to be
        thrown away.

        Returns:
            None
        """

        # Folded away, the video has to come back with the panel -- or the
        # pane is left with neither.
        if self.expanded:
            self.toggle_expand()

        self._set_open(None)

    async def start_review(self) -> None:
        """
        Open the review assistant in the same space.

        Returns:
            None
        """

        if self.on_review is None or self.reviewing:
            return

        self.reviewing = True

        self._set_open("review")
        self._set_running(False)

        await self.on_review()

    def end_review(self) -> None:
        """
        Close the review once it is over.

        The assistant empties the slot itself and then calls this.

        Returns:
            None
        """

        if not self.reviewing:
            return

        self.reviewing = False

        if self.expanded:
            self.toggle_expand()

        self._set_open(None)
        self._set_running(False)

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
        self.usage = {}

        if self.usage_label is not None:
            self.usage_label.set_text("")

        # The previous answer may have been rebuilt into several elements.
        self.parts.clear()

        with self.parts:
            self.output = ui.markdown("", extras=MARKDOWN_EXTRAS)

        self.status.set_text("Waiting for a free worker...")
        self._set_open("analyse")
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
            # A finished answer is rebuilt into passages and diagrams, and
            # the one element being streamed into is dropped. A batch
            # arriving after that -- the hub is still sending when a reader
            # presses Stop -- goes back to the streaming element rather
            # than being lost, since the passages it would be appended to
            # are already drawn.
            if self.output is None:
                self.parts.clear()

                with self.parts:
                    self.output = ui.markdown("", extras=MARKDOWN_EXTRAS)

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

        if not self.answer:
            return

        parts = split_answer(prepare_answer(self.answer))

        self.parts.clear()
        self.passages = []
        self.followed = None

        with self.parts:
            for kind, payload in parts:
                if kind == "mermaid":
                    ui.mermaid(payload).classes("inference-diagram")
                    continue

                for block in text_blocks(payload):
                    self._passage(block)

        self.output = None

    def _passage(self, block: str) -> None:
        """
        Draw one passage of the answer, and let it be followed back.

        Parameters:
            block (str): The passage, as Markdown.

        Returns:
            None
        """

        passage = ui.element("div").classes("inference-passage")

        with passage:
            ui.markdown(block, extras=MARKDOWN_EXTRAS)

        if self.on_jump is None:
            return

        self.passages.append(passage)
        passage.classes(add="is-linked")
        passage.on(
            "click", lambda _, source=block, element=passage: self.jump_to(
                source, element
            )
        )

    def _mark_followed(self, passage) -> None:
        """
        Mark the passage the reader followed, and unmark the last one.

        Parameters:
            passage: The passage element, or None to leave none marked.

        Returns:
            None
        """

        if self.followed is not None and self.followed is not passage:
            self.followed.classes(remove="is-followed")

        self.followed = passage

        if passage is not None:
            passage.classes(add="is-followed")

    def jump_to(self, source: str, passage=None) -> None:
        """
        Move the transcription to where a passage of the answer came from.

        The answer quotes nothing, so the passage is traced back by the
        words it and the transcription have in common -- see
        locate_caption. A heading, or a sentence written entirely in the
        model's own words, belongs to no one caption and is said to be
        unplaceable rather than guessed at.

        Parameters:
            source (str): The passage that was clicked, as Markdown.
            passage: The element it was drawn in, marked as the one
                followed once there is somewhere to follow it to.

        Returns:
            None
        """

        if self.on_jump is None:
            return

        caption = locate_caption(source, self.editor.captions)

        if caption is None:
            # Nothing was moved, so nothing is marked: a line left marked
            # here would claim the transcription is showing where it came
            # from, which is exactly what could not be worked out.
            ui.notify(NOT_FOUND)
            return

        self._mark_followed(passage)
        self.on_jump(caption)

    def _finished_line(self) -> str:
        """
        What the line under the answer says once there is one.

        Returns:
            str: The note about the answer not being saved, and -- where
                the page gave the strip somewhere to jump to -- how to
                follow a line back into the transcription.
        """

        if self.on_jump is None:
            return NOT_SAVED

        return f"{NOT_SAVED} {JUMP_HINT}"

    def _done(self, usage: Optional[dict] = None) -> None:
        """
        Finish a completed answer.

        Parameters:
            usage (Optional[dict]): What it cost, as the hub reported it.

        Returns:
            None
        """

        self.request_id = None
        self.usage = usage or {}
        self.spent = add_usage(self.spent, self.usage)

        with self._on_the_page():
            self._show_usage()
            self._render_answer()
            self.status.set_text(self._finished_line())
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

    def _show_usage(self) -> None:
        """
        Say what the answer cost, under it.

        The whole page's spending is named too once there has been more
        than one answer: a reader asking four questions of a recording is
        entitled to know what the four came to, not only the last one.

        Returns:
            None
        """

        if self.usage_label is None:
            return

        line = usage_line(self.usage)

        if line and self.spent != self.usage and (total := usage_line(self.spent)):
            line = f"{line}  ·  {total} this session"

        self.usage_label.set_text(line)

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
        self.status.set_text(self._finished_line() if self.answer else IDLE_HINT)
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
            extension (str): "txt" for plain text, "md" for Markdown,
                "docx" for Word, "tex" for LaTeX.

        Returns:
            None
        """

        if not self.answer:
            return

        if extension == "docx":
            ui.download.content(
                export_word(
                    task_label=self._task_label(),
                    filename=self.filename,
                    answer=self.answer,
                ),
                filename=self._download_name(extension),
                media_type=(
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                ),
            )

            return

        if extension == "tex":
            ui.download.content(
                export_latex(
                    task_label=self._task_label(),
                    filename=self.filename,
                    answer=self.answer,
                ),
                filename=self._download_name(extension),
                media_type="application/x-tex",
            )

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

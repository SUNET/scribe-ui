"""
The validation panel docked under the video (SUNET/scribe-ui#138).

"Validate" used to answer with a dialog listing every caption with a
problem. Its rows jumped to their caption on a click, but a keyboard could
not reach them, and a problem the editor itself shows (a red character
count) was told by colour alone. The panel replaces that list: it shows one
issue at a time, in words, and steps through them with Previous and Next.

- **Issues, not captions.** A caption with two problems comes up twice; the
  sequence is SRTEditor.validation_items(), in caption order.
- **Stepping keeps the keyboard where it was.** Previous and Next are never
  rebuilt, only relabelled, so focus stays on the one just pressed. At either
  end the button that would go further is disabled, and focus moves to the
  other one first -- a disabled button cannot keep focus, and the browser
  would otherwise drop it on the page.
- **Each step brings the caption into view and marks it**
  (TranscriptEditor.review(): `.transcript-cell-reviewing`), without seeking
  the recording or taking the caret out of wherever the reader left it.
- **"Caption 17" is a button.** It is how the keyboard gets from the issue
  to the text: it puts the caret in that caption -- for a line that is too
  long, where the line passes the limit, which is where a break usually
  belongs.
- **Closing keeps the markings.** The captions stay marked invalid until the
  next Validate; closing only puts the panel away, clears which caption is
  under review, and hands focus back to the Validate button.
- **Words first, colour second.** Every issue says what is wrong and whether
  it is an error (the file is broken) or a warning (a guideline is missed);
  the icon and its colour only repeat that.

Uncertain words and My edits are not here: they are review information, not
a subtitle rule the result breaks.
"""

from typing import Callable, Optional

from nicegui import ui


def position_text(position: int, total: int) -> str:
    """
    "2 of 5" -- where the reader is in the issues.
    """

    return f"{position + 1} of {total}"


def heading_text(total: int) -> str:
    """
    The panel's heading. How many there are is "2 of 5" beside it.
    """

    return "Validation issues" if total else "No validation issues"


# The kinds of issue Validate reports (each item's `rule`, set in
# collect_validation_issues), named for the filter checkboxes -- in this order,
# errors first.
RULE_LABELS = {
    "empty": "No text",
    "order": "Ends before start",
    "duplicate": "Same timing",
    "overlap": "Overlaps",
    "length": "Line length",
    "lines": "Too many lines",
    "short": "Too short",
}


def rule_counts(items: list) -> list[tuple[str, int]]:
    """
    (rule, how many) for each kind present in `items`, in RULE_LABELS order.
    """

    counts: dict[str, int] = {}
    for item in items:
        counts[item["rule"]] = counts.get(item["rule"], 0) + 1

    return [(rule, counts[rule]) for rule in RULE_LABELS if rule in counts]


def filters_wanted(counts: list[tuple[str, int]], hidden: set) -> bool:
    """
    Whether the filter checkboxes are drawn: when there is more than one kind
    to choose between -- or when a kind that is present is hidden, however
    few kinds there are. Hidden kinds outlive a Validate run, so hiding one
    kind and fixing the rest left that kind the only one found, hidden, with
    no checkbox left to show it again.
    """

    return len(counts) > 1 or any(rule in hidden for rule, _ in counts)


def shown_items(items: list, hidden: set) -> list:
    """
    The items whose kind the reader has not hidden, in their own order.
    """

    return [item for item in items if item["rule"] not in hidden]


class ValidationPanel:
    """
    Built once, hidden, under the video; `show()` fills and opens it each
    time Validate runs.

    Parameters:
        transcript: the TranscriptEditor, for review() and focus().
        captions: returns the editor's current caption list, to tell whether
            the caption an issue names still exists.
        return_focus: returns the element focus goes back to on close (the
            Validate button), or None.
        revalidate: checks every caption again and returns the fresh items
            (SRTEditor.revalidate_items), for "Check again"; None hides it.
    """

    def __init__(
        self,
        transcript,
        captions: Callable[[], list],
        return_focus: Callable[[], Optional[ui.element]] = lambda: None,
        revalidate: Optional[Callable[[], list]] = None,
    ) -> None:
        self.transcript = transcript
        self.captions = captions
        self.return_focus = return_focus
        self.revalidate = revalidate
        # Every issue Validate found, and the ones of the kinds shown. The
        # hidden kinds are kept across Validate runs, so a reader working
        # through one kind at a time can re-run it after each fix.
        self.all_items: list = []
        self.items: list = []
        self.hidden: set[str] = set()
        self.checkboxes: dict = {}
        self.position = 0
        self.checked = 0
        # "Skip to validation issue", set by the page: a skip link at the top
        # of the transcript that lands on this panel's open card. Shown only
        # while there is a card to land on (update_skip_link).
        self.skip_link: Optional[ui.element] = None

        # Design B of the six drawn for it: a stripe down the left and a
        # tinted header, both in the colour of the issue shown (amber for a
        # warning, red for an error, green for none), with Previous, the
        # position and Next as a compact group in that header -- and the
        # issue itself below, its kind in small capitals over the rule it
        # breaks. The colour only repeats what the words say.
        # The panel and, below it, the filter checkboxes appear and go together.
        with ui.element("div").classes("validation-panel-wrap w-full") as self.container:
            with ui.element("section").classes("validation-panel w-full").props(
                'aria-labelledby="validation-panel-heading"'
            ) as self.panel:
                with ui.element("div").classes("validation-panel-head"):
                    self.heading = (
                        ui.label("")
                        .classes("validation-panel-heading")
                        .props('id=validation-panel-heading tabindex=-1')
                    )

                    with ui.element("div").classes("validation-panel-nav") as self.foot:
                        self.previous = ui.button(
                            icon="chevron_left", on_click=self.go_previous, color=None
                        ).props('flat aria-label="Previous issue"').classes(
                            "validation-panel-step"
                        )
                        self.position_label = ui.label("").classes(
                            "validation-panel-position"
                        )
                        self.next = ui.button(
                            icon="chevron_right", on_click=self.go_next, color=None
                        ).props('flat aria-label="Next issue"').classes(
                            "validation-panel-step"
                        )

                    ui.button(icon="close", on_click=self.close).props(
                        'flat aria-label="Close validation panel"'
                    ).classes("editor-btn editor-icon validation-panel-close").tooltip(
                        "Close"
                    )

                # What is shown -- kind, rule, caption -- is one live region, so
                # a screen reader hears the new issue as Next moves to it, while
                # focus stays on Next. The position is said inside it too, since
                # the visible "2 of 5" sits up in the header beside the arrows.
                with ui.element("div").classes("validation-panel-body").props(
                    "role=status aria-live=polite aria-atomic=true"
                ):
                    self.spoken_position = ui.label("").classes("sr-only")

                    # What "Check again" found -- said once, cleared by the
                    # next step so it never outlives the issue it was about.
                    self.note = ui.label("").classes("validation-panel-note")

                    with ui.element("div").classes("validation-panel-issue") as self.issue:
                        with ui.element("div").classes("validation-panel-kind"):
                            self.icon = ui.icon("warning").props("aria-hidden=true")
                            self.kind = ui.label("")
                        self.title = ui.label("").classes("validation-panel-title")
                        with ui.element("div").classes("validation-panel-detail"):
                            self.caption_button = (
                                ui.button("", on_click=self.go_to_caption, color=None)
                                .props("flat dense no-caps")
                                .classes("validation-panel-caption")
                            )
                            self.separator = ui.label("·").props("aria-hidden=true")
                            self.detail = ui.label("")

                        # After a fix: check again without leaving the issue.
                        self.recheck = (
                            ui.button(
                                "Check again", icon="refresh", on_click=self.check_again
                            )
                            .props("flat dense no-caps")
                            .classes(
                                "editor-btn editor-toolbar-btn editor-outlined "
                                "validation-panel-recheck"
                            )
                        )
                        self.recheck.set_visibility(revalidate is not None)

                    self.gone = ui.label(
                        "This caption has changed since Validate ran. "
                        "Run Validate again for current results."
                    ).classes("validation-panel-gone")

                    self.all_clear = ui.label("").classes("validation-panel-clear")

            # Which kinds of issue to step through: one toggle per kind
            # found, with its count, below the panel rather than inside it --
            # a setting for the whole review, not part of any one issue.
            # Only there when there is a choice, or a hidden kind to bring back.
            self.filters = (
                ui.element("div")
                .classes("validation-panel-filters")
                .props('role=group aria-label="Show these kinds of issue"')
            )

        self.container.set_visibility(False)

    # -- Opening and closing ---------------------------------------------

    def show(self, items: list, checked: int) -> None:
        """
        Open the panel on the first of `items` (from validation_items()), or
        say there are none. Called by every Validate, so running it again
        reopens and refreshes the panel. Focus moves into the panel -- to
        Next when there is somewhere to go, otherwise to the heading -- so a
        keyboard user is where the results are.
        """

        self.all_items = items
        self.items = shown_items(items, self.hidden)
        self.position = 0
        self.checked = checked
        self.container.set_visibility(True)
        self.draw_filters()
        self.draw()

        if len(self.items) > 1:
            self.focus(self.next)
        else:
            self.focus(self.heading)

    def close(self) -> None:
        """
        Put the panel away. The captions keep their validation markings;
        only the "under review" marking goes. Focus returns to Validate.
        """

        self.container.set_visibility(False)
        self.update_skip_link()
        self.transcript.review(None)

        target = self.return_focus()
        if target is not None:
            self.focus(target)

    # -- Skip link ----------------------------------------------------------

    def update_skip_link(self) -> None:
        """
        Show "Skip to validation issue" only while the panel is open on an
        issue: a skip link to a card that is not there leads nowhere, so it
        goes with the card (hidden, which also takes it out of the tab order).
        """

        if self.skip_link is None:
            return

        self.skip_link.set_visibility(
            self.container.visible and self.current() is not None
        )

    def focus_issue(self) -> None:
        """
        What the skip link lands on: "Check again" on the open card -- where a
        reader who has just fixed something goes next -- or, without it, the
        button that goes to the caption, or the heading.
        """

        if self.issue.visible and self.recheck.visible:
            self.focus(self.recheck)
        elif self.issue.visible:
            self.focus(self.caption_button)
        else:
            self.focus(self.heading)

    # -- Filtering ----------------------------------------------------------

    def toggle(self, rule: str) -> None:
        """
        Show or hide one kind of issue. The issue on screen stays on screen
        if its kind is still shown; otherwise the first shown one is.
        Focus stays on the checkbox: it is never rebuilt by this.
        """

        current = self.current()

        if rule in self.hidden:
            self.hidden.discard(rule)
        else:
            self.hidden.add(rule)

        self.items = shown_items(self.all_items, self.hidden)
        self.position = next(
            (n for n, item in enumerate(self.items) if item is current), 0
        )

        self.draw()

    def set_shown(self, rule: str, shown: bool) -> None:
        """
        A checkbox changed. Only acts when it disagrees with what is shown,
        so a value set from here can never toggle twice.
        """

        if shown == (rule not in self.hidden):
            return

        self.toggle(rule)

    def draw_filters(self) -> None:
        """
        One checkbox per kind found this time, drawn afresh on each
        Validate: "Overlaps (2)", ticked while that kind is shown.
        """

        counts = rule_counts(self.all_items)

        self.filters.clear()
        self.checkboxes = {}
        self.filters.set_visibility(filters_wanted(counts, self.hidden))

        with self.filters:
            for rule, count in counts:
                self.checkboxes[rule] = ui.checkbox(
                    f"{RULE_LABELS[rule]} ({count})",
                    value=rule not in self.hidden,
                    on_change=lambda e, r=rule: self.set_shown(r, e.value),
                ).props("dense").classes("validation-panel-check")

    # -- Checking again ---------------------------------------------------

    def check_again(self) -> None:
        """
        After a fix: validate again and land where it makes sense -- on the
        caption's first remaining issue if it still has one, otherwise on
        the next issue after it -- and say which it was. The filters, and
        focus on this button, stay.
        """

        item = self.current()
        if self.revalidate is None or item is None:
            return

        index = item["caption"].index

        self.all_items = self.revalidate()
        self.items = shown_items(self.all_items, self.hidden)
        self.draw_filters()

        remaining = [i for i in self.items if i["caption"].index == index]

        if remaining:
            self.position = self.items.index(remaining[0])
            count = len(remaining)
            note = (
                f"Caption {index} still has {count} "
                + ("issue." if count == 1 else "issues.")
            )
        else:
            self.position = next(
                (n for n, i in enumerate(self.items) if i["caption"].index > index),
                max(len(self.items) - 1, 0),
            )
            note = f"Caption {index} passes now."

        self.draw()
        self.note.set_text(note)
        self.note.set_visibility(True)

        # The button goes with the last issue; focus goes to the heading.
        if not self.items:
            self.focus(self.heading)

    # -- Stepping -----------------------------------------------------------

    def go_next(self) -> None:
        if self.position < len(self.items) - 1:
            self.position += 1
            self.draw()
        # At the end Next is disabled; keep focus on something that can
        # still take it.
        if self.position == len(self.items) - 1:
            self.focus(self.previous)

    def go_previous(self) -> None:
        if self.position > 0:
            self.position -= 1
            self.draw()
        if self.position == 0:
            self.focus(self.next)

    def go_to_caption(self) -> None:
        """
        From the issue to the text: the caret goes into the caption, where
        the problem is.
        """

        item = self.current()
        if item is None or not self.exists(item):
            return

        caption = item["caption"]
        offset = min(item.get("offset", 0), len(caption.text))
        self.transcript.focus(caption.index, offset)

    # -- Drawing ------------------------------------------------------------

    def current(self) -> Optional[dict]:
        if 0 <= self.position < len(self.items):
            return self.items[self.position]
        return None

    def exists(self, item: dict) -> bool:
        """
        Whether the caption an issue names is still in the list -- a merge,
        a delete or an undo since Validate replaces caption objects.
        """

        return any(caption is item["caption"] for caption in self.captions())

    def draw(self) -> None:
        total = len(self.items)
        item = self.current()

        self.note.set_visibility(False)
        self.heading.set_text(heading_text(len(self.all_items)))
        self.issue.set_visibility(item is not None)
        self.foot.set_visibility(total > 0)
        self.all_clear.set_visibility(total == 0)
        self.gone.set_visibility(False)

        if item is None:
            if self.all_items:
                # Issues exist; the reader has hidden every kind of them.
                self.panel.classes(replace="validation-panel w-full is-muted")
                self.all_clear.set_text(
                    "Every kind of issue is hidden. Choose one below to see it."
                )
            else:
                self.panel.classes(replace="validation-panel w-full is-clear")
                noun = "caption" if self.checked == 1 else "captions"
                self.all_clear.set_text(
                    f"All {self.checked} {noun} follow the subtitle guidelines."
                )
            self.spoken_position.set_text("")
            self.transcript.review(None)
            self.update_skip_link()
            return

        caption = item["caption"]
        severity = "is-error" if item["error"] else "is-warning"

        # The stripe and the header's tint follow the issue shown.
        self.panel.classes(replace=f"validation-panel w-full {severity}")
        self.position_label.set_text(position_text(self.position, total))
        self.spoken_position.set_text(
            f"Issue {position_text(self.position, total)}."
        )
        self.kind.set_text("Error" if item["error"] else "Warning")
        self.title.set_text(item["title"])
        self.icon.name = "error" if item["error"] else "warning"
        self.caption_button.set_text(f"Caption {caption.index}")
        self.caption_button.props(
            f'aria-label="Go to caption {caption.index}"'
        )
        self.detail.set_text(item["detail"])

        self.previous.set_enabled(self.position > 0)
        self.next.set_enabled(self.position < total - 1)

        if self.exists(item):
            self.caption_button.set_enabled(True)
            self.transcript.review(caption.index)
        else:
            self.caption_button.set_enabled(False)
            self.gone.set_visibility(True)
            self.transcript.review(None)

        self.update_skip_link()

    @staticmethod
    def focus(element: ui.element) -> None:
        ui.run_javascript(
            f"const t = getElement({element.id});"
            "const el = t && (t.$el || t);"
            "if (el && el.focus) el.focus();"
        )

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
The comments panel: where a comment is written, read and changed.

A card under the video, built like the validation panel's and drawn like it --
a stripe down the left and a tinted header, with Previous, the position and
Next in the header -- in the colour of the underline on the commented words.
It shows one comment at a time and follows the caret: put the caret in
commented words, or click them, and the panel shows that comment.

It is shut until it is needed: it opens when a comment is written or opened
(Ctrl+Shift+K, the Comment button), when commented words are clicked, and when
a file with comments is opened. What is typed in it is kept when the reader
moves on -- to another comment, to the text, or shutting the panel -- and
abandoned only by Escape or Cancel.
"""

from typing import Optional, Tuple

from nicegui import ui

from utils.caption import SRTCaption, WordComment
from utils.card_fold import CardFold
from utils.srt_comments import COMMENT_MAX_LENGTH
from utils.transcript_editor import format_time_label

# The words a comment is on, as shown in the panel and read out.
QUOTE_LENGTH = 80


def quote_of(text: str) -> str:
    """
    The words a comment is on, flattened to one line and shortened.
    """

    flat = " ".join(text.split())

    return flat if len(flat) <= QUOTE_LENGTH else flat[: QUOTE_LENGTH - 1] + "…"


def position_text(position: int, total: int) -> str:
    return f"{position + 1} of {total}"


def heading_text(pending: bool, position: int, total: int) -> str:
    if pending:
        return "New comment"

    return f"Comment {position_text(position, total)}"


def where_text(caption: SRTCaption) -> str:
    """
    Where a comment is, in what the reader can see beside the text: who is
    speaking and when (the caption's number is not shown in a transcription).
    """

    when = format_time_label(caption.get_start_seconds())

    return f"{caption.speaker} · {when}" if caption.speaker else when


class CommentsPanel:
    """
    Built once, hidden, under the video.

    Parameters:
        transcript: the TranscriptEditor, to redraw after a change and to put
            the selection back on the words.
    """

    def __init__(self, transcript) -> None:
        self.transcript = transcript

        # The comment on screen: (caption, comment). While a new comment is
        # being written it is the last one that was on screen, and `pending`
        # -- (caption, start, end) -- is what the card is about instead.
        self.current: Optional[Tuple[SRTCaption, WordComment]] = None
        self.pending: Optional[Tuple[SRTCaption, int, int]] = None

        with ui.element("div").classes("validation-panel-wrap w-full") as self.container:
            with ui.element("section").classes(
                "validation-panel is-comment w-full"
            ).props('aria-labelledby="comments-panel-heading"') as self.panel:
                with ui.element("div").classes("validation-panel-head"):
                    self.fold = CardFold(
                        self.container, "Comments", "comments-panel-body"
                    )
                    self.heading = self.fold.heading(
                        ui.label("")
                        .classes("validation-panel-heading")
                        .props("id=comments-panel-heading tabindex=-1")
                    )

                    with ui.element("div").classes("validation-panel-nav"):
                        self.previous = ui.button(
                            icon="chevron_left", on_click=self.go_previous, color=None
                        ).props('flat aria-label="Previous comment"').classes(
                            "validation-panel-step"
                        )
                        self.position_label = ui.label("").classes(
                            "validation-panel-position"
                        )
                        self.next = ui.button(
                            icon="chevron_right", on_click=self.go_next, color=None
                        ).props('flat aria-label="Next comment"').classes(
                            "validation-panel-step"
                        )

                    ui.button(icon="close", on_click=self.close).props(
                        'flat aria-label="Close comments panel"'
                    ).classes("editor-btn editor-icon validation-panel-close").tooltip(
                        "Close"
                    )

                # Said as the panel moves between comments, while focus stays
                # where it is.
                self.spoken = ui.label("").classes("sr-only").props(
                    "role=status aria-live=polite aria-atomic=true"
                )

                with ui.element("div").classes("validation-panel-body").props(
                    "id=comments-panel-body"
                ):
                    with ui.element("div").classes("validation-panel-issue"):
                        with ui.element("div").classes("validation-panel-kind"):
                            ui.icon("comment").props("aria-hidden=true")
                            ui.label("Comment")

                        with ui.element("div").classes("validation-panel-detail"):
                            self.words_button = (
                                ui.button("", on_click=self.go_to_words, color=None)
                                .props("flat dense no-caps")
                                .classes("validation-panel-caption comments-panel-words")
                            )
                            self.separator = ui.label("·").props("aria-hidden=true")
                            self.detail = ui.label("")

                        self.text = (
                            ui.textarea(label="Comment")
                            .props(f"outlined autogrow maxlength={COMMENT_MAX_LENGTH}")
                            .classes("w-full comments-panel-text")
                        )
                        # Every key typed here stays here: the page has
                        # shortcuts of its own (undo, save, play) that would
                        # otherwise act on the transcript while a sentence is
                        # being written. Escape abandons and Ctrl/Cmd+Enter
                        # saves.
                        self.text.on(
                            "keydown", js_handler="(event) => event.stopPropagation()"
                        )
                        self.text.on("keydown.escape", self.cancel)
                        self.text.on("keydown.ctrl.enter", self.save)
                        self.text.on("keydown.meta.enter", self.save)
                        self.text.on_value_change(self.value_changed)

                        with ui.element("div").classes("comments-panel-actions"):
                            self.remove_button = (
                                ui.button("Remove", on_click=self.remove)
                                .props("flat dense no-caps")
                                .classes("comments-panel-remove")
                            )
                            self.cancel_button = ui.button(
                                "Cancel", on_click=self.cancel
                            ).props("flat dense no-caps")
                            self.save_button = ui.button(
                                "Save", on_click=self.save
                            ).props("dense no-caps")

        self.hide()

    # -- What there is ------------------------------------------------------

    @property
    def editor(self):
        return self.transcript.editor

    def entries(self) -> list:
        """
        Every comment in the transcription, in the order of the text.
        """

        return [
            (caption, comment)
            for caption in self.editor.captions
            for comment in caption.comments
        ]

    def position(self) -> int:
        """
        Where the comment on screen is among all of them, or -1.
        """

        if self.current is None:
            return -1

        for at, (caption, comment) in enumerate(self.entries()):
            if comment is self.current[1]:
                return at

        return -1

    def span_of(self, caption: SRTCaption, comment: WordComment) -> Optional[tuple]:
        """
        The character range of the words a comment is on.
        """

        return self.editor.word_range(caption.text, min(comment.words), max(comment.words))

    def shown_range(self) -> Optional[tuple]:
        """
        (caption, start, end) of what the card is about: the words of the
        comment on screen, or of the one being written.
        """

        if self.pending is not None:
            return self.pending

        if self.current is not None:
            span = self.span_of(*self.current)

            if span is not None:
                return self.current[0], span[0], span[1]

        return None

    # -- What was typed -------------------------------------------------------

    def draft(self) -> str:
        return self.editor.clean_comment(self.text.value)

    def dirty(self) -> bool:
        """
        Whether there is something typed that is not yet the comment.
        """

        if not self.draft():
            return False

        if self.pending is not None:
            return True

        return self.current is not None and self.draft() != self.current[1].text

    def save_draft(self) -> Optional[tuple]:
        """
        Keep what is typed as the comment on the words it is about, redraw
        the text, and say where: (caption, start, end), or None when nothing
        was kept (nothing typed, the same as there, refused).
        """

        shown = self.shown_range()

        if shown is None or not self.draft():
            return None

        caption, start, end = shown

        if not self.editor.set_comment(caption, start, end, self.draft()):
            return None

        self.transcript.refresh()
        self.transcript.changed()

        return shown

    def commit(self) -> bool:
        """
        Keep what is typed, if there is anything: the reader is moving on, and
        nothing they wrote is thrown away by it.
        """

        if not self.dirty():
            return False

        return self.save_draft() is not None

    def value_changed(self) -> None:
        self.save_button.set_enabled(bool(self.draft()))

    def hide(self) -> None:
        """
        Put the card away, and take its marking off the text.
        """

        self.container.set_visibility(False)
        self.fold.unfold()
        self.transcript.mark_comment(None)

    def mark(self) -> None:
        """
        Mark in the text what the card is about: the caption, and for a
        comment already written, its words.
        """

        if not self.container.visible:
            self.transcript.mark_comment(None)
        elif self.pending is not None:
            self.transcript.mark_comment(self.pending[0].index)
        elif self.current is not None:
            caption, comment = self.current
            at = next(
                (i for i, held in enumerate(caption.comments) if held is comment),
                -1,
            )
            self.transcript.mark_comment(caption.index, at)
        else:
            self.transcript.mark_comment(None)

    # -- Showing ----------------------------------------------------------------

    def show(
        self,
        caption: SRTCaption,
        comment: Optional[WordComment] = None,
        words: Optional[tuple] = None,
        focus: bool = False,
        scroll: bool = True,
    ) -> None:
        """
        Put a comment on the card -- an existing one, or a new one to be
        written on `words` (start, end) -- and open the panel.
        """

        if comment is not None:
            self.current = (caption, comment)
            self.pending = None
            self.text.set_value(comment.text)
        else:
            self.pending = (caption, words[0], words[1])
            self.text.set_value("")

        self.container.set_visibility(True)

        # Asked for with the key or the button -- the reader wants to write --
        # so the card opens whole. Following the caret from one comment to
        # the next leaves it as the reader left it.
        if focus:
            self.fold.unfold()

        self.draw(scroll=scroll)

        if focus:
            self.focus_text()

    def open_for(self, caption: SRTCaption, start: int, end: int) -> bool:
        """
        The key or the button: write a comment on the words around a
        selection, or open the one they already have. False when the
        selection takes no word.
        """

        target = self.editor.comment_target(caption, start, end)

        if target is None:
            return False

        self.reveal()
        self.commit()

        if target["index"] is not None:
            self.show(caption, caption.comments[target["index"]], focus=True)
        else:
            self.show(caption, words=(target["start"], target["end"]), focus=True)

        return True

    def reveal(self) -> None:
        """
        The key or the button, while comments are hidden: turn them on again,
        and say so. The comment on these words, or the one about to be
        written, opens as it always does; nothing is taken away, and what is
        hidden is not touched.

        The notice is a toast, which is announced as it appears (Quasar gives
        it role=alert) and stays until closed, like the others.
        """

        if self.editor.show_comments:
            return

        self.editor.set_show_comments(True)

        ui.notify(
            "Comments were hidden and are shown again.",
            type="info",
            timeout=None,
            close_button="Close",
        )

        if self.editor.on_comments_shown is not None:
            self.editor.on_comments_shown()

    def put_away(self) -> None:
        """
        The comments have been hidden: keep what was typed, as when the panel
        is shut, and shut it without moving focus off the switch.
        """

        self.commit()
        self.pending = None
        self.current = None
        self.hide()

    def open_first(self) -> None:
        """
        A file with comments has just been opened: show the first, without
        taking focus or moving the text. Not while they are hidden.
        """

        if not self.editor.show_comments:
            return

        entries = self.entries()

        if entries:
            caption, comment = entries[0]
            self.show(caption, comment, scroll=False)

    def follow(self, caption: SRTCaption, comment: WordComment, click: bool) -> None:
        """
        The caret is in a comment's words: show that comment.

        An open panel follows the caret; a shut one opens only for a click,
        so an arrow key that happens to cross commented words does not throw
        a card up under someone typing. A comment already on screen is left
        alone.
        """

        if not self.editor.show_comments:
            return

        if not (self.container.visible or click):
            return

        if (
            self.container.visible
            and self.pending is None
            and self.current is not None
            and self.current[1] is comment
        ):
            return

        self.commit()
        self.show(caption, comment, scroll=False)

    def draw(self, scroll: bool = True) -> None:
        """
        Redraw the card on what it is about.
        """

        shown = self.shown_range()
        entries = self.entries()
        total = len(entries)
        at = self.position()
        pending = self.pending is not None

        self.heading.set_text(heading_text(pending, max(at, 0), total))
        self.position_label.set_text("" if pending else position_text(at, total))
        self.spoken.set_text(
            "New comment." if pending else f"Comment {position_text(at, total)}."
        )

        self.previous.set_enabled(not pending and at > 0)
        self.next.set_enabled(not pending and 0 <= at < total - 1)

        if shown is not None:
            caption, start, end = shown
            self.words_button.set_text(f"“{quote_of(caption.text[start:end])}”")
            spoken = quote_of(caption.text[start:end]).replace('"', "'")
            self.words_button.props(f'aria-label="Go to the words: {spoken}"')
            self.detail.set_text(where_text(caption))

            if scroll and self.transcript.body is not None:
                self.transcript.body.scroll_to_block(caption.index)

        self.remove_button.set_visibility(not pending)
        self.cancel_button.set_visibility(True)
        self.save_button.set_enabled(bool(self.draft()))
        self.mark()

    # -- Acting -------------------------------------------------------------------

    def select_words(self, caption: SRTCaption, start: int, end: int) -> None:
        """
        Put the selection, and with it focus, back on the words.
        """

        if self.transcript.body is not None:
            self.transcript.body.select_range(caption.index, start, caption.index, end)

    def save(self) -> None:
        """
        Save and go back to the text, on the words.
        """

        shown = self.save_draft()

        if shown is None:
            return

        caption, start, end = shown
        touched = self.editor.words_in_selection(caption.text, start, end)
        at = self.editor.comment_index_at(caption, touched[0]) if touched else None

        if at is None:
            return

        self.pending = None
        self.current = (caption, caption.comments[at])
        self.draw(scroll=False)
        self.select_words(caption, start, end)

    def remove(self) -> None:
        """
        Take the comment off its words and carry on with the next one.
        """

        shown = self.shown_range()

        if self.pending is not None or shown is None:
            return

        caption, start, end = shown
        before = self.position()

        if not self.editor.remove_comment(caption, start, end):
            return

        self.transcript.refresh()
        self.transcript.changed()

        entries = self.entries()
        self.current = None

        if entries:
            caption_next, comment_next = entries[min(max(before, 0), len(entries) - 1)]
            self.show(caption_next, comment_next, scroll=False)
        else:
            self.hide()

        self.select_words(caption, start, end)

    def cancel(self) -> None:
        """
        Abandon what is typed -- the comment goes back to what it was, a new
        one is not made -- and go back to the text, on the words.
        """

        shown = self.shown_range()

        if self.pending is not None:
            self.pending = None

            if self.position() >= 0:
                self.show(*self.current, scroll=False)
            else:
                self.current = None
                self.hide()
        elif self.current is not None:
            self.text.set_value(self.current[1].text)

        if shown is not None:
            self.select_words(*shown)

    def close(self) -> None:
        """
        Put the panel away, keeping what was typed, and go back to the text.
        """

        shown = self.shown_range()
        self.commit()
        self.pending = None
        self.hide()

        if shown is not None:
            self.select_words(*shown)
        else:
            self.transcript.focus_caret()

    def go_next(self) -> None:
        self.step(1)

    def go_previous(self) -> None:
        self.step(-1)

    def step(self, direction: int) -> None:
        if self.pending is not None:
            return

        self.commit()

        entries = self.entries()
        at = self.position() + direction

        if not 0 <= at < len(entries):
            return

        caption, comment = entries[at]
        self.show(caption, comment, scroll=True)

        # At either end the button just used is disabled; keep focus on
        # something that can still take it.
        if at == 0:
            self.focus(self.next)
        elif at == len(entries) - 1:
            self.focus(self.previous)

    def go_to_words(self) -> None:
        """
        From the card to the text: the words are selected, and the text
        scrolled to them.
        """

        shown = self.shown_range()

        if shown is None:
            return

        if self.transcript.body is not None:
            self.transcript.body.scroll_to_block(shown[0].index)

        self.select_words(*shown)

    # -- Keeping up with the text ------------------------------------------------------

    def sync(self) -> None:
        """
        The text has been redrawn: an undo, a merge, a delete, an edit or a
        renamed speaker may have replaced the comment on screen, moved it, or
        taken it away. Find it again, or shut the panel.

        The card is drawn again either way, so that what it says about where
        the comment is (who is speaking, and when) stays what the text shows.
        What is typed in its text box is not touched, so a comment being
        written is not lost to a change somewhere else.
        """

        if not self.container.visible:
            return

        if self.pending is not None:
            if any(caption is self.pending[0] for caption in self.editor.captions):
                self.draw(scroll=False)
                return

            self.pending = None
            self.hide()
            return

        if self.current is None:
            return

        caption, comment = self.current

        if any(comment is held for held in caption.comments) and any(
            caption is held for held in self.editor.captions
        ):
            self.draw(scroll=False)
            return

        found = self.find_again(caption, comment)

        if found is None:
            self.current = None
            self.hide()
            return

        unsaved = self.dirty()
        self.current = found

        if not unsaved:
            self.text.set_value(found[1].text)

        self.draw(scroll=False)

    def find_again(
        self, caption: SRTCaption, comment: WordComment
    ) -> Optional[tuple]:
        """
        The comment on the card, now that the objects holding it have been
        replaced: (caption, comment), or None when it is gone.

        An undo puts back a copy with the same words. An edit of the text
        builds new comments whose words have moved with it (a word typed into
        the middle of the commented words is one more of them, a word deleted
        from them one less), so there the same words are not to be had, and
        the comment is the one in the caption that has the same text and
        shares the most words with the old one. A caption of the same number
        is the same caption.
        """

        for candidate in self.editor.captions:
            if candidate.index != caption.index:
                continue

            for held in candidate.comments:
                if held.words == comment.words:
                    return candidate, held

            alike = [held for held in candidate.comments if held.text == comment.text]

            if not alike:
                continue

            best = max(
                alike,
                key=lambda held: (
                    len(set(held.words) & set(comment.words)),
                    -abs(min(held.words) - min(comment.words)),
                ),
            )

            return candidate, best

        return None

    @staticmethod
    def focus(element: ui.element) -> None:
        ui.run_javascript(
            f"const t = getElement({element.id});"
            "const el = t && (t.$el || t);"
            "if (el && el.focus) el.focus();"
        )

    def focus_text(self) -> None:
        """
        Into the text area, so what is typed next is the comment.
        """

        self.text.run_method("focus")

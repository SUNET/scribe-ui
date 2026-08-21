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
Marking the reader's own words, and the other half of the same idea: a word
that has been edited is no longer a word the model was unsure of, so its review
flag goes with it.
"""

import json
import pathlib
import re
import sys

import pytest

from utils.caption import SRTCaption
from utils.srt import SRTEditor

TEXT = "Hej på dig idag"

# "på" is the only word the model was unsure of.
PAYLOAD = {
    "version": 1,
    "words": [
        {"t": "Hej", "s": 0.0, "e": 1.0, "c": 0.99},
        {"t": "på", "s": 1.0, "e": 2.0, "c": 0.15},
        {"t": "dig", "s": 2.0, "e": 3.0, "c": 0.99},
        {"t": "idag", "s": 3.0, "e": 4.0, "c": 0.99},
    ],
}


def caption(text: str = TEXT, edited=()) -> SRTCaption:
    """
    A caption, optionally already carrying a record of which of its words the
    reader changed -- word positions counted from its start.
    """

    built = SRTCaption(1, "00:00:00,000", "00:00:04,000", text)
    built.edited_words = set(edited)

    return built


@pytest.fixture
def editor():
    editor = SRTEditor("job-uuid", "txt", "file.txt")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *a, **k: None)

    editor.load_words(PAYLOAD)
    editor.captions = [caption()]

    return editor


def marked(editor, text=TEXT, edited=()):
    """
    Every marked word, paired with the marking it carries.
    """

    html = editor.get_review_html(caption(text, edited), text) or ""

    return re.findall(r'<span class="([\w-]+)"[^>]*>([^<]*)</span>', html)


class TestEditingClearsTheFlag:
    """
    The reported bug: correcting a flagged word must take the flag with it.
    """

    def test_the_flag_goes_with_the_word(self, editor):
        editor.show_uncertain_words = True

        assert marked(editor, TEXT) == [("review-word", "på")]
        assert marked(editor, "Hej två dig idag") == []

    def test_the_replacement_is_marked_as_an_edit_instead(self, editor):
        editor.show_uncertain_words = True
        editor.show_my_edits = True

        assert marked(editor, "Hej två dig idag", edited=[1]) == [
            ("edit-word", "två")
        ]

    def test_the_flag_wins_if_a_word_is_somehow_both(self, editor):
        """
        No longer exclusive by construction: one comes from the model's score,
        the other from the reader. A word worth a second look is the more
        useful thing to say.
        """

        editor.show_uncertain_words = True
        editor.show_my_edits = True

        assert marked(editor, TEXT, edited=[1]) == [("review-word", "på")]

    def test_the_flagged_count_drops(self, editor):
        editor.show_uncertain_words = True

        assert editor.flagged_word_count() == 1

        editor.captions = [caption("Hej två dig idag")]

        assert editor.flagged_word_count() == 0


class TestTogglesAreIndependent:
    def test_neither_marks_nothing(self, editor):
        assert marked(editor, "Hej två dig idag") == []

    def test_both_off_returns_no_markup_at_all(self, editor):
        """
        The read view used to test the toggle before calling in; it now leaves
        that to get_review_html. This is what makes those two the same thing.
        """

        assert editor.get_review_html(caption()) is None
        assert editor.get_review_html(caption("Hej två dig idag")) is None

    def test_edits_alone_does_not_flag_uncertain_words(self, editor):
        editor.show_my_edits = True

        assert marked(editor, TEXT) == []

    def test_review_alone_does_not_mark_edits(self, editor):
        editor.show_uncertain_words = True

        assert marked(editor, "Hej två dig idag") == []

    def test_both_mark_their_own(self, editor):
        editor.show_uncertain_words = True
        editor.show_my_edits = True

        # "på" is the uncertain word; the third is one the reader changed.
        assert marked(editor, "Hej på XXX idag", edited=[2]) == [
            ("review-word", "på"),
            ("edit-word", "XXX"),
        ]


class TestMarkup:
    def test_the_edit_marking_carries_its_message(self, editor):
        editor.show_my_edits = True

        html = editor.get_review_html(caption("Hej två dig idag", edited=[1]))

        assert 'data-edit="You changed this word"' in html
        assert 'aria-label="You changed this word"' in html
        # Never the browser's own tooltip, which no stylesheet can reach.
        assert "title=" not in html

    def test_edited_text_is_escaped(self, editor):
        editor.show_my_edits = True

        html = editor.get_review_html(
            caption("Hej <b>två</b> dig idag", edited=[1])
        )

        assert "<b>" not in html
        assert "&lt;b&gt;" in html

    def test_the_backdrop_shows_edits(self, editor):
        """
        The layer behind an open text area, which is what makes the marking
        visible while a caption is being typed into.
        """

        editor.show_my_edits = True
        html = editor.review_backdrop_html(
            caption(edited=[1]), "Hej två dig idag"
        )

        assert 'class="edit-word"' in html

    def test_the_backdrop_still_mirrors_the_text_with_nothing_marked(self, editor):
        editor.show_my_edits = True

        assert editor.review_backdrop_html(caption(), TEXT) != ""


class TestRuns:
    """
    What the transcription editor renders from.
    """

    def joined(self, runs):
        return "".join(run["t"] for run in runs)

    def test_an_edited_word_is_its_own_run(self, editor):
        editor.show_my_edits = True
        target = caption("Hej två dig idag", edited=[1])
        runs = editor.review_runs(target, target.text)

        assert [run for run in runs if run.get("edit")] == [
            {"t": "två", "flag": False, "edit": True}
        ]

    def test_no_edit_key_when_the_toggle_is_off(self, editor):
        runs = editor.review_runs(caption("Hej två dig idag"), "Hej två dig idag")

        assert all("edit" not in run for run in runs)

    def test_no_edit_key_on_untouched_words(self, editor):
        editor.show_my_edits = True
        runs = editor.review_runs(caption(), TEXT)

        assert all("edit" not in run for run in runs)

    def test_the_text_survives_intact(self, editor):
        editor.show_my_edits = True
        text = "Hej två dig  idag"

        assert self.joined(editor.review_runs(caption(text), text)) == text

    def test_an_edited_word_carries_no_timing(self, editor):
        """
        The timing belonged to the word that was replaced, so following the
        audio must not claim the new one is being spoken.
        """

        editor.show_my_edits = True
        target = caption("Hej två dig idag", edited=[1])
        runs = editor.review_runs(target, target.text, per_word=True)
        edited = [run for run in runs if run.get("edit")]

        assert edited and all("s" not in run for run in edited)


class TestPersistence:
    def test_restore_applies_the_preference(self, editor):
        editor.restore_review_state(False, "low", True)

        assert editor.show_my_edits is True

    def test_restore_defaults_to_off(self, editor):
        """
        Called with two arguments by anything written before this existed.
        """

        editor.restore_review_state(True, "low")

        assert editor.show_my_edits is False

    def test_restore_does_not_refresh(self, editor):
        def explode(*args, **kwargs):
            raise AssertionError("restore must not refresh the display")

        editor.refresh_display = explode
        editor.restore_review_state(True, "low", True)

    def test_the_setter_refreshes(self, editor):
        refreshed = []
        editor.refresh_display = lambda *a, **k: refreshed.append(k)

        editor.set_show_my_edits(True)

        assert editor.show_my_edits is True
        assert refreshed and refreshed[0].get("force_full_refresh") is True


class TestClientContract:
    """
    The mark has to come off the moment a flagged word is typed into. The
    server reaches the same answer, but cannot re-render the block the caret is
    in without moving it, so the browser does this half.
    """

    def source(self) -> str:
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_the_props_the_python_side_sends_are_declared(self):
        """
        A prop the component never declared is silently ignored, so a typo on
        either side shows up as a feature that quietly does nothing.
        """

        declared = set(re.findall(r"^ {4}(\w+): \{ type:", self.source(), re.M))
        sent = set(
            re.findall(
                r'self\._props\["(\w+)"\]',
                pathlib.Path("utils/transcript_editor.py").read_text(),
            )
        )

        assert {"editLabel", "showEdits"} <= declared
        assert sent <= declared, f"not declared in the component: {sent - declared}"

    def mark_changed(self) -> str:
        body = self.source()
        body = body[body.index("markChanged(span) {"):]

        return body[: body.index("\n    },")]

    def test_a_changed_word_is_marked_for_the_stylesheet(self):
        """
        An attribute, not a class: Vue owns the class and rewrites it on the
        next patch, and an attribute can be taken back off again if the reader
        undoes the change.
        """

        body = self.mark_changed()

        assert 'setAttribute("data-changed", "")' in body
        assert "classList" not in body

    def test_a_span_of_pure_whitespace_is_never_marked(self):
        """
        wordAt and effectiveSpan both work at the DOM's own element
        boundaries, not word boundaries -- a caret landing in the gap
        between two words, in a separator's own span, is exactly as valid a
        position as one inside either word either side of it. Marking it
        would draw a floating highlight over a plain space, nothing there
        for the reader to actually look at.
        """

        body = self.mark_changed()

        assert r"/^\s*$/.test(span.textContent)" in body

    def test_nothing_is_compared(self):
        """
        An edit is something that happened, not something to be worked out from
        how the text differs from what the model transcribed -- which is the
        deduction that marked words nobody had touched.
        """

        source = self.source()

        assert "matchKey" not in source
        assert "dataset.w" not in source
        assert "data-w" not in source

    def test_a_changed_word_is_never_followed_as_spoken(self):
        source = self.source()
        body = source[source.index("markCurrentWord() {"):]
        body = body[: body.index("\n    },")]

        assert 'hasAttribute("data-changed")' in body

    def test_it_runs_on_input(self):
        source = self.source()
        body = source[source.index("onInput()"):]
        body = body[: body.index("\n    },")]

        assert "this.markChanged(span)" in body

    def test_switching_words_flushes_the_previous_edit(self):
        """
        Two words edited one after another must be two undo steps, not one:
        a keystroke landing in a different word flushes whatever was pending
        first, rather than letting it merge silently into the next word.
        """

        source = self.source()
        body = source[source.index("onInput()"):]
        body = body[: body.index("\n    },")]

        assert "this.editingWord" in body
        assert "this.flush()" in body

    def test_a_trailing_space_does_not_mark_the_word_before_it(self):
        """
        A caret sitting right after a word, with a space typed there, must
        not mark that word as edited: the browser routinely appends the
        space into the word's own span rather than starting new content --
        verified in an actual browser, both mid-caption and on a caption's
        last word, since this bug has twice looked fixed on paper and then
        broken something else.

        The check has to require the caret at the very end of the span, not
        just whitespace anywhere in it: My edits off renders several words
        into one merged span, and a real edit to a word in the middle of
        that span must still be marked, even though the span as a whole
        contains plenty of whitespace.
        """

        source = self.source()
        body = source[source.index("onInput()"):]
        body = body[: body.index("\n    },")]

        assert "this.effectiveSpan(span, range)" in body

        helper = source[source.index("spaceAtTail(span, range) {"):]
        helper = helper[: helper.index("\n    },")]

        assert r'/\s$/.test(span.textContent)' in helper
        assert "span.contains(range.startContainer)" in helper
        assert "this.offsetWithinSpan(span, range) === span.textContent.length" in helper

    def test_a_real_character_after_the_space_gets_a_span_of_its_own(self):
        """
        The very next real character typed after the space removes the
        span's own trailing whitespace -- the browser keeps extending the
        same span for it too -- so spaceAtTail alone stops matching on that
        keystroke. Marking the shared span at that point would mark the
        word before the space right along with the new one forming after
        it, the exact regression this once caused; splitNewWord gives the
        new content a span of its own instead, so it can be marked without
        marking the original word too.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        assert "this.newWordBoundary = { span, offset:" in body
        assert "offset > boundary" in body
        assert "this.splitNewWord(span, boundary)" in body

    def test_sitting_right_at_the_boundary_marks_nothing_yet(self):
        """
        The instant the space itself was typed, or the caret is still
        sitting right after it with nothing typed there yet -- no new word
        exists to split off, and the original one is not to be marked
        either.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        assert "if (offset === boundary) return null;" in body

    def test_backspacing_before_the_boundary_forgets_it(self):
        """
        Backspace undoing the space, or eating into the new word and then
        the original one, means the reader is editing that earlier content
        now -- the remembered offset has to be dropped there, or typing
        forward again later (appending to the original word for an
        unrelated, genuine reason) reads as still past a boundary that no
        longer describes anything real. This is the exact regression that
        once made a real edit stop marking at all.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        below = body[body.index("if (offset === boundary) return null;"):]

        assert "this.newWordBoundary = null;" in below
        assert "return span;" in below

    def test_split_new_word_moves_the_caret_to_the_end(self):
        """
        The new span is where the caret has to end up too -- typing there
        is always at its own end, since splitNewWord only ever runs the
        instant the boundary is first crossed. Marking it is left to
        onInput's own markChanged call afterward, the same as any other
        span -- not done here, so a span split off holding nothing but more
        whitespace (a second space typed right after the first) is not
        marked either. That case is refused before this ever runs though
        (see TestClientContract's whitespace tests) -- effectiveSpan
        extends the boundary instead of splitting for it.
        """

        source = self.source()
        body = source[source.index("splitNewWord(span, characterOffset) {"):]
        body = body[: body.index("\n    },")]

        assert 'setAttribute("data-changed"' not in body
        assert "node.splitText(remaining)" in body
        assert "range.collapse(false)" in body

    def test_a_second_space_extends_the_boundary_instead_of_splitting(self):
        """
        Nothing but whitespace past the remembered boundary -- a second
        space typed right after the first -- is not a new word yet, so
        there is nothing to give a span of its own or mark. The boundary
        moves out to cover it instead, the same as if the first space had
        landed there to begin with.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        whitespace_check = body[body.index("if (offset > boundary) {"):]
        whitespace_check = whitespace_check[: whitespace_check.index("const wrapper")]

        assert "span.textContent.slice(boundary, offset)" in whitespace_check
        assert "this.newWordBoundary = { span, offset };" in whitespace_check
        assert "return null;" in whitespace_check

    def test_splitting_does_not_flush_the_spaces_own_pending_edit(self):
        """
        spaceAtTail's own null already cleared editingWord on the space
        keystroke -- if the split left onInput to compare against that on
        its own, the new wrapper would read as a different word and flush
        whatever was still pending: the space's own transient snapshot
        (the word with a bare trailing space, not the finished word that
        followed it), splitting one continuous "type a word after a space"
        action into two undo steps. The second one lands on that
        half-finished text, which is why this showed up as a stray extra
        space appearing after a single undo -- the real separator space
        plus the one the reader had just typed, both still there in a
        state nothing should have flushed on its own.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        split_branch = body[body.index("if (offset > boundary) {"):]
        split_branch = split_branch[: split_branch.index("return wrapper;")]

        assert "this.editingWord = wrapper;" in split_branch

    def test_typing_at_the_head_of_the_next_word_gets_a_span_of_its_own(self):
        """
        A caret sitting between a separator and the word right after it
        resolves into the separator's own tail, not the word's head -- so
        inserting a new word there looks, to the DOM, like typing real
        content into what was pure whitespace. Left unsplit the new word
        keeps growing inside the separator's own span, flush against the
        word after it with no whitespace between them in the DOM at all --
        the mirror image of the space-then-word case above, just without a
        remembered boundary, since the whitespace prefix here never
        changes keystroke to keystroke the way a growing word does.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        assert r"/^(\s+)(\S+)$/.exec(span.textContent)" in body
        assert "this.offsetWithinSpan(span, range) === span.textContent.length" in body
        assert "this.splitNewWord(span, headMatch[1].length)" in body

    def test_a_synthetic_separator_follows_the_new_word(self):
        """
        Splitting the new word off its separator is not enough on its own:
        nothing yet stands between it and the word right after it, so a
        debounced flush landing before the reader types their own trailing
        space would still send the two run together -- undo then makes
        that merge permanent, which is what a single Undo actually showed
        after this exact keystroke pattern. A synthetic space, inserted the
        moment the new word is split off, keeps every flush from here on
        properly spaced even before the reader finishes typing one of
        their own.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        head_branch = body[body.index("const headMatch ="):]

        assert 'document.createTextNode(" ")' in head_branch
        assert "this.syntheticSpace = document.createTextNode" in head_branch
        assert "span.appendChild(this.syntheticSpace)" in head_branch
        assert '!/^\\s/.test(next.textContent || "")' in head_branch

    def test_the_synthetic_separator_is_retired_once_a_real_one_exists(self):
        """
        The reader typing their own trailing space is exactly what
        spaceAtTail already watches for -- the moment it fires against the
        new word's own span, whatever synthetic separator was standing in
        is now redundant, and is removed rather than left to sit
        alongside a real one and read back as a double space.
        """

        source = self.source()
        body = source[source.index("effectiveSpan(span, range) {"):]
        body = body[: body.index("\n    },")]

        space_branch = body[body.index("if (this.spaceAtTail(span, range)) {"):]
        space_branch = space_branch[: space_branch.index("this.newWordBoundary = {")]

        assert "this.syntheticSpace.previousSibling === span" in space_branch
        assert "this.syntheticSpace.remove();" in space_branch
        assert "this.syntheticSpace = null;" in space_branch

    def test_the_synthetic_separator_is_retired_when_its_word_is_deleted(self):
        """
        The synthetic space only earns its place while there is a new word in
        front of it to hold apart from the next one. Backspacing that word
        away again leaves it separating nothing, and left in the DOM it is
        read straight back out as part of the caption -- a stray double space
        the reader never typed, flushed as a real undo-able state, and in
        subtitleMode counted against the character guideline too. spaceAtTail's
        own retirement path cannot catch this: it only fires when a real space
        is typed, never when the word is deleted instead.
        """

        source = self.source()
        body = source[source.index("retireSyntheticSpace() {"):]
        body = body[: body.index("\n    },")]

        # "Separating nothing" is everything ahead of it inside its own parent
        # being whitespace -- the word had a span of its own, and the browser
        # takes that span away with the last character of it.
        assert "space.parentNode.firstChild" in body
        assert "node !== space" in body
        assert 'if (!/\\S/.test(before))' in body
        assert "space.remove();" in body
        assert "this.syntheticSpace = null;" in body

    def test_the_retirement_runs_before_the_edit_is_measured(self):
        """
        Ahead of caret() and the text read for the flush, so a space that has
        stopped separating anything is already gone by the time either sees
        the block -- retired afterwards, the stale space would still be in the
        text that gets sent.
        """

        source = self.source()
        body = source[source.index("onInput() {"):]
        body = body[: body.index("\n    },")]

        assert body.index("this.retireSyntheticSpace()") < body.index("this.caret()")

    def test_a_space_already_gone_just_clears_the_reference(self):
        """
        A Backspace reaching the space itself, or a render rebuilding the
        block around it, detaches the node -- nothing to remove then, but the
        reference must not be left pointing at it.
        """

        source = self.source()
        body = source[source.index("retireSyntheticSpace() {"):]
        body = body[: body.index("\n    },")]

        detached = body[body.index("if (!space.parentNode)"):]

        assert "this.syntheticSpace = null;" in detached

    def test_the_template_renders_the_edit_marking(self):
        source = self.source()

        assert "'edit-word'" in source
        # Bound on every word, not only the ones the server marked, so the
        # stylesheet can reach the message on a word the browser marked too.
        assert ':data-edit="editLabel"' in source

    def test_there_is_still_only_one_watch_block(self):
        """
        Duplicate keys in an object literal keep only the last, which silently
        dropped a watcher once already.
        """

        assert self.source().count("\n  watch: {") == 1


def css_rules() -> list:
    """
    The stylesheet as (selectors, body) pairs.

    Comments go first: they are full of commas, and would otherwise be split up
    and counted as selectors. Flat enough to read this way afterwards -- the one
    @media block in the sheet wraps a single rule, which is matched on its own.
    """

    from utils.styles import theme_styles

    css = re.sub(r"/\*.*?\*/", "", theme_styles, flags=re.S)

    return [
        ([part.strip() for part in selectors.split(",") if part.strip()], body)
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    ]


def selectors_where(needle: str) -> set:
    """
    Every selector in a rule whose body contains this.
    """

    return {
        selector
        for selectors, body in css_rules()
        if needle in body
        for selector in selectors
    }


def declarations_for(selector: str) -> str:
    """
    Everything declared for exactly this selector, across all its rules.
    """

    return "".join(
        body for selectors, body in css_rules() if selector in selectors
    )


class TestHoverMessages:
    """
    A hover message is generated content, and generated content that is not
    given the box to sit in renders as ordinary text in the middle of the
    transcription. That was reported: editing a word inserted the words "You
    changed this word" into it.
    """

    def selectors_where(self, needle: str) -> set:
        return selectors_where(needle)

    def test_every_message_is_hidden_until_it_is_hovered(self):
        generated = {
            selector
            for selector in self.selectors_where("content: attr(")
            if selector.endswith("::after")
        }
        hidden = self.selectors_where("visibility: hidden")

        assert generated, "no hover messages found at all"
        assert generated <= hidden, (
            "renders as text in the flow, with no box to sit in: "
            + ", ".join(sorted(generated - hidden))
        )

    def test_every_message_is_positioned_out_of_the_flow(self):
        generated = {
            selector
            for selector in self.selectors_where("content: attr(")
            if selector.endswith("::after")
        }
        positioned = self.selectors_where("position: absolute")

        assert generated <= positioned, (
            "not taken out of the flow: " + ", ".join(sorted(generated - positioned))
        )

    def test_a_changed_word_says_it_was_changed(self):
        messages = self.selectors_where("content: attr(data-edit)")

        assert ".transcript-show-edits [data-changed]::after" in messages


class TestSwitchColours:
    """
    Each switch wears the colour of the marking it turns on. Asserted against
    the same custom properties the words use, so the two cannot drift apart.
    """

    def styles(self) -> str:
        from utils.styles import theme_styles

        return theme_styles


    def test_the_switches_are_named_in_the_page(self):
        page = pathlib.Path("pages/srt.py").read_text()

        assert '"Uncertain words",' in page
        assert 'classes("review-switch")' in page
        assert '"My edits",' in page
        assert 'classes("edits-switch")' in page

    @pytest.mark.parametrize(
        "switch, token",
        [
            ("review-switch", "--color-review-accent"),
            ("edits-switch", "--color-edit-accent"),
        ],
    )
    def test_a_switch_that_is_on_uses_the_marking_colour(self, switch, token):
        rule = re.search(
            rf"\.q-toggle\.{switch} \.q-toggle__inner--truthy \{{([^}}]*)\}}",
            self.styles(),
        )

        assert rule, f"no rule for {switch}"
        assert f"color: var({token})" in rule.group(1)

    def test_it_beats_quasars_own_rules(self):
        """
        Quasar sets the colour on the same element for both light and dark, at
        two classes. The switch class has to be on the switch itself to win.
        """

        assert ".q-toggle.review-switch .q-toggle__inner--truthy" in self.styles()
        assert ".q-toggle.edits-switch .q-toggle__inner--truthy" in self.styles()


class TestSensitivitySelector:
    """
    Low / Medium / High only means anything while uncertain words are being
    marked, so it wears that switch's colour.

    Coloured by naming a colour Quasar can find rather than by overriding its
    palette: a non-flat button turns `color` into `bg-<name>` and `text-color`
    into `text-<name>`, both verified against the bundled Quasar. So a class of
    that name is all it takes, and nothing here depends on which child element
    ends up selected.
    """

    def page(self) -> str:
        return pathlib.Path("pages/srt.py").read_text()

    def asked_for(self) -> dict:
        """
        The colour names the page hands to Quasar, read out rather than matched
        as substrings -- "review-accents" contains "review-accent", so a typo
        would slip past a substring check.
        """

        return dict(
            re.findall(
                r"(toggle-color|toggle-text-color)=([\w-]+)", self.page()
            )
        )

    def test_the_selected_option_asks_for_our_colour(self):
        assert self.asked_for() == {
            "toggle-color": "review-accent",
            "toggle-text-color": "review-accent-fg",
        }

    def test_every_colour_it_asks_for_is_defined(self):
        """
        Quasar builds the class name from the prop, so a name with no rule
        behind it leaves the control silently unstyled.
        """

        for prop, name in self.asked_for().items():
            prefix = "bg-" if prop == "toggle-color" else "text-"

            assert declarations_for(f".{prefix}{name}"), (
                f"{prop}={name} needs a .{prefix}{name} rule"
            )

    @pytest.mark.parametrize(
        "selector, declaration",
        [
            (".bg-review-accent", "background: var(--color-review-accent)"),
            (".text-review-accent-fg", "color: var(--color-review-on-accent)"),
        ],
    )
    def test_the_names_it_asks_for_exist(self, selector, declaration):
        body = declarations_for(selector)

        assert body, f"{selector} is asked for but never defined"
        assert declaration in body
        # Quasar's own palette classes are !important, so ours has to be too.
        assert "!important" in body

    def test_it_is_the_same_colour_as_the_switch(self):
        """
        Both read the one custom property, so they cannot drift apart.
        """

        switch = declarations_for(".q-toggle.review-switch .q-toggle__inner--truthy")

        assert "var(--color-review-accent)" in switch
        assert "var(--color-review-accent)" in declarations_for(".bg-review-accent")

    def test_the_text_on_it_is_defined_for_both_themes(self):
        """
        The dark accent is pale, so white on it would be unreadable -- the two
        themes need different text.
        """

        from utils.styles import theme_styles

        assert theme_styles.count("--color-review-on-accent:") == 2


class TestMarkedWordCursor:
    """
    A marked word is still text to be edited. It keeps the cursor of whatever it
    sits in -- a caret in the editor -- rather than the question mark that says
    "consult me", which was reported as wrong.
    """

    def test_no_marked_word_asks_for_the_help_cursor(self):
        offenders = sorted(selectors_where("cursor: help"))

        assert offenders == [], f"still a question mark over: {offenders}"

    def test_the_marking_rules_are_still_there_to_have_been_checked(self):
        """
        Guards the guard: the test above passes trivially if the markings were
        renamed and nothing matches any more.
        """

        assert declarations_for(".review-word")
        assert declarations_for(".edit-word")


class TestCaretIsNotPaintedOver:
    """
    Reported in Safari: the caret was hidden behind the highlight, on marked
    words only.

    position: relative promotes an inline element to paint above the in-flow
    text, and WebKit draws the caret with the block's own content -- so a
    positioned marking painted its background over the caret. The playing-word
    highlight has a background too and was never affected, because it was never
    positioned. It was only ever positioned to anchor a hover message, so both
    go, for every marking rather than for the word the caret is in: changing an
    element's position while it is being clicked left Safari selecting the word
    before the one clicked.
    """

    MARKINGS = [
        ".transcript-text .review-word",
        ".transcript-text .edit-word",
        ".transcript-show-edits [data-changed]",
    ]

    def declarations(self, selector: str) -> dict:
        body = declarations_for(selector)

        assert body, f"{selector} is not styled at all"

        return {
            part.split(":", 1)[0].strip(): part.split(":", 1)[1].strip()
            for part in body.split(";")
            if ":" in part
        }

    @pytest.mark.parametrize("selector", MARKINGS)
    def test_no_marking_in_the_transcription_is_positioned(self, selector):
        assert self.declarations(selector)["position"] == "static"

    @pytest.mark.parametrize("selector", MARKINGS)
    def test_none_of_them_generates_a_hover_message(self, selector):
        """
        Required, not a preference: an absolutely positioned pseudo-element with
        no positioned ancestor anchors somewhere else entirely.
        """

        assert self.declarations(f"{selector}::after")["content"] == "none"

    @pytest.mark.parametrize(
        "scoped, bare",
        [
            (".transcript-text .review-word", ".review-word"),
            (".transcript-text .edit-word", ".edit-word"),
        ],
    )
    def test_it_outweighs_the_rule_that_positions_that_marking(self, scoped, bare):
        """
        By weight rather than by ordering, so moving the block cannot break it.
        """

        sys.path.insert(0, str(pathlib.Path(__file__).parent))
        from test_caption_editor_styles import specificity

        assert "position: relative" in declarations_for(bare)
        assert specificity(scoped) > specificity(bare)

    def test_the_caret_has_a_colour_of_its_own(self):
        """
        Otherwise it inherits the marking's text colour and goes faint against
        the marking's background.
        """

        assert self.declarations(".transcript-body")["caret-color"] == (
            "var(--color-text-primary)"
        )

    def test_nothing_changes_position_while_a_word_is_clicked(self):
        """
        The transcription no longer tracks which word the caret is in, which is
        what used to mutate the clicked element mid-click.
        """

        source = pathlib.Path("utils/transcript_editor.js").read_text()

        assert "data-caret" not in source
        assert "markCaretWord" not in source

    def test_the_caption_editor_keeps_its_hover_messages(self):
        """
        Nothing is typed into the read view, and the layer behind the caption
        text area already silenced its own.
        """

        assert "position: relative" in declarations_for(".review-word")
        assert declarations_for(".review-word::after")


class TestMarksAreDroppedOnRender:
    """
    A fresh render is the server's own account, diffed properly rather than word
    by word, so the browser's stopgap marks give way to it.
    """

    def revision_watcher(self) -> str:
        source = pathlib.Path("utils/transcript_editor.js").read_text()
        body = source[source.index("    revision() {"):]

        return body[: body.index("\n    },")]

    def test_the_browser_marks_are_cleared(self):
        body = self.revision_watcher()

        assert 'querySelectorAll("[data-changed]")' in body
        assert 'removeAttribute("data-changed")' in body

    def test_the_caret_word_is_marked_when_typing(self):
        source = pathlib.Path("utils/transcript_editor.js").read_text()
        body = source[source.index("onInput()"):]
        body = body[: body.index("\n    },")]

        assert "this.markChanged(span)" in body


class TestWordsWithoutTimings:
    """
    A word can be transcribed without a timing. It used to be discarded at load,
    which left a hole in the word list: the token in the text aligned to nothing,
    so it was marked as a word the reader had written, and the confidence score
    that went out with it stopped being flagged. Both readings were wrong, and
    both were silent.
    """

    MIXED = {
        "version": 1,
        "words": [
            {"t": "Hej", "s": 0.0, "e": 1.0, "c": 0.99},
            {"t": "på", "c": 0.15},                       # no timing
            {"t": "dig", "s": 2.0, "e": 3.0, "c": 0.99},
            {"t": "idag", "s": 3.0, "e": 4.0, "c": 0.99},
        ],
    }

    @pytest.fixture
    def mixed(self):
        editor = SRTEditor("job-uuid", "txt", "file.txt")
        editor.refresh_display = lambda *a, **k: None
        editor.save_state_for_undo = lambda *a, **k: None
        editor.mark_as_changed = lambda *a, **k: None
        editor.load_words(self.MIXED)
        editor.captions = [caption()]
        editor.show_uncertain_words = True
        editor.show_my_edits = True

        return editor

    def test_the_untimed_word_is_kept(self, mixed):
        assert [word["t"] for word in mixed.words] == ["Hej", "på", "dig", "idag"]

    def test_it_keeps_the_order_of_the_transcript(self, mixed):
        """
        Placed beside the word before it, so it lands in the same caption rather
        than outside every time range.
        """

        assert [word["t"] for word in mixed.caption_words(caption())] == [
            "Hej", "på", "dig", "idag"
        ]

    def test_it_is_not_reported_as_the_reader_s_own(self, mixed):
        assert [run["t"] for run in mixed.review_runs(caption(), TEXT)
                if run.get("edit")] == []

    def test_it_is_still_flagged_for_review(self, mixed):
        """
        The score is what decides that, and it never depended on a timing.
        """

        assert [run["t"] for run in mixed.review_runs(caption(), TEXT)
                if run["flag"]] == ["på"]
        assert mixed.flagged_word_count() == 1

    def test_it_carries_no_timing_to_be_followed_by(self, mixed):
        runs = mixed.review_runs(caption(), TEXT, per_word=True)
        timed = {run["t"] for run in runs if "s" in run}

        assert timed == {"Hej", "dig", "idag"}

    def test_editing_it_is_recorded_like_any_other_word(self, mixed):
        target = caption()

        mixed.update_caption_text(target, "Hej XX dig idag")

        assert [run["t"] for run in mixed.review_runs(target, target.text)
                if run.get("edit")] == ["XX"]

    def test_splitting_falls_back_when_a_side_has_no_timing(self, mixed):
        """
        The gap between two words only means something if both are placed in the
        recording. Without that the ordinary fallback decides, rather than the
        split raising.
        """

        boundary = mixed.split_time(
            caption(), "Hej på", "dig idag", at_cursor=True
        )

        assert 0.0 < boundary < 4.0

    def test_seeking_to_it_is_declined(self, mixed):
        """
        Nothing in the recording is known to correspond to it, the same as for a
        word the reader wrote.
        """

        from utils.transcript_editor import TranscriptEditor

        view = TranscriptEditor(mixed)

        # Caret inside "på", the word with no timing.
        assert view.time_at_offset(caption(), 5) is None
        # Its neighbours are unaffected.
        assert view.time_at_offset(caption(), 0) == pytest.approx(0.0)
        assert view.time_at_offset(caption(), 9) == pytest.approx(2.0)


class TestEditsAreRecordedNotDeduced:
    """
    An edit is something that happened, so it is written down when it happens.

    It used to be deduced afterwards, from a word failing to align against the
    words the model transcribed. That deduction marked words nobody had
    touched: reported from a real recording where whisper dated a segment from
    2.32 and its first word from 0.00, so the caption never claimed that word
    and the token had nothing to align to.
    """

    @pytest.fixture
    def reported(self, editor):
        """
        The recording that was reported, with its first word timed before the
        caption it belongs to.
        """

        editor.load_words({"version": 1, "words": [
            {"t": "Ja,", "s": 0.0, "e": 1.62, "c": 0.686},
            {"t": "tack", "s": 2.96, "e": 4.08, "c": 0.421},
            {"t": "för", "s": 4.08, "e": 4.32, "c": 0.604},
            {"t": "inbjudan.", "s": 4.32, "e": 5.08, "c": 0.946},
        ]})
        editor.captions = [
            SRTCaption(1, "00:00:02,320", "00:00:05,100", "Ja, tack för inbjudan.")
        ]
        editor.show_my_edits = True

        return editor

    def edited(self, editor, caption):
        return [
            run["t"]
            for run in editor.review_runs(caption, caption.text)
            if run.get("edit")
        ]

    def test_an_untouched_transcription_marks_nothing(self, reported):
        assert self.edited(reported, reported.captions[0]) == []

    def test_changing_a_word_records_it(self, reported):
        target = reported.captions[0]

        reported.update_caption_text(target, "Ja, tack för allt.")

        assert self.edited(reported, target) == ["allt."]

    def test_changing_only_the_capitalisation_still_counts(self, reported):
        """
        The reader changed it. Unlike the alignment used for confidence, this
        does not normalise the word away.
        """

        target = reported.captions[0]

        reported.update_caption_text(target, "Ja, TACK för inbjudan.")

        assert self.edited(reported, target) == ["TACK"]

    def test_a_mark_moves_when_a_word_is_added_ahead_of_it(self, reported):
        target = reported.captions[0]

        reported.update_caption_text(target, "Ja, tack för allt.")
        reported.update_caption_text(target, "Så, ja, tack för allt.")

        # "allt." is still the marked word, now one place further along.
        assert "allt." in self.edited(reported, target)
        assert "inbjudan." not in self.edited(reported, target)

    def test_a_mark_goes_when_its_word_is_deleted(self, reported):
        target = reported.captions[0]

        reported.update_caption_text(target, "Ja, tack för allt.")
        reported.update_caption_text(target, "Ja, tack för")

        assert self.edited(reported, target) == []

    def test_a_snapshot_carries_the_marks(self):
        """
        The undo stack holds copies of the captions, so undoing a change has to
        take its marks back with it.
        """

        original = caption("Hej på dig idag", edited=[1])
        snapshot = original.copy()

        assert snapshot.edited_words == {1}

        # And they are separate sets, or undoing would edit the live caption.
        snapshot.edited_words.add(2)

        assert original.edited_words == {1}

    def test_a_word_no_caption_claimed_is_not_an_edit(self, reported):
        """
        The reported case in one line: "Ja," is claimed now, but even if it
        were not, nothing about the word list decides this any more.
        """

        reported.captions[0].start_time = "00:00:04,000"

        assert self.edited(reported, reported.captions[0]) == []


class TestMarksSurviveStructuralEdits:
    @pytest.fixture
    def editing(self, editor):
        editor.captions = [caption("Hej på dig idag", edited=[3])]
        editor.show_my_edits = True

        return editor

    def edited(self, editor, caption):
        return [
            run["t"]
            for run in editor.review_runs(caption, caption.text)
            if run.get("edit")
        ]

    def test_a_split_hands_the_mark_to_the_half_that_has_the_word(self, editing):
        editing.split_caption(editing.captions[0], cursor_position=len("Hej på"))

        first, second = editing.captions

        assert self.edited(editing, first) == []
        assert self.edited(editing, second) == ["idag"]

    def test_a_merge_moves_the_mark_along(self, editing):
        editing.captions.insert(0, caption("Ett två", edited=[]))
        editing.renumber_captions()

        editing.merge_with_previous(editing.captions[1])

        assert self.edited(editing, editing.captions[0]) == ["idag"]

    def test_merging_forwards_moves_the_second_half(self, editing):
        editing.captions.append(caption("Ett två", edited=[1]))
        editing.renumber_captions()

        editing.merge_with_next(editing.captions[0])

        assert self.edited(editing, editing.captions[0]) == ["idag", "två"]


class TestMarksAreSaved:
    """
    Persisted with the transcription, so they still mean something after a
    reload -- which was the point of recording them rather than deducing them.
    """

    def reloaded(self, editor):
        fresh = SRTEditor("job-uuid", "txt", "file.txt")
        fresh.refresh_display = lambda *a, **k: None
        fresh.parse_txt(json.dumps(editor.export_json()))
        fresh.show_my_edits = True

        return fresh

    @pytest.fixture
    def saved(self, editor):
        editor.captions = [
            caption("Hej på dig idag", edited=[1]),
            caption("Ett två tre"),
        ]
        editor.captions[1].index = 2
        editor.speakers = {"UNKNOWN"}
        editor.show_my_edits = True

        return editor

    def test_an_untouched_transcription_records_nothing(self, editor):
        editor.captions = [caption()]
        editor.speakers = {"UNKNOWN"}

        exported = editor.export_json()

        assert "edited" not in exported["segments"][0]

    def test_the_marks_are_written_out(self, saved):
        exported = saved.export_json()

        assert exported["segments"][0]["edited"] == [1]
        assert "edited" not in exported["segments"][1]

    def test_they_come_back_on_reload(self, saved):
        fresh = self.reloaded(saved)

        assert fresh.captions[0].edited_words == {1}
        assert fresh.captions[1].edited_words == set()

    def test_the_marking_survives_the_round_trip(self, saved):
        fresh = self.reloaded(saved)
        target = fresh.captions[0]

        assert [run["t"] for run in fresh.review_runs(target, target.text)
                if run.get("edit")] == ["på"]

    def test_a_transcription_saved_before_this_existed_marks_nothing(self):
        """
        Backward compatible: no record, so nothing is claimed about it.
        """

        # A fresh editor: parse_txt appends, so the fixture's own caption would
        # be the one inspected.
        editor = SRTEditor("job-uuid", "txt", "file.txt")
        editor.refresh_display = lambda *a, **k: None
        editor.parse_txt(json.dumps({
            "segments": [
                {"speaker": "A", "text": "Hej på dig idag",
                 "start": 0.0, "end": 4.0},
            ],
            "preserve_segments": True,
        }))
        editor.show_my_edits = True
        target = editor.captions[0]

        assert target.edited_words == set()
        assert [run["t"] for run in editor.review_runs(target, target.text)
                if run.get("edit")] == []

    def test_a_bad_record_is_ignored_rather_than_trusted(self):
        """
        It came back over the wire, so it is not taken on faith.
        """

        editor = SRTEditor("job-uuid", "txt", "file.txt")
        editor.refresh_display = lambda *a, **k: None
        editor.parse_txt(json.dumps({
            "segments": [
                {"speaker": "A", "text": "Hej på", "start": 0.0, "end": 4.0,
                 "edited": ["nonsense", None, 1]},
            ],
            "preserve_segments": True,
        }))

        assert editor.captions[0].edited_words == {1}


class TestFindAndReplaceKeepsMarksStraight:
    """
    Replacing a word is the reader changing it, exactly as typing over it is,
    and a replacement of a different length moves every mark after it along.

    Both replace paths used to assign caption.text directly, so neither
    happened: the replaced word came out unmarked, and a mark further along
    stayed at its old position -- pointing at whatever word had moved into it.
    That is the same "a word I never touched is marked" symptom typing once
    produced, reached through Find and Replace instead.
    """

    def editor(self, text, edited=()):
        editor = SRTEditor("job-uuid", "srt", "file.srt")

        for name in ("refresh_display", "update_words_per_minute",
                     "mark_as_changed", "update_beforeunload_state",
                     "update_flagged_count"):
            setattr(editor, name, lambda *a, **k: None)

        editor.data_format = "srt"
        editor.captions = [caption(text, edited)]
        editor.search_term = "beta"
        editor.case_sensitive = True

        return editor

    def words(self, editor):
        target = editor.captions[0]
        parts = target.text.split()

        return sorted(parts[i] for i in target.edited_words if i < len(parts))

    def test_replace_all_carries_a_later_mark_across(self, monkeypatch):
        monkeypatch.setattr("utils.srt_search.ui.notify", lambda *a, **k: None)
        editor = self.editor("alpha beta gamma", edited=[2])

        editor.replace_all("two words")

        assert editor.captions[0].text == "alpha two words gamma"
        assert "gamma" in self.words(editor)

    def test_replace_all_marks_the_replacement(self, monkeypatch):
        monkeypatch.setattr("utils.srt_search.ui.notify", lambda *a, **k: None)
        editor = self.editor("alpha beta gamma")

        editor.replace_all("BETA")

        assert self.words(editor) == ["BETA"]

    def test_replace_one_carries_a_later_mark_across(self, monkeypatch):
        monkeypatch.setattr("utils.srt_search.ui.notify", lambda *a, **k: None)
        editor = self.editor("alpha beta gamma", edited=[2])
        editor.selected_caption = editor.captions[0]

        editor.replace_in_current_caption("two words")

        assert editor.captions[0].text == "alpha two words gamma"
        assert "gamma" in self.words(editor)

    def test_replace_one_marks_the_replacement(self, monkeypatch):
        monkeypatch.setattr("utils.srt_search.ui.notify", lambda *a, **k: None)
        editor = self.editor("alpha beta gamma")
        editor.selected_caption = editor.captions[0]

        editor.replace_in_current_caption("BETA")

        assert self.words(editor) == ["BETA"]

    def test_a_replacement_is_still_one_undo_step(self, monkeypatch):
        """
        Retagging is done inline rather than through update_caption_text,
        which would take a second snapshot on top of the one already saved --
        Replace All across many captions has to stay a single undo.
        """

        monkeypatch.setattr("utils.srt_search.ui.notify", lambda *a, **k: None)
        editor = self.editor("alpha beta gamma")
        editor.captions.append(caption("beta again"))

        editor.replace_all("BETA")

        assert len(editor.undo_redo_manager.undo_stack) == 1


class TestFlaggedCountFollowsHistory:
    """
    Undo and redo move the text, so which words are flagged moves with it.
    The counter is not recomputed on read -- update_flagged_count has to be
    called, the same as editing does -- so without this the number left over
    from before the undo stays on screen.
    """

    def editor(self):
        editor = SRTEditor("job-uuid", "srt", "file.srt")

        for name in ("refresh_display", "update_words_per_minute",
                     "mark_as_changed", "update_beforeunload_state"):
            setattr(editor, name, lambda *a, **k: None)

        editor.data_format = "srt"
        editor.load_words(PAYLOAD)
        editor.captions = [caption()]
        editor.show_uncertain_words = True

        return editor

    def test_undo_refreshes_the_counter(self, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor()
        calls = []
        editor.update_flagged_count = lambda *a, **k: calls.append(1)

        editor.update_caption_text(editor.captions[0], "Hej XX dig idag")
        before = len(calls)
        editor.undo()

        assert len(calls) > before

    def test_redo_refreshes_it_too(self, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor()
        editor.update_caption_text(editor.captions[0], "Hej XX dig idag")
        editor.undo()

        calls = []
        editor.update_flagged_count = lambda *a, **k: calls.append(1)
        editor.redo()

        assert calls

    def test_the_count_itself_is_right_either_way(self, monkeypatch):
        """
        Guards the guard: a counter refreshed to the wrong number would still
        pass the two above.
        """

        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor()
        editor.update_flagged_count = lambda *a, **k: None

        assert editor.flagged_word_count() == 1

        editor.update_caption_text(editor.captions[0], "Hej XX dig idag")
        assert editor.flagged_word_count() == 0

        editor.undo()
        assert editor.flagged_word_count() == 1


class TestMarksAcrossSubtitleSplitAndMerge:
    """
    Splitting and merging are structural: they move words between captions
    without changing any of them, so marks travel with the words they belong
    to and no new mark is ever invented. Subtitles only -- that is where the
    split/merge actions live.
    """

    def editor(self, texts, marks=None):
        editor = SRTEditor("job-uuid", "srt", "file.srt")

        for name in ("refresh_display", "update_words_per_minute",
                     "mark_as_changed", "update_beforeunload_state",
                     "update_flagged_count"):
            setattr(editor, name, lambda *a, **k: None)

        editor.data_format = "srt"
        editor.captions = [
            SRTCaption(i + 1, f"00:00:0{i * 2},000", f"00:00:0{i * 2 + 2},000", t)
            for i, t in enumerate(texts)
        ]
        for i, m in (marks or {}).items():
            editor.captions[i].edited_words = set(m)

        return editor

    def marked(self, caption):
        words = caption.text.split()

        return [words[i] for i in sorted(caption.edited_words) if i < len(words)]

    def test_split_sends_each_mark_with_its_own_word(self, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor(["aa bb cc dd"], {0: [0, 3]})

        editor.split_caption(editor.captions[0], cursor_position=len("aa bb"))

        assert self.marked(editor.captions[0]) == ["aa"]
        assert self.marked(editor.captions[1]) == ["dd"]

    def test_split_invents_no_marks(self, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor(["aa bb cc dd"])

        editor.split_caption(editor.captions[0], cursor_position=len("aa bb"))

        assert all(not c.edited_words for c in editor.captions)

    def test_merge_moves_the_second_half_along(self, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor(["aa bb", "cc dd"], {0: [1], 1: [0]})

        editor.merge_with_next(editor.captions[0])

        assert editor.captions[0].text == "aa bb\ncc dd"
        assert self.marked(editor.captions[0]) == ["bb", "cc"]

    def test_merge_invents_no_marks(self, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor(["aa bb", "cc dd"])

        editor.merge_with_next(editor.captions[0])

        assert not editor.captions[0].edited_words

    def test_split_then_merge_puts_every_mark_back(self, monkeypatch):
        """
        The round trip is what a reader doing and undoing by hand sees.
        """

        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor(["aa bb cc dd"], {0: [0, 3]})

        editor.split_caption(editor.captions[0], cursor_position=len("aa bb"))
        editor.merge_with_next(editor.captions[0])

        assert self.marked(editor.captions[0]) == ["aa", "dd"]

    def test_merging_an_empty_caption_does_not_shift_marks(self, monkeypatch):
        """
        An empty first half contributes no words, so the second half's marks
        move along by nothing -- and the join adds no blank line to count.
        """

        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor(["", "cc dd"], {1: [1]})

        editor.merge_with_next(editor.captions[0])

        assert editor.captions[0].text == "cc dd"
        assert self.marked(editor.captions[0]) == ["dd"]


class TestMarksAcrossTranscriptionLinesAndBlocks:
    """
    A line break rearranges a block without changing a word in it, so it must
    leave every mark exactly where it was -- adding one would be the editor
    claiming the reader changed a word they only moved to the next line.
    Starting a new block is the same. Transcriptions, where those live.
    """

    def editor(self, texts, marks=None):
        from utils.transcript_editor import TranscriptEditor

        editor = SRTEditor("job-uuid", "txt", "file.txt")

        for name in ("refresh_display", "update_words_per_minute",
                     "mark_as_changed", "update_beforeunload_state",
                     "update_flagged_count"):
            setattr(editor, name, lambda *a, **k: None)

        editor.data_format = "txt"
        editor.captions = [
            SRTCaption(i + 1, f"00:00:0{i * 2},000", f"00:00:0{i * 2 + 2},000",
                       t, speaker="Talare 1")
            for i, t in enumerate(texts)
        ]
        editor.speakers = {"Talare 1"}
        for i, m in (marks or {}).items():
            editor.captions[i].edited_words = set(m)

        view = TranscriptEditor(editor)
        view.refresh = lambda *a, **k: None
        view.changed = lambda *a, **k: None
        view.focus = lambda *a, **k: None

        return editor, view

    def marked(self, caption):
        words = caption.text.split()

        return [words[i] for i in sorted(caption.edited_words) if i < len(words)]

    def test_a_line_break_at_a_word_boundary_marks_nothing(self):
        """
        The reported shape of this bug class: a word going untouched must not
        come out green because the line under it moved.
        """

        editor, view = self.editor(["aa bb cc dd"], {0: [0, 3]})

        view.set_text({"id": 1, "text": "aa bb\ncc dd"})

        assert self.marked(editor.captions[0]) == ["aa", "dd"]

    def test_a_line_break_leaves_an_unmarked_block_unmarked(self):
        editor, view = self.editor(["aa bb cc dd"])

        view.set_text({"id": 1, "text": "aa bb\ncc dd"})

        assert not editor.captions[0].edited_words

    def test_a_break_through_a_word_marks_the_halves(self):
        """
        Cutting a word in two does change it, so both halves are the reader's
        own -- unlike a break placed between words.
        """

        editor, view = self.editor(["aa bb cc dd"])

        view.set_text({"id": 1, "text": "aa bb c\nc dd"})

        assert self.marked(editor.captions[0]) == ["c", "c"]

    def test_a_new_block_at_the_end_starts_unmarked(self):
        editor, view = self.editor(["aa bb cc"], {0: [2]})

        view.split({"id": 1, "offset": len("aa bb cc")})

        assert self.marked(editor.captions[0]) == ["cc"]
        assert editor.captions[1].text == ""
        assert not editor.captions[1].edited_words

    def test_splitting_a_block_sends_marks_to_the_right_half(self):
        editor, view = self.editor(["aa bb cc dd"], {0: [0, 3]})

        view.split({"id": 1, "offset": len("aa bb")})

        assert self.marked(editor.captions[0]) == ["aa"]
        assert self.marked(editor.captions[1]) == ["dd"]

    def test_adding_a_block_then_merging_it_back_changes_nothing(self):
        """
        Backspace straight after "Add block after" has to leave the neighbour
        exactly as it was -- no shifted marks, and no blank line joined on.
        """

        editor, view = self.editor(["aa bb"], {0: [1]})

        view.add_after({"id": 1})
        view.merge({"id": 2, "direction": "previous"})

        assert editor.captions[0].text == "aa bb"
        assert self.marked(editor.captions[0]) == ["bb"]

    def test_merging_two_blocks_moves_the_second_half_along(self):
        editor, view = self.editor(["aa bb", "cc dd"], {0: [1], 1: [0]})

        view.merge({"id": 1, "direction": "next"})

        assert editor.captions[0].text == "aa bb\ncc dd"
        assert self.marked(editor.captions[0]) == ["bb", "cc"]

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
import shutil
import subprocess
import sys
import tempfile

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


def caption(text: str = TEXT) -> SRTCaption:
    return SRTCaption(1, "00:00:00,000", "00:00:04,000", text)


@pytest.fixture
def editor():
    editor = SRTEditor("job-uuid", "txt", "file.txt")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *a, **k: None)

    editor.load_words(PAYLOAD)
    editor.captions = [caption()]

    return editor


def marked(editor, text=TEXT):
    """
    Every marked word, paired with the marking it carries.
    """

    html = editor.get_review_html(caption(text), text) or ""

    return re.findall(r'<span class="([\w-]+)"[^>]*>([^<]*)</span>', html)


class TestWordIsEdit:
    def test_a_replaced_word_is_an_edit(self, editor):
        words = editor.aligned_words(caption("Hej två dig idag"))

        # Second word: "två" replaced "på", so it aligns to nothing.
        assert editor.word_is_edit(words[1])

    def test_an_untouched_word_is_not(self, editor):
        words = editor.aligned_words(caption())

        assert not any(editor.word_is_edit(word) for word in words)

    def test_recasing_and_punctuation_are_not_edits(self, editor):
        """
        The alignment ignores case and surrounding punctuation, so tidying a
        word must not report it as rewritten.
        """

        words = editor.aligned_words(caption("Hej På, dig idag"))

        assert not any(editor.word_is_edit(word) for word in words)

    def test_nothing_is_an_edit_without_word_data(self):
        """
        With nothing to compare against every word looks unaligned, and marking
        the whole transcription would be worse than marking none of it.
        """

        bare = SRTEditor("job-uuid", "txt", "file.txt")
        bare.refresh_display = lambda *a, **k: None

        assert bare.words == []
        assert not bare.word_is_edit(None)


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

        assert marked(editor, "Hej två dig idag") == [("edit-word", "två")]

    def test_a_word_is_never_both(self, editor):
        editor.show_uncertain_words = True
        editor.show_my_edits = True

        for text in (TEXT, "Hej två dig idag", "helt annan text", "Hej"):
            words = editor.aligned_words(caption(text), text)

            assert not any(
                editor.word_needs_review(word) and editor.word_is_edit(word)
                for word in words
            )

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

        assert marked(editor, "Hej på XXX idag") == [
            ("review-word", "på"),
            ("edit-word", "XXX"),
        ]


class TestMarkup:
    def test_the_edit_marking_carries_its_message(self, editor):
        editor.show_my_edits = True

        html = editor.get_review_html(caption("Hej två dig idag"))

        assert 'data-edit="You changed this word"' in html
        assert 'aria-label="You changed this word"' in html
        # Never the browser's own tooltip, which no stylesheet can reach.
        assert "title=" not in html

    def test_edited_text_is_escaped(self, editor):
        editor.show_my_edits = True

        html = editor.get_review_html(caption("Hej <b>två</b> dig idag"))

        assert "<b>" not in html
        assert "&lt;b&gt;" in html

    def test_the_backdrop_shows_edits(self, editor):
        """
        The layer behind an open text area, which is what makes the marking
        visible while a caption is being typed into.
        """

        editor.show_my_edits = True
        html = editor.review_backdrop_html(caption(), "Hej två dig idag")

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
        runs = editor.review_runs(caption("Hej två dig idag"), "Hej två dig idag")

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
        runs = editor.review_runs(
            caption("Hej två dig idag"), "Hej två dig idag", per_word=True
        )
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

    def reclassify(self) -> str:
        body = self.source()
        body = body[body.index("reclassify(span)"):]

        return body[: body.index("\n    },")]

    def test_a_changed_word_is_marked_for_the_stylesheet(self):
        """
        An attribute, not a class: Vue owns the class and rewrites it on the
        next patch, and an attribute can be taken back off again if the reader
        undoes the change.
        """

        body = self.reclassify()

        assert 'setAttribute("data-changed", "")' in body
        assert 'removeAttribute("data-changed")' in body
        assert "classList" not in body

    def test_the_decision_is_the_same_one_the_server_makes(self):
        body = self.reclassify()

        assert "this.matchKey(span.textContent)" in body
        assert "this.matchKey(span.dataset.w)" in body

    def test_a_changed_word_is_never_followed_as_spoken(self):
        source = self.source()
        body = source[source.index("markCurrentWord() {"):]
        body = body[: body.index("\n    },")]

        assert 'hasAttribute("data-changed")' in body

    def test_reclassify_runs_on_input(self):
        source = self.source()
        body = source[source.index("onInput()"):]
        body = body[: body.index("\n    },")]

        assert "this.reclassify" in body

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


# Characters where Python's casefold and JavaScript's toLowerCase agree. The
# two part company only on characters that change length when lowercased, and
# nothing in the JS can do better -- it has no casefold.
NORMALISED = [
    "på", "På", "PÅ", "på,", '"på"', "på.", "(på)", "på!?", "Hej", "HEJ",
    "två", "Två", "idag", "i_dag", "3:e", "1985", "l'été", "Über", "ÜBER",
    "naïve", "co-op", "...", "", "   ", "don't", "Ω", "ω", "мир", "東京",
]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
class TestNormalisationParity:
    """
    The browser decides whether a flagged word still matches what was
    transcribed, and so does the server. If they disagree, a mark comes off as
    the reader types and the next render puts it back -- which is the bug this
    whole path exists to avoid. So the two implementations are compared
    directly rather than trusted to stay in step.
    """

    def js(self, script: str) -> list:
        component = pathlib.Path("utils/transcript_editor.js").read_text()
        component = component.replace("export default", "module.exports =", 1)

        with tempfile.TemporaryDirectory() as directory:
            module = pathlib.Path(directory) / "component.js"
            module.write_text(component)
            runner = pathlib.Path(directory) / "run.js"
            runner.write_text(
                f'const component = require({str(module)!r});\n{script}'
            )

            result = subprocess.run(
                ["node", str(runner)],
                capture_output=True,
                text=True,
                check=True,
            )

        return json.loads(result.stdout)

    def test_match_key_agrees_with_the_server(self):
        keys = self.js(
            "const m = component.methods.matchKey;\n"
            f"console.log(JSON.stringify({json.dumps(NORMALISED)}.map(m)));"
        )
        expected = [SRTEditor.match_key(text) for text in NORMALISED]

        assert keys == expected

    def reclassified(self, cases) -> list:
        """
        Run reclassify against a stub of the one bit of DOM it touches, and
        report whether each word came out marked as changed.
        """

        return self.js(
            """
            const reclassify = component.methods.reclassify;
            const context = { matchKey: component.methods.matchKey };

            function span(text, transcribed, changed) {
              const attributes = changed ? { "data-changed": "" } : {};
              return {
                textContent: text,
                dataset: transcribed === null ? {} : { w: transcribed },
                setAttribute: (k, v) => { attributes[k] = v; },
                removeAttribute: (k) => { delete attributes[k]; },
                hasAttribute: (k) => k in attributes,
                attributes,
              };
            }

            console.log(JSON.stringify(
            """
            + json.dumps(cases)
            + """.map(([text, transcribed, changed]) => {
                const el = span(text, transcribed, changed);
                reclassify.call(context, el);
                return "data-changed" in el.attributes;
              })
            ));
            """
        )

    def test_the_flag_comes_off_a_word_that_was_changed(self):
        marked = self.reclassified([
            ["på", "på", False],        # untouched
            ["två", "på", False],       # replaced
            ["p", "på", False],         # part way through retyping
            ["", "på", False],          # deleted
        ])

        assert marked == [False, True, True, True]

    def test_tidying_case_or_punctuation_is_not_a_change(self):
        """
        The server keeps the score in these cases, so the browser must keep the
        mark -- otherwise it flickers off and comes back.
        """

        marked = self.reclassified([
            ["På", "på", False],
            ["PÅ", "på", False],
            ["på,", "på", False],
            ['"på."', "på", False],
        ])

        assert marked == [False, False, False, False]

    def test_undoing_the_change_puts_the_mark_back(self):
        marked = self.reclassified([
            ["på", "på", True],         # already marked, then typed back
            ["två", "på", True],        # still different
        ])

        assert marked == [False, True]

    def test_a_word_with_nothing_to_compare_is_left_alone(self):
        """
        A merged run of several words, or one already replaced, carries no
        transcribed word. Nothing can be concluded, so nothing is touched.
        """

        marked = self.reclassified([
            ["anything", None, False],
            ["anything", None, True],
        ])

        assert marked == [False, True]


class TestRunsCarryTheTranscribedWord:
    """
    Without it the browser cannot tell a real change from tidied
    capitalisation, so a word that has one can be marked while it is still
    being typed and a word that has none cannot.
    """

    def words_with_a_key(self, editor):
        runs = editor.review_runs(caption(), TEXT)

        return [run["t"] for run in runs if "w" in run]

    def test_a_flagged_run_says_what_was_transcribed(self, editor):
        editor.show_uncertain_words = True
        runs = editor.review_runs(caption(), TEXT)

        assert [run for run in runs if run["flag"]] == [
            {"t": "på", "flag": True, "w": "på"}
        ]

    def test_only_the_flagged_word_has_one_by_default(self, editor):
        editor.show_uncertain_words = True

        assert self.words_with_a_key(editor) == ["på"]

    def test_marking_edits_gives_every_word_one(self, editor):
        """
        The reported bug: only flagged words could be marked while typing,
        because they were the only ones that were a run of their own.
        """

        editor.show_my_edits = True

        assert self.words_with_a_key(editor) == ["Hej", "på", "dig", "idag"]

    def test_marking_edits_splits_every_word_into_its_own_run(self, editor):
        editor.show_my_edits = True
        runs = editor.review_runs(caption(), TEXT)

        assert [run["t"] for run in runs] == [
            "Hej", " ", "på", " ", "dig", " ", "idag"
        ]

    def test_the_text_still_survives_the_split(self, editor):
        editor.show_my_edits = True
        text = "Hej  på\ndig idag"
        runs = editor.review_runs(caption(text), text)

        assert "".join(run["t"] for run in runs) == text

    def test_splitting_costs_no_timings_it_was_not_asked_for(self, editor):
        """
        Following the audio is what pays for start and end; the split on its
        own does not.
        """

        editor.show_my_edits = True
        runs = editor.review_runs(caption(), TEXT)

        assert all("s" not in run for run in runs)

    def test_following_the_audio_still_carries_timings(self, editor):
        editor.show_my_edits = True
        runs = editor.review_runs(caption(), TEXT, per_word=True)

        assert [run["t"] for run in runs if "s" in run] == [
            "Hej", "på", "dig", "idag"
        ]

    def test_an_already_replaced_word_has_none(self, editor):
        """
        Nothing was transcribed there, so there is nothing to compare against
        and the browser leaves it alone -- it is already marked as an edit.
        """

        editor.show_my_edits = True
        text = "Hej XXX dig idag"
        runs = editor.review_runs(caption(text), text)

        assert [run["t"] for run in runs if "w" not in run and run["t"].strip()] == [
            "XXX"
        ]


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


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
class TestMarksDoNotStrandThemselves:
    """
    Reported: placing the caret on an edited word left another word marked too.

    The marks the browser puts on are a stopgap between renders, and they are
    plain attributes -- not part of Vue's data. The spans are keyed by position,
    so Vue reuses them, and a mark judged only for the word under the caret can
    be left behind on a word nobody touched.
    """

    def run(self, script: str):
        component = pathlib.Path("utils/transcript_editor.js").read_text()
        component = component.replace("export default", "module.exports =", 1)

        with tempfile.TemporaryDirectory() as directory:
            module = pathlib.Path(directory) / "component.js"
            module.write_text(component)
            runner = pathlib.Path(directory) / "run.js"
            runner.write_text(
                "const component = require(%r);\n%s" % (str(module), script)
            )

            return json.loads(
                subprocess.run(
                    ["node", str(runner)],
                    capture_output=True, text=True, check=True,
                ).stdout
            )

    HARNESS = """
    const methods = component.methods;

    // The one bit of DOM these touch: a block holding word spans.
    function span(text, transcribed, changed) {
      const attributes = changed ? { "data-changed": "" } : {};
      return {
        textContent: text,
        dataset: transcribed === null ? {} : { w: transcribed },
        setAttribute: (k, v) => { attributes[k] = v; },
        removeAttribute: (k) => { delete attributes[k]; },
        hasAttribute: (k) => k in attributes,
        attributes,
      };
    }

    function block(words) {
      const spans = words.map(([t, w, c]) => span(t, w, c));
      return {
        spans,
        querySelectorAll: (selector) =>
          selector === "[data-w]"
            ? spans.filter((s) => s.dataset.w !== undefined)
            : spans,
      };
    }

    const context = {
      matchKey: methods.matchKey,
      reclassify: methods.reclassify,
      reclassifyBlock: methods.reclassifyBlock,
    };
    """

    def marked_after_block_pass(self, words) -> list:
        return self.run(
            self.HARNESS
            + """
            const b = block(%s);
            context.reclassifyBlock(b);
            console.log(JSON.stringify(
              b.spans.map((s) => "data-changed" in s.attributes)
            ));
            """ % json.dumps(words)
        )

    def test_a_word_nobody_touched_loses_its_mark(self):
        """
        The stranded mark: set on a span whose text still matches what was
        transcribed there, so nothing about it is an edit.
        """

        marked = self.marked_after_block_pass([
            ["Hej", "Hej", False],
            ["XX", "på", True],     # genuinely edited
            ["dig", "dig", True],   # stranded, must come off
            ["idag", "idag", False],
        ])

        assert marked == [False, True, False, False]

    def test_a_word_the_caret_has_left_is_still_judged(self):
        """
        Two real edits stay marked -- the pass judges every word, so it neither
        strands nor forgets.
        """

        marked = self.marked_after_block_pass([
            ["Hej", "Hej", False],
            ["XX", "på", False],
            ["YY", "dig", False],
            ["idag", "idag", False],
        ])

        assert marked == [False, True, True, False]

    def test_putting_a_word_back_unmarks_it(self):
        marked = self.marked_after_block_pass([
            ["på", "på", True],
            ["dig", "dig", False],
        ])

        assert marked == [False, False]

    def test_words_with_nothing_transcribed_are_left_alone(self):
        """
        Whitespace runs and words already replaced carry no transcribed word, so
        the pass skips them rather than guessing.
        """

        marked = self.marked_after_block_pass([
            [" ", None, False],
            ["XXX", None, True],
            ["dig", "dig", False],
        ])

        assert marked == [False, True, False]


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

    def test_the_whole_block_is_re_read_when_typing(self):
        source = pathlib.Path("utils/transcript_editor.js").read_text()
        body = source[source.index("onInput()"):]
        body = body[: body.index("\n    },")]

        assert "this.reclassifyBlock(at.block)" in body

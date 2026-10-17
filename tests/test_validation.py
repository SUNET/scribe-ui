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
What "Validate" reports, and how it is grouped.

The checks themselves had no tests at all -- only that the shortcut reaches
them -- so this covers what each one flags, that a caption is reported once
with everything found in it rather than once per finding, and that errors
(the file is wrong) stay apart from warnings (a viewer will struggle).
"""

from utils.caption import SRTCaption
from utils.settings import get_settings
from utils.srt import SRTEditor

settings = get_settings()


def editor(*captions: SRTCaption) -> SRTEditor:
    editor = SRTEditor("job-uuid", "srt", "file.srt")
    editor.data_format = "srt"
    editor.captions = list(captions)

    return editor


def caption(index, start, end, text="Hej"):
    return SRTCaption(index, start, end, text)


class TestErrors:
    """
    A file that is wrong: nothing to show, or timings that cannot be played.
    """

    def test_an_empty_caption(self):
        issues = editor(
            caption(1, "00:00:00,000", "00:00:02,000", "   ")
        ).collect_validation_issues()

        assert issues[0]["errors"] == ["No text."]

    def test_an_end_before_its_start(self):
        issues = editor(
            caption(1, "00:00:05,000", "00:00:02,000")
        ).collect_validation_issues()

        assert "Ends before it starts." in issues[0]["errors"]

    def test_two_captions_with_the_same_timing(self):
        issues = editor(
            caption(1, "00:00:00,000", "00:00:02,000"),
            caption(2, "00:00:00,000", "00:00:02,000"),
        ).collect_validation_issues()

        # The second one is the duplicate; the first is only an overlap of it.
        assert "Same timing as an earlier caption." in issues[1]["errors"]

    def test_an_overlap_names_both_captions(self):
        issues = editor(
            caption(1, "00:00:00,000", "00:00:05,000"),
            caption(2, "00:00:02,000", "00:00:07,000"),
        ).collect_validation_issues()

        assert "Overlaps caption #2." in issues[0]["errors"]
        assert "Overlaps caption #1." in issues[1]["errors"]

    def test_a_shared_start_is_reported_once_not_three_times(self):
        """
        Two captions starting together used to be reported as a duplicate
        timestamp, as an overlap, and again as "multiple captions start at
        the same time" -- three lines for one problem.
        """

        issues = editor(
            caption(1, "00:00:00,000", "00:00:02,000"),
            caption(2, "00:00:00,000", "00:00:02,000"),
        ).collect_validation_issues()

        assert issues[1]["errors"].count("Same timing as an earlier caption.") == 1
        assert not any(
            "start at the same time" in message
            for entry in issues
            for message in entry["errors"] + entry["warnings"]
        )


class TestWarnings:
    """
    Perfectly valid text a viewer will struggle with -- the subtitle
    guidelines, which is why these are warnings and not errors.
    """

    def test_a_long_line_names_which_line_it_is(self):
        text = "kort\n" + "x" * (settings.CHARACTER_LIMIT + 5)
        issues = editor(
            caption(1, "00:00:00,000", "00:00:04,000", text)
        ).collect_validation_issues()

        assert issues[0]["errors"] == []
        assert issues[0]["warnings"][0].startswith("Line 2 is")

    def test_too_many_lines(self):
        text = "\n".join(["rad"] * (settings.MAX_SUBTITLE_LINES + 1))
        issues = editor(
            caption(1, "00:00:00,000", "00:00:04,000", text)
        ).collect_validation_issues()

        assert any("lines (max" in message for message in issues[0]["warnings"])

    def test_a_caption_gone_too_fast(self):
        issues = editor(
            caption(1, "00:00:00,000", "00:00:00,300")
        ).collect_validation_issues()

        assert any("On screen for" in message for message in issues[0]["warnings"])

    def test_a_caption_ending_before_it_starts_is_not_also_called_short(self):
        """
        It is already reported as the error it is; a second line saying it
        is also brief adds nothing.
        """

        issues = editor(
            caption(1, "00:00:05,000", "00:00:02,000")
        ).collect_validation_issues()

        assert issues[0]["warnings"] == []

    def test_a_transcription_has_no_guidelines_to_miss(self):
        """
        A block is a speaker's whole turn: no length to keep to, and no
        viewer reading it off a screen.
        """

        transcription = editor(
            caption(1, "00:00:00,000", "00:00:00,300", "x" * 200)
        )
        transcription.data_format = "txt"

        assert transcription.collect_validation_issues() == []


class TestGrouping:
    """
    One entry per caption, carrying everything found in it, in the caption
    list's own order -- not one entry per finding in whatever order the
    checks happen to run.
    """

    def test_a_caption_appears_once_with_all_of_its_issues(self):
        text = "x" * (settings.CHARACTER_LIMIT + 5)
        issues = editor(
            caption(1, "00:00:05,000", "00:00:02,000", text)
        ).collect_validation_issues()

        assert len(issues) == 1
        assert issues[0]["errors"] == ["Ends before it starts."]
        assert len(issues[0]["warnings"]) == 1

    def test_entries_follow_the_caption_order(self):
        issues = editor(
            caption(1, "00:00:00,000", "00:00:02,000", ""),
            caption(2, "00:00:02,000", "00:00:04,000"),
            caption(3, "00:00:04,000", "00:00:06,000", ""),
        ).collect_validation_issues()

        assert [entry["caption"].index for entry in issues] == [1, 3]

    def test_a_clean_list_reports_nothing(self):
        issues = editor(
            caption(1, "00:00:00,000", "00:00:02,000"),
            caption(2, "00:00:02,000", "00:00:04,000"),
        ).collect_validation_issues()

        assert issues == []

    def test_every_reported_caption_is_marked_invalid(self):
        """
        The editor's own red left rule follows from the same pass, so the
        report and the list can never disagree about which captions are at
        fault.
        """

        subtitles = editor(
            caption(1, "00:00:00,000", "00:00:02,000", ""),
            caption(2, "00:00:02,000", "00:00:04,000"),
        )

        issues = subtitles.collect_validation_issues()

        assert subtitles.captions[0].is_valid is False
        assert [entry["caption"] for entry in issues] == [subtitles.captions[0]]

    def test_a_caption_knows_whether_it_has_an_error(self):
        """
        The marking is red for an error and amber for warnings only, the
        colours the validation panel uses for the same issues.
        """

        subtitles = editor(
            caption(1, "00:00:00,000", "00:00:02,000", ""),
            caption(2, "00:00:02,000", "00:00:02,100"),
            caption(3, "00:00:03,000", "00:00:05,000"),
            # An error and a warning: the error decides.
            caption(4, "00:00:06,000", "00:00:06,100", "   "),
        )

        subtitles.collect_validation_issues()
        first, second, third, fourth = subtitles.captions

        assert first.has_error is True
        assert (second.is_valid, second.has_error) == (False, False)
        assert (third.is_valid, third.has_error) == (True, False)
        rules = {i["rule"] for i in subtitles.validation_items(
            subtitles.collect_validation_issues()
        ) if i["caption"] is fourth}
        assert rules == {"empty", "short"}
        assert fourth.has_error is True


class TestSummaryWording:
    """
    Counted by kind, and pluralised -- it said "caption(s)" for everything.
    """

    def test_one_caption_is_singular(self):
        assert editor().caption_count(1) == "1 caption"

    def test_several_captions_are_plural(self):
        assert editor().caption_count(3) == "3 captions"

    def test_errors_and_warnings_are_counted_apart(self):
        summary = editor().validation_summary(2, 1)

        assert summary == "2 captions with errors, 1 caption with warnings"

    def test_only_warnings_says_only_warnings(self):
        assert editor().validation_summary(0, 4) == "4 captions with warnings"


class TestTheDockedPanel:
    """
    Issue #138: Validate opens a panel under the video that steps through
    the issues one at a time, in words, rather than a dialog of captions.
    """

    def test_each_issue_is_one_item_in_caption_order(self):
        long_line = "x" * (settings.CHARACTER_LIMIT + 6)
        subject = editor(
            caption(1, "00:00:00,000", "00:00:03,000", "Fine"),
            caption(2, "00:00:03,000", "00:00:06,000", f"Short\n{long_line}"),
            caption(3, "00:00:05,000", "00:00:08,000", "Starts too early"),
        )

        items = subject.validation_items(subject.collect_validation_issues())

        # Caption 2 twice (too long, and overlapping 3), then caption 3.
        assert [(i["caption"].index, i["title"]) for i in items] == [
            (2, f"Line exceeds {settings.CHARACTER_LIMIT} characters"),
            (2, "Overlapping timestamps"),
            (3, "Overlapping timestamps"),
        ]

    def test_an_issue_says_what_is_wrong_in_words(self):
        long_line = "x" * (settings.CHARACTER_LIMIT + 6)
        subject = editor(
            caption(1, "00:00:00,000", "00:00:03,000", f"Short\n{long_line}")
        )

        item = subject.validation_items(subject.collect_validation_issues())[0]

        assert item["error"] is False
        assert item["detail"] == f"Line 2 has {len(long_line)} characters."
        # The caret lands where line 2 passes the limit.
        assert item["offset"] == len("Short\n") + settings.CHARACTER_LIMIT

    def test_a_duplicate_names_the_caption_it_repeats(self):
        subject = editor(
            caption(1, "00:00:00,000", "00:00:02,000"),
            caption(2, "00:00:00,000", "00:00:02,000"),
        )

        items = subject.validation_items(subject.collect_validation_issues())
        duplicate = [i for i in items if i["title"].startswith("Same timing")]

        assert duplicate[0]["caption"].index == 2
        assert duplicate[0]["detail"].endswith("caption 1.")

    def test_validate_opens_the_panel_when_the_page_has_one(self, monkeypatch):
        subject = editor(caption(1, "00:00:00,000", "00:00:02,000", "   "))
        shown = []

        class Panel:
            def show(self, items, checked):
                shown.append((items, checked))

        subject.validation_panel = Panel()
        subject.render_override = None
        monkeypatch.setattr(subject, "update_flagged_count", lambda: None)
        monkeypatch.setattr(
            subject, "show_validation_report", lambda issues: shown.append("dialog")
        )

        subject.validate_captions()

        assert shown[0][1] == 1
        assert shown[0][0][0]["title"] == "No text"
        assert "dialog" not in shown

    def test_the_panel_words(self):
        from utils.validation_panel import heading_text, position_text

        assert heading_text(5) == "Validation issues"
        assert heading_text(0) == "No validation issues"
        assert position_text(1, 5) == "2 of 5"


class TestShowingSomeKinds:
    """
    The panel can step through some kinds of issue and not others.
    """

    def items(self):
        long_line = "x" * (settings.CHARACTER_LIMIT + 6)
        subject = editor(
            caption(1, "00:00:00,000", "00:00:03,000", f"Short\n{long_line}"),
            caption(2, "00:00:02,000", "00:00:05,000", long_line),
        )
        return subject.validation_items(subject.collect_validation_issues())

    def test_every_issue_names_its_kind(self):
        from utils.validation_panel import RULE_LABELS

        assert {item["rule"] for item in self.items()} <= set(RULE_LABELS)

    def test_kinds_are_counted_in_a_fixed_order(self):
        from utils.validation_panel import rule_counts

        # Overlaps (an error) before line length (a warning).
        assert rule_counts(self.items()) == [("overlap", 2), ("length", 2)]

    def test_a_hidden_kind_is_left_out(self):
        from utils.validation_panel import shown_items

        shown = shown_items(self.items(), {"overlap"})

        assert {item["rule"] for item in shown} == {"length"}
        assert len(shown) == 2

    def test_toggling_keeps_the_issue_on_screen_when_it_is_still_shown(self):
        from utils.validation_panel import ValidationPanel

        panel = ValidationPanel.__new__(ValidationPanel)
        panel.all_items = self.items()
        panel.hidden = set()
        panel.items = list(panel.all_items)
        panel.checkboxes = {}
        panel.draw = lambda: None

        # Stand on caption 2's line-length issue, then hide overlaps.
        on_screen = next(
            i for i in panel.items if i["rule"] == "length" and i["caption"].index == 2
        )
        panel.position = panel.items.index(on_screen)
        panel.toggle("overlap")

        assert panel.current() is on_screen

        # Hide its own kind: back to the first issue still shown -- none.
        panel.toggle("length")
        assert panel.items == [] and panel.position == 0


class TestCheckingAgain:
    """
    "Check again" after a fix: validate again, and land on the caption's
    first remaining issue, or on the next issue after it once it passes.
    """

    def panel(self, subject):
        from utils.validation_panel import ValidationPanel

        panel = ValidationPanel.__new__(ValidationPanel)
        panel.revalidate = subject.revalidate_items
        panel.hidden = set()
        panel.all_items = subject.revalidate_items()
        panel.items = list(panel.all_items)
        panel.position = 0
        panel.draw = lambda: None
        panel.draw_filters = lambda: None
        panel.focus = lambda element: None
        panel.heading = None

        class Note:
            text = ""

            def set_text(self, text):
                Note.text = text

            def set_visibility(self, shown):
                pass

        panel.note = Note()
        return panel

    def subject(self):
        subject = editor(
            caption(1, "00:00:00,000", "00:00:03,000", "   "),
            caption(2, "00:00:04,000", "00:00:06,000", "   "),
        )
        subject.render_override = None
        subject.update_flagged_count = lambda: None
        return subject

    def test_a_fixed_caption_moves_on_to_the_next_issue(self):
        subject = self.subject()
        panel = self.panel(subject)

        subject.captions[0].text = "Fixed"
        panel.check_again()

        assert panel.current()["caption"].index == 2
        assert panel.note.text == "Caption 1 passes now."
        assert subject.captions[0].is_valid

    def test_a_caption_still_wrong_stays(self):
        subject = self.subject()
        panel = self.panel(subject)

        panel.check_again()

        assert panel.current()["caption"].index == 1
        assert panel.note.text == "Caption 1 still has 1 issue."


class TestTheCheckboxes:
    def test_they_are_drawn_when_there_is_a_choice(self):
        from utils.validation_panel import filters_wanted

        assert filters_wanted([("overlap", 2), ("length", 1)], set())
        assert not filters_wanted([("length", 3)], set())
        assert not filters_wanted([], {"length"})

    def test_a_lone_hidden_kind_can_still_be_shown_again(self):
        # Hide line length, fix everything else: line length is the only
        # kind left, and hidden. Without its checkbox nothing could show it.
        from utils.validation_panel import filters_wanted

        assert filters_wanted([("length", 3)], {"length"})

    def test_a_checkbox_only_acts_when_it_disagrees(self):
        from utils.validation_panel import ValidationPanel

        panel = ValidationPanel.__new__(ValidationPanel)
        panel.hidden = set()
        toggled = []
        panel.toggle = lambda rule: toggled.append(rule)

        panel.set_shown("overlap", True)  # already shown: nothing to do
        panel.set_shown("overlap", False)  # hide it

        assert toggled == ["overlap"]


class TestStepping:
    """
    Previous and Next keep focus on something that can take it: the button
    that would go past either end is disabled, and a disabled button drops
    focus on the page.
    """

    def panel(self, count):
        from utils.validation_panel import ValidationPanel

        panel = ValidationPanel.__new__(ValidationPanel)
        panel.items = [{"caption": None}] * count
        panel.position = 0
        panel.previous, panel.next = "previous", "next"
        panel.focused = []
        panel.draw = lambda: None
        panel.focus = lambda element: panel.focused.append(element)
        return panel

    def test_next_to_the_end_hands_focus_to_previous(self):
        panel = self.panel(3)

        panel.go_next()
        assert panel.position == 1 and panel.focused == []

        panel.go_next()
        assert panel.position == 2 and panel.focused == ["previous"]

    def test_previous_to_the_start_hands_focus_to_next(self):
        panel = self.panel(3)
        panel.position = 1

        panel.go_previous()

        assert panel.position == 0 and panel.focused == ["next"]

    def test_the_panel_lives_below_uncertain_words(self):
        import pathlib

        page = pathlib.Path("pages/srt.py").read_text()

        video = page.index('with ui.element("div").classes("video-frame')
        uncertain = page.index('ui.label("Uncertain words:")')
        panel = page.index("editor.validation_panel = ValidationPanel(")

        assert video < uncertain < panel


class TestFollowingTheCaret:
    """
    WCAG 1.4.1: a caption's issue is shown as the caret comes to rest in it.
    An open panel switches to it; a closed one, after Validate, opens on it;
    a caption without an issue, or no Validate yet, changes nothing.
    """

    def subject(self):
        long_line = "x" * (settings.CHARACTER_LIMIT + 6)

        return editor(
            caption(1, "00:00:00,000", "00:00:03,000", "Fine"),
            caption(2, "00:00:03,000", "00:00:06,000", f"Short\n{long_line}"),
            caption(3, "00:00:05,000", "00:00:08,000", "Starts too early"),
            caption(4, "00:00:09,000", "00:00:11,000", "Also fine"),
        )

    def panel(self, monkeypatch, visible=True, validated=True):
        import utils.validation_panel as module

        subject = self.subject()
        items = subject.validation_items(subject.collect_validation_issues())

        panel = module.ValidationPanel.__new__(module.ValidationPanel)
        panel.captions = lambda: subject.captions
        panel.hidden = set()
        panel.all_items = items if validated else []
        panel.items = list(panel.all_items)
        panel.position = 0

        class Container:
            def __init__(self):
                self.visible = visible

            def set_visibility(self, shown):
                self.visible = shown

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        panel.container = Container()
        panel.draws = []
        panel.draw = lambda **kwargs: panel.draws.append(kwargs)
        panel.timers = []
        monkeypatch.setattr(
            module.ui, "timer", lambda *args, **kwargs: panel.timers.append(args)
        )

        return panel

    def test_an_open_panel_switches_to_the_caption_the_caret_is_in(self, monkeypatch):
        panel = self.panel(monkeypatch)

        panel.follow_caret(3)

        assert panel.current()["caption"].index == 3
        # The caret is already there: the text must not scroll under it.
        assert panel.draws == [{"scroll": False}]
        assert panel.timers == []

    def test_a_caption_with_several_issues_shows_its_first(self, monkeypatch):
        panel = self.panel(monkeypatch)
        panel.position = 2

        panel.follow_caret(2)

        assert panel.current()["caption"].index == 2
        assert panel.position == 0

    def test_the_issue_already_shown_for_that_caption_is_left_alone(self, monkeypatch):
        """
        "Caption 2" puts the caret in caption 2 itself; the caret following
        that must not redraw (and so re-announce) the issue it was pressed on
        -- not even when it is the caption's second one.
        """

        panel = self.panel(monkeypatch)
        panel.position = 1

        panel.follow_caret(2)

        assert panel.position == 1
        assert panel.draws == []

    def test_a_caption_without_an_issue_changes_nothing(self, monkeypatch):
        panel = self.panel(monkeypatch)
        panel.position = 1

        panel.follow_caret(4)

        assert panel.position == 1
        assert panel.draws == []

    def test_a_closed_panel_opens_on_the_caption_after_a_validate(self, monkeypatch):
        panel = self.panel(monkeypatch, visible=False)

        panel.follow_caret(3)

        assert panel.container.visible is True
        assert panel.current()["caption"].index == 3
        # Said a moment after it is on screen, not as it appears.
        assert panel.draws == [{"scroll": False, "speak": False}]
        assert len(panel.timers) == 1

    def test_a_closed_panel_stays_closed_on_a_caption_without_an_issue(
        self, monkeypatch
    ):
        panel = self.panel(monkeypatch, visible=False)

        panel.follow_caret(4)

        assert panel.container.visible is False
        assert panel.draws == []

    def test_nothing_happens_before_validate_has_run(self, monkeypatch):
        panel = self.panel(monkeypatch, visible=False, validated=False)

        panel.follow_caret(2)

        assert panel.container.visible is False
        assert panel.draws == []

    def test_a_hidden_kind_is_not_followed(self, monkeypatch):
        from utils.validation_panel import shown_items

        panel = self.panel(monkeypatch, visible=False)
        panel.hidden = {"overlap", "length"}
        panel.items = shown_items(panel.all_items, panel.hidden)

        panel.follow_caret(3)

        assert panel.container.visible is False
        assert panel.draws == []

    def test_an_issue_whose_caption_is_gone_is_not_followed(self, monkeypatch):
        panel = self.panel(monkeypatch)
        stale = panel.items[2]["caption"]
        panel.captions = lambda: []

        panel.follow_caret(stale.index)

        assert panel.draws == []

    def test_the_caret_is_reported_once_it_has_settled(self):
        import pathlib

        script = pathlib.Path("utils/transcript_editor.js").read_text()
        watcher = script[script.index("    caretId(id) {") :]
        watcher = watcher[: watcher.index("    },") + len("    },")]

        # Only a caret that is in a caption, only when it has stayed there,
        # and told as the event the Python side listens for.
        assert "if (id === null) return;" in watcher
        assert "setTimeout" in watcher
        assert "this.caretId === id" in watcher
        assert '$emit("caretblock", { id })' in watcher

    def test_the_page_hands_the_caret_to_the_panel(self):
        import pathlib

        page = pathlib.Path("pages/srt.py").read_text()

        assert "transcript.on_caret = (" in page
        assert "editor.validation_panel.follow_caret" in page


class TestOutsideMedia:
    """
    A caption that starts after the media ends, or that starts within it and
    ends after it, cannot be played as written. Checked against how long the
    player says the media file is -- when it knows.
    """

    def subject(self, media_seconds):
        subject = editor(
            caption(1, "00:00:00,000", "00:00:10,000"),
            caption(2, "00:00:10,000", "00:00:20,000"),
            caption(3, "00:00:20,000", "00:00:30,000"),
        )
        subject.media_seconds = media_seconds

        return subject

    def issues(self, subject):
        return [
            item
            for item in subject.validation_items(subject.collect_validation_issues())
            if item["rule"] == "outside"
        ]

    def test_nothing_is_reported_while_the_length_is_unknown(self):
        assert self.issues(self.subject(None)) == []

    def test_captions_within_the_media_pass(self):
        assert self.issues(self.subject(30.0)) == []

    def test_a_caption_ending_after_the_media_is_an_error(self):
        found = self.issues(self.subject(25.0))

        assert [(i["caption"].index, i["title"]) for i in found] == [
            (3, "Ends after the media ends")
        ]
        assert found[0]["error"] is True
        assert found[0]["detail"] == (
            "Ends at 00:00:30,000, the media ends at 00:00:25,000."
        )

    def test_a_caption_starting_after_the_media_is_one_issue_not_two(self):
        found = self.issues(self.subject(15.0))

        assert [(i["caption"].index, i["title"]) for i in found] == [
            (2, "Ends after the media ends"),
            (3, "Starts after the media ends"),
        ]

    def test_a_caption_ending_exactly_where_the_media_ends_passes(self):
        # 30.0004 s is 30.000 s in a timestamp: whole milliseconds are all
        # either side holds.
        assert self.issues(self.subject(30.0004)) == []
        assert self.issues(self.subject(30.0)) == []

    def test_a_transcription_has_no_captions_to_play(self):
        subject = self.subject(5.0)
        subject.data_format = "txt"

        assert self.issues(subject) == []

    def test_the_kind_is_named_for_the_filter_and_comes_among_the_errors(self):
        from utils.validation_panel import RULE_LABELS

        rules = list(RULE_LABELS)

        assert RULE_LABELS["outside"] == "Outside media"
        assert rules.index("outside") < rules.index("length")


class TestTooLong:
    """
    A caption left up for much longer than the guidelines' "about 7 seconds"
    is a warning: usually cut in the wrong place, or left up through a pause.
    """

    def items(self, *captions):
        subject = editor(*captions)

        return [
            item
            for item in subject.validation_items(subject.collect_validation_issues())
            if item["rule"] == "long"
        ]

    def test_a_caption_over_the_limit_is_a_warning(self):
        found = self.items(caption(1, "00:00:00,000", "00:00:08,500", "Hej"))

        assert [i["title"] for i in found] == ["Longer than 8s on screen"]
        assert found[0]["error"] is False
        assert found[0]["detail"] == "On screen for 8.5s."

    def test_exactly_the_limit_passes(self):
        assert self.items(caption(1, "00:00:00,000", "00:00:08,000", "Hej")) == []

    def test_a_shorter_caption_passes(self):
        assert self.items(caption(1, "00:00:00,000", "00:00:06,000", "Hej")) == []

    def test_a_transcription_has_no_guidelines_to_miss(self):
        subject = editor(caption(1, "00:00:00,000", "00:00:30,000", "Hej"))
        subject.data_format = "txt"

        issues = subject.collect_validation_issues()

        assert [i for e in issues for i in e["items"] if i["rule"] == "long"] == []


class TestReadingSpeed:
    """
    Characters per second: spaces and punctuation counted, the line break not,
    over the time the caption is up. A warning above the limit (18).
    """

    def items(self, *captions):
        subject = editor(*captions)

        return [
            item
            for item in subject.validation_items(subject.collect_validation_issues())
            if item["rule"] == "speed"
        ]

    def test_a_caption_read_faster_than_the_limit_is_a_warning(self):
        # 40 characters in 2 seconds: 20 characters/s.
        found = self.items(caption(1, "00:00:00,000", "00:00:02,000", "x" * 40))

        assert [i["title"] for i in found] == [
            "Reading speed above 18 characters/s"
        ]
        assert found[0]["error"] is False
        assert found[0]["detail"] == "20.0 characters/s (40 characters in 2.0s)."

    def test_exactly_the_limit_passes(self):
        # 36 characters in 2 seconds: 18.0.
        assert self.items(caption(1, "00:00:00,000", "00:00:02,000", "x" * 36)) == []

    def test_the_line_break_is_not_counted(self):
        # 20 + 20 characters over two lines, in 2.2 s: 40 / 2.2 = 18.2 would
        # be flagged; 39 characters (the break not counted) in 2.2 s is 17.7.
        text = "a" * 20 + "\n" + "b" * 19
        assert self.items(caption(1, "00:00:00,000", "00:00:02,200", text)) == []

    def test_spaces_and_punctuation_are_counted(self):
        text = "Hello, there. How are you?!"  # 27 characters
        found = self.items(caption(1, "00:00:00,000", "00:00:01,000", text))

        assert found[0]["detail"] == "27.0 characters/s (27 characters in 1.0s)."

    def test_the_figure_shown_is_the_figure_compared(self):
        # 902 characters over 50 s is 18.04: shown as 18.0, the limit, so not
        # flagged -- a caption never says "18.0 characters/s, limit 18" and
        # warns about it.
        text = "x" * 902
        assert self.items(caption(1, "00:00:00,000", "00:00:50,000", text)) == []

    def test_an_empty_caption_is_not_a_reading_speed_problem(self):
        assert self.items(caption(1, "00:00:00,000", "00:00:02,000", "   ")) == []

    def test_a_caption_ending_before_it_starts_is_not_divided_by(self):
        assert self.items(caption(1, "00:00:05,000", "00:00:02,000", "Hej")) == []

    def test_a_caption_with_no_duration_is_not_divided_by(self):
        assert self.items(caption(1, "00:00:05,000", "00:00:05,000", "Hej")) == []

    def test_a_transcription_has_no_guidelines_to_miss(self):
        subject = editor(caption(1, "00:00:00,000", "00:00:01,000", "x" * 100))
        subject.data_format = "txt"

        issues = subject.collect_validation_issues()

        assert [i for e in issues for i in e["items"] if i["rule"] == "speed"] == []

    def test_both_kinds_are_named_for_the_filter_among_the_warnings(self):
        from utils.validation_panel import RULE_LABELS

        rules = list(RULE_LABELS)

        assert RULE_LABELS["speed"] == "Reading speed"
        assert RULE_LABELS["long"] == "Too long"
        assert rules.index("overlap") < rules.index("speed")
        assert rules.index("length") < rules.index("speed") < rules.index("long")


class TestMediaLength:
    """
    How long the media file is, asked of the player and shown in
    Information. Only the player knows; a recording made in the browser has
    no length until played, and the player says Infinity.
    """

    def test_the_figure_is_shown_as_a_running_time(self):
        subject = editor()
        subject.set_media_seconds(125.4)

        assert subject.status_values()["media"] == "2:05"

    def test_it_is_a_dash_until_known(self):
        subject = editor()

        assert subject.status_values()["media"] == "\u2013"

    def test_the_figure_is_redrawn_when_it_arrives(self):
        subject = editor()
        shown = []

        class Figure:
            def set_text(self, text):
                shown.append(text)

        subject.status_elements = {"media": Figure()}
        subject.set_media_seconds(61.0)

        assert shown == ["1:01"]

    def look_up(self, monkeypatch, answer):
        import asyncio

        import utils.srt as module

        async def run_javascript(code, timeout=1.0):
            if isinstance(answer, Exception):
                raise answer
            return answer

        monkeypatch.setattr(module.ui, "run_javascript", run_javascript)

        subject = editor()
        subject.update_status = lambda: None

        class Video:
            id = 7

        asyncio.run(subject.look_up_media_seconds(Video()))

        return subject.media_seconds

    def test_the_length_the_player_reports_is_kept(self, monkeypatch):
        assert self.look_up(monkeypatch, 40.5) == 40.5

    def test_a_player_that_cannot_tell_leaves_it_unknown(self, monkeypatch):
        assert self.look_up(monkeypatch, None) is None

    def test_a_zero_or_nonsense_answer_leaves_it_unknown(self, monkeypatch):
        assert self.look_up(monkeypatch, 0) is None
        assert self.look_up(monkeypatch, "40") is None

    def test_waiting_too_long_leaves_it_unknown(self, monkeypatch):
        assert self.look_up(monkeypatch, TimeoutError()) is None

    def test_the_player_is_asked_once_the_page_is_up(self):
        import pathlib

        page = pathlib.Path("pages/srt.py").read_text()

        assert "editor.look_up_media_seconds(video)" in page
        assert page.index("editor.set_video_player(video)") < page.index(
            "editor.look_up_media_seconds(video)"
        )

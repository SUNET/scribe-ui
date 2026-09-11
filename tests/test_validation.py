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

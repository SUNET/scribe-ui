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
CSS properties of the document editor that a behavioural test cannot reach --
the failure mode is a silent visual one, so it is guarded here instead.
"""

import re

import pytest

from utils.styles import default_styles


def rules():
    """
    Every rule in the stylesheet, as (selectors, declarations).

    Comments come out first: they contain both commas and semicolons, so left in
    they get split up and read as selectors and declarations of their own.
    """

    css = re.sub(r"/\*.*?\*/", "", default_styles, flags=re.S)

    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [
            part.strip() for part in match.group(1).split(",") if part.strip()
        ]
        yield selectors, match.group(2)


def rem(value: str) -> float:
    assert value.endswith("rem"), value
    return float(value[: -len("rem")])


def effective(selector: str) -> dict:
    """
    Properties a selector ends up with, after later rules of equal weight have
    overridden earlier ones. Several rules name the same selector, so reading
    only the first would misjudge what the browser applies.
    """

    applied = {}
    found = False

    for selectors, declarations in rules():
        if selector not in selectors:
            continue
        found = True
        for declaration in declarations.split(";"):
            if ":" not in declaration:
                continue
            prop, _, value = declaration.partition(":")
            applied[prop.strip()] = value.strip()

    assert found, f"no rule for {selector!r}"

    return applied


def specificity(selector: str) -> tuple:
    """
    A selector's weight, as the browser counts it: ids, then classes and
    attributes and pseudo-classes, then elements and pseudo-elements.

    Enough for the selectors here, which are all classes -- the point is to show
    an override wins on its own rather than by sitting further down the file.
    """

    ids = re.findall(r"#[\w-]+", selector)
    classes = re.findall(r"\.[\w-]+|\[[^\]]+\]|(?<!:):[\w-]+(?:\([^)]*\))?", selector)
    elements = re.findall(r"(?:^|[\s>+~])[a-z][\w-]*|::[\w-]+", selector)

    return len(ids), len(classes), len(elements)


class TestSpecificityHelper:
    """
    Guards the guard below: a counter that stopped counting would make every
    override look fine.
    """

    def test_counts_classes(self):
        assert specificity(".a .b .c") == (0, 3, 0)

    def test_counts_a_pseudo_class_as_a_class(self):
        assert specificity(".a:hover") == (0, 2, 0)

    def test_counts_a_pseudo_element_as_an_element(self):
        assert specificity(".a::after") == (0, 1, 1)

    def test_more_classes_outweighs_fewer(self):
        assert specificity(".a.b .c") > specificity(".a .c")


class TestSubtitleGuidelineColouring:
    """
    The character/line count under a subtitle's timestamp reads as ordinary
    muted text until the caption drifts past the guideline, then it takes the
    danger colour -- never a background or a border, so it does not read as
    an error the way the review marking deliberately avoids doing too.
    """

    def test_exceeded_uses_the_danger_colour(self):
        assert effective(".transcript-count-exceeded")["color"] == (
            "var(--color-text-danger)"
        )


class TestTranscriptCellStates:
    """
    A block's left rule marks its state: invalid (failed "Validate") and
    highlighted (a search match) each get their own colour, distinct from
    active (currently playing).
    """

    def test_invalid_and_highlighted_are_distinct_colours(self):
        invalid = effective(".transcript-cell-invalid")["border-left-color"]
        highlighted = effective(".transcript-cell-highlighted")["border-left-color"]
        active = effective(".transcript-cell-active")["border-left-color"]

        assert len({invalid, highlighted, active}) == 3


class TestCaptionActions:
    """
    Split, merge, add and delete (subtitles only) stay out of the way until
    the block they belong to is hovered or focused, so a long list of cues
    is not lined with icons -- and when they do appear, they ride the same
    hover-reveal separator a caption's boundary is already drawn with (see
    TestCaptionSeparator), rather than sitting beside the text as a fifth
    thing to read there.
    """

    def test_hidden_by_default(self):
        assert effective(".transcript-cell-actions")["opacity"] == "0"

    def test_revealed_on_hover(self):
        assert effective(
            ".transcript-cell:hover .transcript-cell-actions"
        )["opacity"] == "1"

    def test_revealed_on_hovering_the_margin_too(self):
        """
        The separator itself has this same second trigger -- the margin
        (its timing) belongs to the same caption as the cell right before
        it, so hovering either one reveals both the line and the actions
        riding it.
        """

        assert effective(
            ".transcript-gutter:hover + .transcript-cell .transcript-cell-actions"
        )["opacity"] == "1"

    def test_revealed_on_keyboard_focus(self):
        assert effective(".transcript-cell-actions:focus-within")["opacity"] == "1"

    def test_it_sits_on_the_separator_not_beside_the_text(self):
        """
        Absolutely positioned at the same bottom offset the separator's own
        border-bottom sits at (see TestCaptionSeparator), centred on that
        line both ways by translate(-50%, 50%) -- not a flex sibling of the
        text any more, which is what let it sit beside the text in the
        first place.
        """

        applied = effective(".transcript-cell-actions")

        assert applied["position"] == "absolute"
        assert applied["left"] == "50%"
        assert applied["bottom"] == effective(
            ".transcript-subtitle-mode .transcript-cell::before"
        )["bottom"]
        assert applied["transform"] == "translate(-50%, 50%)"

    def test_each_icon_has_a_solid_background(self):
        """
        The separator passes directly behind these -- without a solid
        background of its own, the line would show through the gaps an
        icon's shape leaves inside its circle.
        """

        assert (
            effective(".transcript-action")["background-color"]
            == "var(--color-bg-page)"
        )


class TestCaptionSeparator:
    """
    Subtitles are read as separate cues, so hovering one draws a line above
    it to mark where it ends and its neighbour begins. Quiet otherwise, or a
    long list of captions would read as a table.
    """

    def test_hidden_by_default(self):
        assert effective(".transcript-subtitle-mode .transcript-cell::before")[
            "opacity"
        ] == "0"

    def test_revealed_on_hover(self):
        assert effective(
            ".transcript-subtitle-mode .transcript-cell:hover::before"
        )["opacity"] == "1"


class TestSubtitleTimingInputWidth:
    """
    A timestamp reads as "start - end" with even space either side of the
    dash. ch is the width of "0", not of the punctuation a timestamp is
    mostly made of, so a fixed ch-based width left slack after the text that
    made the gap before the dash wider than the one after it -- sizing to
    the input's own content instead is what keeps the two gaps equal.
    """

    def test_the_input_sizes_to_its_own_content(self):
        applied = effective(".transcript-time-input")

        assert applied["field-sizing"] == "content"
        assert "width" not in applied


class TestSubtitleMarginAlignment:
    """
    The margin skips the timing row the same way the base rule skips a
    speaker past the timestamp (see .transcript-gutter's own padding-top),
    rather than heading the timing with an index of matched height -- so a
    count lines up with its text line only because each row's own
    line-height takes up exactly the space one text line does.
    """

    def test_the_margin_skips_the_timing_row(self):
        assert effective(".transcript-subtitle-mode .transcript-gutter")[
            "padding-top"
        ] != "0"

    def test_the_count_row_line_height_matches_the_text(self):
        """
        .transcript-count-row's line-height is stated in absolute terms to
        equal .transcript-text's own (1.85 times its font-size) -- the two
        have to move together, or a row drifts away from the line it
        belongs to.
        """

        text_size = rem(effective(".transcript-text")["font-size"])
        row_line_height = rem(effective(".transcript-count-row")["line-height"])

        assert row_line_height == pytest.approx(text_size * 1.85)


class TestSubtitleTextOffset:
    """
    A subtitle's text, and the divider before it, have to sit the same
    distance from the edge a transcription's do -- otherwise the two read as
    differently indented rather than as the same editor in a different mode.
    Three rules place that distance (the margin column's width, the column
    gap, and the cell's own padding-left); subtitleMode leaves all three at
    the base rule's own values rather than overriding them, so this checks
    that no override has crept back in.
    """

    def test_the_margin_column_and_gap_are_not_overridden(self):
        subtitle_body = effective(".transcript-subtitle-mode .transcript-body")

        assert "grid-template-columns" not in subtitle_body
        assert "column-gap" not in subtitle_body

    def test_the_cell_padding_is_not_overridden(self):
        """
        There is no ".transcript-subtitle-mode .transcript-cell" rule at
        all any more -- the actions that once needed it to lay out beside
        the text now ride the separator instead (see TestCaptionActions),
        so subtitleMode has nothing left to say about the cell's own
        layout, padding-left included.
        """

        selectors = {selector for selectors, _ in rules() for selector in selectors}

        assert ".transcript-subtitle-mode .transcript-cell" not in selectors

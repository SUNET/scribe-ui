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


def px(value: str) -> float:
    assert value.endswith("px"), value
    return float(value[: -len("px")])


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


class TestTheCaptionBeingEdited:
    """
    The caret's own caption is marked, so the editor says where you are
    working even when the recording is playing somewhere else entirely.
    """

    def test_it_carries_the_same_rule_as_the_active_caption(self):
        editing = effective(".transcript-cell-editing")

        assert editing["border-left-color"] == "var(--color-brand-primary)"
        assert editing["border-left-width"] == "2px"

    def test_it_is_stated_after_the_playing_caption(self):
        """
        Both can be true at once -- reading one caption while another
        plays -- and the later rule wins the background. What the reader is
        doing beats what the player is doing.
        """

        selectors = [
            selector for group, _ in rules() for selector in group
        ]

        assert selectors.index(".transcript-cell-editing") > selectors.index(
            ".transcript-cell-active"
        )


class TestCaptionActions:
    """
    Split, merge, add and delete (subtitles only) stay out of the way until
    the caption they belong to is hovered or focused, so a long list of
    cues is not lined with icons -- they ride the timing row, on its true
    centre, rather than sitting beside the text as a fifth thing to read
    there.
    """

    def test_hidden_by_default(self):
        assert effective(".transcript-cell-actions")["opacity"] == "0"

    def test_revealed_on_hover(self):
        assert effective(
            ".transcript-cell:hover .transcript-cell-actions"
        )["opacity"] == "1"

    def test_revealed_on_hovering_the_margin_too(self):
        """
        Hovering the margin (its timing) belongs to the same caption as the
        cell right before it, so hovering either one reveals the actions.
        """

        assert effective(
            ".transcript-gutter:hover + .transcript-cell .transcript-cell-actions"
        )["opacity"] == "1"

    def test_revealed_on_keyboard_focus(self):
        assert effective(".transcript-cell-actions:focus-within")["opacity"] == "1"

    def test_the_tray_costs_the_row_no_height(self):
        """
        The actions sit in a tray of their own, and its padding and border
        are cancelled by a negative margin of the same size: the timing row
        has to stay exactly one .transcript-action tall, since that height
        is what the margin's index -- and so every character count under it
        -- is lined up against.
        """

        applied = effective(".transcript-cell-actions")

        padding = px(applied["padding"])
        border = px(applied["border"].split()[0])
        margin = px(applied["margin"].split()[0])

        assert margin == -(padding + border)

    def test_it_is_centred_on_the_timing_row(self):
        """
        The middle column of the timing row's own three-column grid, which
        is what puts it on the row's true centre. Equal auto margins on a
        flex item only centred it in whatever space the timing left over,
        which sat noticeably right of centre.

        Still in flow, not absolutely positioned, so hidden it reserves its
        own width and height and the row does not reflow as the icons fade
        in and out.
        """

        row = effective(".transcript-subtitle-time")

        assert row["display"] == "grid"
        assert row["grid-template-columns"] == "1fr auto 1fr"
        assert "position" not in effective(".transcript-cell-actions")

    def test_the_timing_keeps_the_first_column_to_itself(self):
        """
        Wrapped so the row has exactly three grid children -- left loose,
        the two inputs and the dash would each take a column of their own
        and the actions would land wherever that left them.
        """

        assert effective(".transcript-subtitle-timing")["display"] == "flex"


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


class TestTimingIsNotText:
    """
    A selection dragged across captions selects words. The timing row is
    not one of them, and painting it as selected reads as text about to go
    with them -- which it never is: a cross-block delete acts on the
    blocks' own text alone (see selectionSpan in transcript_editor.js).
    """

    def test_neither_timing_row_takes_the_highlight(self):
        assert effective(".transcript-time")["user-select"] == "none"
        assert effective(".transcript-subtitle-time")["user-select"] == "none"

    def test_the_field_does_not_paint_while_a_selection_passes_it(self):
        """
        A document selection that only encloses an input still paints the
        input's own value as selected -- so the field opts out too, and
        opts back in on focus alone.
        """

        assert effective(".transcript-time-input")["user-select"] == "none"
        assert effective(".transcript-time-input:focus")["user-select"] == "text"


class TestSubtitleMarginAlignment:
    """
    The margin is a column, the index heading it at the same height as the
    timing row rather than skipped past the way the base rule skips a
    speaker past the timestamp -- so a count lines up with its text line
    only because the index row and each count row's own line-height
    together take up exactly the space the timing row and one text line do.
    """

    def test_the_margin_is_a_column(self):
        assert effective(".transcript-subtitle-mode .transcript-gutter")[
            "flex-direction"
        ] == "column"

    def test_the_index_row_matches_the_actions_height(self):
        """
        .transcript-cell-actions reserves 1.5rem of height in the timing
        row even hidden, which decides that row's actual rendered height --
        not the shorter plain text sitting beside it. The index has to
        match that, or the counts beneath it drift out from under their
        own text lines.
        """

        index = effective(".transcript-subtitle-index")

        assert index["height"] == "1.5rem"
        assert effective(".transcript-action")["height"] == "1.5rem"

    def test_the_index_is_centred_in_its_own_row(self):
        """
        And centred in that height rather than left to half-leading, which
        put the figure at the top of the box and read as the index sitting
        above the timestamp beside it.
        """

        index = effective(".transcript-subtitle-index")

        assert index["display"] == "flex"
        assert index["align-items"] == "center"

    def test_the_count_row_line_height_matches_the_text(self):
        """
        .transcript-count-row's line-height is stated in absolute terms to
        equal .transcript-text's own -- the two have to move together, or a
        row drifts away from the line it belongs to. Read from the text's
        own declared line-height rather than restating the multiplier here,
        so changing the leading is one edit and not two.
        """

        text = effective(".transcript-text")
        text_size = rem(text["font-size"])
        leading = float(text["line-height"])

        row_line_height = rem(effective(".transcript-count-row")["line-height"])

        assert row_line_height == pytest.approx(text_size * leading)


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
        all -- the actions and the index both ride the timing row instead
        (see TestCaptionActions), so subtitleMode has nothing left to say
        about the cell's own layout, padding-left included.
        """

        selectors = {selector for selectors, _ in rules() for selector in selectors}

        assert ".transcript-subtitle-mode .transcript-cell" not in selectors


class TestVideoSubtitleOverlay:
    """
    The overlay sits above the video's own native controls, not over them --
    a percentage offset once put it there on a short or wide video, since
    the control bar's own height is fixed while a percentage of the frame's
    height is not, and shrinks below it.
    """

    def test_it_sits_at_the_foot_of_the_frame(self):
        """
        Where a viewer would see it. It only moves up while the player's own
        control bar is up, so the rest of the time the preview is where the
        real thing is.
        """

        assert rem(effective(".video-subtitle-overlay")["bottom"]) == 1

    def test_it_clears_the_control_bar_while_that_is_up(self):
        raised = effective(".video-controls-visible .video-subtitle-overlay")

        assert rem(raised["bottom"]) > rem(
            effective(".video-subtitle-overlay")["bottom"]
        )

    def test_the_offset_is_fixed_not_a_percentage(self):
        bottom = effective(".video-subtitle-overlay")["bottom"]

        assert not bottom.endswith("%")

    def test_it_never_captures_a_click(self):
        """
        Belt and suspenders alongside the fixed offset above -- clicks (the
        seek bar, a click-to-pause) always reach the video underneath, even
        if the two ever end up overlapping regardless.
        """

        assert effective(".video-subtitle-overlay")["pointer-events"] == "none"

    def test_a_line_never_wraps(self):
        """
        draw_overlay gives each of the caption's own lines an element, so a
        wrap inside one of them is a break the subtitle file does not have --
        the overlay stops being a preview of what a viewer sees.
        """

        assert effective(".video-subtitle-line")["white-space"] == "nowrap"

    def test_the_type_is_sized_against_the_frame(self):
        """
        What keeps the nowrap above from overflowing: the font shrinks with
        the frame so a line of the guideline's full length fits, capped at
        1rem so a wide video keeps an ordinary subtitle. The frame has to be
        a container of its own for cqi to resolve against it.
        """

        font_size = effective(".video-subtitle-overlay")["font-size"]

        assert "cqi" in font_size
        assert "--subtitle-char-limit" in font_size
        assert font_size.startswith("min(1rem,")
        assert effective(".video-frame")["container-type"] == "inline-size"


class TestTheInformationRows:
    """
    Each figure in the information dialog is a small heading with its value
    under it, not a name in one column and a value in another: the
    two-column form gave every label a fixed 8rem whatever it said, and the
    filename -- the one value with no room to spare -- got what was left.
    """

    def rule(self, selector: str) -> str:
        from utils.styles import theme_styles

        rule = theme_styles[theme_styles.index(f"{selector} {{"):]

        return rule[: rule.index("}")]

    def test_a_row_stacks(self):
        rule = self.rule(".editor-info-row")

        assert "flex-direction: column" in rule

    def test_the_label_heads_it(self):
        rule = self.rule(".editor-info-label")

        assert "font-weight: 600" in rule
        assert "var(--color-text-primary)" in rule

    def test_the_explanation_cannot_be_read_as_a_figure(self):
        rule = self.rule(".editor-info-explanation")

        assert "font-style: italic" in rule

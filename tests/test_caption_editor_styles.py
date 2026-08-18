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
The highlight layer sits behind the caption text area and has to line up with
it character for character. That is a property of the stylesheet, so it is
guarded here: the failure mode is a silent visual one that no behavioural test
would catch.
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


class TestSharedTextMetrics:
    """
    Anything that decides where a character lands must be set on both layers
    by the same rule, never inherited.
    """

    @pytest.mark.parametrize(
        "prop",
        ["font-size", "line-height", "letter-spacing", "padding",
         "white-space", "overflow-wrap"],
    )
    def test_metric_is_shared_by_both_layers(self, prop):
        shared = re.search(
            r"\.caption-highlights,\s*\.caption-editor \.caption-entry "
            r"\.q-field__native \{([^}]*)\}",
            default_styles,
        )

        assert shared, "the two layers no longer share one metrics rule"
        assert prop in shared.group(1), f"{prop} is not shared, so it can drift"


class TestMarkedWordsAreLayoutNeutral:
    """
    A marked word in the layer may only paint. Anything that takes up space
    widens it and pushes the rest of the line out of step with the text area;
    anything that gives it a colour draws the word a second time under the one
    the reader is typing.
    """

    def test_read_view_styling_is_neutralised(self):
        applied = effective(".caption-highlights .review-word")

        assert applied["color"] == "transparent"
        assert applied["padding"] == "0"
        assert applied["border"] == "0"

    def test_flag_paints_with_background_and_shadow_only(self):
        """
        Background and inset shadow are the only visible properties that cost
        no space.
        """

        applied = effective(".caption-highlights .review-word")

        assert applied["background-color"] == "var(--color-review-bg)"
        assert applied["box-shadow"].startswith("inset")
        # Whatever else it sets must not take up space.
        assert applied["padding"] == "0"
        assert applied["border"] == "0"
        assert "font-size" not in applied
        assert "margin" not in applied

    def test_layer_hides_its_text(self):
        assert effective(".caption-highlights")["color"] == "transparent"

    def test_no_tooltip_behind_the_text_area(self):
        assert effective(".caption-highlights .review-word::after")["content"] == "none"


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


class TestCaptionActionButtons:
    """
    Split, Merge prev, Merge next, Close, Add and Delete, which repeat under
    every open caption. They share .editor-btn with the toolbar buttons above
    them and then narrow it, so what matters is that the narrowing actually
    takes -- by weight, not by ordering.
    """

    def test_they_are_sized_to_their_labels(self):
        """
        They used to be given a floor of 100px each and told to share the row
        out between them, which is what made them large.
        """

        applied = effective(".editor-caption-btn")

        assert applied["min-width"] == "0 !important"
        assert applied["flex"] == "0 0 auto"

    def test_they_are_smaller_than_a_default_button(self):
        applied = effective(".editor-caption-btn")
        size = int(re.match(r"(\d+)", applied["font-size"]).group(1))

        # Quasar's own button text is 14px.
        assert size < 14
        assert int(re.match(r"(\d+)", applied["min-height"]).group(1)) <= 28

    def test_the_row_gap_is_not_doubled(self):
        """
        Quasar gives every button a margin of its own, and the row already has a
        gap; both would space them twice as far apart as intended.
        """

        assert effective(".editor-caption-btn")["margin"] == "0 !important"

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_the_caption_look_outweighs_the_toolbar_look(self, theme):
        assert specificity(
            f".body--{theme} .q-btn.editor-btn.editor-caption-btn"
        ) > specificity(f".body--{theme} .q-btn.editor-btn")

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_delete_is_the_danger_colour_on_its_label_too(self, theme):
        """
        .editor-btn paints .q-btn__content explicitly, so a colour set on the
        button alone never reaches the label -- which is why Delete carried an
        inline style that did nothing.
        """

        for target in ("", " .q-btn__content", " .q-icon"):
            selector = (
                f".body--{theme} .q-btn.editor-caption-btn.caption-btn-danger{target}"
            )

            assert effective(selector)["color"] == "var(--color-text-danger) !important"
            assert specificity(selector) > specificity(
                f".body--{theme} .q-btn.editor-btn{target}"
            )

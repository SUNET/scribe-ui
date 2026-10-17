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
Colour of the toasts ui.notify raises (WCAG 1.4.3, 1.4.11, 2.4.7).

Quasar paints a toast from its own palette, so the background is not in this
repository -- the four values below are what Quasar 2 ships and what a toast
measured in the browser, one per type. The stylesheet decides everything drawn
on top of them: the message, the icon, the Close button and its focus ring.
A wrong pairing is a silent visual failure, so the arithmetic is guarded here.
"""

import re

import pytest

from utils.styles import default_styles

# Quasar's own colours for the four toast types.
BACKGROUNDS = {
    "warning": "#f2c037",
    "negative": "#c10015",
    "positive": "#21ba45",
    "info": "#31ccec",
}


def rules():
    """
    Every rule in the stylesheet, as (selectors, declarations).

    Comments come out first: they contain commas and semicolons, which would
    otherwise be read as selectors and declarations of their own.
    """

    css = re.sub(r"/\*.*?\*/", "", default_styles, flags=re.S)

    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [part.strip() for part in match.group(1).split(",") if part.strip()]
        yield selectors, match.group(2)


def declared(selector: str) -> dict:
    """The properties the stylesheet gives a selector, later rules winning."""

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


def channels(colour: str) -> tuple:
    colour = colour.replace("!important", "").strip()
    assert re.fullmatch(r"#[0-9a-f]{6}", colour), colour
    return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))


def luminance(colour: str) -> float:
    def linear(value: int) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(value) for value in channels(colour))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def text_colour(kind: str) -> str:
    return declared(f".q-notification.bg-{kind}")["color"]


class TestToastText:
    """The message, and the icon that takes its colour."""

    @pytest.mark.parametrize("kind", sorted(BACKGROUNDS))
    def test_every_type_clears_4_5_to_1(self, kind):
        assert contrast(text_colour(kind), BACKGROUNDS[kind]) >= 4.5

    def test_each_type_has_a_rule_of_its_own(self):
        """A type left out falls back to Quasar's white, which fails on three of four."""

        for kind in BACKGROUNDS:
            assert text_colour(kind)

    def test_the_ratios_are_the_ones_measured_in_the_browser(self):
        """Guards the arithmetic itself against the figures taken from a toast."""

        assert contrast("#1d1d1d", BACKGROUNDS["warning"]) == pytest.approx(9.93, abs=0.01)
        assert contrast("#ffffff", BACKGROUNDS["negative"]) == pytest.approx(6.41, abs=0.01)
        assert contrast("#1d1d1d", BACKGROUNDS["positive"]) == pytest.approx(6.56, abs=0.01)
        assert contrast("#1d1d1d", BACKGROUNDS["info"]) == pytest.approx(8.81, abs=0.01)

    def test_the_old_colours_would_have_failed(self):
        """What the toasts had before: white on green and cyan, and the two button colours."""

        assert contrast("#ffffff", BACKGROUNDS["positive"]) < 3
        assert contrast("#ffffff", BACKGROUNDS["info"]) < 2
        assert contrast("#5898d4", BACKGROUNDS["warning"]) < 2
        assert contrast("#e6e8eb", BACKGROUNDS["warning"]) < 1.5


class TestToastCloseButton:
    """The button takes the toast's own colour, so it clears whatever the toast is painted with."""

    ACTIONS = ".q-notification .q-notification__actions .q-btn.q-btn--flat"

    def test_the_label_inherits_the_text_colour(self):
        assert declared(self.ACTIONS)["color"] == "inherit !important"

    def test_the_actions_container_is_reset_too(self):
        """
        Quasar paints the container that holds the button in its own primary blue
        (#5898d4), and the button reads its colour from there, so inheriting
        alone passed the blue straight through -- measured, not assumed.
        """

        container = declared(".q-notification .q-notification__actions")
        assert container["color"] == "inherit !important"

    def test_the_label_text_and_icon_inherit_it_too(self):
        """
        The global dark-mode flat-button rule names these children directly, and
        a colour set on a parent is overridden, not inherited away, by one that
        names the child.
        """

        for child in (".q-btn__content", ".block", ".q-icon"):
            assert declared(f"{self.ACTIONS} {child}")["color"] == "inherit !important"

    def test_the_dark_border_follows_the_text_colour(self):
        """The dark-mode rule's grey border measured about 2:1 on the yellow toast."""

        border = declared(f".body--dark {self.ACTIONS}")
        assert border["border-color"] == "currentColor !important"

    def test_the_focus_ring_follows_the_text_colour(self):
        """
        The global ring is the brand colour: 2.25:1 on the red toast in light mode
        and 1.15-2.16:1 on all four in dark, under the 3:1 a focus indicator needs.
        """

        ring = declared(f"{self.ACTIONS}:focus-visible")
        assert ring["outline-color"] == "currentColor !important"

    def test_the_overrides_sit_in_the_theme_layer(self):
        """
        They beat !important rules, Quasar's and the dark-mode flat button's, and
        a layered !important beats an unlayered one whatever the specificity.
        """

        css = re.sub(r"/\*.*?\*/", "", default_styles, flags=re.S)
        start = css.index(".q-notification.bg-warning")
        before = css[:start]

        assert before.rstrip().endswith("@layer theme {")


class TestToastWidth:
    """
    Every toast is one width. Quasar sizes one to its message, which measured
    189-866px across a handful of the app's own messages.
    """

    STANDARD = ".q-notification.q-notification--standard"
    MULTI_LINE = ".q-notification.q-notification--multi-line"

    def width_rule(self) -> dict:
        for selectors, declarations in rules():
            if self.STANDARD in selectors and self.MULTI_LINE in selectors:
                return dict(
                    part.partition(":")[::2]
                    for part in (d.strip() for d in declarations.split(";"))
                    if ":" in part
                )
        raise AssertionError("no shared width rule for standard and multi-line toasts")

    def test_both_layouts_get_the_same_width(self):
        """A toast with two actions is multi-line; it must not stand out."""

        rule = {k.strip(): v.strip() for k, v in self.width_rule().items()}
        assert rule["width"] == "min(26rem, calc(100vw - 20px))"

    def test_it_is_never_wider_than_the_window_less_the_margins(self):
        """Quasar gives a toast 10px each side; at 320px the toast has to fit."""

        rule = {k.strip(): v.strip() for k, v in self.width_rule().items()}
        assert "calc(100vw - 20px)" in rule["width"]

    def test_quasars_own_cap_is_lifted(self):
        """Its 65vw would leave a narrow window's toast too small to read."""

        rule = {k.strip(): v.strip() for k, v in self.width_rule().items()}
        assert rule["max-width"] == "none"

    def test_it_beats_quasars_selector_on_its_own(self):
        """Two classes against Quasar's one, so the order of the sheets does not matter."""

        assert self.STANDARD.count(".q-") == 2
        assert self.MULTI_LINE.count(".q-") == 2

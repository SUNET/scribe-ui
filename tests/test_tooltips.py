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

"""Tooltips on one line where they fit: the menu's beside it, and none cut short by Quasar's rounding."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMON = (ROOT / "utils" / "common.py").read_text()
STYLES = (ROOT / "utils" / "styles.py").read_text()


def rule(selector: str) -> str:
    at = STYLES.index(f"\n    {selector} {{")

    return STYLES[at : STYLES.index("}", at)]


def test_our_limit_over_quasars_rounded_one():
    tooltip = rule(".q-tooltip")
    assert "max-width: min(320px, calc(100vw - 32px)) !important;" in tooltip
    # Still as wide as its text, and wrapping between words when long.
    assert "width: max-content;" in tooltip
    assert "white-space: normal;" in tooltip


def test_the_menus_tooltips_beside_the_rail():
    assert """ui.tooltip(text).props('anchor="center right" self="center left" :offset="[8, 0]"')""" in COMMON
    assert "t = menu_tooltip(label)" in COMMON
    assert 't = menu_tooltip("API documentation")' in COMMON
    # Every tooltip in the menu goes through it.
    menu = COMMON[COMMON.index("def menu_link(") : COMMON.index("menu_btn_tooltip = ui.tooltip(")]
    assert "ui.tooltip(" not in menu

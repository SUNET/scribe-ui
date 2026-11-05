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

"""User settings (pages/user.py) on a phone and on a wide page."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "user.py").read_text()
STYLES = (ROOT / "utils" / "styles.py").read_text()


def rule(selector: str) -> str:
    at = STYLES.index(f"\n    {selector} {{") + 1

    return STYLES[at : STYLES.index("}", at)]


def narrow() -> str:
    at = STYLES.index("    @container (max-width: 24rem) {\n        .user-profile-row {")

    return STYLES[at : at + 600]


class TestTheColumns:
    def test_side_by_side_where_both_fit_one_above_the_other_otherwise(self):
        assert PAGE.count('ui.column().classes("user-settings-column")') == 2
        assert "flex: 1 1 22rem;" in rule(".user-settings-column")
        assert "min-width: 0;" in rule(".user-settings-column")
        assert "container-type: inline-size;" in rule(".user-settings-column")


class TestTheProfile:
    def test_icon_name_value_in_columns(self):
        assert PAGE.count('ui.element("div").classes("user-profile-row")') == 4
        assert "grid-template-columns: 1.25rem 9rem minmax(0, 1fr);" in rule(".user-profile-row")
        assert 'min-width: 140px' not in PAGE

    def test_the_value_under_the_name_on_a_narrow_column(self):
        assert "grid-template-columns: 1.25rem minmax(0, 1fr);" in narrow()
        assert "grid-column: 2;" in narrow()
        assert "overflow-wrap: anywhere;" in rule(".user-profile-value")

    def test_the_icons_are_not_read_out(self):
        profile = PAGE[PAGE.index('ui.label("Profile")') : PAGE.index("# -- Email section --")]
        assert profile.count('.classes("user-profile-icon").props("aria-hidden=true")') == 4


class TestTheEmail:
    def test_the_field_takes_the_room_and_the_button_goes_under_it(self):
        assert 'ui.element("div").classes("user-email-row mt-2 mb-6")' in PAGE
        assert 'classes("user-email-field")' in PAGE and "min-width: 300px" not in PAGE
        assert "grid-template-columns: 1.25rem minmax(0, 1fr) auto;" in rule(".user-email-row")
        assert ".user-email-row > .q-btn {\n            grid-column: 2;" in narrow()


class TestHeadings:
    def test_the_sections_are_headings(self):
        for name in ("Profile", "Email", "Notifications"):
            assert f'ui.label("{name}").classes("text-lg font-semibold mb-2").props("role=heading aria-level=2")' in PAGE
        assert 'ui.label("Theme").classes("text-lg font-semibold mb-2").props("role=heading aria-level=2")' in PAGE
        assert 'ui.label(name).classes("text-lg font-semibold mb-2").props("role=heading aria-level=2")' in PAGE

    def test_personal_and_administration_under_notifications(self):
        assert PAGE.count('.props("role=heading aria-level=3")') == 2


class TestTheTokenDialog:
    def test_no_wider_than_a_phone(self):
        assert 'ui.card().classes("user-token-card")' in PAGE
        assert "min-width: 500px" not in PAGE
        assert "width: min(32rem, 100%);" in rule(".user-token-card")

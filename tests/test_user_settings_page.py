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

"""User settings (pages/user.py): the cards, on a phone and on a wide page."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "user.py").read_text()
STYLES = (ROOT / "utils" / "styles.py").read_text()


def rule(selector: str) -> str:
    at = STYLES.index(f"\n    {selector} {{") + 1

    return STYLES[at : STYLES.index("}", at)]


def block(start: str, length: int = 900) -> str:
    at = STYLES.index(start)

    return STYLES[at : at + length]


class TestTheCards:
    def test_four_cards_each_with_a_heading(self):
        for title in ("Account", "Email notifications", "Theme"):
            assert f'card("' in PAGE and f'"{title}",' in PAGE, title
        assert 'ui.label("Connected services").classes("settings-card-title").props(' in PAGE
        assert 'ui.label(title).classes("settings-card-title").props("role=heading aria-level=2")' in PAGE

    def test_in_the_page_as_the_columns_are_read(self):
        """Left column top to bottom, then the right: the keyboard's order on a wide page."""

        account = PAGE.index('card("account_circle", "Account",')
        theme = PAGE.index('card("palette", "Theme",')
        services = PAGE.index('drive_section = ui.element("section")')
        notifications = PAGE.index('card("notifications", "Email notifications",')
        assert account < theme < services < notifications
        assert PAGE.count('ui.element("div").classes("settings-column")') == 2
        right = PAGE.rindex('ui.element("div").classes("settings-column")')
        assert services < right < notifications

    def test_two_columns_on_a_wide_page_one_on_a_phone(self):
        assert "grid-template-columns: minmax(0, 1fr);" in rule(".settings-grid")
        wide = block("    @container (min-width: 52rem) {\n        .settings-grid {")
        assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in wide
        assert "grid-row" not in wide  # no placing: the columns are the page's own order
        assert "flex-direction: column;" in rule(".settings-column")
        assert "container-type: inline-size;" in rule(".settings")


class TestTheAccount:
    def test_who_is_signed_in_without_initials(self):
        assert 'ui.label("Signed in as")' in PAGE
        assert 'ui.label(userdata["username"]).classes("settings-identity-name")' in PAGE
        assert 'ui.label("Administrator").classes("settings-role")' in PAGE
        assert "avatar" not in PAGE

    def test_the_details_are_a_list(self):
        assert 'ui.element("dl").classes("settings-list")' in PAGE
        assert 'with ui.element("dt"):' in PAGE and 'with ui.element("dd"):' in PAGE
        for name in ("User ID", "Transcribed time", "Time zone"):
            assert f'("{name}",' in PAGE

    def test_the_api_token_has_a_button_of_its_own(self):
        assert 'ui.button("Show token", icon="key", on_click=show_user_token)' in PAGE
        assert "user-token-btn" not in PAGE and "user-token-btn" not in STYLES
        assert "width: min(32rem, 100%);" in rule(".user-token-card")


class TestTheNotifications:
    def test_the_address_with_the_choices(self):
        notifications = PAGE[PAGE.index('"Email notifications",') :]
        assert 'ui.input("Email address", value=current_email)' in notifications
        assert 'ui.button("Send test and save", on_click=lambda: email_save(email.value))' in notifications

    def test_what_each_is_for_is_on_the_page_not_in_a_tooltip(self):
        assert ".tooltip(" not in PAGE
        for text in (
            "When one of your transcriptions has finished.",
            "24 hours before one of your files is deleted.",
            "When a new account is waiting to be enabled.",
            "When a group or account is close to its monthly limit or quota.",
            "A weekly email with this month's transcription use.",
        ):
            assert text in PAGE, text
        assert 'box._props["aria-describedby"] = text.html_id' in PAGE

    def test_saved_when_changed_by_keyboard_too(self):
        assert "ui.checkbox(label, value=value, on_change=on_change)" in PAGE
        assert '.on(\n                        "click",' not in PAGE

    def test_groups_named_by_their_headings(self):
        assert """ui.element("div").classes("settings-group").props('role="group"')""" in PAGE
        assert 'block._props["aria-labelledby"] = title.html_id' in PAGE
        assert '"role=heading aria-level=3"' in PAGE
        assert 'group("Administration", "Only administrators see these.")' in PAGE


class TestTheTheme:
    def test_real_radio_buttons_named_by_their_tiles(self):
        assert """'role=radiogroup aria-label="Theme"'""" in PAGE
        assert 'ui.element("label").classes("settings-theme-choice")' in PAGE
        assert 'f"type=radio name=theme value={key}"' in PAGE
        assert '("auto", "brightness_auto", "Match system")' in PAGE

    def test_one_dark_mode_element_for_the_page(self):
        """A new ui.dark_mode each time left the page dark from dark back to light."""

        theme = PAGE[PAGE.index("def apply(dark)") : PAGE.index("# Real radio buttons")]
        assert "element = page_dark_mode()" in theme and "element.value = dark" in theme
        assert theme.count("ui.dark_mode(") == 1  # only where page_init made none
        common = (ROOT / "utils" / "common.py").read_text()
        assert "_remember_dark_mode(dark_mode_el)" in common
        assert "def page_dark_mode():" in common

    def test_the_chosen_tile_is_framed_and_the_focus_seen(self):
        assert ".settings-theme-choice:has(input:checked)" in STYLES
        assert ".settings-theme-choice:has(input:focus-visible)" in STYLES
        assert "opacity: 0;" in rule(".settings-theme-choice input")


class TestTheServices:
    def test_only_where_the_organisation_offers_drive(self):
        assert "drive_section.set_visibility(False)" in PAGE
        assert "section.set_visibility(True)" in PAGE

    def test_the_state_is_said_when_it_changes(self):
        assert 'state = ui.label("").classes("settings-status").props(\n                        "role=status aria-live=polite"' in PAGE
        assert 'f"Log out from {name}"' in PAGE


class TestTargets:
    def test_buttons_and_tiles_big_enough_to_hit(self):
        assert "min-height: 44px;" in rule(".settings-button")
        assert "min-height: 44px;" in rule(".settings-theme-choice")

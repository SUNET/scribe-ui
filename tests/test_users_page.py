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

"""The Users page (pages/admin/users.py) on a phone and on a wide page."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "admin" / "users.py").read_text()
STYLES = (ROOT / "utils" / "styles.py").read_text()


def rule(selector: str) -> str:
    at = STYLES.index(f"    {selector} {{")

    return STYLES[at : STYLES.index("}", at)]


def phone() -> str:
    at = STYLES.index("    /* A phone: the users as cards")

    return STYLES[at : at + 900]


class TestOnAPhone:
    def test_each_user_is_a_card_as_the_files_are_on_home(self):
        assert """users_table.props(':grid="window.innerWidth < 700"')""" in PAGE
        assert 'users_table.add_slot(\n        "item",' in PAGE
        assert 'class="jobs-card user-card"' in PAGE

    def test_the_card_has_its_checkbox_named_for_the_user(self):
        item = PAGE[PAGE.index('"item",') :]
        assert """:aria-label="'Select ' + props.row.username\"""" in item
        assert 'v-model="props.selected"' in item

    def test_the_card_says_what_the_columns_say(self):
        item = PAGE[PAGE.index('"item",') :]
        for field in ("username", "realm", "status", "groups", "admin_domains"):
            assert f"props.row.{field}" in item, field
        assert 'v-if="props.row.groups"' in item and 'v-if="props.row.admin_domains"' in item

    def test_one_status_line_for_three_columns(self):
        assert '"Admin" if user["admin"] == "Yes" else ""' in PAGE
        assert '"Active" if user["active"] == "Yes" else "Disabled"' in PAGE
        assert "f\"{user['provisioning']} provisioning\"" in PAGE

    def test_lists_read_as_a_comma_and_a_space(self):
        assert 'for field in ("groups", "admin_domains"):' in PAGE
        assert '", ".join(str(item) for item in user[field])' in PAGE

    def test_the_list_is_as_long_as_it_is_and_the_search_comes_first(self):
        block = phone()
        assert "height: auto;" in block
        assert "order: -1;" in block and "flex: 1 1 100%;" in block
        assert "flex: 1 1 0;" in block


class TestTheBar:
    def test_the_title_is_above_the_table_not_in_it(self):
        title = PAGE.index('ui.label("Users").classes("text-3xl font-bold").props("role=heading aria-level=1")')
        assert title < PAGE.index("users_table = ui.table(")
        assert 'add_slot("top-left")' not in PAGE

    def test_actions_and_search_in_one_bar(self):
        assert 'users_table.add_slot("top")' in PAGE
        assert 'ui.element("div").classes("users-toolbar")' in PAGE
        assert 'ui.element("div").classes("users-actions")' in PAGE
        assert '"users-search"' in PAGE
        assert "flex-wrap: wrap;" in rule(".users-toolbar")

    def test_buttons_big_enough_to_hit_and_no_fixed_width(self):
        assert "min-height: 44px;" in rule(".users-actions .q-btn")
        assert 'style(\n                "width: 150px"' not in PAGE and '"width: 150px"' not in PAGE

    def test_the_height_and_size_in_the_stylesheet(self):
        assert "height: calc(100vh - 160px - var(--banner-offset, 0px));" in rule(".users-table")
        assert "height: calc(100vh - 100px" not in PAGE

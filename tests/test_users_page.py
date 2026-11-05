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

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "admin" / "users.py").read_text()
STYLES = (ROOT / "utils" / "styles.py").read_text()


def rule(selector: str) -> str:
    at = STYLES.index(f"    {selector} {{")

    return STYLES[at : STYLES.index("}", at)]


def phone() -> str:
    at = STYLES.index("    /* A phone: the users as cards")

    return STYLES[at : at + 1300]


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
        assert 'user["active"] = "Enabled" if user.get("active", True) else "Disabled"' in PAGE
        assert '                    user["active"],' in PAGE

    def test_status_in_the_words_of_the_buttons(self):
        assert '"name": "active",\n                "label": "Status",' in PAGE
        assert '"label": "Active"' not in PAGE
        assert "f\"{user['provisioning']} provisioning\"" in PAGE

    def test_lists_read_as_a_comma_and_a_space(self):
        assert 'for field in ("groups", "admin_domains"):' in PAGE
        assert '", ".join(str(item) for item in user[field])' in PAGE

    def test_the_list_is_as_long_as_it_is_and_the_search_comes_first(self):
        block = phone()
        assert "height: auto;" in block
        assert "order: -2;" in block and "flex: 1 1 100%;" in block
        assert ".users-find-group {\n            order: -2;" in block
        assert "flex: 1 1 0;" in block


class TestTheBar:
    def test_the_title_on_the_left_the_controls_on_the_right(self):
        header = PAGE[PAGE.index('with ui.element("div").classes("users-header"):') :]
        assert header.index('ui.label("Users").classes("text-3xl font-bold users-title")') < header.index("users-toolbar")
        assert "justify-content: space-between;" in rule(".users-header")
        assert "justify-content: flex-end;" in rule(".users-toolbar")
        assert 'add_slot("top-left")' not in PAGE

    def test_actions_and_search_in_one_bar(self):
        assert 'users_table.add_slot("top")' in PAGE
        assert 'ui.element("div").classes("users-toolbar")' in PAGE
        assert 'ui.element("div").classes("users-actions")' in PAGE
        assert '"users-search"' in PAGE
        assert "flex-wrap: wrap;" in rule(".users-toolbar")
        assert "align-items: flex-start;" in rule(".users-toolbar")
        assert "align-items: flex-start;" in rule(".users-header")

    def test_buttons_big_enough_to_hit_and_no_fixed_width(self):
        assert "min-height: 44px;" in rule(".users-actions .q-btn")
        assert 'style(\n                "width: 150px"' not in PAGE and '"width: 150px"' not in PAGE

    def test_the_height_and_size_in_the_stylesheet(self):
        assert "height: calc(100vh - 160px - var(--banner-offset, 0px));" in rule(".users-table")
        assert "height: calc(100vh - 100px" not in PAGE


class TestFilters:
    def test_status_admin_provisioning_and_realm_where_there_are_several(self):
        assert '("active", "Status", {"": "All", "Enabled": "Enabled", "Disabled": "Disabled"})' in PAGE
        assert '("admin", "Admin", {"": "All", "Yes": "Admins", "No": "Not admins"})' in PAGE
        assert '("provisioning", "Provisioning", {"": "All", "Auto": "Auto", "Manual": "Manual"})' in PAGE
        assert "if len(realms) > 1:" in PAGE

    def test_group_with_no_group_wherever_there_are_groups(self):
        assert '("group", "Group", {"": "All", "__none__": "No group", **{name: name for name in group_names}})' in PAGE
        assert "if group_names:" in PAGE
        assert "users-filter-group" not in PAGE and "users-filter-group" not in STYLES

    def test_long_lists_can_be_typed_into(self):
        assert 'with_input=key in ("realm", "group"),' in PAGE

    def test_a_groups_own_comma_is_not_a_separator(self):
        assert 'user["group_list"] = (' in PAGE
        assert "else ([str(groups)] if groups else [])" in PAGE

    def test_each_filter_has_a_visible_label(self):
        assert "label=label," in PAGE

    def test_the_filter_method(self):
        method = PAGE[PAGE.index('FILTER_METHOD = """') :]
        method = method[: method.index('"""\n', 20)]
        assert '["active", "admin", "provisioning", "realm"].every' in method
        assert "cols.some((col) =>" in method
        assert "JSON.parse(terms)" in method
        assert 'users_table._props[":filter-method"] = FILTER_METHOD' in PAGE
        assert "users_table.filter = json.dumps(asked)" in PAGE
        # The search no longer binds the filter as a bare string.
        assert 'bind_value(users_table, "filter")' not in PAGE

    def test_how_many_are_shown_is_said(self):
        assert "ui.label(\"\").classes(\"users-count text-theme-secondary\").props('role=status aria-live=polite')" in PAGE
        method = PAGE[PAGE.index('FILTER_METHOD = """') :]
        assert '"Showing " + shown.length + " of " + all' in method

    def test_behind_a_filter_button(self):
        assert 'ui.button(icon="filter_alt", color=None)' in PAGE
        assert "color: var(--color-text-primary);" in rule(".users-filter-toggle")
        assert '.users-filter-toggle[aria-expanded="true"]' in STYLES
        assert 'toggle._props["aria-label"] = "Filters"' in PAGE
        assert 'toggle._props["aria-expanded"] = "true" if opened else "false"' in PAGE
        assert "panel.set_visibility(False)" in PAGE
        assert "min-height: 44px;" in rule(".users-filter-toggle")

    def test_the_button_says_how_many_filters_are_in_use(self):
        assert 'f"Filters, {in_use} in use"' in PAGE
        assert "badge.set_visibility(in_use > 0)" in PAGE

    def test_filters_can_be_cleared(self):
        assert 'ui.button("Clear filters", on_click=clear_filters, color=None)' in PAGE
        assert "color: var(--color-brand-primary);" in rule(".users-filter-clear")

    def test_all_filters_one_size_and_clear_in_the_cell_after_them(self):
        assert "grid-column: -2 / -1;" in rule(".users-filter-clear")
        assert 'classes("users-filter")' in PAGE

    def test_two_filters_to_a_line_in_a_box_under_the_search(self):
        assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in rule(".users-filters")
        assert "border: 1px solid var(--color-border-subtle);" in rule(".users-filters")
        assert "flex-direction: column;" in rule(".users-find-group")

    def test_search_button_and_filters_in_one_group_in_that_order(self):
        group = PAGE[PAGE.index('with ui.element("div").classes("users-find-group"):') :]
        search = group.index('placeholder="Search"')
        toggle = group.index('ui.button(icon="filter_alt"')
        panel = group.index('panel = ui.element("div").classes("users-filters")')
        clear = group.index('ui.button("Clear filters"')
        assert search < toggle < panel < clear
        # The actions come before the group, as on the screen.
        assert PAGE.index('ui.element("div").classes("users-actions")') < PAGE.index('classes("users-find-group")')

    def test_the_panel_is_a_group_named_by_its_button(self):
        assert 'toggle._props["aria-controls"] = f"c{panel.id}"' in PAGE
        assert 'panel._props["aria-labelledby"] = f"c{toggle.id}"' in PAGE
        assert """.props('role="group"')""" in PAGE


def run_filter(rows: list, asked: dict) -> list:
    """FILTER_METHOD run in node on made-up rows; the user names it keeps."""

    from pages.admin.users import FILTER_METHOD

    script = (
        "global.document = { querySelector: () => null };\n"
        f"const filter = {FILTER_METHOD};\n"
        f"const rows = {json.dumps(rows)};\n"
        "const cols = Object.keys(rows[0]);\n"
        f"const shown = filter(rows, {json.dumps(json.dumps(asked))}, cols, (col, row) => row[col]);\n"
        "console.log(JSON.stringify(shown.map((row) => row.username)));\n"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)

    return json.loads(out.stdout)


ROWS = [
    {"username": "anna.berg@su.se", "realm": "su.se", "active": "Enabled", "admin": "No", "provisioning": "Auto",
     "group_list": ["Humsam"]},
    {"username": "erik.lund@gu.se", "realm": "gu.se", "active": "Disabled", "admin": "Yes", "provisioning": "Manual",
     "group_list": ["Humsam", "Krishantering, styrning och samverkan"]},
    {"username": "anna.ek@gu.se", "realm": "gu.se", "active": "Disabled", "admin": "No", "provisioning": "Auto",
     "group_list": []},
    {"username": "a+b(c)@x.se", "realm": "x.se", "active": "Enabled", "admin": "No", "provisioning": "Auto",
     "group_list": []},
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
class TestTheFilterInTheBrowser:
    def test_a_plain_word_anywhere_in_any_column(self):
        assert run_filter(ROWS, {"q": "ANNA"}) == ["anna.berg@su.se", "anna.ek@gu.se"]
        assert run_filter(ROWS, {"q": "gu.se"}) == ["erik.lund@gu.se", "anna.ek@gu.se"]

    def test_wildcards_are_the_whole_cell(self):
        assert run_filter(ROWS, {"q": "*@su.se"}) == ["anna.berg@su.se"]
        assert run_filter(ROWS, {"q": "anna*"}) == ["anna.berg@su.se", "anna.ek@gu.se"]
        assert run_filter(ROWS, {"q": "anna.??@gu.se"}) == ["anna.ek@gu.se"]
        assert run_filter(ROWS, {"q": "*"}) == [row["username"] for row in ROWS]

    def test_the_rest_of_a_pattern_is_taken_as_it_is(self):
        assert run_filter(ROWS, {"q": "a+b(c)*"}) == ["a+b(c)@x.se"]
        assert run_filter(ROWS, {"q": "anna.berg@su?se"}) == ["anna.berg@su.se"]
        assert run_filter(ROWS, {"q": "anna.berg@su.s"}) == ["anna.berg@su.se"]  # plain: anywhere

    def test_a_group_and_no_group(self):
        assert run_filter(ROWS, {"group": "Humsam"}) == ["anna.berg@su.se", "erik.lund@gu.se"]
        assert run_filter(ROWS, {"group": "Krishantering, styrning och samverkan"}) == ["erik.lund@gu.se"]
        assert run_filter(ROWS, {"group": "__none__"}) == ["anna.ek@gu.se", "a+b(c)@x.se"]
        assert run_filter(ROWS, {"group": "__none__", "realm": "gu.se"}) == ["anna.ek@gu.se"]

    def test_the_filters_and_the_search_together(self):
        assert run_filter(ROWS, {"active": "Disabled"}) == ["erik.lund@gu.se", "anna.ek@gu.se"]
        assert run_filter(ROWS, {"active": "Disabled", "realm": "gu.se", "admin": "No"}) == ["anna.ek@gu.se"]
        assert run_filter(ROWS, {"active": "Enabled", "q": "anna*"}) == ["anna.berg@su.se"]
        assert run_filter(ROWS, {"provisioning": "Manual"}) == ["erik.lund@gu.se"]


class TestTheSameWordsOnTheEditGroupPage:
    def test_members_status_is_enabled_or_disabled(self):
        groups = (ROOT / "pages" / "admin" / "groups.py").read_text()
        edit = groups[groups.index("async def edit_group") :]

        assert 'user["active"] = "Enabled" if user.get("active", True) else "Disabled"' in edit
        assert '"name": "active",\n                    "label": "Status",' in edit
        assert '"label": "Active"' not in groups

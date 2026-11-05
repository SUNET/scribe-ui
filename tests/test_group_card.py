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

"""The group cards on the Groups page (utils/group.py, Group.create_card)."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARD = (ROOT / "utils" / "group.py").read_text()
CARD = CARD[CARD.index("    def create_card(self)") :]
STYLES = (ROOT / "utils" / "styles.py").read_text()
GROUPS = (ROOT / "pages" / "admin" / "groups.py").read_text()


def rule(selector: str) -> str:
    at = STYLES.index(f"    {selector} {{")

    return STYLES[at : STYLES.index("}", at)]




class TestWhatIsOnIt:
    def test_the_name_is_a_heading(self):
        assert "self.name_and_description()" in CARD

    def test_details_in_one_line_on_a_wide_card_one_to_a_line_on_a_narrow(self):
        assert 'with ui.element("div").classes("group-meta-wrap"):' in CARD
        assert 'with ui.element("div").classes("group-meta-line"):' in CARD
        assert "flex-direction: column;" in rule(".group-meta-line")
        assert "overflow: hidden;" in rule(".group-meta-wrap")
        wide = STYLES[STYLES.index("    @container (min-width: 36rem) {\n        .group-meta-line {") :][:900]
        assert "flex-direction: row;" in wide and "flex-wrap: wrap;" in wide
        assert "margin-left: -1.25rem;" in wide and "width: 1.25rem;" in wide
        # Drawn, not read out.
        assert 'content: "\\\\00B7" / "";' in wide
        from utils.styles import default_styles

        assert 'content: "\\00B7" / "";' in default_styles  # the CSS escape, not a NUL

    def test_details(self):
        assert 'ui.label(members).classes("group-meta")' in CARD
        assert 'ui.label(f"Monthly limit: {limit}").classes("group-meta")' in CARD
        assert 'ui.label(f"Created {self.created_at}").classes("group-meta")' in CARD
        # No "current month" under a "This month" heading, no "Statistics" heading.
        assert "current month" not in CARD and '"Statistics").classes("text-h6' not in CARD

    def test_the_months_as_summary_cards_by_name(self):
        assert "summary_cards(" in CARD
        assert CARD.count("month_name(") == 2
        assert "previous_first = (this_first - timedelta(days=1)).replace(day=1)" in CARD
        assert 'amount(self.stats["total_transcribed_minutes"])' in CARD
        assert 'amount(self.stats["total_transcribed_minutes_last_month"])' in CARD
        assert ":.0f" not in CARD

    def test_one_member_and_one_file_in_the_singular(self):
        assert 'f"{self.nr_users}{NBSP}member" if self.nr_users == 1' in CARD
        assert 'f"{count}{NBSP}file" if count == 1' in CARD


class TestALongNameOrDescription:
    def test_cut_with_one_button_to_open_both(self):
        source = (ROOT / "utils" / "group.py").read_text()
        block = source[source.index("    def name_and_description(self)") :]

        assert "LONG_NAME = 48" in source and "LONG_DESCRIPTION = 120" in source
        assert "if len(self.name) > self.LONG_NAME:" in block
        assert "if len(self.description) > self.LONG_DESCRIPTION:" in block
        assert 'ui.button("Show more", color=None)' in block and '"Show less" if opened' in block
        assert 'toggle._props["aria-expanded"]' in block
        assert 'toggle._props["aria-controls"] = " ".join(' in block
        assert "self.name_and_description()" in CARD

    def test_the_name_is_still_the_heading(self):
        source = (ROOT / "utils" / "group.py").read_text()
        block = source[source.index("    def name_and_description(self)") :]

        assert 'ui.label(self.name).classes("group-name").props("role=heading aria-level=2")' in block

    def test_three_lines_of_description_two_of_name(self):
        clamp = STYLES[STYLES.index("    .group-name.is-clamped,\n    .group-description.is-clamped {") :][:400]
        assert "-webkit-line-clamp: 3;" in clamp and "overflow: hidden;" in clamp
        assert "-webkit-line-clamp: 2;" in rule(".group-name.is-clamped")

    def test_shown_only_where_something_is_cut(self):
        from utils.group import TOGGLE_SCRIPT

        assert "element.scrollHeight > element.clientHeight + 1" in TOGGLE_SCRIPT
        assert "new ResizeObserver(checkAll)" in TOGGLE_SCRIPT
        assert 'button.getAttribute("aria-expanded") === "true"' in TOGGLE_SCRIPT
        assert ".group-description-toggle[hidden]" in TOGGLE_SCRIPT
        assert "ui.add_head_html(GROUP_TOGGLE_SCRIPT)" in GROUPS
        # The split on white space reaches the browser as \\s+.
        assert ".split(/\\s+/)" in TOGGLE_SCRIPT

    def test_the_toggle_is_big_enough_to_hit(self):
        assert "min-height: 44px;" in rule(".group-description-toggle")

    def test_the_toggle_in_the_brand_colour_not_quasars_lighter_primary(self):
        assert "color: var(--color-brand-primary);" in rule(".group-description-toggle")
        assert 'ui.button("Show more", color=None)' in (ROOT / "utils" / "group.py").read_text()


class TestTheActions:
    def test_each_named_for_its_group(self):
        assert 'f"Statistics for {self.name}"' in CARD
        assert 'f"Edit {self.name}"' in CARD
        assert 'f"Delete {self.name}"' in CARD
        # The visible word first in the name (2.5.3), and set directly so a
        # quote in a group's name cannot break the props string.
        assert 'control._props["aria-label"] = name' in CARD

    def test_all_users_has_statistics_only(self):
        statistics = CARD.index('"Statistics",')
        early = CARD.index('if self.name == "All users":\n                        return')
        edit = CARD.index('button("Edit"')

        assert statistics < early < edit


class TestTheLayout:
    def test_the_card_decides_by_its_own_width(self):
        assert "container-type: inline-size;" in rule(".group-card")
        assert "@container (min-width: 52rem)" in STYLES
        wide = STYLES[STYLES.index("@container (min-width: 52rem)") :][:200]
        assert "grid-template-columns: minmax(16rem, 1fr) minmax(0, 1fr) 10rem;" in wide
        middling = STYLES[STYLES.index("    @container (min-width: 36rem) {\n        .group-layout {") :][:400]
        assert "grid-template-columns: minmax(0, 1fr) 10rem;" in middling
        assert "grid-column: 2;" in middling

    def test_the_actions_one_above_the_other_all_the_same_width(self):
        assert "flex-direction: column;" in rule(".group-actions")
        buttons = rule(".group-actions .q-btn")
        assert "width: 100%;" in buttons and "min-width: 0;" in buttons
        assert "min-height: 44px;" in buttons

    def test_not_bold_inside_the_customers_bold_expansion(self):
        assert "font-weight: 400;" in rule(".group-card")

    def test_the_two_months_share_their_column(self):
        assert "grid-template-columns: repeat(auto-fit, minmax(min(13rem, 100%), 1fr));" in rule(".group-card .stats-tiles")


class TestNoReloadWithoutCharts:
    def test_the_groups_and_edit_pages_do_not_reload_on_a_theme_change(self):
        assert "reload_on_theme_change" not in GROUPS


EDIT = GROUPS[GROUPS.index("async def edit_group") : GROUPS.index('@ui.page("/admin/stats/{group_id}")')]


class TestTheEditPage:
    def test_the_fields_full_width_one_under_another_on_a_narrow_card(self):
        assert "grid-template-columns: minmax(0, 1fr);" in rule(".edit-group-fields")
        assert "container-type: inline-size;" in rule(".edit-group-card")
        wide = STYLES[STYLES.index("@container (min-width: 40rem)") :][:300]
        assert "grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);" in wide
        assert "grid-column: 1 / -1;" in wide
        assert "w-1/3" not in EDIT and "w-1/2" not in EDIT

    def test_the_description_is_a_growing_textarea(self):
        assert 'ui.textarea("Group description", value=group["description"])' in EDIT
        assert '.props("outlined autogrow")' in EDIT

    def test_the_limits_label_fits_and_says_what_0_is(self):
        assert '"Monthly limit in minutes (0 = unlimited)"' in EDIT

    def test_headings_for_the_two_parts(self):
        assert 'ui.label("Group details").classes("text-xl font-semibold").props("role=heading aria-level=2")' in EDIT
        assert 'ui.label("Members").classes("text-xl font-semibold mt-4").props("role=heading aria-level=2")' in EDIT
        assert "Select users to be included in group:" not in EDIT

    def test_the_members_table_has_no_height_of_its_own(self):
        assert "calc(100vh - 550px" not in EDIT

    def test_the_actions_share_a_phones_width(self):
        phone = STYLES[STYLES.index("    /* On a phone the two actions share the width, side by side. */") :][:300]
        assert "flex: 1 1 0;" in phone and "width: 100%;" in phone
        assert "min-height: 44px;" in rule(".edit-group-actions .q-btn")
        assert 'style("width: 150px")' not in EDIT

    def test_the_members_table_fits_a_narrow_card(self):
        narrow = STYLES[STYLES.index("    @container (max-width: 36rem) {\n        .edit-group-members") :][:500]
        assert "white-space: normal;" in narrow and "overflow-wrap: anywhere;" in narrow

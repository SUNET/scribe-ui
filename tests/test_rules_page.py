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

"""The User provisioning page (pages/admin/rules.py) at any width."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "pages" / "admin" / "rules.py").read_text()
PAGE = SOURCE[SOURCE.index('@ui.page("/admin/rules")') : SOURCE.index("def delete_attribute_dialog")]
STYLES = (ROOT / "utils" / "styles.py").read_text()


def rule(selector: str) -> str:
    at = STYLES.index(f"\n    {selector} {{")

    return STYLES[at : STYLES.index("}", at)]


class TestTheHeader:
    def test_title_and_actions_wrap(self):
        assert PAGE.count('with ui.element("div").classes("rules-header"):') == 2
        assert "flex-wrap: wrap;" in rule(".rules-header")
        assert 'style("width: 200px;")' not in PAGE

    def test_the_actions_share_a_phones_width_and_are_big_enough(self):
        assert "min-height: 44px;" in rule(".rules-actions .q-btn")
        phone = STYLES[STYLES.index("@media (max-width: 600px) {\n        .rules-actions {") :][:300]
        assert "width: 100%;" in phone and "flex: 1 1 auto;" in phone

    def test_attributes_is_a_heading(self):
        assert 'ui.label("Attributes (BOFH)").classes("text-2xl font-bold").props("role=heading aria-level=2")' in PAGE


class TestTheRulesTable:
    def test_what_it_matches_in_one_column(self):
        assert '"name": "match",' in PAGE and '"label": "Matches",' in PAGE
        for gone in ('"label": "Attribute",', '"label": "Condition",', '"label": "Value",'):
            assert gone not in PAGE
        assert "body-cell-match" in PAGE

    def test_long_names_and_values_wrap(self):
        assert '"classes": "rules-col-wrap",' in PAGE
        wrap = rule(".rules-table td.rules-col-wrap")
        assert "white-space: normal;" in wrap and "overflow-wrap: anywhere;" in wrap

    def test_test_and_delete_named_for_the_rule(self):
        assert PAGE.count(":aria-label=\"'Test ' + props.row.name\"") == 2
        assert PAGE.count(":aria-label=\"'Delete ' + props.row.name\"") == 2

    def test_the_name_in_the_brand_colour_not_quasars_primary(self):
        assert "text-primary" not in PAGE
        assert "var(--color-brand-primary)" in rule(".rule-name-link")
        assert "text-decoration: underline;" in rule(".rule-name-link")


class TestTheRuleCards:
    def test_cards_where_the_table_does_not_fit(self):
        assert """rules_table.props(':grid="window.innerWidth < 900"')""" in PAGE
        assert '<q-card flat bordered class="jobs-card rule-card">' in PAGE

    def test_what_is_on_a_card(self):
        card = PAGE[PAGE.index('rules_table.add_slot(\n            "item",') :][:3500]
        assert "@keydown.enter=\"$parent.$emit('edit_rule', props.row)\"" in card
        assert "(props.row.condition_label || '').toLowerCase()" in card
        assert "Actions: {{ props.row.actions_summary }}" in card
        # Always set: a rule only reaches users its admin can administer.
        assert '<div class="jobs-card-meta">Realm: {{ props.row.realm }}</div>' in card
        assert 'label="Enabled"' in card

    def test_the_cards_carry_their_own_styles(self):
        assert "padding: 0.75rem;" in rule(".rule-card")
        assert "min-height: 44px;" in rule(".rule-card-actions .q-btn")

    def test_the_search_as_wide_as_the_card_on_a_phone(self):
        assert ".rules-table .q-table__top .q-field {" in STYLES


class TestTheAttributeCards:
    def test_cards_on_a_phone(self):
        assert """attrs_table.props(':grid="window.innerWidth < 700"')""" in PAGE
        assert "Example: {{ props.row.example }}" in PAGE
        assert ":aria-label=\"'Delete attribute ' + props.row.name\"" in PAGE

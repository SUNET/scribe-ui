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

"""The customer cards on the Customers page (utils/customer.py, Customer.create_card)."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARD = (ROOT / "utils" / "customer.py").read_text()
STYLES = (ROOT / "utils" / "styles.py").read_text()
PAGE = (ROOT / "pages" / "admin" / "customers.py").read_text()
TILES = (ROOT / "utils" / "chart_tables.py").read_text()
LIST_PAGE = PAGE[PAGE.index('@ui.page("/admin/customers")') :]


def rule(selector: str) -> str:
    at = STYLES.index(f"\n    {selector} {{")

    return STYLES[at : STYLES.index("}", at)]


class TestWhatIsOnIt:
    def test_the_name_is_a_heading(self):
        assert 'ui.label(name).classes("group-name").props("role=heading aria-level=2")' in CARD

    def test_the_same_three_lines_for_every_customer(self):
        assert '[f"Plan: {self.priceplan.capitalize()}"]' in CARD
        assert '[f"Base fee: {self.base_fee}", users_text],' in CARD
        assert '[f"Created {self.created_at}"],' in CARD
        # Lines on any width, not one item to a line on a narrow card.
        assert "flex-direction: row;" in rule(".customer-meta .group-meta-line")
        assert 'content: "\\\\00B7" / "";' in rule(".customer-meta .group-meta-line > .group-meta::before")

    def test_blocks_only_on_a_fixed_plan_and_one_in_the_singular(self):
        assert "if fixed" in CARD
        assert 'blocks = "block" if self.blocks_purchased == 1 else "blocks"' in CARD
        assert "MINUTES_PER_BLOCK" in CARD and "* 4000" not in CARD

    def test_a_contact_always_and_says_when_there_is_none(self):
        assert 'facts.append(("Contact", self.contact_email or None))' in CARD
        assert 'ui.label("No contact address").classes("customer-missing")' in CARD

    def test_drive_and_kaltura_only_where_the_customer_has_them(self):
        assert "if self.drive_enabled and self.drive_url:" in CARD
        assert "No instance set" not in CARD
        assert 'kaltura = self.partner_id not in ("N/A", "")' in CARD
        assert 'facts.append(("Kaltura Partner ID", self.partner_id))' in CARD

    def test_the_facts_line_up_from_card_to_card(self):
        assert 'with ui.element("dl").classes("customer-facts"):' in CARD
        assert "grid-template-columns: 8.5rem minmax(0, 1fr);" in rule(".customer-facts")

    def test_long_notes_cut_with_the_groups_pages_toggle(self):
        assert "LONG_NOTES = 120" in CARD
        assert 'toggle._props["aria-expanded"] = "false"' in CARD
        assert 'toggle._props["aria-controls"] = notes_id' in CARD
        assert ".classes(\"group-description-toggle\")" in CARD
        assert "ui.add_head_html(TOGGLE_SCRIPT)" in PAGE


class TestTheMonths:
    def test_summary_cards_by_name(self):
        assert "summary_cards(" in CARD
        assert "month_name(this_first.isoformat())" in CARD
        assert "month_name(previous_first.isoformat())" in CARD
        assert 'ui.label("This month")' not in CARD and '"Last month"' not in CARD

    def test_scribe_and_play_for_play_customers(self):
        assert 'via Scribe, "' in CARD and 'via Play"' in CARD

    def test_a_line_may_draw_itself(self):
        assert "line() if callable(line) else ui.label(line)" in TILES


class TestTheBlocks:
    def test_in_this_months_card(self):
        assert "this_month.append(self.blocks_used)" in CARD

    def test_used_capped_at_the_blocks_and_all_said_in_words(self):
        assert 'used = min(float(self.stats.get("blocks_consumed", 0) or 0), bought)' in CARD
        assert '"All blocks used" if used >= bought else f"{used:.2f} of {bought}{NBSP}{blocks} used"' in CARD

    def test_left_or_over_in_words(self):
        assert 'f"{amount(overage)} over"' in CARD
        assert "} left\"" in CARD
        assert '.classes("customer-blocks-state is-over")' in CARD
        assert '.classes("customer-blocks-state is-left")' in CARD

    def test_amber_not_red_for_overage(self):
        assert "#d97706" in rule(".customer-meter-over")
        over = rule(".customer-blocks-state.is-over")
        assert "#92400e" in over and "#fef3c7" in over
        assert "⚠" not in CARD

    def test_the_bar_is_two_colours_once_over_and_hidden_from_assistive_technology(self):
        assert '.classes("customer-meter").props("aria-hidden=true")' in CARD
        assert "share = 100 * within / (within + overage)" in CARD
        assert '.classes("customer-meter-over")' in CARD
        # The blocks stay green when over: no amber override of the fill.
        assert ":has(.is-over) .customer-meter-fill" not in STYLES

    def test_high_contrast(self):
        forced = STYLES[STYLES.index("@media (forced-colors: active) {\n        .customer-meter-fill") :][:300]
        assert "CanvasText" in forced and "Highlight" in forced


class TestTheActions:
    def test_only_for_bofh_and_named_for_the_customer(self):
        assert "if not self.is_bofh:" in CARD
        assert 'control._props["aria-label"] = f"{text} {self.name}"' in CARD

    def test_no_column_for_them_on_a_realm_admins_card(self):
        assert ".group-layout:not(:has(> .group-actions))" in STYLES


class TestThePage:
    def test_no_height_of_its_own(self):
        assert "scroll_area" not in LIST_PAGE
        assert "100vh" not in LIST_PAGE

    def test_title_and_actions_wrap(self):
        assert 'with ui.element("div").classes("customers-header"):' in LIST_PAGE
        assert "flex-wrap: wrap;" in rule(".customers-header")
        assert "min-height: 44px;" in rule(".customers-actions .q-btn")

    def test_billing_explained_in_the_menu_not_a_tooltip(self):
        assert "ui.tooltip(" not in LIST_PAGE
        assert '.props("caption")' in LIST_PAGE

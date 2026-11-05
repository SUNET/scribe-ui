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

from datetime import date, timedelta

import httpx

from nicegui import ui
from utils.bar_chart import NBSP, amount, month_name
from utils.chart_tables import summary_cards
from utils.helpers import MINUTES_PER_BLOCK
from utils.settings import get_settings
from utils.token import get_auth_header

settings = get_settings()


class Customer:
    def __init__(
        self,
        customer_abbr: str,
        customer_id: str,
        partner_id: str,
        name: str,
        contact_email: str,
        support_contact_email: str,
        priceplan: str,
        base_fee: int,
        realms: str,
        notes: str,
        created_at: str,
        stats: dict,
        blocks_purchased: int = 0,
        drive_enabled: bool = False,
        drive_url: str | None = None,
        drive_display_name: str | None = None,
        is_bofh: bool = False,
    ) -> None:
        self.customer_abbr = customer_abbr
        self.customer_id = customer_id
        self.partner_id = partner_id
        self.name = name
        self.contact_email = contact_email
        self.support_contact_email = support_contact_email
        self.priceplan = priceplan
        self.base_fee = (base_fee,)
        self.realms = realms
        self.notes = notes
        self.created_at = created_at.split(".")[0]
        self.stats = stats
        self.blocks_purchased = blocks_purchased
        self.drive_enabled = drive_enabled
        self.drive_url = drive_url
        self.drive_display_name = drive_display_name
        self.is_bofh = is_bofh

        if isinstance(self.base_fee, tuple):
            self.base_fee = self.base_fee[0]

    def edit_customer(self) -> None:
        ui.navigate.to(f"/admin/customers/edit/{self.customer_id}")

    # Over this many characters the notes are cut to three lines on the
    # card, with a button to show them whole.
    LONG_NOTES = 120

    def create_card(self) -> None:
        """
        The customer as a card, in the Groups page's layout (utils/styles.py,
        .group-card): the name as a heading, the plan and the short facts in
        one line, the longer ones (contact, realms, Drive, Kaltura) as a list,
        the notes cut when long; this month and the one before as summary
        cards, months by name; and Edit / Delete in a column of their own,
        each named for its customer. Realm admins, who see their own account
        only, get no actions, and the card does without their column.
        """

        today = date.today()
        this_first = today.replace(day=1)
        previous_first = (this_first - timedelta(days=1)).replace(day=1)
        kaltura = self.partner_id not in ("N/A", "")
        fixed = self.priceplan == "fixed"
        users = self.stats.get("total_users", 0)

        def files(count) -> str:
            return f"{count}{NBSP}file" if count == 1 else f"{count}{NBSP}files"

        def month(files_key: str, minutes_key: str, scribe_key: str, play_key: str) -> list:
            lines = [
                f"{files(self.stats.get(files_key, 0))} transcribed",
                amount(self.stats.get(minutes_key, 0)),
            ]

            if kaltura:
                lines.append(
                    f"{amount(self.stats.get(scribe_key, 0))} via Scribe, "
                    f"{amount(self.stats.get(play_key, 0))} via Play"
                )

            return lines

        this_month = month(
            "transcribed_files", "total_transcribed_minutes",
            "transcribed_minutes", "transcribed_minutes_external",
        )

        if fixed and self.blocks_purchased > 0:
            this_month.append(self.blocks_used)

        last_month = month(
            "transcribed_files_last_month", "total_transcribed_minutes_last_month",
            "transcribed_minutes_last_month", "transcribed_minutes_external_last_month",
        )

        with ui.card().classes("group-card admin-card my-2"):
            with ui.element("div").classes("group-layout"):
                with ui.element("div").classes("group-info"):
                    name = self.name + (f" ({self.customer_abbr})" if self.customer_abbr else "")
                    ui.label(name).classes("group-name").props("role=heading aria-level=2")

                    # The same three lines for every customer: the plan
                    # (and its blocks), the fee and the users, the date. A
                    # line wraps between its items on a narrow card, with
                    # no dot at the start (utils/styles.py, .customer-meta).
                    blocks = "block" if self.blocks_purchased == 1 else "blocks"
                    users_text = f"{users}{NBSP}user" if users == 1 else f"{users}{NBSP}users"

                    with ui.element("div").classes("group-meta-wrap customer-meta"):
                        for items in (
                            [f"Plan: {self.priceplan.capitalize()}"]
                            + (
                                [f"{self.blocks_purchased}{NBSP}{blocks} ({amount(self.blocks_purchased * MINUTES_PER_BLOCK)})"]
                                if fixed
                                else []
                            ),
                            [f"Base fee: {self.base_fee}", users_text],
                            [f"Created {self.created_at}"],
                        ):
                            with ui.element("div").classes("group-meta-line"):
                                for item in items:
                                    ui.label(item).classes("group-meta")

                    facts = []

                    # Every customer should have a contact; one without it
                    # says so, rather than leaving the line out.
                    facts.append(("Contact", self.contact_email or None))

                    if self.realms:
                        facts.append(("Realms", ", ".join(r.strip() for r in self.realms.split(",") if r.strip())))

                    # Only what the customer has: no Drive line without a
                    # Drive instance, no Kaltura line without Play.
                    if self.drive_enabled and self.drive_url:
                        facts.append((self.drive_display_name or "Sunet Drive", self.drive_url))

                    if kaltura:
                        facts.append(("Kaltura Partner ID", self.partner_id))

                    if facts:
                        with ui.element("dl").classes("customer-facts"):
                            for term, value in facts:
                                with ui.element("dt"):
                                    ui.label(term)
                                with ui.element("dd"):
                                    if value is None:
                                        ui.label("No contact address").classes("customer-missing")
                                    else:
                                        ui.label(value)

                    if self.notes:
                        self.notes_text()

                summary_cards(
                    (
                        (month_name(this_first.isoformat()), this_month),
                        (month_name(previous_first.isoformat()), last_month),
                    )
                )

                if not self.is_bofh:
                    return

                with ui.element("div").classes("group-actions"):
                    for text, look, props, action in (
                        ("Edit", "button-edit", "color=white flat", lambda: self.edit_customer()),
                        ("Delete", "button-close", "color=black flat", lambda: self.delete_customer_dialog()),
                    ):
                        control = ui.button(text).classes(look).props(props)
                        # Set directly, not through props(): a name may hold
                        # a quote, which the props string would take apart.
                        control._props["aria-label"] = f"{text} {self.name}"
                        control.on("click", action)

    def blocks_used(self) -> None:
        """
        This month's blocks, in the month's summary card: how many of them
        are used, a bar to see it at a glance, and what is left or over in
        a tinted label -- green while there are minutes left, amber once
        they are used up and the month runs into overage, which is billed,
        not an error; the bar is then green for the blocks and amber for the
        overage after them. The bar is a picture of the sentence above it, so it
        is hidden from assistive technology; the words say it all, and the
        tint is never all there is (1.4.1).
        """

        bought = self.blocks_purchased
        # The backend counts up to the blocks bought and no further; what
        # goes beyond them is overage.
        used = min(float(self.stats.get("blocks_consumed", 0) or 0), bought)
        overage = float(self.stats.get("overage_minutes", 0) or 0)
        blocks = "block" if bought == 1 else "blocks"

        with ui.element("div").classes("customer-blocks"):
            # Once they are all used, say so: "2.00 of 2" reads as a sum to
            # check. How many there are is in the card's plan line.
            ui.label(
                "All blocks used" if used >= bought else f"{used:.2f} of {bought}{NBSP}{blocks} used"
            ).classes("customer-blocks-used")

            # The bar is the month's minutes: while within the blocks, the
            # blocks' minutes, filled as far as they are used; once over,
            # the blocks and the overage together, the blocks in full in
            # green and the overage after them in amber -- so the more
            # overage, the further left the blocks' end moves.
            with ui.element("div").classes("customer-meter").props("aria-hidden=true"):
                if overage > 0:
                    within = bought * MINUTES_PER_BLOCK
                    share = 100 * within / (within + overage)
                    ui.element("div").classes("customer-meter-fill").style(f"width: {share:.1f}%")
                    ui.element("div").classes("customer-meter-over").style(f"width: {100 - share:.1f}%")
                else:
                    ui.element("div").classes("customer-meter-fill").style(f"width: {100 * used / bought:.1f}%")

            if overage > 0:
                ui.label(f"{amount(overage)} over").classes("customer-blocks-state is-over")
            else:
                ui.label(
                    f"{amount(self.stats.get('remaining_minutes', 0))} left"
                ).classes("customer-blocks-state is-left")

    def notes_text(self) -> None:
        """
        The notes, cut to three lines when long, with "Show more" / "Show
        less" (aria-expanded, aria-controls) -- the Groups page's toggle,
        shown only where the text is actually cut (utils/group.py,
        TOGGLE_SCRIPT). The whole text is in the page either way.
        """

        notes = ui.label(self.notes).classes("group-description customer-notes")

        if len(self.notes) <= self.LONG_NOTES:
            return

        notes_id = f"customer-notes-{self.customer_id}"
        notes.classes("is-clamped")
        notes._props["id"] = notes_id

        toggle = ui.button("Show more", color=None).classes("group-description-toggle").props("flat dense no-caps")
        toggle._props["aria-expanded"] = "false"
        toggle._props["aria-controls"] = notes_id

        def flip() -> None:
            opened = toggle._props.get("aria-expanded") == "false"
            notes.classes(remove="is-clamped") if opened else notes.classes(add="is-clamped")
            toggle.text = "Show less" if opened else "Show more"
            toggle._props["aria-expanded"] = "true" if opened else "false"
            toggle.update()

        toggle.on("click", flip)

    def delete_customer_dialog(self) -> None:
        with ui.dialog().props('aria-label="Delete customer"') as delete_customer_dialog:
            with ui.card():
                ui.label("Delete customer").classes("text-h6")
                ui.label(
                    "Are you sure you want to delete this customer? This action cannot be undone."
                ).classes("text-subtitle2").style("margin-bottom: 10px;")

                with ui.row().classes("justify-between w-full"):
                    ui.button("Cancel", on_click=lambda: delete_customer_dialog.close()).props(
                        "color=black"
                    )
                    ui.button(
                        "Delete",
                        on_click=lambda: (
                            httpx.delete(
                                settings.API_URL
                                + f"/api/v1/admin/customers/{self.customer_id}",
                                headers=get_auth_header(),
                            ),
                            delete_customer_dialog.close(),
                            ui.navigate.to("/admin/customers"),
                        ),
                    ).props("color=red")

            delete_customer_dialog.open()

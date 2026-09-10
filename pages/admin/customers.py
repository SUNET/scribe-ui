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
Customer administration.
"""

import httpx


from nicegui import app, ui
from utils.common import page_init
from utils.styles import default_styles
from utils.helpers import (
    save_customer,
    export_billing_data,
    export_customers_csv,
    customers_get,
)
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
    get_bofh_status,
)
from utils.customer import Customer
from pages.admin.shared import _get_valid_realms

settings = get_settings()


def create_customer_dialog(page: callable) -> None:
    ui.dark_mode(app.storage.user.get("dark_mode", None))
    realms = _get_valid_realms()

    with ui.dialog() as create_customer_dialog:
        with ui.card().style("width: 600px; max-width: 90vw;"):
            ui.label("Create new customer").classes("text-2xl font-bold")

            customer_abbr = (
                ui.input("Customer abbreviation").classes("w-full").props("outlined")
            )
            partner_id_input = (
                ui.input("Kaltura Partner ID", value="N/A")
                .classes("w-full")
                .props("outlined")
            )
            name_input = ui.input("Customer name").classes("w-full").props("outlined")
            contact_email_input = (
                ui.input("Contact email").classes("w-full").props("outlined")
            )
            support_contact_email_input = (
                ui.input("Support contact address").classes("w-full").props("outlined")
            )

            priceplan_select = (
                ui.select(["fixed", "variable"], label="Price plan", value="variable")
                .classes("w-full")
                .props("outlined")
            )

            base_fee = (
                ui.input("Base fee", value="0")
                .classes("w-full")
                .props("outlined type=number min=0")
            )

            blocks_input = (
                ui.input("Blocks purchased (4000 min/block)", value="0")
                .classes("w-full")
                .props("outlined type=number min=0")
            )

            # Show/hide blocks input based on price plan
            def update_blocks_visibility():
                if priceplan_select.value == "fixed":
                    blocks_input.set_visibility(True)
                else:
                    blocks_input.set_visibility(False)
                    blocks_input.value = "0"

            priceplan_select.on(
                "update:model-value", lambda: update_blocks_visibility()
            )
            blocks_input.set_visibility(False)  # Initially hidden

            realm_select = (
                ui.select(
                    realms, label="Select existing realms", multiple=True, value=[]
                )
                .classes("w-full")
                .props("outlined")
            )

            new_realms_input = (
                ui.input("Add new realms (comma-separated)")
                .classes("w-full")
                .props("outlined")
            )

            notes_input = ui.textarea("Notes").classes("w-full").props("outlined")

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: create_customer_dialog.close())

                def create_customer():
                    if not partner_id_input.value.strip():
                        ui.notify("Kaltura Partner ID is required.", color="red")
                        return
                    if not name_input.value.strip():
                        ui.notify("Customer name is required.", color="red")
                        return

                    selected_realms = realm_select.value if realm_select.value else []
                    new_realms = [
                        r.strip()
                        for r in new_realms_input.value.split(",")
                        if r.strip()
                    ]
                    all_realms = list(set(selected_realms + new_realms))
                    realms_str = ",".join(all_realms)

                    try:
                        res = httpx.post(
                            settings.API_URL + "/api/v1/admin/customers",
                            headers=get_auth_header(),
                            json={
                                "customer_abbr": customer_abbr.value,
                                "partner_id": partner_id_input.value,
                                "name": name_input.value,
                                "contact_email": contact_email_input.value,
                                "support_contact_email": support_contact_email_input.value,
                                "priceplan": priceplan_select.value,
                                "base_fee": int(base_fee.value)
                                if base_fee.value
                                else 0,
                                "blocks_purchased": int(blocks_input.value)
                                if blocks_input.value
                                else 0,
                                "realms": realms_str,
                                "notes": notes_input.value,
                            },
                        )

                        res.raise_for_status()
                    except httpx.HTTPError as e:
                        if res.status_code == 400:
                            error_msg = res.json().get("error", "Unknown error")
                            ui.notify(
                                f"Error creating customer: {error_msg}", color="red"
                            )
                            return
                        else:
                            ui.notify(f"Error creating customer: {e}", color="red")
                            return
                    else:
                        create_customer_dialog.close()
                        ui.navigate.to("/admin/customers")

                ui.button("Create").classes("default-style").props(
                    "color=black flat"
                ).on("click", create_customer)

        create_customer_dialog.open()


@ui.refreshable
@ui.page("/admin/customers/edit/{customer_id}")
def edit_customer(customer_id: str) -> None:
    """
    Page to edit a customer.
    """
    page_init(use_drawer=True, title="Edit customer")

    if not get_admin_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    try:
        res = httpx.get(
            settings.API_URL + f"/api/v1/admin/customers/{customer_id}",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        customer = res.json()["result"]

        realms = _get_valid_realms()
        customer_realms = [
            r.strip() for r in customer["realms"].split(",") if r.strip()
        ]

    except httpx.HTTPError as e:
        ui.label(f"Error fetching customer: {e}").classes("text-lg").style("color: var(--color-text-danger);")
        return

    ui.label(f"Edit customer: {customer['name']}").classes("text-3xl font-bold mb-4")

    with ui.card().style("width: 100%; box-shadow: none; align-self: center;"):
        with ui.column().classes("gap-4 w-full"):
            customer_abbr_input = (
                ui.input(
                    "Customer abbreviation", value=customer.get("customer_abbr", "")
                )
                .props("outlined")
                .classes("w-full")
            )
            partner_id_input = (
                ui.input("Kaltura Partner ID", value=customer["partner_id"])
                .props("outlined")
                .classes("w-full")
            )
            name_input = (
                ui.input("Customer name", value=customer["name"])
                .props("outlined")
                .classes("w-full")
            )
            contact_email_input = (
                ui.input("Contact email", value=customer.get("contact_email", ""))
                .props("outlined")
                .classes("w-full")
            )
            support_contact_email_input = (
                ui.input(
                    "Support contact address",
                    value=customer.get("support_contact_email", ""),
                )
                .props("outlined")
                .classes("w-full")
            )

            priceplan_select = (
                ui.select(
                    ["fixed", "variable"],
                    label="Price plan",
                    value=customer["priceplan"],
                )
                .classes("w-full")
                .props("outlined")
            )
            base_fee = (
                ui.input("Base fee", value=str(customer.get("base_fee", 0)))
                .classes("w-full")
                .props("outlined type=number min=0")
            )
            blocks_input = (
                ui.input(
                    "Blocks purchased (4000 min/block)",
                    value=str(customer.get("blocks_purchased", 0)),
                )
                .classes("w-full")
                .props("outlined type=number min=0")
            )

            # Show/hide blocks input based on price plan
            def update_blocks_visibility():
                if priceplan_select.value == "fixed":
                    blocks_input.set_visibility(True)
                else:
                    blocks_input.set_visibility(False)

            priceplan_select.on(
                "update:model-value", lambda: update_blocks_visibility()
            )
            update_blocks_visibility()

            realm_select = (
                ui.select(
                    realms,
                    label="Select existing realms",
                    multiple=True,
                    value=customer_realms,
                )
                .classes("w-full")
                .props("outlined use-chips")
            )

            new_realms_input = (
                ui.input("Add new realms (comma-separated)")
                .classes("w-full")
                .props("outlined")
            )

            notes_input = (
                ui.textarea("Notes", value=customer.get("notes", ""))
                .classes("w-full")
                .props("outlined")
            )

    with ui.row().style(
        "justify-content: flex-end; width: 100%; padding: 16px; gap: 8px;"
    ):
        ui.button("Save customer").classes("default-style").props(
            "color=black flat"
        ).style("width: 150px").on(
            "click",
            lambda: save_customer(
                customer_abbr_input.value,
                customer_id,
                partner_id_input.value,
                name_input.value,
                contact_email_input.value,
                support_contact_email_input.value,
                priceplan_select.value,
                base_fee.value,
                realm_select.value if realm_select.value else [],
                new_realms_input.value,
                notes_input.value,
                blocks_input.value,
            ),
        )
        ui.button("Cancel").classes("delete-style").props("color=black flat").on(
            "click", lambda: ui.navigate.to("/admin/customers")
        )


@ui.page("/admin/customers")
def customers() -> None:
    """
    Customer management page.
    """
    page_init(use_drawer=True, title="Customers")

    if not get_admin_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    with ui.row().style(
        "justify-content: space-between; align-items: center; width: 100%;"
    ):
        with ui.element("div").style("display: flex; gap: 0px;"):
            if get_bofh_status():
                ui.label("Customers").classes("text-3xl font-bold")
            elif get_admin_status():
                ui.label("Account information").classes("text-3xl font-bold")
            else:
                pass

        with ui.element("div").style("display: flex; gap: 10px;"):
            if get_bofh_status():
                create = (
                    ui.button("Create new customer")
                    .classes("default-style")
                    .props("color=black flat")
                )
                create.on("click", lambda: create_customer_dialog(page=customers))

            if get_bofh_status():
                # Billing covers every customer, so it is BOFH only. With two
                # exports to choose from they go behind one menu rather than
                # spreading buttons along the header.
                with (
                    ui.dropdown_button("Export", auto_close=True)
                    .classes("button-edit")
                    .props("color=white flat")
                ):
                    ui.item(
                        "Customers (CSV)",
                        on_click=lambda: export_customers_csv(),
                    )
                    with ui.item(
                        "Billing (CSV)",
                        on_click=lambda: export_billing_data(),
                    ):
                        ui.tooltip(
                            "Base fee, blocks and overage minutes per "
                            "customer, for the last full month"
                        )
            else:
                # Realm admins see their own account information only, so the
                # plain customer export is all there is to offer.
                export_csv = (
                    ui.button("Export CSV")
                    .classes("button-edit")
                    .props("color=white flat")
                )
                export_csv.on("click", lambda: export_customers_csv())

    customers_data = customers_get()

    if not customers_data or "result" not in customers_data:
        ui.label("No customers found. Create a new customer to get started.").classes(
            "text-lg"
        )
        return

    with ui.scroll_area().style(
        "height: calc(100vh - 160px - var(--banner-offset, 0px)); width: 100%;"
    ):
        customers_list = sorted(
            customers_data["result"], key=lambda x: x["name"].lower()
        )
        for customer in customers_list:
            c = Customer(
                customer_abbr=customer.get("customer_abbr", ""),
                customer_id=customer["id"],
                partner_id=customer["partner_id"],
                name=customer["name"],
                contact_email=customer.get("contact_email", ""),
                support_contact_email=customer.get("support_contact_email", ""),
                priceplan=customer["priceplan"],
                realms=customer["realms"],
                notes=customer.get("notes", ""),
                created_at=customer["created_at"],
                stats=customer.get("stats", {}),
                blocks_purchased=customer.get("blocks_purchased", 0),
                base_fee=customer["base_fee"],
            )
            c.create_card()

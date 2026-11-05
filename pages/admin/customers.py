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
    get_auth_header,
)
from utils.customer import Customer
from utils.group import TOGGLE_SCRIPT
from pages.admin.shared import _get_valid_realms

settings = get_settings()


def drive_fields(customer: dict | None = None, title: bool = True) -> tuple:
    """
    The Sunet Drive settings of a customer (SUNET/scribe-backend#64): which
    instance is theirs -- users do not choose one -- and what the
    organisation calls it. Always shown. Drive is offered to the customer's
    users exactly when an instance is set (see drive_enabled), so there is
    no switch to keep in step with the address. The backend only accepts
    Sunet Drive addresses.

    Returns:
        tuple: (instance input, display name input).
    """

    customer = customer or {}

    if title:
        ui.label("Sunet Drive").classes("text-lg font-semibold mt-2")

    instance = (
        ui.input(
            "Drive instance",
            value=customer.get("drive_url") or "",
            placeholder="https://<organisation>.drive.sunet.se",
        )
        .classes("w-full")
        .props(
            'outlined type=url hint="The organisation\'s own Drive, used by all '
            'its users. Leave empty to not offer Drive."'
        )
    )
    display = (
        ui.input(
            "Drive display name",
            value=customer.get("drive_display_name") or "",
            placeholder="Sunet Drive",
        )
        .classes("w-full")
        .props(
            'outlined maxlength=64 hint="What the organisation calls its Drive, '
            'e.g. in Get from ... and Save to ...  Empty means Sunet Drive."'
        )
    )

    return instance, display


def drive_enabled(instance) -> bool:
    """Drive is offered to a customer's users when it has an instance."""

    return bool((instance.value or "").strip())


def create_customer_dialog(page: callable) -> None:
    ui.dark_mode(app.storage.user.get("dark_mode", None))
    realms = _get_valid_realms()

    with ui.dialog().props('aria-label="Create new customer"') as create_customer_dialog:
        with ui.card().style("width: 600px; max-width: 90vw;"):
            ui.label("Create new customer").classes("text-2xl font-bold")

            customer_abbr = (
                ui.input("Customer abbreviation").classes("w-full").props("outlined")
            )
            partner_id_input = (
                ui.input("Kaltura Partner ID", value="N/A")
                .classes("w-full")
                .props("outlined required")
            )
            name_input = (
                ui.input("Customer name").classes("w-full").props("outlined required")
            )
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

            drive_url_input, drive_name_input = drive_fields()

            notes_input = ui.textarea("Notes").classes("w-full").props("outlined")

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: create_customer_dialog.close())

                def create_customer():
                    # Errors attach to the field itself and move focus there
                    # (3.3.1): a toast alone never named which of the two
                    # required fields was empty, and left focus sitting on
                    # this button rather than on the problem.
                    if not partner_id_input.value.strip():
                        partner_id_input.props(
                            'error error-message="Kaltura Partner ID is required."'
                        )
                        partner_id_input.run_method("focus")
                        return
                    partner_id_input.props(remove="error error-message")

                    if not name_input.value.strip():
                        name_input.props(
                            'error error-message="Customer name is required."'
                        )
                        name_input.run_method("focus")
                        return
                    name_input.props(remove="error error-message")

                    selected_realms = realm_select.value if realm_select.value else []
                    new_realms = [
                        r.strip()
                        for r in new_realms_input.value.split(",")
                        if r.strip()
                    ]
                    all_realms = list(set(selected_realms + new_realms))
                    realms_str = ",".join(all_realms)

                    # int() on these two raised a bare ValueError with no
                    # message shown anywhere -- e.g. a decimal like "12.5" is
                    # accepted by the browser's own type=number spinner but
                    # not by int(). Same field/focus treatment as above
                    # (3.3.1).
                    try:
                        base_fee_val = int(base_fee.value) if base_fee.value else 0
                    except ValueError:
                        base_fee.props(
                            'error error-message="Base fee must be a whole number."'
                        )
                        base_fee.run_method("focus")
                        return
                    base_fee.props(remove="error error-message")

                    try:
                        blocks_val = int(blocks_input.value) if blocks_input.value else 0
                    except ValueError:
                        blocks_input.props(
                            'error error-message="Blocks purchased must be a '
                            'whole number."'
                        )
                        blocks_input.run_method("focus")
                        return
                    blocks_input.props(remove="error error-message")

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
                                "base_fee": base_fee_val,
                                "blocks_purchased": blocks_val,
                                "realms": realms_str,
                                "notes": notes_input.value,
                                "drive_enabled": drive_enabled(drive_url_input),
                                "drive_url": drive_url_input.value.strip(),
                                "drive_display_name": drive_name_input.value.strip(),
                            },
                        )

                        res.raise_for_status()
                    except httpx.HTTPError as e:
                        if res.status_code == 400:
                            error_msg = res.json().get("error", "Unknown error")
                            ui.notify(
                                f"Error creating customer: {error_msg}",
                                color="red",
                                timeout=None,
                                close_button="Close",
                            )
                            return
                        else:
                            ui.notify(f"Error creating customer: {e}", color="red", timeout=None, close_button="Close")
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
async def edit_customer(customer_id: str) -> None:
    """
    Page to edit a customer.
    """
    user_data = await page_init(use_drawer=True, title="Edit customer")

    if not (user_data or {}).get("admin"):
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

    # The title and the actions, as on Edit group: wrapping on a phone,
    # where the two buttons share the width (utils/styles.py, .edit-group-*).
    # Then the fields in one card, in sections with headings, laid out by
    # the card's own width (.edit-customer-fields): two to a line from
    # 40rem, one to a line under it.
    with ui.element("div").classes("edit-group-header"):
        ui.label(f"Edit customer: {customer['name']}").classes("text-3xl font-bold edit-group-title").props(
            "role=heading aria-level=1"
        )

        with ui.element("div").classes("edit-group-actions"):
            # do_save is defined further down; the click comes after.
            ui.button("Save customer").classes("default-style").props(
                "color=black flat no-wrap"
            ).on("click", lambda: do_save())
            ui.button("Cancel").classes("delete-style").props("color=black flat").on(
                "click", lambda: ui.navigate.to("/admin/customers")
            )

    def section(title: str):
        ui.label(title).classes("text-xl font-semibold edit-customer-heading").props(
            "role=heading aria-level=2"
        )

        return ui.element("div").classes("edit-customer-fields")

    with ui.card().classes("edit-group-card admin-card"):
        with section("Customer details"):
            name_input = (
                ui.input("Customer name", value=customer["name"])
                .props("outlined")
            )
            customer_abbr_input = (
                ui.input(
                    "Customer abbreviation", value=customer.get("customer_abbr", "")
                )
                .props("outlined")
            )
            contact_email_input = (
                ui.input("Contact email", value=customer.get("contact_email", ""))
                .props("outlined type=email")
            )
            support_contact_email_input = (
                ui.input(
                    "Support contact address",
                    value=customer.get("support_contact_email", ""),
                )
                .props("outlined type=email")
            )

        with section("Plan"):
            priceplan_select = (
                ui.select(
                    {"fixed": "Fixed", "variable": "Variable"},
                    label="Price plan",
                    value=customer["priceplan"],
                )
                .props("outlined")
            )
            blocks_input = (
                ui.input(
                    "Blocks per month (4000 minutes each)",
                    value=str(customer.get("blocks_purchased", 0)),
                )
                .props("outlined type=number min=0")
            )

            base_fee = (
                ui.input("Base fee", value=str(customer.get("base_fee", 0)))
                .props("outlined type=number min=0")
            )
            # Blocks are for a fixed plan only, beside the plan; without
            # them the base fee takes their place.
            def update_blocks_visibility():
                blocks_input.set_visibility(priceplan_select.value == "fixed")

            priceplan_select.on(
                "update:model-value", lambda: update_blocks_visibility()
            )
            update_blocks_visibility()

        with section("Realms"):
            realm_select = (
                ui.select(
                    realms,
                    label="Select existing realms",
                    multiple=True,
                    value=customer_realms,
                )
                .classes("edit-customer-wide")
                .props("outlined use-chips")
            )
            new_realms_input = (
                ui.input("Add new realms (comma-separated)")
                .classes("edit-customer-wide")
                .props("outlined")
            )

        with section("Kaltura REACH integration"):
            partner_id_input = (
                ui.input("Kaltura Partner ID", value=customer["partner_id"])
                .props('outlined hint="N/A for a customer without Kaltura."')
            )

        with section("Sunet Drive"):
            drive_url_input, drive_name_input = drive_fields(customer, title=False)

        with section("Notes"):
            # A textarea that grows, as on Edit group.
            notes_input = (
                ui.textarea("Notes", value=customer.get("notes", ""))
                .classes("edit-customer-wide")
                .props("outlined autogrow")
            )

    async def do_save() -> None:
        # save_customer's own int(base_fee) raised a bare, unshown ValueError
        # on anything int() rejects (a decimal like "12.5", which the
        # browser's type=number spinner accepts without complaint). Same
        # field/focus treatment as create_customer_dialog's own copy of this
        # bug (3.3.1).
        try:
            int(base_fee.value) if base_fee.value else 0
        except ValueError:
            base_fee.props('error error-message="Base fee must be a whole number."')
            base_fee.run_method("focus")
            return
        base_fee.props(remove="error error-message")

        try:
            int(blocks_input.value) if blocks_input.value else 0
        except ValueError:
            blocks_input.props(
                'error error-message="Blocks purchased must be a whole number."'
            )
            blocks_input.run_method("focus")
            return
        blocks_input.props(remove="error error-message")

        error = await save_customer(
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
            drive_enabled=drive_enabled(drive_url_input),
            drive_url=drive_url_input.value.strip(),
            drive_display_name=drive_name_input.value.strip(),
        )

        # The one field the backend itself refuses: an address that is not
        # a Sunet Drive instance. Same field/focus treatment as above.
        if error and "Drive" in error:
            drive_url_input.props(f'error error-message="{error.replace(chr(34), chr(39))}"')
            drive_url_input.run_method("focus")
        elif error:
            ui.notify(
                f"Error saving customer: {error}",
                type="negative",
                timeout=None,
                close_button="Close",
            )
        else:
            ui.navigate.to("/admin/customers")


@ui.page("/admin/customers")
async def customers() -> None:
    """
    Customer management page.
    """
    user_data = await page_init(use_drawer=True, title="Customers")

    if not (user_data or {}).get("admin"):
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    is_bofh = bool((user_data or {}).get("bofh"))

    # The title on the left, the actions on the right; on a phone the
    # actions go under the title and share its width (utils/styles.py,
    # .customers-header).
    with ui.element("div").classes("customers-header"):
        ui.label("Customers" if is_bofh else "Account information").classes(
            "text-3xl font-bold"
        ).props("role=heading aria-level=1")

        with ui.element("div").classes("customers-actions"):
            if is_bofh:
                create = (
                    ui.button("Create new customer")
                    .classes("default-style")
                    .props("color=black flat")
                )
                create.on("click", lambda: create_customer_dialog(page=customers))

                # Billing covers every customer, so it is BOFH only. With two
                # exports to choose from they go behind one menu rather than
                # spreading buttons along the header. What each holds is said
                # in the menu itself, not in a tooltip (1.4.13).
                with (
                    ui.dropdown_button("Export", auto_close=True)
                    .classes("button-edit")
                    .props("color=white flat")
                ):
                    ui.item("Customers (CSV)", on_click=lambda: export_customers_csv())

                    with ui.item(on_click=lambda: export_billing_data()):
                        with ui.item_section():
                            ui.item_label("Billing (CSV)")
                            ui.item_label(
                                "Base fee, blocks and overage minutes per "
                                "customer, for the last full month"
                            ).props("caption")
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

    # No height of its own: the page scrolls, as any other page does.
    ui.add_head_html(TOGGLE_SCRIPT)

    with ui.element("div").classes("customers-list"):
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
                drive_enabled=bool(customer.get("drive_enabled")),
                drive_url=customer.get("drive_url"),
                drive_display_name=customer.get("drive_display_name"),
                is_bofh=is_bofh,
            )
            c.create_card()

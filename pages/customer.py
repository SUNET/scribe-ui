import requests

from nicegui import ui
from utils.common import default_styles, get_auth_header, page_init, realms_get
from utils.settings import get_settings
from utils.token import get_admin_status, get_bofh_status

settings = get_settings()


def customers_get() -> list:
    """
    Fetch all customers from backend.
    """
    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/customers", headers=get_auth_header()
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching customers: {e}")
        return []


def create_customer_dialog(page: callable) -> None:
    realms = realms_get()

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
                        res = requests.post(
                            settings.API_URL + "/api/v1/admin/customers",
                            headers=get_auth_header(),
                            json={
                                "customer_abbr": customer_abbr.value,
                                "partner_id": partner_id_input.value,
                                "name": name_input.value,
                                "contact_email": contact_email_input.value,
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
                    except requests.RequestException as e:
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


class Customer:
    def __init__(
        self,
        customer_abbr: str,
        customer_id: str,
        partner_id: str,
        name: str,
        contact_email: str,
        priceplan: str,
        base_fee: int,
        realms: str,
        notes: str,
        created_at: str,
        stats: dict,
        blocks_purchased: int = 0,
    ) -> None:
        self.customer_abbr = customer_abbr
        self.customer_id = customer_id
        self.partner_id = partner_id
        self.name = name
        self.contact_email = contact_email
        self.priceplan = priceplan
        self.base_fee = (base_fee,)
        self.realms = realms
        self.notes = notes
        self.created_at = created_at.split(".")[0]
        self.stats = stats
        self.blocks_purchased = blocks_purchased

        if isinstance(self.base_fee, tuple):
            self.base_fee = self.base_fee[0]

    def edit_customer(self) -> None:
        ui.navigate.to(f"/admin/customers/edit/{self.customer_id}")

    def delete_customer_dialog(self) -> None:
        with ui.dialog() as delete_customer_dialog:
            with ui.card().style("width: 400px; max-width: 90vw;"):
                ui.label("Delete customer").classes("text-2xl font-bold")
                ui.label(
                    "Are you sure you want to delete this customer? This action cannot be undone."
                ).classes("my-4")
                with ui.row().style("justify-content: flex-end; width: 100%;"):
                    ui.button("Cancel").classes("button-close").props(
                        "color=black flat"
                    ).on("click", lambda: delete_customer_dialog.close())
                    ui.button("Delete").classes("button-close").props(
                        "color=red flat"
                    ).on(
                        "click",
                        lambda: (
                            requests.delete(
                                settings.API_URL
                                + f"/api/v1/admin/customers/{self.customer_id}",
                                headers=get_auth_header(),
                            ),
                            delete_customer_dialog.close(),
                            ui.navigate.to("/admin/customers"),
                        ),
                    )

            delete_customer_dialog.open()

    def create_card(self):
        with ui.card().classes("my-2").style(
            "width: 100%; box-shadow: none; border: 1px solid #e0e0e0; padding: 16px;"
        ):
            with ui.row().style(
                "justify-content: space-between; align-items: center; width: 100%;"
            ):
                with ui.column().style("flex: 0 0 auto; min-width: 25%;"):
                    customer_name = f"{self.name}"

                    if self.customer_abbr:
                        customer_name += f" ({self.customer_abbr})"

                    ui.label(customer_name).classes("text-h5 font-bold")

                    if self.partner_id != "N/A" and self.partner_id != "":
                        ui.label(f"Kaltura Partner ID: {self.partner_id}").classes(
                            "text-md"
                        )
                    ui.label(f"Plan: {self.priceplan.capitalize()}").classes(
                        "text-sm text-gray-500"
                    )
                    if self.priceplan == "fixed":
                        ui.label(
                            f"Blocks: {self.blocks_purchased} ({self.blocks_purchased * 4000} minutes)"
                        ).classes("text-sm text-gray-500")
                    ui.label(f"Base fee: {self.base_fee}").classes(
                        "text-sm text-gray-500"
                    )
                    if self.contact_email:
                        ui.label(f"Contact: {self.contact_email}").classes(
                            "text-sm text-gray-500"
                        )
                    ui.label(f"Realms: {self.realms}").classes("text-sm text-gray-500")
                    ui.label(
                        f"Total users: {self.stats.get('total_users', 0)}"
                    ).classes("text-sm text-gray-500")

                    ui.label(f"Created {self.created_at}").classes(
                        "text-sm text-gray-500"
                    )
                    if self.notes:
                        ui.label(f"Notes: {self.notes}").classes(
                            "text-sm text-gray-500"
                        )

                with ui.column().style("flex: 1;"):
                    ui.label("Statistics").classes("text-h6 font-bold")

                    with ui.row().classes("w-full gap-8"):
                        with ui.column().style("min-width: 30%;"):
                            ui.label("This month").classes("font-semibold")
                            ui.label(
                                f"Total transcribed files: {self.stats.get('transcribed_files', 0)}"
                            ).classes("text-sm")
                            ui.label(
                                f"Total transcribed minutes: {self.stats.get('total_transcribed_minutes', 0):.0f}"
                            ).classes("text-sm")

                            if self.partner_id != "N/A" and self.partner_id != "":
                                ui.label(
                                    f"Transcribed minutes via Sunet Scribe: {self.stats.get('transcribed_minutes', 0):.0f}"
                                )
                                ui.label(
                                    f"Transcribed minutes via Sunet Play: {self.stats.get('transcribed_minutes_external', 0):.0f}"
                                ).classes("text-sm")

                            # Show block usage for fixed plan
                            if self.priceplan == "fixed" and self.blocks_purchased > 0:
                                ui.label(
                                    f"Blocks consumed: {self.stats.get('blocks_consumed', 0):.2f}"
                                ).classes("text-sm font-semibold text-blue-600")

                                overage = self.stats.get("overage_minutes", 0)
                                if overage > 0:
                                    ui.label(
                                        f"⚠️ Overage minutes: {overage:.0f} min"
                                    ).classes("text-sm font-semibold text-red-600")
                                else:
                                    ui.label(
                                        f"Remaining minutes: {self.stats.get('remaining_minutes', 0):.0f}"
                                    ).classes("text-sm font-semibold text-green-600")

                        with ui.column():
                            ui.label("Last month").classes("font-semibold")
                            ui.label(
                                f"Transcribed files: {self.stats.get('transcribed_files_last_month', 0)}"
                            ).classes("text-sm")
                            ui.label(
                                f"Total transcribed minutes: {self.stats.get('total_transcribed_minutes_last_month', 0):.0f}"
                            ).classes("text-sm")
                            if self.partner_id != "N/A" and self.partner_id != "":
                                ui.label(
                                    f"Transcribed minutes via Sunet Scribe: {self.stats.get('transcribed_minutes_last_month', 0):.0f}"
                                ).classes("text-sm")
                                ui.label(
                                    f"Transcribed minutes via Sunet Play: {self.stats.get('transcribed_minutes_external_last_month', 0):.0f}"
                                ).classes("text-sm")

                with ui.column().style("flex: 0 0 auto;"):
                    if get_bofh_status():
                        edit = (
                            ui.button("Edit")
                            .classes("button-edit")
                            .props("color=white flat")
                            .style("width: 100%")
                        )
                        delete = (
                            ui.button("Delete")
                            .classes("button-close")
                            .props("color=black flat")
                            .style("width: 100%")
                        )

                        edit.on("click", lambda e: self.edit_customer())
                        delete.on("click", lambda e: self.delete_customer_dialog())


def save_customer(
    customber_abbr: str,
    customer_id: str,
    partner_id: str,
    name: str,
    contact_email: str,
    priceplan: str,
    base_fee: int,
    selected_realms: list,
    new_realms: str,
    notes: str,
    blocks_purchased: int,
) -> None:
    # Combine selected and new realms
    new_realm_list = [r.strip() for r in new_realms.split(",") if r.strip()]
    all_realms = list(set(selected_realms + new_realm_list))
    realms_str = ",".join(all_realms)

    try:
        res = requests.put(
            settings.API_URL + f"/api/v1/admin/customers/{customer_id}",
            headers=get_auth_header(),
            json={
                "customer_abbr": customber_abbr,
                "partner_id": partner_id,
                "name": name,
                "contact_email": contact_email,
                "priceplan": priceplan,
                "base_fee": int(base_fee) if base_fee else 0,
                "realms": realms_str,
                "notes": notes,
                "blocks_purchased": int(blocks_purchased) if blocks_purchased else 0,
            },
        )
        res.raise_for_status()
        ui.navigate.to("/admin/customers")
    except requests.RequestException as e:
        ui.notify(f"Error saving customer: {e}", type="negative")


@ui.refreshable
@ui.page("/admin/customers/edit/{customer_id}")
def edit_customer(customer_id: str) -> None:
    """
    Page to edit a customer.
    """
    page_init()

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #f5f5f5;
            }
        </style>
        """
    )

    try:
        res = requests.get(
            settings.API_URL + f"/api/v1/admin/customers/{customer_id}",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        customer = res.json()["result"]

        realms = realms_get()
        customer_realms = [
            r.strip() for r in customer["realms"].split(",") if r.strip()
        ]

    except requests.RequestException as e:
        ui.label(f"Error fetching customer: {e}").classes("text-lg text-red-500")
        return

    with ui.card().style(
        "width: 100%; box-shadow: none; border: 1px solid #e0e0e0; align-self: center;"
    ):
        ui.label(f"Edit customer: {customer['name']}").classes(
            "text-3xl font-bold mb-4"
        )
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
                .props("outlined")
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

    with ui.footer().style("background-color: #ffffff;"):
        with ui.row().style(
            "justify-content: flex-left; width: 100%; padding: 16px; gap: 8px;"
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
                    priceplan_select.value,
                    base_fee.value,
                    realm_select.value if realm_select.value else [],
                    new_realms_input.value,
                    notes_input.value,
                    blocks_input.value,
                ),
            )
            ui.button("Cancel").classes("button-close").props("color=black flat").style(
                "width: 150px;"
            ).on("click", lambda: ui.navigate.to("/admin/customers"))


def export_customers_csv() -> None:
    """
    Export customers data as CSV.
    """
    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/customers/export/csv",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        csv_data = res.content.decode("utf-8")

        ui.download.content(str(csv_data), filename="customers_export.csv")

    except requests.RequestException:
        ui.notify("Error when exporting customers", color="red")


def create() -> None:
    @ui.page("/admin/customers")
    def customers() -> None:
        """
        Customer management page.
        """
        page_init()

        ui.add_head_html(default_styles)
        ui.add_head_html(
            """
            <style>
                body {
                    background-color: #f5f5f5;
                }
            </style>
            """
        )

        with ui.footer().style("background-color: #ffffff; color: black;"):
            with ui.row().style(
                "justify-content: flex-left; width: 100%; padding: 16px; gap: 8px;"
            ):
                ui.button("Back to groups").classes("button-close").props(
                    "color=black flat"
                ).style("width: 150px").on("click", lambda: ui.navigate.to("/admin"))

        with ui.row().style(
            "justify-content: space-between; align-items: center; width: 100%;"
        ):
            with ui.element("div").style("display: flex; gap: 0px;"):
                if get_bofh_status():
                    ui.label("Customer Management").classes("text-3xl font-bold")
                elif get_admin_status():
                    ui.label("Account Information").classes("text-3xl font-bold")
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

                # Export CSV button
                export_csv = (
                    ui.button("Export CSV")
                    .classes("button-edit")
                    .props("color=white flat")
                )
                export_csv.on("click", lambda: export_customers_csv())

        customers_data = customers_get()

        if not customers_data or "result" not in customers_data:
            ui.label(
                "No customers found. Create a new customer to get started."
            ).classes("text-lg")
            return

        with ui.scroll_area().style("height: calc(100vh - 160px); width: 100%;"):
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
                    priceplan=customer["priceplan"],
                    realms=customer["realms"],
                    notes=customer.get("notes", ""),
                    created_at=customer["created_at"],
                    stats=customer.get("stats", {}),
                    blocks_purchased=customer.get("blocks_purchased", 0),
                    base_fee=customer["base_fee"],
                )
                c.create_card()

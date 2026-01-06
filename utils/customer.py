import requests

from nicegui import ui
from utils.settings import get_settings
from utils.token import get_auth_header, get_bofh_status

settings = get_settings()


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

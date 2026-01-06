import requests

from nicegui import ui
from utils.settings import get_settings
from utils.token import get_auth_header
settings = get_settings()

class Group:
    def __init__(self, group_id: str, name: str, description: str, created_at: str, users: dict, nr_users: int, stats: dict, quota_seconds: int) -> None:
        self.group_id = group_id
        self.name = name
        self.description = description
        self.created_at = created_at.split(".")[0]
        self.users = users
        self.nr_users = nr_users
        self.stats = stats
        self.quota_seconds = quota_seconds

    def edit_group(self) -> None:
        ui.navigate.to(f"/admin/edit/{self.group_id}")

    def delete_group_dialog(self) -> None:
        with ui.dialog() as delete_group_dialog:
            with ui.card().style("width: 400px; max-width: 90vw;"):
                ui.label("Delete group").classes("text-2xl font-bold")
                ui.label("Are you sure you want to delete this group? This action cannot be undone.").classes("my-4")
                with ui.row().style("justify-content: flex-end; width: 100%;"):
                    ui.button("Cancel").classes("button-close").props(
                        "color=black flat"
                    ).on("click", lambda: delete_group_dialog.close())
                    ui.button("Delete").classes("button-close").props(
                        "color=red flat"
                    ).on(
                        "click",
                        lambda: (
                            requests.delete(
                                settings.API_URL + f"/api/v1/admin/groups/{self.group_id}",
                                headers=get_auth_header(),
                            ),
                            delete_group_dialog.close(),
                            ui.navigate.to("/admin")
                        ),
                    )

            delete_group_dialog.open()

    def create_card(self):
        with ui.card().classes("my-2").style("width: 100%; box-shadow: none; border: 1px solid #e0e0e0; padding: 16px;"):
            with ui.row().style(
                "justify-content: space-between; align-items: center; width: 100%;"
            ):
                with ui.column().style("flex: 0 0 auto; min-width: 25%;"):
                    ui.label(f"{self.name}").classes("text-h5 font-bold")
                    ui.label(self.description).classes("text-md")

                    if self.name != "All users":
                        ui.label(f"Created {self.created_at}").classes("text-sm text-gray-500")

                    ui.label(f"{self.nr_users} members").classes("text-sm text-gray-500")
                    ui.label(f"Monthly transcription limit: {'Unlimited' if self.quota_seconds == 0 else str(self.quota_seconds // 60) + ' minutes'}").classes("text-sm text-gray-500")
                with ui.column().style("flex: 1;"):
                    ui.label("Statistics").classes("text-h6 font-bold")

                    with ui.row().classes("w-full gap-8"):
                        with ui.column().style("min-width: 30%;"):
                            ui.label("This month").classes("font-semibold")
                            ui.label(f"Transcribed files current month: {self.stats["transcribed_files"]}").classes("text-sm")
                            ui.label(f"Transcribed minutes current month: {self.stats["total_transcribed_minutes"]:.0f}").classes("text-sm")
                        with ui.column():
                            ui.label("Last month").classes("font-semibold")
                            ui.label(f"Transcribed files last month: {self.stats["transcribed_files_last_month"]}").classes("text-sm")
                            ui.label(f"Transcribed minutes last month: {self.stats["total_transcribed_minutes_last_month"]:.0f}").classes("text-sm")

                with ui.column().style("flex: 0 0 auto;"):

                    statistics = ui.button("Statistics").classes("button-edit").props(
                        "color=white flat"
                    ).style("width: 100%")

                    statistics.on(
                        "click",
                        lambda: ui.navigate.to(f"/admin/stats/{self.group_id}")
                    )

                    if self.name == "All users":
                        return

                    edit = ui.button("Edit").classes("button-edit").props(
                        "color=white flat"
                    ).style("width: 100%")
                    delete = ui.button("Delete").classes("button-close").props(
                        "color=black flat"
                    ).style("width: 100%")

                    edit.on(
                        "click",
                        lambda e: self.edit_group()
                    )
                    delete.on(
                        "click",
                        lambda e: self.delete_group_dialog()
                    )

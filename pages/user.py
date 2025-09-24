from nicegui import ui
from utils.common import (
    page_init,
)
from utils.token import get_user_data
from datetime import datetime


def create() -> None:
    @ui.refreshable
    @ui.page("/user")
    def home() -> None:
        """
        User page for managing user settings and information.
        """
        page_init()
        userdata = get_user_data()

        with ui.card().classes("w-full max-w-4xl mx-auto mb-6 no-shadow"):
            with ui.card_section():
                ui.label("User Information").classes("text-xl font-semibold mb-4")

                with ui.grid(columns=2).classes("gap-4"):
                    with ui.column():
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("person").classes("text-blue-500")
                            ui.label("Username:").classes("font-medium")
                            ui.label(userdata["user"]["username"]).classes(
                                "text-gray-700"
                            )

                        with ui.row().classes("items-center gap-2"):
                            ui.icon("domain").classes("text-green-500")
                            ui.label("Realm:").classes("font-medium")
                            ui.label(userdata["user"]["realm"]).classes("text-gray-700")

                        with ui.row().classes("items-center gap-2"):
                            ui.icon("admin_panel_settings").classes("text-purple-500")
                            ui.label("Admin:").classes("font-medium")
                            admin_status = "Yes" if userdata["user"]["admin"] else "No"
                            ui.label(admin_status).classes("text-gray-700")

                    with ui.column():
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("schedule").classes("text-orange-500")
                            ui.label("Transcribed Time:").classes("font-medium")
                            minutes = userdata["user"]["transcribed_seconds"] // 60
                            seconds = userdata["user"]["transcribed_seconds"] % 60
                            ui.label(f"{minutes}min {seconds}s").classes(
                                "text-gray-700"
                            )

                        with ui.row().classes("items-center gap-2"):
                            ui.icon("login").classes("text-teal-500")
                            ui.label("Last Login:").classes("font-medium")
                            last_login = datetime.fromisoformat(
                                userdata["user"]["last_login"].replace(" ", "T")
                            )
                            formatted_date = last_login.strftime("%B %d, %Y at %H:%M")
                            ui.label(formatted_date).classes("text-gray-700")

                        with ui.row().classes("items-center gap-2"):
                            ui.icon("fingerprint").classes("text-gray-600")
                            ui.label("User ID:").classes("font-medium")
                            ui.label(userdata["user"]["user_id"]).classes(
                                "text-gray-700"
                            )

            with ui.card_section().classes("w-full"):
                ui.label("Job History").classes("text-xl font-semibold mb-4")

                if userdata["jobs"]["jobs"]:
                    columns = [
                        {
                            "name": "filename",
                            "label": "Filename",
                            "field": "filename",
                            "align": "left",
                        },
                        {
                            "name": "job_type",
                            "label": "Type",
                            "field": "job_type",
                            "align": "center",
                        },
                        {
                            "name": "created_at",
                            "label": "Created",
                            "field": "created_at",
                            "align": "center",
                        },
                        {
                            "name": "deletion_date",
                            "label": "Expires",
                            "field": "deletion_date",
                            "align": "center",
                        },
                    ]

                    jobs_data = []
                    for job in userdata["jobs"]["jobs"]:
                        created_date = datetime.fromisoformat(
                            job["created_at"].replace(" ", "T")
                        )
                        deletion_date = datetime.fromisoformat(
                            job["deletion_date"].replace(" ", "T")
                        )

                        jobs_data.append(
                            {
                                "filename": job["filename"],
                                "job_type": job["job_type"].capitalize(),
                                "created_at": created_date.strftime("%m/%d/%Y %H:%M"),
                                "deletion_date": deletion_date.strftime("%m/%d/%Y"),
                            }
                        )

                    ui.table(columns=columns, rows=jobs_data).classes("w-full").style(
                        "box-shadow: none;"
                    )

                else:
                    with ui.row().classes("justify-center items-center py-8"):
                        ui.icon("work_off").classes("text-6xl text-gray-400")
                        with ui.column().classes("text-center ml-4"):
                            ui.label("No jobs found").classes("text-xl text-gray-500")
                            ui.label(
                                "Your transcription jobs will appear here"
                            ).classes("text-gray-400")

from nicegui import app, ui
from utils.common import add_timezone_to_timestamp, page_init
from utils.token import get_user_data


def create() -> None:
    @ui.refreshable
    @ui.page("/user")
    def home() -> None:
        """
        User page for managing user settings and information.
        """
        page_init()
        userdata = get_user_data()

        with ui.card().classes("w-full mx-auto mb-6 no-shadow"):
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
                            ui.icon("public").classes("text-purple-500")
                            ui.label("Timezone:").classes("font-medium")
                            ui.label(app.storage.user.get("timezone", "UTC")).classes(
                                "text-gray-700"
                            )

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
                            "name": "created_at",
                            "label": "Created",
                            "field": "created_at",
                            "align": "center",
                        },
                        {
                            "name": "updated_at",
                            "label": "Last Updated",
                            "field": "updated_at",
                            "align": "center",
                        },
                        {
                            "name": "deletion_date",
                            "label": "Scheduled deletion",
                            "field": "deletion_date",
                            "align": "center",
                        },
                        {
                            "name": "status",
                            "label": "Status",
                            "field": "status",
                            "align": "center",
                        },
                        {
                            "name": "length",
                            "label": "Length",
                            "field": "length",
                            "align": "center",
                        },
                    ]

                    jobs_data = []
                    for job in userdata["jobs"]["jobs"]:
                        created_at = add_timezone_to_timestamp(job["created_at"])
                        updated_at = add_timezone_to_timestamp(job["updated_at"])
                        deletion_date = add_timezone_to_timestamp(job["deletion_date"])

                        if job["transcribed_seconds"] > 0:
                            length = f"{int(job['transcribed_seconds'] // 60)}min {int(job['transcribed_seconds'] % 60)}s"
                        else:
                            length = "-"

                        jobs_data.append(
                            {
                                "filename": job["filename"],
                                "job_type": job["job_type"].capitalize(),
                                "created_at": created_at,
                                "updated_at": updated_at,
                                "deletion_date": deletion_date,
                                "status": job["status"].capitalize(),
                                "length": length,
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

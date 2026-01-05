import requests

from nicegui import app, ui
from utils.common import add_timezone_to_timestamp, page_init
from utils.common import default_styles
from utils.settings import get_settings
from utils.token import get_auth_header, get_user_data

settings = get_settings()


def email_save(email: str) -> None:
    """
    Save and test the notification email address.

    Parameters:
        email (str): The email address to save.
    """

    try:
        response = requests.put(
            f"{settings.API_URL}/api/v1/me",
            headers=get_auth_header(),
            json={"email": email},
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data.get("result", {}):
            ui.notify(f"Error: {data['result']['error']}", color="red")
            return None

        ui.notify("E-mail address saved successfully", color="green")
        return data["result"]

    except requests.exceptions.RequestException:
        ui.notify("Failed to save e-mail address", color="red")
        return None


def email_get() -> str:
    """
    Get the current notification email address.

    Returns:
        str: The current email address.
    """

    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/me", headers=get_auth_header(), json={}
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data.get("result", {}):
            ui.notify(f"Error: {data['result']['error']}", color="red")
            return ""

        return data["result"]["user"].get("email", "")

    except requests.exceptions.RequestException:
        ui.notify("Failed to retrieve e-mail address", color="red")
        return ""


def create() -> None:
    @ui.refreshable
    @ui.page("/user")
    def home() -> None:
        """
        User page for managing user settings and information.
        """
        page_init()
        userdata = get_user_data()

        ui.add_head_html(default_styles)
        current_email = email_get()

        with ui.card().classes("w-full mx-auto mb-6"):
            with ui.card_section():
                ui.label("User Information").classes("text-xl font-semibold mb-6")

                with ui.grid(columns=3).classes("gap-6"):
                    # Column 1 — Identity
                    with ui.column().classes("gap-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("person").classes("text-blue-500")
                            ui.label("Username").classes("font-medium text-gray-600")
                            ui.label(userdata["user"]["username"]).classes(
                                "text-gray-900"
                            )

                        with ui.row().classes("items-center gap-2 mt-2"):
                            ui.icon("fingerprint").classes("text-gray-500")
                            ui.label("User ID").classes("font-medium text-gray-600")
                            ui.label(userdata["user"]["user_id"]).classes(
                                "text-gray-500 text-sm break-all"
                            )

                    # Column 2 — Usage
                    with ui.column().classes("gap-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("schedule").classes("text-orange-500")
                            ui.label("Transcribed Time").classes(
                                "font-medium text-gray-600"
                            )

                            minutes = userdata["user"]["transcribed_seconds"] // 60
                            seconds = userdata["user"]["transcribed_seconds"] % 60
                            ui.label(f"{minutes} min {seconds} s").classes(
                                "text-gray-900"
                            )

                    # Column 3 — Locale
                    with ui.column().classes("gap-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("public").classes("text-purple-500")
                            ui.label("Timezone").classes("font-medium text-gray-600")

                            ui.label(app.storage.user.get("timezone", "UTC")).classes(
                                "text-gray-900"
                            )

            with ui.card_section().classes("w-full"):
                ui.label("Notifications").classes("text-lg font-semibold mb-4")

                with ui.row().classes("items-center gap-2 w-full"):
                    ui.icon("email").classes("text-red-500")
                    email = ui.input(
                        placeholder=current_email,
                        label=current_email,
                        value=current_email,
                    ).classes("w-1/3")
                    save = ui.button("Test and save")
                    save.props("color=black flat")
                    save.classes("default-style")
                    save.on("click", lambda: email_save(email.value))

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

from nicegui import ui
from utils.common import page_init
from utils.common import default_styles
from utils.helpers import (
    email_get,
    email_save,
    email_save_notifications,
    email_save_notifications_get,
)
from utils.settings import get_settings
from utils.token import get_admin_status, get_user_data
from utils.storage import storage

settings = get_settings()


def show_user_token() -> None:
    with ui.dialog() as dialog:
        with ui.card().style("max-width: 50%; width: 500px; min-width: 500px;"):
            ui.label("User Token").classes("text-2xl font-bold")
            ui.label("Your user token is used to authenticate API requests.").classes(
                "my-4"
            )
            token = storage.get("token", "No token found.")
            ui.textarea(value=token).classes("w-full h-full")
            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Close").classes("button-close").props("color=black flat").on(
                    "click", lambda: dialog.close()
                )

        dialog.open()


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
        current_notifications = email_save_notifications_get()

        # If userdata is not available, do not render the page
        if userdata is None or not userdata:
            ui.navigate.to("/")
            return

        with ui.card().classes("w-full mx-auto mb-6 no-border no-shadow"):
            with ui.card_section():
                ui.label("User Information").classes("text-xl font-semibold mb-6")

                with ui.grid(columns=3).classes("gap-6"):
                    with ui.column().classes("gap-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("person").classes("text-blue-500")
                            ui.label("Username").classes("font-medium text-gray-600")
                            ui.label(userdata["username"]).classes("text-gray-900").on(
                                "click", lambda: show_user_token()
                            )

                        with ui.row().classes("items-center gap-2 mt-2"):
                            ui.icon("fingerprint").classes("text-gray-500")
                            ui.label("User ID").classes("font-medium text-gray-600")
                            ui.label(userdata["user_id"]).classes(
                                "text-gray-500 text-sm break-all"
                            )

                    with ui.column().classes("gap-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("schedule").classes("text-orange-500")
                            ui.label("Transcribed Time").classes(
                                "font-medium text-gray-600"
                            )

                            minutes = userdata["transcribed_seconds"] // 60
                            seconds = userdata["transcribed_seconds"] % 60
                            ui.label(f"{minutes} min {seconds} s").classes(
                                "text-gray-900"
                            )

                    with ui.column().classes("gap-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("public").classes("text-purple-500")
                            ui.label("Timezone").classes("font-medium text-gray-600")

                            ui.label(storage.get("timezone", "UTC")).classes(
                                "text-gray-900"
                            )

            with ui.card_section().classes("w-full "):
                ui.label("Notifications").classes("text-lg font-semibold mb-4")

                with ui.grid(columns=2).classes("gap-8 w-full"):
                    with ui.column().classes("gap-4"):
                        ui.label("E-mail settings").classes("font-medium text-base")

                        with ui.row().classes("items-center gap-2 w-full"):
                            ui.icon("email").classes("text-red-500")

                            email = ui.input(
                                placeholder=current_email,
                                value=current_email,
                            ).classes("flex-grow")

                            save = ui.button("Test and save")
                            save.props("color=black flat")
                            save.classes("default-style")
                            save.on("click", lambda: email_save(email.value))

                    with ui.column().classes("gap-3"):
                        users = None
                        with ui.grid(columns=2).classes("gap-x-6 gap-y-2"):
                            ui.label("My notifications").classes(
                                "col-span-2 font-semibold"
                            )
                            ui.label(
                                "(Notifications related to your own files and activity)"
                            ).classes("col-span-2 text-sm text-gray-600")

                            jobs = ui.checkbox(
                                "Transcription completed",
                                value=True if "job" in current_notifications else False,
                            )
                            jobs.on(
                                "click",
                                lambda e: email_save_notifications(
                                    job=jobs.value,
                                    user=users.value if users is not None else None,
                                    deletion=deletions.value,
                                    # quota=quota.value,
                                ),
                            )
                            jobs.tooltip(
                                "Get an email when one of your transcription jobs finishes processing."
                            )

                            deletions = ui.checkbox(
                                "Upcoming file deletions",
                                value=True
                                if "deletion" in current_notifications
                                else False,
                            )
                            deletions.on(
                                "click",
                                lambda e: email_save_notifications(
                                    job=jobs.value,
                                    user=users.value if users is not None else None,
                                    deletion=deletions.value,
                                    # quota=quota.value,
                                ),
                            )
                            deletions.tooltip(
                                "Get an email one day before your uploaded files are permanently deleted."
                            )

                        if get_admin_status():
                            with ui.grid(columns=2).classes("gap-x-6 gap-y-2"):
                                ui.label("Administrator notifications").classes(
                                    "col-span-2 font-semibold"
                                )
                                ui.label(
                                    "(Notifications related to administrative tasks)"
                                ).classes("col-span-2 text-sm text-gray-600")

                                users = ui.checkbox(
                                    "New user registrations",
                                    value=True
                                    if "user" in current_notifications
                                    else False,
                                )
                                users.on(
                                    "click",
                                    lambda e: email_save_notifications(
                                        job=jobs.value,
                                        user=users.value,
                                        deletion=deletions.value,
                                        # quota=quota.value,
                                    ),
                                )
                                users.tooltip(
                                    "Get an email when a new user creates an account."
                                )

                                # quota = ui.checkbox(
                                #     "Quota nearing limit",
                                #     value=True
                                #     if "quota" in current_notifications
                                #     else False,
                                # )
                                # quota.on(
                                #     "click",
                                #     lambda e: email_save_notifications(
                                #         job=jobs.value,
                                #         user=users.value,
                                #         deletion=deletions.value,
                                #         quota=quota.value,
                                #     ),
                                # )
                                # quota.tooltip(
                                #     "Get an email when your transcription quota is nearing its limit."
                                # )

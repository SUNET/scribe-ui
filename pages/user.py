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

from nicegui import app, ui
from utils.common import page_init
from utils.common import default_styles
from utils.helpers import (
    email_get,
    email_save,
    email_save_notifications,
    email_save_notifications_get,
    test_all_notifications,
)
from utils.settings import get_settings
from utils.token import get_admin_status, get_user_data, get_bofh_status

settings = get_settings()


def show_user_token() -> None:
    with ui.dialog() as dialog:
        with ui.card().style("max-width: 50%; width: 500px; min-width: 500px;"):
            ui.label("User token").classes("text-2xl font-bold")
            ui.label("Your user token is used to authenticate API requests.").classes(
                "my-4"
            )
            token = app.storage.user.get("token", "No token found.")
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
        page_init(use_drawer=True)
        userdata = get_user_data()

        ui.add_head_html(default_styles)
        current_email = email_get()
        current_notifications = email_save_notifications_get()

        # If userdata is not available, do not render the page
        if userdata is None or not userdata:
            ui.navigate.to("/")
            return

        ui.label("User settings").classes("text-3xl font-bold mb-4")

        total_seconds = userdata["transcribed_seconds"]
        hours = int(total_seconds) // 3600
        minutes = int(total_seconds) % 3600 // 60

        # -- Profile section --
        ui.label("Profile").classes("text-lg font-semibold mb-2")
        ui.separator()

        with ui.column().classes("gap-2 mt-2 mb-6"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("person", color="black").style("font-size: 20px;")
                ui.label("Username").classes("font-medium text-gray-600").style(
                    "min-width: 140px;"
                )
                ui.label(userdata["username"]).classes("text-gray-900").style(
                    "cursor: pointer; text-decoration: underline;"
                ).on("click", lambda: show_user_token())
                ui.tooltip("Click to view your API token")

            with ui.row().classes("items-center gap-3"):
                ui.icon("fingerprint", color="black").style("font-size: 20px;")
                ui.label("User id").classes("font-medium text-gray-600").style(
                    "min-width: 140px;"
                )
                ui.label(userdata["user_id"]).classes("text-gray-500 text-sm")

            with ui.row().classes("items-center gap-3"):
                ui.icon("schedule", color="black").style("font-size: 20px;")
                ui.label("Transcribed time").classes(
                    "font-medium text-gray-600"
                ).style("min-width: 140px;")
                ui.label(f"{hours}h {minutes}min").classes("text-gray-900")

            with ui.row().classes("items-center gap-3"):
                ui.icon("public", color="black").style("font-size: 20px;")
                ui.label("Timezone").classes("font-medium text-gray-600").style(
                    "min-width: 140px;"
                )
                ui.label(app.storage.user.get("timezone", "UTC")).classes(
                    "text-gray-900"
                )

        # -- Email section --
        ui.label("Email").classes("text-lg font-semibold mb-2")
        ui.separator()

        with ui.row().classes("items-center gap-3 mt-2 mb-6"):
            ui.icon("email", color="black").style("font-size: 20px;")
            email = ui.input(
                placeholder=current_email,
                value=current_email,
            ).style("min-width: 300px;")

            save = ui.button("Test and save")
            save.props("color=black flat")
            save.classes("default-style")
            save.on("click", lambda: email_save(email.value))

        # -- Notifications section --
        ui.label("Notifications").classes("text-lg font-semibold mb-2")
        ui.separator()

        users = None
        quota = None
        weekly_report = None

        with ui.column().classes("gap-1 mt-2"):
            ui.label("Personal").classes("font-medium text-gray-600 mb-1")
            ui.label(
                "Notifications related to your own files and activity."
            ).classes("text-sm text-gray-500 mb-2")

            jobs = ui.checkbox(
                "Transcription completed",
                value="job" in current_notifications,
            )
            jobs.on(
                "click",
                lambda e: email_save_notifications(
                    job=jobs.value,
                    user=users.value if users is not None else None,
                    deletion=deletions.value,
                    quota=quota.value if quota is not None else None,
                    weekly_report=weekly_report.value
                    if weekly_report is not None
                    else None,
                ),
            )
            jobs.tooltip(
                "Get an email when one of your transcription jobs finishes processing."
            )

            deletions = ui.checkbox(
                "Upcoming file deletions",
                value="deletion" in current_notifications,
            )
            deletions.on(
                "click",
                lambda e: email_save_notifications(
                    job=jobs.value,
                    user=users.value if users is not None else None,
                    deletion=deletions.value,
                    quota=quota.value if quota is not None else None,
                    weekly_report=weekly_report.value
                    if weekly_report is not None
                    else None,
                ),
            )
            deletions.tooltip(
                "Get an email one day before your uploaded files are permanently deleted."
            )

        if get_admin_status():
            with ui.column().classes("gap-1 mt-4"):
                ui.label("Administration").classes("font-medium text-gray-600 mb-1")
                ui.label(
                    "Notifications related to administrative tasks."
                ).classes("text-sm text-gray-500 mb-2")

                users = ui.checkbox(
                    "New user registrations",
                    value="user" in current_notifications,
                )
                users.on(
                    "click",
                    lambda e: email_save_notifications(
                        job=jobs.value,
                        user=users.value,
                        deletion=deletions.value,
                        quota=quota.value,
                        weekly_report=weekly_report.value,
                    ),
                )
                users.tooltip(
                    "Get an email when a new user creates an account."
                )

                quota = ui.checkbox(
                    "Quota alerts",
                    value="quota" in current_notifications,
                )
                quota.on(
                    "click",
                    lambda e: email_save_notifications(
                        job=jobs.value,
                        user=users.value,
                        deletion=deletions.value,
                        quota=quota.value,
                        weekly_report=weekly_report.value,
                    ),
                )
                quota.tooltip(
                    "Get an email when a group or account quota is approaching its limit."
                )

                weekly_report = ui.checkbox(
                    "Usage summary (current month, sent weekly)",
                    value="weekly_report" in current_notifications,
                )
                weekly_report.on(
                    "click",
                    lambda e: email_save_notifications(
                        job=jobs.value,
                        user=users.value,
                        deletion=deletions.value,
                        quota=quota.value,
                        weekly_report=weekly_report.value,
                    ),
                )
                weekly_report.tooltip(
                    "Get a weekly email with a summary of transcription usage."
                )


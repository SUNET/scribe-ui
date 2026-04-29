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
from utils.styles import default_styles
from utils.helpers import (
    dark_mode_get,
    dark_mode_save,
    email_get,
    email_save,
    email_save_notifications,
    email_save_notifications_get,
)
from utils.settings import get_settings
from utils.token import get_admin_status, get_user_data

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

        with ui.row().classes("w-full gap-8 items-start"):
            # ── Left column: Profile, Email, Dark mode ──
            with ui.column().classes("flex-1"):
                # -- Profile section --
                ui.label("Profile").classes("text-lg font-semibold mb-2")
                ui.separator()

                with ui.column().classes("gap-2 mt-2 mb-6"):
                    with ui.row().classes("items-center gap-3"):
                        ui.icon("person").style("font-size: 20px;")
                        ui.label("Username").classes("font-medium text-theme-secondary").style(
                            "min-width: 140px;"
                        )
                        ui.label(userdata["username"]).classes("text-theme-primary").style(
                            "cursor: pointer; text-decoration: underline;"
                        ).on("click", lambda: show_user_token())
                        ui.tooltip("Click to view your API token")

                    with ui.row().classes("items-center gap-3"):
                        ui.icon("fingerprint").style("font-size: 20px;")
                        ui.label("User id").classes("font-medium text-theme-secondary").style(
                            "min-width: 140px;"
                        )
                        ui.label(userdata["user_id"]).classes("text-theme-muted text-sm")

                    with ui.row().classes("items-center gap-3"):
                        ui.icon("schedule").style("font-size: 20px;")
                        ui.label("Transcribed time").classes(
                            "font-medium text-theme-secondary"
                        ).style("min-width: 140px;")
                        ui.label(f"{hours}h {minutes}min").classes("text-theme-primary")

                    with ui.row().classes("items-center gap-3"):
                        ui.icon("public").style("font-size: 20px;")
                        ui.label("Timezone").classes("font-medium text-theme-secondary").style(
                            "min-width: 140px;"
                        )
                        ui.label(app.storage.user.get("timezone", "UTC")).classes(
                            "text-theme-primary"
                        )

                # -- Email section --
                ui.label("Email").classes("text-lg font-semibold mb-2")
                ui.separator()

                with ui.row().classes("items-center gap-3 mt-2 mb-6"):
                    ui.icon("email").style("font-size: 20px;")
                    email = ui.input(
                        placeholder=current_email,
                        value=current_email,
                    ).style("min-width: 300px;")

                    save = ui.button("Test and save")
                    save.props("color=black flat")
                    save.classes("default-style")
                    save.on("click", lambda: email_save(email.value))

                # -- Theme section --
                ui.label("Theme").classes("text-lg font-semibold mb-2")
                ui.separator()

                with ui.column().classes("gap-2 mt-2 mb-6"):
                    dark_options = {"off": "Light", "on": "Dark", "auto": "Auto (System)"}

                    # Current value: True -> "on", False -> "off", None -> "auto"
                    raw = app.storage.user.get("dark_mode", None)
                    if raw is None:
                        current_dark = "auto"
                    elif raw:
                        current_dark = "on"
                    else:
                        current_dark = "off"

                    def set_dark_mode(value: str) -> None:
                        if value == "on":
                            app.storage.user["dark_mode"] = True
                            app.storage.user["_resolved_dark"] = True
                            ui.dark_mode(True)
                            dark_mode_save(True)
                            icon_name = "dark_mode"
                        elif value == "off":
                            app.storage.user["dark_mode"] = False
                            app.storage.user["_resolved_dark"] = False
                            ui.dark_mode(False)
                            dark_mode_save(False)
                            icon_name = "light_mode"
                        else:
                            app.storage.user["dark_mode"] = None
                            ui.dark_mode(None)
                            dark_mode_save(None)
                            icon_name = "brightness_auto"
                        # Update header dark mode icon without reload
                        ui.run_javascript(f'''
                            document.querySelectorAll(".header-btn .q-icon").forEach(el => {{
                                if (["dark_mode", "light_mode", "brightness_auto"].includes(el.textContent.trim())) {{
                                    el.textContent = "{icon_name}";
                                }}
                            }});
                        ''')

                    ui.toggle(
                        dark_options,
                        value=current_dark,
                        on_change=lambda e: set_dark_mode(e.value),
                    ).props("toggle-color=primary no-caps").tooltip("Light: always light, Dark: always dark, Auto: follow system settings.")

            # ── Right column: Notifications ──
            with ui.column().classes("flex-1"):
                ui.label("Notifications").classes("text-lg font-semibold mb-2")
                ui.separator()

                users = None
                quota = None
                weekly_report = None

                with ui.column().classes("gap-1 mt-2"):
                    ui.label("Personal").classes("font-medium text-theme-secondary mb-1")
                    ui.label(
                        "Notifications related to your own files and activity."
                    ).classes("text-sm text-theme-muted mb-2")

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
                        ui.label("Administration").classes("font-medium text-theme-secondary mb-1")
                        ui.label(
                            "Notifications related to administrative tasks."
                        ).classes("text-sm text-theme-muted mb-2")

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



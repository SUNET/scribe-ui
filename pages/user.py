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
    dark_mode_save,
    email_get,
    email_save,
    email_save_notifications,
    email_save_notifications_get,
)
from utils.drive import (
    display_name as drive_display_name,
    drive_logout,
    drive_status,
)
from utils.settings import get_settings

settings = get_settings()


async def draw_drive_section(section: ui.column) -> None:
    """
    Whether Scribe is signed in to the reader's Sunet Drive, and a way to
    log out of it. Drawn only when their organisation offers Drive -- which
    Drive that is, and what it is called, is the organisation's setting,
    not the reader's.

    Logging out revokes Scribe's access in Drive as well; the next Get from
    or Save to asks the reader to sign in again.
    """

    status = await drive_status()
    if not status.ok or not status.result.get("enabled"):
        return

    name = drive_display_name(status.result)

    section.clear()
    with section:
        ui.label(name).classes("text-lg font-semibold mb-2")
        ui.separator()

        with ui.row().classes("items-center gap-3 mt-2 mb-6"):
            ui.icon("cloud").style("font-size: 20px;").props("aria-hidden=true")
            state = ui.label("").classes("text-theme-secondary").props(
                "role=status aria-live=polite"
            )
            logout = ui.button(f"Log out from {name}", icon="logout")
            logout.props("color=black flat")
            logout.classes("delete-style")

    def show_state(connected: bool) -> None:
        state.set_text(
            f"Signed in to {name}." if connected else f"Not signed in to {name}."
        )
        logout.set_visibility(connected)

    async def do_logout() -> None:
        result = await drive_logout()
        if not result.ok:
            ui.notify(result.error, type="negative", timeout=None, close_button="Close")
            return
        ui.notify(f"Logged out from {name}", type="positive")
        show_state(False)

    logout.on("click", do_logout)
    show_state(bool(status.result.get("connected")))


def show_user_token() -> None:
    with ui.dialog().props('aria-label="User token"') as dialog:
        with ui.card().style("max-width: 50%; width: 500px; min-width: 500px;"):
            ui.label("User token").classes("text-2xl font-bold")
            ui.label("Your user token is used to authenticate API requests.").classes(
                "my-4"
            )
            token = app.storage.user.get("token", "No token found.")
            ui.textarea(value=token).props(
                'aria-label="API token" readonly'
            ).classes("w-full h-full")
            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Close").classes("button-close").props("color=black flat").on(
                    "click", lambda: dialog.close()
                )

        dialog.open()


def create() -> None:
    @ui.refreshable
    @ui.page("/user")
    async def home() -> None:
        """
        User page for managing user settings and information.
        """
        user_data = await page_init(use_drawer=True, title="User settings")
        userdata = user_data

        ui.add_head_html(default_styles)
        current_email = email_get()
        current_notifications = email_save_notifications_get()

        # If userdata is not available, do not render the page
        if userdata is None or not userdata:
            ui.navigate.to("/")
            return

        ui.label("User settings").classes("text-3xl font-bold mb-4").props("role=heading aria-level=1")

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
                        ui.label("Username").classes(
                            "font-medium text-theme-secondary"
                        ).style("min-width: 140px;")
                        # A ui.label with an on-click handler renders as a
                        # div: no role, not in the Tab order, and Enter/Space
                        # do nothing to it, so the API token was reachable by
                        # mouse only (WCAG 2.1.1). ui.button gives the control
                        # what a label structurally cannot: a button role, a
                        # Tab stop, and Enter/Space activation. Its own
                        # default chrome (padding, border, min-height) is
                        # reset in styles.py under .user-token-btn, so it
                        # still reads as the underlined username it replaces,
                        # not a boxed button.
                        # color=None, not left at ui.button's own default
                        # of "primary": that default adds Quasar's own
                        # "text-primary" class, painting the button
                        # #5898d4 (Quasar's JS config, unrelated to either
                        # theme) ahead of the text-theme-primary class
                        # below -- measured with axe, which is how this
                        # was caught even though the button visibly still
                        # looked underlined and in-place. color=None adds
                        # no Quasar colour class at all, leaving
                        # text-theme-primary as the only rule painting it.
                        with ui.button(
                            userdata["username"],
                            on_click=show_user_token,
                            color=None,
                        ).props("flat no-caps").classes(
                            "text-theme-primary user-token-btn"
                        ):
                            ui.tooltip("Click to view your API token")

                    with ui.row().classes("items-center gap-3"):
                        ui.icon("fingerprint").style("font-size: 20px;")
                        ui.label("User id").classes(
                            "font-medium text-theme-secondary"
                        ).style("min-width: 140px;")
                        ui.label(userdata["user_id"]).classes(
                            "text-theme-muted text-sm"
                        )

                    with ui.row().classes("items-center gap-3"):
                        ui.icon("schedule").style("font-size: 20px;")
                        ui.label("Transcribed time").classes(
                            "font-medium text-theme-secondary"
                        ).style("min-width: 140px;")
                        ui.label(f"{hours}h {minutes}min").classes("text-theme-primary")

                    with ui.row().classes("items-center gap-3"):
                        ui.icon("public").style("font-size: 20px;")
                        ui.label("Timezone").classes(
                            "font-medium text-theme-secondary"
                        ).style("min-width: 140px;")
                        ui.label(app.storage.user.get("timezone", "UTC")).classes(
                            "text-theme-primary"
                        )

                # -- Email section --
                ui.label("Email").classes("text-lg font-semibold mb-2")
                ui.separator()

                with ui.row().classes("items-center gap-3 mt-2 mb-6"):
                    ui.icon("email").style("font-size: 20px;")
                    # The "Email" heading two rows above is a section title,
                    # not this field's label -- nothing connected the two,
                    # and the placeholder was the reader's own current
                    # address, which describes nothing about what the field
                    # is for (WCAG 3.3.2). A real label fixes both: it is
                    # the field's accessible name, and it reads as an
                    # instruction on its own. type=email and
                    # autocomplete=email were also missing; value already
                    # covers what the placeholder used to.
                    email = ui.input(
                        "Email address for notifications",
                        value=current_email,
                    ).props("type=email autocomplete=email").style(
                        "min-width: 300px;"
                    )

                    save = ui.button("Test and save")
                    save.props("color=black flat")
                    save.classes("default-style")
                    save.on("click", lambda: email_save(email.value))

                # -- Theme section --
                theme_label = ui.label("Theme").classes("text-lg font-semibold mb-2")
                ui.separator()

                with ui.column().classes("gap-2 mt-2 mb-6"):
                    dark_options = {
                        "off": "Light",
                        "on": "Dark",
                        "auto": "Auto (System)",
                    }

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
                        ui.run_javascript(
                            f"""
                            document.querySelectorAll(".header-btn .q-icon").forEach(el => {{
                                if (["dark_mode", "light_mode", "brightness_auto"].includes(el.textContent.trim())) {{
                                    el.textContent = "{icon_name}";
                                }}
                            }});
                        """
                        )

                    # A button group has no name of its own: role=group and
                    # the visible "Theme" heading as its label (WCAG 1.3.1,
                    # 4.1.2).
                    ui.toggle(
                        dark_options,
                        value=current_dark,
                        on_change=lambda e: set_dark_mode(e.value),
                    ).props(
                        "toggle-color=primary no-caps role=group "
                        f"aria-labelledby={theme_label.html_id}"
                    ).tooltip(
                        "Light: always light, Dark: always dark, Auto: follow system settings."
                    )

                # -- Sunet Drive sign-in, when the organisation offers it --
                drive_section = ui.column().classes("w-full gap-0")
                ui.timer(
                    0.0, lambda: draw_drive_section(drive_section), once=True
                )

            # ── Right column: Notifications ──
            with ui.column().classes("flex-1"):
                ui.label("Notifications").classes("text-lg font-semibold mb-2")
                ui.separator()

                users = None
                quota = None
                weekly_report = None

                with ui.column().classes("gap-1 mt-2"):
                    ui.label("Personal").classes(
                        "font-medium text-theme-secondary mb-1"
                    )
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

                if (user_data or {}).get("admin"):
                    with ui.column().classes("gap-1 mt-4"):
                        ui.label("Administration").classes(
                            "font-medium text-theme-secondary mb-1"
                        )
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

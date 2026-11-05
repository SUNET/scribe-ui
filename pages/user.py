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

from typing import Callable

from nicegui import app, ui
from utils.common import page_dark_mode, page_init
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


def card(icon: str, title: str, summary: str) -> ui.element:
    """
    A settings card: an icon (not read out), the title as a heading (h2)
    and a line saying what the card is for. Returns the card, to fill.
    """

    section = ui.element("section").classes("settings-card")

    with section:
        with ui.element("div").classes("settings-card-head"):
            ui.icon(icon).props("aria-hidden=true")

            with ui.element("div"):
                ui.label(title).classes("settings-card-title").props("role=heading aria-level=2")
                ui.label(summary).classes("settings-card-summary")

    return section


async def draw_drive_section(section: ui.element) -> None:
    """
    Whether Scribe is signed in to the reader's Sunet Drive, and a way to
    log out of it, in the Connected services card. Drawn only when their
    organisation offers Drive -- which Drive that is, and what it is called,
    is the organisation's setting, not the reader's; without it the card is
    not shown at all.

    Logging out revokes Scribe's access in Drive as well; the next Get from
    or Save to asks the reader to sign in again.
    """

    status = await drive_status()
    if not status.ok or not status.result.get("enabled"):
        return

    name = drive_display_name(status.result)

    section.clear()
    section.set_visibility(True)

    with section:
        with ui.element("div").classes("settings-card-head"):
            ui.icon("cloud").props("aria-hidden=true")

            with ui.element("div"):
                ui.label("Connected services").classes("settings-card-title").props(
                    "role=heading aria-level=2"
                )
                ui.label("Services Scribe can get files from and save files to.").classes(
                    "settings-card-summary"
                )

        with ui.element("div").classes("settings-row settings-row-first"):
            with ui.element("div").classes("settings-row-text"):
                with ui.element("div").classes("settings-service"):
                    ui.label(name).classes("settings-row-title")
                    # Said when it changes: signed in, or not after logging out.
                    state = ui.label("").classes("settings-status").props(
                        "role=status aria-live=polite"
                    )
                hint = ui.label("").classes("settings-row-summary")

            logout = ui.button(f"Log out from {name}", icon="logout")
            logout.props("color=black flat no-caps")
            logout.classes("delete-style settings-button")

    def show_state(connected: bool) -> None:
        state.set_text("Signed in" if connected else "Not signed in")
        state.classes(add="is-on") if connected else state.classes(remove="is-on")
        hint.set_text(
            f"Logging out also removes Scribe's access in {name}."
            if connected
            else "Scribe asks you to sign in the first time you get or save a file."
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
    with ui.dialog().props('aria-label="API token"') as dialog:
        # As wide as it was on a wide screen, the screen's width on a phone.
        with ui.card().classes("user-token-card"):
            ui.label("API token").classes("text-2xl font-bold").props("role=heading aria-level=2")
            ui.label("Used to authenticate requests to the Scribe API.").classes(
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


def option(label: str, description: str, value: bool, on_change: Callable) -> ui.checkbox:
    """
    A notification to choose: the checkbox with its name, and under it, in
    the page rather than in a tooltip, what it is for -- the checkbox's
    description for a screen reader too. Saved when it changes, by mouse or
    by keyboard.
    """

    with ui.element("div").classes("settings-option"):
        box = ui.checkbox(label, value=value, on_change=on_change).classes("settings-option-box")
        text = ui.label(description).classes("settings-option-summary")
        box._props["aria-describedby"] = text.html_id

    return box


def create() -> None:
    @ui.refreshable
    @ui.page("/user")
    async def home() -> None:
        """
        User settings: who the reader is, their e-mail notifications, how
        Scribe looks, and the services it is connected to -- as cards, two
        columns on a wide page and one on a phone (utils/styles.py,
        .settings-grid). In the page they come as the columns are read:
        Account, Theme, Connected services, then Email notifications.
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

        total_seconds = userdata["transcribed_seconds"]
        hours = int(total_seconds) // 3600
        minutes = int(total_seconds) % 3600 // 60
        is_admin = bool(userdata.get("admin") or userdata.get("bofh"))

        with ui.element("div").classes("settings"):
            ui.label("User settings").classes("text-3xl font-bold mb-4").props(
                "role=heading aria-level=1"
            )

            with ui.element("div").classes("settings-grid"):
                # Two columns on a wide page, each read top to bottom, the left one
                # first -- the order of the page, of the keyboard and of a phone:
                # Account, Theme, Connected services, then Email notifications.
                with ui.element("div").classes("settings-column"):
                    # ── Account ──
                    with card("account_circle", "Account", "Who you are signed in as, and your use of Scribe.").classes(
                        "settings-account"
                    ):
                        with ui.element("div").classes("settings-identity"):
                            ui.label("Signed in as").classes("settings-identity-summary")

                            with ui.element("div").classes("settings-identity-line"):
                                ui.label(userdata["username"]).classes("settings-identity-name")

                                if is_admin:
                                    ui.label("Administrator").classes("settings-role")

                        with ui.element("dl").classes("settings-list"):
                            for name, value, extra in (
                                ("User ID", userdata["user_id"], "settings-mono"),
                                ("Transcribed time", f"{hours} h {minutes} min", ""),
                                ("Time zone", app.storage.user.get("timezone", "UTC"), ""),
                            ):
                                with ui.element("dt"):
                                    ui.label(name)
                                with ui.element("dd"):
                                    ui.label(value).classes(extra)

                        with ui.element("div").classes("settings-row"):
                            with ui.element("div").classes("settings-row-text"):
                                ui.label("API token").classes("settings-row-title")
                                ui.label("Used to authenticate requests to the Scribe API.").classes(
                                    "settings-row-summary"
                                )

                            ui.button("Show token", icon="key", on_click=show_user_token).props(
                                "color=black flat no-caps"
                            ).classes("button-close settings-button")

                    # ── Theme ──
                    with card("palette", "Theme", "How Scribe looks on this and your other devices.").classes(
                        "settings-theme-card"
                    ):
                        # Current value: True -> "on", False -> "off", None -> "auto"
                        raw = app.storage.user.get("dark_mode", None)
                        if raw is None:
                            current_dark = "auto"
                        elif raw:
                            current_dark = "on"
                        else:
                            current_dark = "off"

                        def apply(dark) -> None:
                            # The page's own dark mode element, the one the
                            # header's button changes too: a new ui.dark_mode
                            # each time made several, and from dark back to
                            # light the page stayed dark.
                            element = page_dark_mode()

                            if element is not None:
                                element.value = dark
                            else:
                                ui.dark_mode(dark)

                        def set_dark_mode(value: str) -> None:
                            if value == "on":
                                app.storage.user["dark_mode"] = True
                                app.storage.user["_resolved_dark"] = True
                                apply(True)
                                dark_mode_save(True)
                                icon_name = "dark_mode"
                            elif value == "off":
                                app.storage.user["dark_mode"] = False
                                app.storage.user["_resolved_dark"] = False
                                apply(False)
                                dark_mode_save(False)
                                icon_name = "light_mode"
                            else:
                                app.storage.user["dark_mode"] = None
                                apply(None)
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

                        # Real radio buttons, one name: a radio group to a screen
                        # reader, moved through with the arrow keys, each named by
                        # the words in its tile (utils/styles.py, .settings-theme).
                        with ui.element("div").classes("settings-theme").props(
                            'role=radiogroup aria-label="Theme"'
                        ):
                            for key, icon, name in (
                                ("off", "light_mode", "Light"),
                                ("on", "dark_mode", "Dark"),
                                ("auto", "brightness_auto", "Match system"),
                            ):
                                with ui.element("label").classes("settings-theme-choice"):
                                    radio = ui.element("input").props(
                                        f"type=radio name=theme value={key}"
                                    )

                                    if key == current_dark:
                                        radio._props["checked"] = True

                                    radio.on("change", lambda e, key=key: set_dark_mode(key))
                                    ui.icon(icon).props("aria-hidden=true")
                                    ui.label(name)

                        ui.label("Match system follows the light or dark setting of your device.").classes(
                            "settings-hint"
                        )

                    # ── Connected services, when the organisation offers Drive ──
                    drive_section = ui.element("section").classes("settings-card settings-services")
                    drive_section.set_visibility(False)
                    ui.timer(
                        0.0, lambda: draw_drive_section(drive_section), once=True
                    )

                with ui.element("div").classes("settings-column"):
                    # ── Email notifications ──
                    with card("notifications", "Email notifications", "What Scribe emails you about, and where.").classes(
                        "settings-notifications"
                    ):
                        with ui.element("div").classes("settings-email"):
                            # A real label: the field's accessible name (3.3.2);
                            # type=email and autocomplete=email for the keyboard
                            # and for autofill.
                            email = ui.input("Email address", value=current_email).props(
                                "outlined type=email autocomplete=email"
                            )
                            ui.button("Send test and save", on_click=lambda: email_save(email.value)).props(
                                "color=black flat no-caps"
                            ).classes("default-style settings-button")

                        chosen = {
                            "job": "job" in current_notifications,
                            "deletion": "deletion" in current_notifications,
                            "user": "user" in current_notifications if is_admin else None,
                            "quota": "quota" in current_notifications if is_admin else None,
                            "weekly_report": "weekly_report" in current_notifications if is_admin else None,
                        }

                        def save(key: str, value: bool) -> None:
                            chosen[key] = value
                            email_save_notifications(**chosen)

                        def group(heading: str, summary: str = "") -> ui.element:
                            block = ui.element("div").classes("settings-group").props('role="group"')

                            with block:
                                title = ui.label(heading).classes("settings-group-title").props(
                                    "role=heading aria-level=3"
                                )

                                if summary:
                                    ui.label(summary).classes("settings-group-summary")

                            block._props["aria-labelledby"] = title.html_id

                            return block

                        with group("Your files"):
                            option(
                                "Transcription completed",
                                "When one of your transcriptions has finished.",
                                chosen["job"],
                                lambda e: save("job", e.value),
                            )
                            option(
                                "Upcoming file deletions",
                                "24 hours before one of your files is deleted.",
                                chosen["deletion"],
                                lambda e: save("deletion", e.value),
                            )

                        if (user_data or {}).get("admin"):
                            with group("Administration", "Only administrators see these."):
                                option(
                                    "New user registrations",
                                    "When a new account is waiting to be enabled.",
                                    chosen["user"],
                                    lambda e: save("user", e.value),
                                )
                                option(
                                    "Quota alerts",
                                    "When a group or account is close to its monthly limit or quota.",
                                    chosen["quota"],
                                    lambda e: save("quota", e.value),
                                )
                                option(
                                    "Usage summary",
                                    "A weekly email with this month's transcription use.",
                                    chosen["weekly_report"],
                                    lambda e: save("weekly_report", e.value),
                                )

                        with ui.element("div").classes("settings-saved"):
                            ui.icon("check_circle").props("aria-hidden=true")
                            ui.label("Changes are saved as you make them.")

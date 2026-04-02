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

import asyncio
import re
import httpx
import pytz

from datetime import datetime, timedelta
from nicegui import ui, app
from starlette.formparsers import MultiPartParser
from typing import Optional
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
    get_bofh_status,
    get_user_data,
    token_refresh,
)
from utils.helpers import storage_decrypt, customers_get
from utils.styles import (
    default_styles,
    jobs_columns,
    menu_active_style,
    menu_item_style,
    severity_styles,
    theme_styles,
)

MultiPartParser.spool_max_size = 1024 * 1024 * 4096
settings = get_settings()


def sanitize_filename(filename: str) -> str:
    """
    Remove or replace characters that are unsafe in filenames.
    """
    # Replace path separators and null bytes
    filename = filename.replace("/", "_").replace("\\", "_").replace("\x00", "")
    # Remove other problematic characters
    filename = re.sub(r'[<>:"|?*\x01-\x1f]', "_", filename)
    # Strip leading/trailing dots and spaces
    filename = filename.strip(". ")
    return filename or "unnamed"




def _get_support_contact_email() -> str:
    """
    Look up the support contact email for the current user's customer.
    """

    try:
        user_data = get_user_data() or {}
        user_realm = user_data.get("realm", "")
        if not user_realm:
            return ""

        customers_data = customers_get()
        customers = (
            customers_data.get("result", []) if isinstance(customers_data, dict) else []
        )

        for c in customers:
            c_realms = [
                r.strip() for r in (c.get("realms") or "").split(",") if r.strip()
            ]
            if user_realm in c_realms:
                return c.get("support_contact_email", "")
    except Exception:
        pass

    return ""


def show_help_dialog() -> None:
    """
    Show a help dialog with information about the application.
    """

    with ui.dialog() as dialog:
        with (
            ui.card()
            .style("max-width: 900px; padding: 32px;")
            .classes("no-shadow help-dialog-card")
        ):
            with ui.row().classes("w-full items-center justify-between mb-6"):
                ui.label("Help & Documentation").classes("text-h4 font-bold")
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round dense color=grey-7"
                )

            with ui.column().classes("w-full gap-6"):
                with ui.card().classes("help-about-card border-l-4").style(
                    "padding: 20px;"
                ):
                    ui.label("About Sunet Scribe").classes("text-h6 font-semibold mb-2")
                    ui.label(
                        "A powerful transcription service using Whisper AI models to convert audio and video files into searchable text or time-coded subtitles with high accuracy."
                    ).classes("text-body1")

                ui.label("Getting started").classes("text-h6 font-bold mt-2")

                with ui.grid(columns=2).classes("w-full gap-4"):
                    for step_num, step_title, step_desc, step_icon in [
                        (
                            "1",
                            "Upload Files",
                            "Click Upload or drag & drop up to 5 files (max 4GB each). Supports MP3, WAV, MP4, MKV, AVI, and more.",
                            "upload_file",
                        ),
                        (
                            "2",
                            "Configure",
                            'Click the "Transcribe" button, select language, number of speakers, and output format (transcript or subtitles).',
                            "settings",
                        ),
                        (
                            "3",
                            "Monitor",
                            "Track job status on the dashboard. Jobs process in the background.",
                            "pending_actions",
                        ),
                        (
                            "4",
                            "Edit & Export",
                            "Click completed jobs to refine in the editor. Press ? for keyboard shortcuts.",
                            "edit_note",
                        ),
                    ]:
                        with ui.card().classes("p-4"):
                            with ui.row().classes("items-center gap-3 mb-2"):
                                ui.icon(step_icon, size="md").classes("help-about-icon")
                                ui.label(f"{step_num}. {step_title}").classes(
                                    "text-subtitle1 font-semibold"
                                )
                            ui.label(step_desc).classes("text-body2 text-theme-secondary")

                with ui.row().classes("w-full gap-4 items-stretch"):
                    with ui.card().classes("flex-1 help-privacy-card p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("security", size="sm").classes("help-privacy-icon")
                            ui.label("Privacy").classes("text-subtitle1 font-semibold")
                        ui.label(
                            "Files are encrypted, only accessible to you, and auto-deleted after the scheduled deletion date."
                        ).classes("text-body2")

                    with ui.card().classes("flex-1 help-support-card p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("help", size="sm").classes("help-support-icon")
                            ui.label("Support").classes("text-subtitle1 font-semibold")

                        ui.label(
                            "Contact your institution's IT department for technical support or questions."
                        ).classes("text-body2")

                        support_contact = _get_support_contact_email()
                        if support_contact:
                            is_url = support_contact.startswith(("http://", "https://"))
                            href = support_contact if is_url else f"mailto:{support_contact}"
                            label = "Support:" if is_url else "Support email:"
                            with ui.row().classes("items-center gap-1"):
                                ui.label(label).classes("text-body2")
                                ui.link(
                                    support_contact, href
                                ).classes("text-body2")

        dialog.open()


def logout() -> None:
    """
    Log out the user by clearing the token and navigating to the logout endpoint.
    """

    app.storage.user["token"] = None
    app.storage.user["refresh_token"] = None
    app.storage.user["encryption_password"] = None

    ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)


def _show_announcement_banners() -> None:
    """Show active announcement banners below the header."""

    user_data = get_user_data()
    if not user_data:
        return

    announcements = user_data.get("announcements", [])
    if not announcements:
        return

    dismissed = app.storage.user.get("dismissed_announcements", [])

    visible_count = 0
    for a in announcements:
        sev = a.get("severity", "info")
        style = severity_styles.get(sev, severity_styles["info"])
        if style["dismissible"] and a.get("id") in dismissed:
            continue
        visible_count += 1

    if visible_count > 0:
        ui.add_head_html(
            f"<style>:root {{ --banner-offset: {visible_count * 40}px; }}</style>"
        )

    # JS to fix link attributes (target, rel) for all banner links
    ui.add_head_html(
        "<script>"
        "document.addEventListener('DOMContentLoaded', function() {"
        "  new MutationObserver(function() {"
        "    document.querySelectorAll('.announcement-banner a').forEach(function(a) {"
        "      if (!a.getAttribute('target')) a.setAttribute('target', '_top');"
        "      try { var u = new URL(a.href, location.origin);"
        "        if (u.origin !== location.origin)"
        "          a.setAttribute('rel', 'noopener noreferrer');"
        "      } catch(e) {}"
        "    });"
        "  }).observe(document.body, {childList: true, subtree: true});"
        "});"
        "</script>"
    )

    for announcement in announcements:
        ann_id = announcement.get("id")
        sev = announcement.get("severity", "info")
        style = severity_styles.get(sev, severity_styles["info"])

        if style["dismissible"] and ann_id in dismissed:
            continue

        banner_container = (
            ui.element("div")
            .classes(f"announcement-banner {style['css_class']}")
            .style(
                "padding: 8px 20px; display: flex; align-items: center;"
                " justify-content: space-between;"
                " margin-left: -2rem; margin-right: -2rem; margin-top: -1rem;"
                " width: calc(100% + 4rem);"
            )
        )

        with banner_container:
            with ui.element("div").style(
                "display: flex; align-items: center; gap: 10px; flex: 1;"
            ):
                ui.icon(style["icon"], size="sm").style(
                    f"color: {style['icon_color']};"
                )
                ui.html(announcement.get("message", ""), sanitize=False).style(
                    "color: var(--color-text-primary); font-size: 0.95rem;"
                )

            if style["dismissible"]:

                def dismiss(a_id=ann_id, container=banner_container):
                    current = app.storage.user.get("dismissed_announcements", [])
                    if a_id not in current:
                        current.append(a_id)
                        app.storage.user["dismissed_announcements"] = current
                    container.set_visibility(False)

                ui.button(icon="close", on_click=dismiss).props(
                    "flat round dense size=sm color=grey-7"
                )


def page_init(header_text: Optional[str] = "", use_drawer: bool = False) -> None:
    """
    Initialize the page with a header and background color.
    """

    if "_scribe_bk" not in app.storage.browser:
        ui.navigate.to("/")
        return

    def refresh():
        if not token_refresh():
            app.storage.user["token"] = None
            app.storage.user["refresh_token"] = None
            app.storage.user["encryption_password"] = None

            ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)

    refresh()

    # Apply dark mode preference
    ui.add_head_html(default_styles)
    dark_pref = app.storage.user.get("dark_mode", None)
    ui.dark_mode(dark_pref)

    is_admin = get_admin_status()
    is_bofh = get_bofh_status()
    ui.timer(30, refresh)

    try:
        client = ui.context.client
        current_path = client.page.path if client and client.page else ""
    except Exception:
        current_path = ""

    if header_text:
        header_text = f" - {header_text}"

    if is_admin:
        header_text += " (Administrator)"

    def _cycle_dark_mode():
        current = app.storage.user.get("dark_mode", None)
        if current is None:
            new_val = True
        elif current:
            new_val = False
        else:
            new_val = None
        app.storage.user["dark_mode"] = new_val
        ui.dark_mode(new_val)

    if use_drawer:
        drawer_open = app.storage.user.get("drawer_open", False)
        drawer = ui.left_drawer(value=True, elevated=True).style(
            "background-color: var(--color-bg-surface-alt); padding: 0;"
        )

        drawer.props(':mini-width="56" :width="250" :breakpoint="0"')

        if not drawer_open:
            drawer.props(add="mini")

        menu_tooltips = []

        menu_btn = None

        def toggle_drawer():
            is_open = app.storage.user.get("drawer_open", False)
            if is_open:
                drawer.props(add="mini")
                for t in menu_tooltips:
                    t.set_visibility(True)
                if menu_btn:
                    menu_btn._props["icon"] = "menu"
                    menu_btn.update()
                if menu_btn_tooltip_ref:
                    menu_btn_tooltip_ref.text = "Expand menu"
                    menu_btn_tooltip_ref.update()
            else:
                drawer.props(remove="mini")
                for t in menu_tooltips:
                    t.set_visibility(False)
                if menu_btn:
                    menu_btn._props["icon"] = "close"
                    menu_btn.update()
                if menu_btn_tooltip_ref:
                    menu_btn_tooltip_ref.text = "Close menu"
                    menu_btn_tooltip_ref.update()
            app.storage.user["drawer_open"] = not is_open

        menu_btn_tooltip_ref = None

        # menu_item_style, menu_active_style imported from utils.styles

        def menu_style(path: str) -> str:
            active = current_path == path
            return menu_item_style + (menu_active_style if active else "")

        # Menu items: (path, icon, label)
        menu_items = [
            ("/home", "folder", "My files"),
            ("/user", "person", "User settings"),
        ]

        admin_items = [
            ("/admin/users", "people", "Users"),
            ("/admin", "group_work", "Groups"),
            ("/admin/rules", "rule", "User provisioning"),
            ("/admin/customers", "business", "Customers" if is_bofh else "Account"),
        ]

        system_items = [
            ("/health", "health_and_safety", "System status"),
            ("/admin/analytics", "analytics", "Activity overview"),
            ("/admin/announcements", "campaign", "Announcements"),
        ]

        with drawer:
            with ui.column().classes("w-full").style("gap: 0;"):
                ui.separator()

                show_tips = not drawer_open

                for path, icon, label in menu_items:
                    with ui.element("div").style(menu_style(path)).classes(
                        "menu-item"
                    ).on("click", lambda p=path: ui.navigate.to(p)):
                        ui.icon(icon).style("font-size: 20px;")
                        ui.label(label).classes("menu-label")
                        t = ui.tooltip(label)
                        t.set_visibility(show_tips)
                        menu_tooltips.append(t)

                if is_admin:
                    ui.separator().classes("menu-separator")
                    ui.label("Administration").classes("menu-header").style(
                        "padding: 10px 16px 4px; font-weight: bold; font-size: 0.85rem; color: var(--color-text-tertiary);"
                    )

                    for path, icon, label in admin_items:
                        with ui.element("div").style(menu_style(path)).classes(
                            "menu-item"
                        ).on("click", lambda p=path: ui.navigate.to(p)):
                            ui.icon(icon).style("font-size: 20px;")
                            ui.label(label).classes("menu-label")
                            t = ui.tooltip(label)
                            t.set_visibility(show_tips)
                            menu_tooltips.append(t)

                    with ui.element("div").style(menu_item_style).classes(
                        "menu-item"
                    ).on(
                        "click",
                        lambda: ui.run_javascript(
                            f"window.open('{settings.API_URL}/api/docs', '_blank')"
                        ),
                    ):
                        ui.icon("description").style("font-size: 20px;")
                        ui.label("API documentation").classes("menu-label")
                        t = ui.tooltip("API documentation")
                        t.set_visibility(show_tips)
                        menu_tooltips.append(t)

                if is_bofh:
                    ui.separator().classes("menu-separator")
                    ui.label("System").classes("menu-header").style(
                        "padding: 10px 16px 4px; font-weight: bold; font-size: 0.85rem; color: var(--color-text-tertiary);"
                    )

                    for path, icon, label in system_items:
                        with ui.element("div").style(menu_style(path)).classes(
                            "menu-item"
                        ).on("click", lambda p=path: ui.navigate.to(p)):
                            ui.icon(icon).style("font-size: 20px;")
                            ui.label(label).classes("menu-label")
                            t = ui.tooltip(label)
                            t.set_visibility(show_tips)
                            menu_tooltips.append(t)

                ui.separator()

                with ui.element("div").style(menu_item_style).classes("menu-item").on(
                    "click", lambda: ui.navigate.to("/logout")
                ):
                    ui.icon("logout").style("font-size: 20px;")
                    ui.label("Logout").classes("menu-label")
                    t = ui.tooltip("Logout")
                    t.set_visibility(show_tips)
                    menu_tooltips.append(t)

        with (
            ui.header()
            .style("justify-content: space-between; background-color: var(--color-header-bg);")
            .classes("drop-shadow-md")
        ):
            with ui.element("div").style(
                "display: flex; gap: 0px; align-items: center; margin-left: -12px;"
            ):
                with ui.button(
                    icon="close" if drawer_open else "menu",
                    on_click=lambda: toggle_drawer(),
                ).props("flat").classes("header-btn") as menu_btn:
                    menu_btn_tooltip = ui.tooltip(
                        "Close menu" if drawer_open else "Expand menu"
                    )
                    menu_btn_tooltip_ref = menu_btn_tooltip
                ui.image(f"static/{settings.LOGO_TOPBAR}").classes("q-mr-sm").style(
                    "height: 30px; width: 30px;"
                )
                ui.label(settings.TOPBAR_TEXT + header_text).classes(
                    "text-h6"
                )

            with ui.element("div").style("display: flex; gap: 0px;"):
                dark_val = app.storage.user.get("dark_mode", None)
                dark_icon = "dark_mode" if dark_val else ("brightness_auto" if dark_val is None else "light_mode")
                with ui.button(
                    icon=dark_icon,
                    on_click=lambda: (_cycle_dark_mode(), ui.navigate.to(ui.context.client.page.path)),
                ).props("flat").classes("header-btn"):
                    ui.tooltip("Toggle dark mode")
                with ui.button(
                    icon="help",
                    on_click=lambda: show_help_dialog(),
                ).props("flat").classes("header-btn"):
                    ui.tooltip("Help")

            # body background and .nicegui-content padding are in theme_styles
    else:
        with (
            ui.header()
            .style("justify-content: space-between; background-color: var(--color-header-bg);")
            .classes("drop-shadow-md")
        ):
            with ui.element("div").style("display: flex; gap: 0px;"):
                ui.image(f"static/{settings.LOGO_TOPBAR}").classes("q-mr-sm").style(
                    "height: 30px; width: 30px;"
                )
                ui.label(settings.TOPBAR_TEXT + header_text).classes(
                    "text-h6"
                )

            with ui.element("div").style("display: flex; gap: 0px;"):
                if is_admin:
                    with ui.button(
                        icon="settings",
                        on_click=lambda: ui.navigate.to("/admin"),
                    ).props("flat color=red"):
                        ui.tooltip("Admin settings")

                if is_bofh:
                    with ui.button(
                        icon="health_and_safety",
                        on_click=lambda: ui.navigate.to("/health"),
                    ).props("flat color=red"):
                        ui.tooltip("System status")
                    with ui.button(
                        icon="analytics",
                        on_click=lambda: ui.navigate.to("/admin/analytics"),
                    ).props("flat color=red"):
                        ui.tooltip("Page view statistics")
                with ui.button(
                    icon="home",
                    on_click=lambda: ui.navigate.to("/home"),
                ).props("flat").classes("header-btn"):
                    ui.tooltip("Home")
                with ui.button(
                    icon="person",
                    on_click=lambda: ui.navigate.to("/user"),
                ).props("flat").classes("header-btn"):
                    ui.tooltip("User settings")
                dark_val2 = app.storage.user.get("dark_mode", None)
                dark_icon2 = "dark_mode" if dark_val2 else ("brightness_auto" if dark_val2 is None else "light_mode")
                with ui.button(
                    icon=dark_icon2,
                    on_click=lambda: (_cycle_dark_mode(), ui.navigate.to(ui.context.client.page.path)),
                ).props("flat").classes("header-btn"):
                    ui.tooltip("Toggle dark mode")
                with ui.button(
                    icon="help",
                    on_click=lambda: show_help_dialog(),
                ).props("flat").classes("header-btn"):
                    ui.tooltip("Help")
                with ui.button(
                    icon="logout",
                    on_click=lambda: ui.navigate.to("/logout"),
                ).props("flat").classes("header-btn"):
                    ui.tooltip("Logout")
                # body background is in theme_styles

    _show_announcement_banners()


def add_timezone_to_timestamp(timestamp: str) -> str:
    """
    Convert a UTC timestamp to the user's local timezone.
    """
    user_timezone = app.storage.user.get("timezone", "UTC")
    utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
    utc_time = pytz.utc.localize(utc_time)
    local_tz = pytz.timezone(user_timezone)
    local_time = utc_time.astimezone(local_tz)

    return local_time.strftime("%Y-%m-%d %H:%M")


async def jobs_get() -> list:
    """
    Get the list of transcription jobs from the API.
    """
    jobs = []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "GET",
                f"{settings.API_URL}/api/v1/transcriber",
                headers=get_auth_header(),
                json={
                    "encryption_password": storage_decrypt(
                        app.storage.user.get("encryption_password"),
                    )
                },
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return []

    # Get current time in user's timezone
    user_timezone = app.storage.user.get("timezone", "UTC")
    local_tz = pytz.timezone(user_timezone)
    current_time = datetime.now(local_tz)

    for idx, job in enumerate(response.json()["result"]["jobs"]):
        if job["status"] == "in_progress":
            job["status"] = "transcribing"

        deletion_date = add_timezone_to_timestamp(job["deletion_date"])
        created_at = add_timezone_to_timestamp(job["created_at"])
        updated_at = add_timezone_to_timestamp(job["updated_at"])

        # Check if deletion is approaching (within 24 hours)
        deletion_approaching = False
        if deletion_date:
            try:
                deletion_dt = datetime.strptime(deletion_date, "%Y-%m-%d %H:%M")
                deletion_dt = local_tz.localize(deletion_dt)
                time_until_deletion = deletion_dt - current_time
                # Default threshold: 24 hours
                deletion_approaching = time_until_deletion <= timedelta(hours=24)
            except (ValueError, AttributeError):
                pass

            deletion_date_display = deletion_date.split(" ")[0]
        else:
            deletion_date_display = "N/A"

        if job["status"] != "completed":
            job_type = ""
        elif job["output_format"] == "txt":
            job_type = "Transcript"
        elif job["output_format"] == "srt":
            job_type = "Subtitles"
        else:
            job_type = "Transcript"

        job_data = {
            "id": idx,
            "uuid": job["uuid"],
            "filename": job["filename"],
            "created_at": created_at,
            "updated_at": updated_at,
            "deletion_date": deletion_date_display,
            "deletion_approaching": deletion_approaching,
            "language": job["language"].capitalize(),
            "status": job["status"].capitalize(),
            "model_type": job["model_type"].capitalize(),
            "output_format": job["output_format"].upper(),
            "job_type": job_type,
        }

        jobs.append(job_data)

    # Sort jobs by created_at in descending order
    jobs.sort(key=lambda x: x["created_at"], reverse=True)

    return jobs


def table_click(event) -> None:
    """
    Handle the click event on the table rows.
    """

    status = event.args["status"].lower()
    uuid = event.args["uuid"]
    filename = event.args["filename"]
    model_type = event.args["model_type"]
    language = event.args["language"]
    output_format = event.args.get("output_format")

    if status != "completed":
        return

    if output_format == "TXT":
        ui.navigate.to(
            f"/srt?uuid={uuid}&filename={filename}&model={model_type}&language={language}&data_format=txt"
        )
    else:
        ui.navigate.to(
            f"/srt?uuid={uuid}&filename={filename}&model={model_type}&language={language}&data_format=srt"
        )


async def post_file(filedata: bytes, filename: str) -> bool:
    """
    Post a file to the API.
    """

    files_json = {"file": (filename, filedata)}

    try:
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(
                f"{settings.API_URL}/api/v1/transcriber",
                files=files_json,
                headers=get_auth_header(),
            )
            response.raise_for_status()

            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"Upload failed, status code: {response.status_code}",
                    request=response.request,
                    response=response,
                )
    except httpx.HTTPStatusError as e:
        ui.notify(
            f"Error when uploading file: {str(e)}", type="negative", position="top"
        )
        return False

    return True


def format_size(bytes_val) -> str:
    """
    Format bytes into a human-readable string.
    """
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"


def toggle_upload_status(upload_column, status_column, dialog):
    upload_column.visible = False
    status_column.visible = True
    dialog.props("persistent")


def table_upload(table) -> None:
    """
    Handle the click event on the Upload button with improved UX.
    """

    ui.add_head_html(default_styles)

    with ui.dialog() as dialog:
        with ui.card().style("min-width: 400px; padding: 32px;"):
            with ui.column().classes("w-full items-center") as status_column:
                ui.label("Uploading files").classes("text-h6 q-mb-sm")
                status_label = ui.label("Please wait...").classes(
                    "text-body1 q-mb-lg text-theme-muted"
                )
                ui.spinner(size="50px")
                status_column.visible = False

            with ui.column().classes("w-full items-center mt-10") as upload_column:
                upload = (
                    ui.upload(
                        label="hidden",
                        on_multi_upload=lambda e: handle_upload_with_feedback(
                            e, dialog, table
                        ),
                        auto_upload=True,
                        multiple=True,
                        max_files=5,
                    )
                    .props(
                        "accept=.mp3,.wav,.flac,.mp4,.mkv,.avi,.m4a,.aiff,.aif,.mov,.ogg,.opus,.webm,.wma,.mpg,.mpeg"
                    )
                    .style(
                        "position: absolute; width: 0; height: 0; overflow: hidden; opacity: 0"
                    )
                )

                upload.on(
                    "start",
                    lambda _: toggle_upload_status(
                        upload_column, status_column, dialog
                    ),
                )
                upload.on("finish", lambda _: dialog.close())

                def on_byte_progress(e):
                    uploaded = e.args.get("uploaded", 0)
                    total = e.args.get("total", 0)
                    if total > 0:
                        status_label.set_text(
                            f"{format_size(uploaded)} / {format_size(total)}"
                        )

                upload.on("byte_progress", on_byte_progress)

                dropzone = ui.html(
                    """
                    <div class="w-96 h-40 flex items-center justify-center
                                border-2 border-dashed rounded-2xl cursor-pointer
                                dropzone-area">
                        Drag & drop files here or click to upload.
                        <br/><br/>
                        5 files at a maximum of 4GB can be uploaded at once.
                    </div>
                    """,
                    sanitize=False,
                )

                upload_id = upload.id
                dropzone_id = dropzone.id
                ui.timer(
                    0.1,
                    lambda: ui.run_javascript(
                        "const dz = getHtmlElement(" + str(dropzone_id) + ");"
                        "const upl = getElement(" + str(upload_id) + ");"
                        "if (!dz || !upl) return;"
                        "dz.addEventListener('click', () => upl.$refs.qRef.pickFiles());"
                        "dz.addEventListener('dragover', e => {"
                        "  e.preventDefault();"
                        "  dz.querySelector('div').classList.add('dropzone-drag');"
                        "});"
                        "dz.addEventListener('dragleave', () => {"
                        "  dz.querySelector('div').classList.remove('dropzone-drag');"
                        "});"
                        "dz.addEventListener('drop', e => {"
                        "  e.preventDefault();"
                        "  dz.querySelector('div').classList.remove('dropzone-drag');"
                        "  upl.$refs.qRef.addFiles(Array.from(e.dataTransfer.files));"
                        "});"
                        "setInterval(() => {"
                        "  const qRef = upl.$refs.qRef;"
                        "  if (!qRef || !qRef.files || qRef.files.length === 0) return;"
                        "  let totalSize = 0, uploaded = 0, currentFile = '';"
                        "  qRef.files.forEach(f => {"
                        "    totalSize += f.size || 0;"
                        "    uploaded += f.__uploaded || 0;"
                        "    if (f.__status === 'uploading') currentFile = f.name;"
                        "  });"
                        "  if (currentFile) {"
                        "    getElement("
                        + str(upload_id)
                        + ").$emit('byte_progress', {"
                        "      uploaded: uploaded, total: totalSize, current_file: currentFile"
                        "    });"
                        "  }"
                        "}, 500);"
                    ),
                    once=True,
                )
                with ui.row().style("justify-content: flex-end; gap: 12px;"):
                    with ui.button(
                        "Cancel",
                        icon="cancel",
                        on_click=lambda: dialog.close(),
                    ) as cancel:
                        cancel.props("color=black flat")
                        cancel.classes("cancel-style")

        dialog.open()


async def handle_upload_with_feedback(files, dialog, table):
    """
    Handle file uploads with user feedback and validation.
    """

    client = ui.context.client

    dialog.close()

    # Read file data while the client context is still active
    file_items = []
    for file in files.files:
        file_name = sanitize_filename(file.name)
        file_data = await file.read()
        file_items.append((file_name, file_data))

    # Upload to backend in a background task so the UI stays responsive
    async def _upload():
        for file_name, file_data in file_items:
            try:
                await post_file(file_data, file_name)

                if not client._deleted:
                    with table:
                        ui.notify(
                            f"Successfully uploaded {file_name}",
                            type="positive",
                            timeout=3000,
                        )
            except Exception as e:
                if not client._deleted:
                    with table:
                        ui.notify(
                            f"Error uploading {file_name}: {str(e)}",
                            type="negative",
                            timeout=5000,
                        )

        if not client._deleted:
            table.update_rows(await jobs_get(), clear_selection=False)

    asyncio.create_task(_upload())


def table_transcribe(selected_row, on_complete=None) -> None:
    """
    Handle the click event on the Transcribe button.
    """
    with ui.dialog() as dialog:
        with (
            ui.card()
            .style(
                "background-color: var(--color-bg-surface); align-self: center; border: 0; width: 80%;"
            )
            .classes("w-full no-shadow no-border")
        ):
            with ui.row().classes("w-full"):
                ui.label("Transcription settings").style("width: 100%;").classes(
                    "text-h6 q-mb-xl"
                )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Filename:").classes("text-subtitle2 q-mb-sm")
                    ui.label(f"{selected_row['filename']}")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        value=settings.WHISPER_LANGUAGES[0],
                    ).classes("w-full")

                with ui.column().classes("col-12 col-sm-24") as verbatim_container:
                    verbatim = ui.checkbox(
                        "Verbatim (include filler words, repetitions and unfinished sentences)"
                    ).classes("q-mt-sm")
                    verbatim_container.set_visibility(
                        language.value.lower() == "swedish"
                    )
                    language.on_value_change(
                        lambda e: verbatim_container.set_visibility(
                            e.value.lower() == "swedish"
                            or e.value.lower() == "norwegian"
                        )
                    )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers, automatic if not chosen").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0", min=0).classes("w-full")

            with ui.row().classes("justify-between w-full"):
                ui.label("Output format").classes("text-subtitle2 q-mb-sm")
                output_format = (
                    ui.radio(
                        ["Transcript", "Subtitles"],
                        value="Transcript",
                    )
                    .classes("w-full")
                    .props("inline")
                )

            with ui.row().classes("justify-between w-full"):
                with ui.button(
                    "Cancel",
                    icon="cancel",
                ) as cancel:
                    cancel.on("click", lambda: dialog.close())
                    cancel.props("color=black flat")
                    cancel.classes("cancel-style")

                with ui.button(
                    "Start transcribing",
                    on_click=lambda: start_transcription(
                        [selected_row],
                        f"{language.value} (verbatim)"
                        if verbatim.value
                        else language.value,
                        speakers.value,
                        output_format.value,
                        dialog,
                        on_complete=on_complete,
                    ),
                ) as start:
                    start.props("color=black flat")
                    start.classes("default-style")

            dialog.open()


def table_bulk_transcribe(table: ui.table, on_complete=None) -> None:
    """
    Handle bulk transcription of selected uploaded jobs.
    Shows the same transcription settings dialog but applies to all selected rows.
    """
    selected = table.selected
    uploadable = [r for r in selected if r.get("status") == "Uploaded"]
    already_done = [r for r in selected if r.get("status") == "Completed"]
    if not uploadable:
        ui.notify("No uploaded files selected", type="warning", position="top")
        return

    with ui.dialog() as dialog:
        with (
            ui.card()
            .style(
                "background-color: var(--color-bg-surface); align-self: center; border: 0; width: 80%;"
            )
            .classes("w-full no-shadow no-border")
        ):
            with ui.row().classes("w-full"):
                ui.label("Transcription settings").style("width: 100%;").classes(
                    "text-h6 q-mb-xl"
                )

                with ui.column().classes("w-full q-mb-sm").style(
                    "background-color: var(--color-severity-maint-bg); padding: 8px 12px; border-radius: 4px;"
                ):
                    with ui.row().classes("items-center"):
                        ui.icon("rtt").classes("text-body1")
                        ui.label(
                            f"{len(uploadable)} file(s) will be transcribed."
                        ).classes("text-body2")
                    if already_done:
                        with ui.row().classes("items-center"):
                            ui.icon("block").classes("text-body1")
                            ui.label(
                                f"{len(already_done)} completed file(s) will be skipped."
                            ).classes("text-body2")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        value=settings.WHISPER_LANGUAGES[0],
                    ).classes("w-full")

                with ui.column().classes("col-12 col-sm-24") as verbatim_container:
                    verbatim = ui.checkbox(
                        "Verbatim (include filler words, repetitions and unfinished sentences)"
                    ).classes("q-mt-sm")
                    verbatim_container.set_visibility(
                        language.value.lower() == "swedish"
                    )
                    language.on_value_change(
                        lambda e: verbatim_container.set_visibility(
                            e.value.lower() == "swedish"
                        )
                    )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers, automatic if not chosen").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0", min=0).classes("w-full")

            with ui.row().classes("justify-between w-full"):
                ui.label("Output format").classes("text-subtitle2 q-mb-sm")
                output_format = (
                    ui.radio(
                        ["Transcript", "Subtitles"],
                        value="Transcript",
                    )
                    .classes("w-full")
                    .props("inline")
                )

            with ui.row().classes("justify-between w-full"):
                with ui.button(
                    "Cancel",
                    icon="cancel",
                ) as cancel:
                    cancel.on("click", lambda: dialog.close())
                    cancel.props("color=black flat")
                    cancel.classes("cancel-style")

                with ui.button(
                    "Start transcribing",
                    on_click=lambda: (
                        start_transcription(
                            uploadable,
                            f"{language.value} (verbatim)"
                            if verbatim.value
                            else language.value,
                            speakers.value,
                            output_format.value,
                            dialog,
                            table,
                            on_complete=on_complete,
                        ),
                    ),
                ) as start:
                    start.props("color=black flat")
                    start.classes("default-style")

            dialog.open()


def table_delete(table: ui.table) -> None:
    """
    Handle the click event on the Delete button.
    """

    count = len(table.selected)

    with ui.dialog() as dialog:
        with ui.card():
            ui.label("Delete files").classes("text-h6")
            ui.label(
                f"{str(count)} files will be permanently deleted. This action cannot be undone."
            ).classes("text-subtitle2").style("margin-bottom: 10px;")

            with ui.row().classes("justify-between w-full"):
                ui.button("Cancel", on_click=lambda: dialog.close()).props(
                    "color=black"
                )
                ui.button(
                    "Delete",
                    on_click=lambda: __delete_files(table, dialog),
                ).props("color=red")

        dialog.open()


async def __delete_files(table: ui.table, dialog: ui.dialog) -> None:
    selected = list(table.selected)
    total = len(selected)
    dialog.close()

    deleted = 0
    failed = 0

    for row in selected:
        uuid = row["uuid"]
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.delete(
                    f"{settings.API_URL}/api/v1/transcriber/{uuid}",
                    headers=get_auth_header(),
                )
                response.raise_for_status()
            deleted += 1
        except (httpx.HTTPStatusError, httpx.RequestError):
            failed += 1

    table.selected = []
    table.update_rows(await jobs_get(), clear_selection=True)

    if failed == 0:
        ui.notify(
            f"Successfully deleted {deleted} file{'s' if deleted != 1 else ''}",
            type="positive",
            position="top",
        )
    else:
        ui.notify(
            f"Deleted {deleted} of {total} files ({failed} failed)",
            type="warning",
            position="top",
        )


def table_bulk_export(table: ui.table) -> None:
    """
    Handle bulk export of selected completed jobs as a zip file.
    All selected jobs must be of the same type (output_format).
    """

    selected = table.selected
    if not selected:
        ui.notify("No files selected", type="warning", position="top")
        return

    completed = [r for r in selected if r.get("status") == "Completed"]
    if not completed:
        ui.notify("No already completed files selected", type="warning", position="top")
        return

    formats = set(r.get("output_format", "") for r in completed)
    if len(formats) > 1:
        ui.notify(
            "All selected files must be of the same type",
            type="warning",
            position="top",
        )
        return

    source_format = formats.pop()
    data_format = "srt" if source_format == "SRT" else "txt"

    # Show progress dialog while fetching
    with ui.dialog() as progress_dialog:
        with ui.card().classes("p-6 items-center").style(
            "min-width: 400px; background-color: var(--color-bg-surface);"
        ):
            ui.label("Preparing export...").classes("text-h6 mb-2")
            progress_label = ui.label(f"Fetching file 0 of {len(completed)}").classes(
                "text-body2 mb-2"
            )
            progress = ui.linear_progress(value=0, show_value=False).classes("w-full")

    progress_dialog.open()

    async def fetch_and_show():
        from utils.srt import SRTEditor

        editors = []
        for i, row in enumerate(completed):
            uuid = row["uuid"]
            filename = row["filename"]
            progress_label.set_text(
                f"Fetching file {i + 1} of {len(completed)}: {filename}"
            )
            progress.set_value((i + 1) / len(completed))
            try:
                fmt = "srt" if data_format == "srt" else "txt"
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        "GET",
                        f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/{fmt}",
                        headers=get_auth_header(),
                        json={
                            "encryption_password": storage_decrypt(
                                app.storage.user.get("encryption_password"),
                            )
                        },
                    )
                    response.raise_for_status()
                data = response.json()

                editor = SRTEditor(uuid, data_format, filename)
                if data_format == "srt":
                    editor.parse_srt(data["result"])
                else:
                    editor.parse_txt(data["result"])
                editors.append((filename, editor))
            except httpx.HTTPError as e:
                progress_dialog.close()
                ui.notify(
                    f"Error fetching {filename}: {str(e)}",
                    type="negative",
                    position="top",
                )
                return

        progress_dialog.close()
        # Use the first editor to show the export dialog with all editors
        first_filename, first_editor = editors[0]
        first_editor.show_export_dialog(first_filename, bulk_editors=editors)

    ui.timer(0.1, fetch_and_show, once=True)


def start_transcription(
    rows: list,
    language: str,
    speakers: str,
    output_format: str,
    dialog: ui.dialog,
    table: ui.table = None,
    on_complete=None,
) -> None:
    selected_language = language
    error = ""

    if output_format == "Subtitles":
        output_format = "SRT"
    elif output_format in ("Transcript", "Transcribed text"):
        output_format = "TXT"
    else:
        output_format = "TXT"

    for row in rows:
        uuid = row["uuid"]

        try:
            response = httpx.put(
                f"{settings.API_URL}/api/v1/transcriber/{uuid}",
                json={
                    "language": f"{selected_language}",
                    "speakers": int(speakers),
                    "output_format": output_format,
                    "encryption_password": storage_decrypt(
                        app.storage.user.get("encryption_password"),
                    ),
                },
                headers=get_auth_header(),
            )
            response.raise_for_status()
        except httpx.HTTPError:
            if response.status_code == 403:
                error = response.json()["result"]["error"]
            else:
                error = "Error: Failed to start transcription."
            break

    if error:
        with dialog:
            dialog.clear()

            with ui.card().style(
                "background-color: var(--color-bg-surface); align-self: center; border: 0; width: 50%;"
            ):
                ui.label(error).classes("text-h6 q-mb-md")
                ui.button(
                    "Close",
                ).on("click", lambda: dialog.close()).classes(
                    "button-close"
                ).props("color=black flat")
            dialog.open()
    else:
        if table is not None:
            table.selected = []
        dialog.close()
        if on_complete is not None:
            on_complete()

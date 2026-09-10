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


"""
The user administration page.
"""

import httpx


from nicegui import ui
from utils.common import page_init
from utils.styles import default_styles
from utils.helpers import (
    remove_user,
    reset_manual_override,
    set_active_status,
    set_admin_status,
    open_make_admin_dialog,
    set_domains,
)
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
)

settings = get_settings()


@ui.page("/admin/users")
def users() -> None:
    """
    Page to show all users.
    """
    page_init(use_drawer=True, title="Users")

    if not get_admin_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    try:
        res = httpx.get(
            settings.API_URL + "/api/v1/admin/users", headers=get_auth_header()
        )
        res.raise_for_status()
        users = res.json()["result"]

        # Add an id field to each user for table selection
        for index, user in enumerate(users):
            user["id"] = index
            user["admin"] = "Yes" if user.get("admin", True) else "No"
            user["active"] = "Yes" if user.get("active", True) else "No"
            user["provisioning"] = (
                "Manual"
                if user.get("manually_activated") or user.get("manually_deactivated")
                else "Auto"
            )

    except httpx.HTTPError as e:
        ui.label(f"Error fetching users: {e}").classes("text-lg").style("color: var(--color-text-danger);")
        return

    users_table = ui.table(
        columns=[
            {
                "name": "username",
                "label": "Username",
                "field": "username",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "realm",
                "label": "Realm",
                "field": "realm",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "role",
                "label": "Admin",
                "field": "admin",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "groups",
                "label": "Groups",
                "field": "groups",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "domains",
                "label": "Domains",
                "field": "admin_domains",
                "align": "left",
                "sortable": False,
                "style": "max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;",
            },
            {
                "name": "active",
                "label": "Active",
                "field": "active",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "provisioning",
                "label": "Provisioning",
                "field": "provisioning",
                "align": "left",
                "sortable": True,
            },
        ],
        rows=users,
        selection="multiple",
        pagination=20,
        on_select=lambda e: None,
    )
    users_table.style(
        "width: 100%; height: calc(100vh - 100px - var(--banner-offset, 0px)); box-shadow: none; font-size: 18px;"
    )
    users_table.classes("table-style")

    with users_table.add_slot("top-left"):
        ui.label("Users").classes("text-3xl font-bold")

    with users_table.add_slot("top-right"):
        with ui.row().classes("items-center"):
            ui.button("Enable").classes("button-close").props("color=black flat").style(
                "width: 150px"
            ).on("click", lambda: set_active_status(users_table.selected, True))
            ui.button("Disable").classes("delete-style").props("color=black flat").on(
                "click", lambda: set_active_status(users_table.selected, False)
            )

            def confirm_remove_user():
                selected = users_table.selected
                if not selected:
                    ui.notify("No users selected", type="warning")
                    return

                usernames = ", ".join(u["username"] for u in selected)

                with ui.dialog() as dialog:
                    with ui.card():
                        ui.label("Remove users").classes("text-h6")
                        ui.label(
                            f"Are you sure you want to remove: {usernames}? "
                            "Statistics will be preserved until all associated data has been cleaned up."
                        ).classes("text-subtitle2").style("margin-bottom: 10px;")

                        with ui.row().classes("justify-between w-full"):
                            ui.button("Cancel", on_click=lambda: dialog.close()).props(
                                "color=black"
                            )
                            ui.button(
                                "Remove",
                                on_click=lambda: (
                                    dialog.close(),
                                    remove_user(selected),
                                ),
                            ).props("color=red")

                dialog.open()

            with ui.button("More").classes("button-close").props(
                "color=black flat icon-right=arrow_drop_down"
            ):
                with ui.menu():
                    ui.menu_item(
                        "Domains",
                        on_click=lambda: set_domains(users_table.selected, users),
                    )
                    ui.menu_item(
                        "Make admin",
                        on_click=lambda: open_make_admin_dialog(
                            users_table.selected, users,
                        ),
                    )       
                    ui.menu_item(
                        "Remove admin",
                        on_click=lambda: set_admin_status(
                            users_table.selected, False, None, ""
                        ),
                    )
                    ui.menu_item(
                        "Reset to auto provisioning",
                        on_click=lambda: reset_manual_override(users_table.selected),
                    )
                    ui.menu_item(
                        "Remove user",
                        on_click=confirm_remove_user,
                    )

            with ui.input(placeholder="Search").props("type=search").bind_value(
                users_table, "filter"
            ).add_slot("append"):
                ui.icon("search")

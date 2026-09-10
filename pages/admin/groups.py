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
Groups: the admin landing page, group editing and per-group statistics.
"""

import plotly.graph_objects as go
import httpx


from nicegui import app, ui
from utils.common import add_timezone_to_timestamp, page_init
from utils.styles import default_styles, chart_colors
from utils.helpers import (
    groups_get,
    save_group,
    set_admin_status,
    open_make_admin_dialog,
    user_statistics_get,
)
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
    get_bofh_status,
)
from utils.group import Group

settings = get_settings()


def create_group_dialog(page: callable) -> None:
    """
    Show a dialog to create a new group.
    """

    with ui.dialog().props('aria-label="Create new group"') as create_group_dialog:
        with ui.card().style("width: 500px; max-width: 90vw;"):
            ui.label("Create new group").classes("text-2xl font-bold")
            name_input = ui.input("Group name").classes("w-full").props("outlined")
            description_input = (
                ui.textarea("Group description").classes("w-full").props("outlined")
            )
            quota = (
                ui.input(
                    "Monthly transcription limit (minutes, 0 = unlimited)", value=0
                )
                .classes("w-full")
                .props("outlined type=number min=0")
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: create_group_dialog.close())
                ui.button("Create").classes("default-style").props(
                    "color=black flat"
                ).on(
                    "click",
                    lambda: (
                        httpx.post(
                            settings.API_URL + "/api/v1/admin/groups",
                            headers=get_auth_header(),
                            json={
                                "name": name_input.value,
                                "description": description_input.value,
                                "quota_seconds": int(quota.value) * 60,
                            },
                        ),
                        create_group_dialog.close(),
                        ui.navigate.to("/admin"),
                    ),
                )

        create_group_dialog.open()


def admin_dialog(users: list, group_id: str) -> None:
    """
    Show a dialog with a table of users and buttons to ether make users
    administrator or remove administrator rights.
    """

    with ui.dialog().props('aria-label="Administrators"') as dialog:
        with ui.card().style("width: 600px; max-width: 90vw; "):
            ui.label("Administrators").classes("text-2xl font-bold")
            admin_table = ui.table(
                columns=[
                    {
                        "name": "username",
                        "label": "Username",
                        "field": "username",
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
                ],
                rows=users,
                selection="multiple",
                pagination=20,
                on_select=lambda e: None,
            ).style("width: 100%; box-shadow: none; font-size: 18px;")

            with admin_table.add_slot("top-right"):
                with ui.input(placeholder="Search").props("type=search").bind_value(
                    admin_table, "filter"
                ).add_slot("append"):
                    ui.icon("search")

            with ui.row().style(
                "justify-content: flex-end; width: 100%; padding-top: 16px; gap: 8px;"
            ):
                ui.button("Close").classes("button-close").props("color=black flat").on(
                    "click", lambda: dialog.close()
                )
                ui.button("Make admin").classes("default-style").props(
    		    "color=black flat"
		).on(
    		    "click",
                    lambda: open_make_admin_dialog(
        	       	admin_table.selected, users,
    		    ),
		)
                ui.button("Remove admin").classes("button-close").props(
                    "color=black flat"
                ).on(
                    "click",
                    lambda: set_admin_status(
                        admin_table.selected, False, dialog, group_id
                    ),
                )
        dialog.open()


@ui.refreshable
@ui.page("/admin/edit/{group_id}")
def edit_group(group_id: str) -> None:
    """
    Page to edit a group.
    """
    page_init(use_drawer=True, title="Edit group")

    if not get_admin_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    try:
        res = httpx.get(
            settings.API_URL + f"/api/v1/admin/groups/{group_id}",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        group = res.json()["result"]

        # Add an id field to each user for table selection
        for index, user in enumerate(group["users"]):
            user["id"] = index
            user["admin"] = "Yes" if user.get("admin", True) else "No"
            user["active"] = "Yes" if user.get("active", True) else "No"

    except httpx.HTTPError as e:
        ui.label(f"Error fetching group: {e}").classes("text-lg").style("color: var(--color-text-danger);")
        return

    with ui.row().style(
        "justify-content: space-between; align-items: center; width: 100%;"
    ):
        ui.label(f"Edit group: {group['name']}").classes("text-3xl font-bold")
        with ui.element("div").style("display: flex; gap: 8px;"):
            ui.button("Save group").classes("default-style").props(
                "color=black flat"
            ).style("width: 150px").on(
                "click",
                lambda: save_group(
                    users_table.selected,
                    name_input.value,
                    description_input.value,
                    group_id,
                    quota.value,
                ),
            )
            ui.button("Cancel").classes("delete-style").props("color=black flat").on(
                "click", lambda: ui.navigate.to("/admin")
            )

    with ui.card().style("width: 100%; box-shadow: none; align-self: center;"):
        with ui.row().classes("gap-4 w-full"):
            name_input = (
                ui.input("Group name", value=group["name"])
                .props("outlined")
                .classes("w-1/3")
            )
            description_input = (
                ui.input("Group description", value=group["description"])
                .props("outlined")
                .classes("w-1/2")
            )
            quota = (
                ui.input(
                    "Monthly transcription limit (minutes, 0 = unlimited)",
                    value=group["quota_seconds"] // 60,
                )
                .props("outlined type=number min=0")
                .classes("w-1/2")
            )

        ui.label("Select users to be included in group:").classes(
            "text-xl font-semibold mt-4 mb-2"
        )

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
                    "name": "role",
                    "label": "Admin",
                    "field": "admin",
                    "align": "left",
                    "sortable": True,
                },
                {
                    "name": "active",
                    "label": "Active",
                    "field": "active",
                    "align": "left",
                    "sortable": True,
                },
            ],
            rows=group["users"],
            selection="multiple",
            pagination=20,
            on_select=lambda e: None,
        ).style(
            "width: 100%; box-shadow: none; font-size: 18px; height: calc(100vh - 550px - var(--banner-offset, 0px));"
        )

        users_table.selected = [
            user for user in group["users"] if user.get("in_group", True)
        ]

        with users_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                users_table, "filter"
            ).add_slot("append"):
                ui.icon("search")


@ui.refreshable
@ui.page("/admin/stats/{group_id}")
async def statistics(group_id: str) -> None:
    """
    Page to show statistics of a group with improved layout and design.
    """
    page_init(use_drawer=True, title="Group statistics")

    if not get_admin_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    # Detect resolved dark mode (handles auto mode with OS preference)
    dark_pref = app.storage.user.get("dark_mode", None)
    if dark_pref is None:
        try:
            await ui.context.client.connected()
            prefers_dark = await ui.run_javascript(
                "window.matchMedia('(prefers-color-scheme: dark)').matches",
                timeout=5.0,
            )
            app.storage.user["_resolved_dark"] = bool(prefers_dark)
        except (TimeoutError, Exception):
            pass

    is_dark = app.storage.user.get("_resolved_dark", False)
    cc = chart_colors["dark" if is_dark else "light"]

    stats = user_statistics_get(group_id=group_id)

    if not stats or "result" not in stats:
        ui.label("Error fetching statistics.").classes(
            "text-lg text-center mt-6"
        ).style("color: var(--color-text-danger);"
        )
        return

    result = stats["result"]

    per_day = result.get("transcribed_minutes_per_day", {})
    per_day_previous_month = result.get("transcribed_minutes_per_day_last_month", {})
    per_user = result.get("transcribed_minutes_per_user", {})
    job_queue = result.get("job_queue", [])
    total_users = result.get("total_users", 0)

    # Add timezone to created_at fields in job queue
    for job in job_queue:
        job["created_at"] = add_timezone_to_timestamp(job["created_at"])

    ui.label("Group statistics").classes("text-3xl font-bold mb-4")

    with ui.element("div").classes("stats-container w-full"):
        with ui.element("div").classes("stats-card w-full"):
            ui.label(f"Number of users: {total_users}").classes(
                "text-lg text-theme-secondary"
            )
            ui.label(
                f"Transcribed files this month: {result.get('transcribed_files', 0)} files"
            ).classes("text-lg text-theme-secondary")
            ui.label(
                f"Transcribed files last month: {result.get('transcribed_files_last_month', 0)} files"
            ).classes("text-lg text-theme-secondary")
            ui.label(
                f"Transcribed minutes this month: {result.get('total_transcribed_minutes', 0):.0f} minutes"
            ).classes("text-lg text-theme-secondary")
            ui.label(
                f"Transcribed minutes last month: {result.get('total_transcribed_minutes_last_month', 0):.0f} minutes"
            ).classes("text-lg text-theme-secondary")

        if per_day:
            dates = list(per_day.keys())
            values = list(per_day.values())

            fig = go.Figure(
                data=[
                    go.Bar(
                        x=dates,
                        y=values,
                        marker=dict(color=cc["bar_current"], line=dict(width=0)),
                        hovertemplate="%{x} - %{y:.1f} minutes<extra></extra>",
                    )
                ]
            )
            fig.update_layout(
                title="Transcribed minutes per day (current month)",
                xaxis_title="Date",
                yaxis_title="Minutes",
                template="plotly_dark" if is_dark else "plotly_white",
                margin=dict(l=40, r=20, t=60, b=40),
                height=400,
            )

            with ui.element("div").classes("chart-container"):
                ui.plotly(fig).classes("w-full")

        if per_day_previous_month:
            dates_prev = list(per_day_previous_month.keys())
            values_prev = list(per_day_previous_month.values())

            fig_prev = go.Figure(
                data=[
                    go.Bar(
                        x=dates_prev,
                        y=values_prev,
                        marker=dict(color=cc["bar_previous"], line=dict(width=0)),
                        hovertemplate="%{x} - %{y:.1f} minutes<extra></extra>",
                    )
                ]
            )
            fig_prev.update_layout(
                title="Transcribed minutes per day (previous month)",
                xaxis_title="Date",
                yaxis_title="Minutes",
                template="plotly_dark" if is_dark else "plotly_white",
                margin=dict(l=40, r=20, t=60, b=40),
                height=400,
            )

            with ui.element("div").classes("chart-container"):
                ui.plotly(fig_prev).classes("w-full")

        if per_user:
            with ui.element("div").classes("table-container"):
                ui.label("Transcribed minutes per user this month").classes(
                    "text-theme-primary"
                )
                user_rows = [
                    {"username": username, "minutes": f"{minutes:.1f}"}
                    for username, minutes in per_user.items()
                ]

                user_columns = [
                    {
                        "name": "username",
                        "label": "Username",
                        "field": "username",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "minutes",
                        "label": "Minutes",
                        "field": "minutes",
                        "align": "left",
                        "sortable": True,
                        ":sort": "(a, b, rowA, rowB) => a - b",
                    },
                ]

                stats_table = ui.table(
                    columns=user_columns,
                    rows=user_rows,
                    pagination=20,
                ).style(
                    "width: 100%; box-shadow: none; font-size: 16px; margin: auto; height: calc(100vh - 160px - var(--banner-offset, 0px));"
                )

                with stats_table.add_slot("top-right"):
                    with ui.input(placeholder="Search").props("type=search").bind_value(
                        stats_table, "filter"
                    ).add_slot("append"):
                        ui.icon("search")

        if job_queue:
            with ui.element("div").classes("table-container"):
                ui.label("Job queue for group").classes(
                    "text-2xl font-bold mb-4 text-theme-primary"
                )
                queue_columns = [
                    {
                        "name": "job_id",
                        "label": "Job ID",
                        "field": "job_id",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "username",
                        "label": "Username",
                        "field": "username",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "status",
                        "label": "Status",
                        "field": "status",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "created_at",
                        "label": "Created at",
                        "field": "created_at",
                        "align": "left",
                        "sortable": True,
                    },
                ]

                stats_table = ui.table(
                    columns=queue_columns,
                    rows=job_queue,
                    pagination=20,
                ).style(
                    "width: 100%; box-shadow: none; font-size: 16px; margin: auto; height: calc(100vh - 160px - var(--banner-offset, 0px));"
                )

                with stats_table.add_slot("top-right"):
                    with ui.input(placeholder="Search").props("type=search").bind_value(
                        stats_table, "filter"
                    ).add_slot("append"):
                        ui.icon("search")


def create() -> None:
    @ui.refreshable
    @ui.page("/admin")
    def admin() -> None:
        """
        Main page of the application.
        """
        page_init(use_drawer=True, title="Groups")

        if not get_admin_status():
            ui.navigate.to("/home")
            return

        ui.add_head_html(default_styles)

        with ui.row().style(
            "justify-content: space-between; align-items: center; width: 100%;"
        ):
            with ui.element("div").style("display: flex; gap: 0px;"):
                ui.label("Groups").classes("text-3xl font-bold")

            with ui.element("div").style("display: flex; gap: 10px;"):
                create = (
                    ui.button("Create new group")
                    .classes("default-style")
                    .props("color=black flat")
                )
                create.on("click", lambda: create_group_dialog(page=admin))

                groups = groups_get()

            if not groups:
                ui.label("No groups found. Create a new group to get started.").classes(
                    "text-lg"
                )
                return

            with ui.scroll_area().style(
                "height: calc(100vh - 160px - var(--banner-offset, 0px)); width: 100%;"
            ):
                groups = sorted(
                    groups,
                    key=lambda x: (
                        x["name"].lower() != "all users",
                        x["name"].lower(),
                    ),
                )

                g = Group(
                    group_id=groups[0]["id"],
                    name=groups[0]["name"],
                    description=groups[0]["description"],
                    created_at=groups[0]["created_at"],
                    users=groups[0]["users"],
                    nr_users=groups[0]["nr_users"],
                    stats=groups[0]["stats"],
                    quota_seconds=groups[0]["quota_seconds"],
                )

                g.create_card()

                expansions = {}
                groups = sorted(
                    groups,
                    key=lambda x: (
                        x["customer_name"].lower() != "all users",
                        x["customer_name"].lower(),
                    ),
                )

                for group in groups[1:]:
                    if group["name"] == "All users":
                        continue
                    customer_name = group.get("customer_name", "None")

                    g = Group(
                        group_id=group["id"],
                        name=group["name"],
                        description=group["description"],
                        created_at=group["created_at"],
                        users=group["users"],
                        nr_users=group["nr_users"],
                        stats=group["stats"],
                        quota_seconds=group["quota_seconds"],
                    )

                    if get_bofh_status():
                        if customer_name not in expansions:
                            expansions[customer_name] = (
                                ui.expansion(
                                    f"Customer: {customer_name}",
                                    value=False,
                                )
                                .classes("text-bold")
                                .style(
                                    "width: 100%; background-color: var(--color-bg-surface);"
                                )
                            )

                        if group["name"] == "All users":
                            g.create_card()
                        else:
                            with expansions[customer_name]:
                                g.create_card()
                    else:
                        g.create_card()

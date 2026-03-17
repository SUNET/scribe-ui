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

import plotly.graph_objects as go
import requests

import re

from collections import defaultdict
from datetime import datetime
from nicegui import ui
from utils.common import add_timezone_to_timestamp, default_styles, page_init
from db.analytics import (
    log_action,
    get_page_views,
    get_page_views_summary,
    get_views_per_day,
    get_recent_views,
    get_hourly_heatmap,
    get_hourly_distribution,
    get_week_over_week,
    get_total_stats,
)
from utils.helpers import (
    groups_get,
    realms_get,
    remove_user,
    save_customer,
    save_group,
    set_active_status,
    set_admin_status,
    set_domains,
    get_customer_realms,
    user_statistics_get,
    export_customers_csv,
    customers_get,
    rules_get,
    rule_create,
    rule_update,
    rule_delete,
    attributes_get,
    attribute_create,
    attribute_delete,
)
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
    get_bofh_status,
    get_user_data,
)
from utils.group import Group
from utils.customer import Customer


settings = get_settings()


def create_group_dialog(page: callable) -> None:
    """
    Show a dialog to create a new group.
    """

    with ui.dialog() as create_group_dialog:
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
                        requests.post(
                            settings.API_URL + "/api/v1/admin/groups",
                            headers=get_auth_header(),
                            json={
                                "name": name_input.value,
                                "description": description_input.value,
                                "quota_seconds": int(quota.value) * 60,
                            },
                        ),
                        log_action("create_group"),
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

    with ui.dialog() as dialog:
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
                    lambda: set_admin_status(
                        admin_table.selected, True, dialog, group_id
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
    page_init(use_drawer=True)

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #ffffff;
            }
        </style>
        """
    )

    try:
        res = requests.get(
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

    except requests.RequestException as e:
        ui.label(f"Error fetching group: {e}").classes("text-lg text-red-500")
        return

    ui.label(f"Edit group: {group['name']}").classes("text-3xl font-bold mb-4")

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
            "width: 100%; box-shadow: none; font-size: 18px; height: calc(100vh - 550px);"
        )

        users_table.selected = [
            user for user in group["users"] if user.get("in_group", True)
        ]

        with users_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                users_table, "filter"
            ).add_slot("append"):
                ui.icon("search")

    with ui.row().style(
        "justify-content: flex-end; width: 100%; padding: 16px; gap: 8px;"
    ):
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


@ui.refreshable
@ui.page("/admin/stats/{group_id}")
def statistics(group_id: str) -> None:
    """
    Page to show statistics of a group with improved layout and design.
    """
    page_init(use_drawer=True)

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #ffffff;
            }
            .stats-container {
                max-width: 1500px;
                margin: 0 auto;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 2rem;
                padding: 2rem 1rem;
            }
            .stats-card {
                width: 100%;
                background-color: #ffffff;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
                border-radius: 1rem;
                padding: 1.5rem 2rem;
                text-align: center;
            }
            .stats-card h1 {
                font-size: 1.8rem;
                font-weight: 700;
                margin-bottom: 1rem;
                color: #111827;
            }
            .stats-card p {
                margin: 0.25rem 0;
                font-size: 1.1rem;
                color: #374151;
            }
            .chart-container {
                width: 100%;
                background-color: #ffffff;
                border-radius: 1rem;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
                padding: 1.5rem 2rem;
            }
            .table-container {
                width: 100%;
                background-color: #ffffff;
                border-radius: 1rem;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
                padding: 1.5rem 2rem;
            }
        </style>
        """
    )

    stats = user_statistics_get(group_id=group_id)

    if not stats or "result" not in stats:
        ui.label("Error fetching statistics.").classes(
            "text-lg text-red-500 text-center mt-6"
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
            ui.label(f"Number of users: {total_users}").classes("text-lg text-gray-600")
            ui.label(
                f"Transcribed files this month: {result.get('transcribed_files', 0)} files"
            ).classes("text-lg text-gray-600")
            ui.label(
                f"Transcribed files last month: {result.get('transcribed_files_last_month', 0)} files"
            ).classes("text-lg text-gray-600")
            ui.label(
                f"Transcribed minutes this month: {result.get('total_transcribed_minutes', 0):.0f} minutes"
            ).classes("text-lg text-gray-600")
            ui.label(
                f"Transcribed minutes last month: {result.get('total_transcribed_minutes_last_month', 0):.0f} minutes"
            ).classes("text-lg text-gray-600")

        if per_day:
            dates = list(per_day.keys())
            values = list(per_day.values())

            fig = go.Figure(
                data=[
                    go.Bar(
                        x=dates,
                        y=values,
                        marker=dict(color="#4F46E5", line=dict(width=0)),
                        hovertemplate="%{x} - %{y:.1f} minutes<extra></extra>",
                    )
                ]
            )
            fig.update_layout(
                title="Transcribed minutes per day (current month)",
                xaxis_title="Date",
                yaxis_title="Minutes",
                template="plotly_white",
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
                        marker=dict(color="#10B981", line=dict(width=0)),
                        hovertemplate="%{x} - %{y:.1f} minutes<extra></extra>",
                    )
                ]
            )
            fig_prev.update_layout(
                title="Transcribed minutes per day (previous month)",
                xaxis_title="Date",
                yaxis_title="Minutes",
                template="plotly_white",
                margin=dict(l=40, r=20, t=60, b=40),
                height=400,
            )

            with ui.element("div").classes("chart-container"):
                ui.plotly(fig_prev).classes("w-full")

        if per_user:
            with ui.element("div").classes("table-container"):
                ui.label("Transcribed minutes per user this month").classes(
                    "text-gray-800"
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
                    "width: 100%; box-shadow: none; font-size: 16px; margin: auto; height: calc(100vh - 160px);"
                )

                with stats_table.add_slot("top-right"):
                    with ui.input(placeholder="Search").props("type=search").bind_value(
                        stats_table, "filter"
                    ).add_slot("append"):
                        ui.icon("search")

        if job_queue:
            with ui.element("div").classes("table-container"):
                ui.label("Job queue for group").classes(
                    "text-2xl font-bold mb-4 text-gray-800"
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
                    "width: 100%; box-shadow: none; font-size: 16px; margin: auto; height: calc(100vh - 160px);"
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
        page_init(use_drawer=True)

        ui.add_head_html(default_styles)
        ui.add_head_html(
            """
            <style>
                body {
                    background-color: #ffffff;
                }
            </style>
            """
        )

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

            with ui.scroll_area().style("height: calc(100vh - 160px); width: 100%;"):
                groups = sorted(
                    groups_get()["result"],
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
                    groups_get()["result"],
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
                                .style("width: 100%; background-color: #ffffff;")
                            )

                        if group["name"] == "All users":
                            g.create_card()
                        else:
                            with expansions[customer_name]:
                                g.create_card()
                    else:
                        g.create_card()


@ui.page("/admin/users")
def users() -> None:
    """
    Page to show all users.
    """
    page_init(use_drawer=True)

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #ffffff;
            }
        </style>
        """
    )

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/users", headers=get_auth_header()
        )
        res.raise_for_status()
        users = res.json()["result"]

        # Add an id field to each user for table selection
        for index, user in enumerate(users):
            user["id"] = index
            user["admin"] = "Yes" if user.get("admin", True) else "No"
            user["active"] = "Yes" if user.get("active", True) else "No"

    except requests.RequestException as e:
        ui.label(f"Error fetching users: {e}").classes("text-lg text-red-500")
        return

    ui.label("Users").classes("text-3xl font-bold mb-4")

    with ui.card().style("width: 100%; box-shadow: none; align-self: center;"):
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
            ],
            rows=users,
            selection="multiple",
            pagination=20,
            on_select=lambda e: None,
        ).style(
            "width: 100%; box-shadow: none; font-size: 18px; height: calc(100vh - 300px);"
        )

        with users_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                users_table, "filter"
            ).add_slot("append"):
                ui.icon("search")

    with ui.row().style(
        "justify-content: flex-end; width: 100%; padding: 16px; gap: 8px;"
    ):
        ui.button("Enable").classes("button-close").props("color=black flat").style(
            "width: 150px"
        ).on("click", lambda: set_active_status(users_table.selected, True))
        ui.button("Disable").classes("delete-style").props("color=black flat").on(
            "click", lambda: set_active_status(users_table.selected, False)
        )
        ui.button("Domains").classes("button-close").props("color=black flat").style(
            "width: 150px"
        ).on("click", lambda: set_domains(users_table.selected, users))
        ui.button("Make admin").classes("button-close").props("color=black flat").style(
            "width: 150px"
        ).on("click", lambda: set_admin_status(users_table.selected, True, None, ""))
        ui.button("Remove admin").classes("delete-style").props("color=black flat").on(
            "click", lambda: set_admin_status(users_table.selected, False, None, "")
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

        ui.button("Remove user").classes("delete-style").props("color=black flat").on(
            "click", confirm_remove_user
        )


@ui.page("/health")
def health() -> None:
    """
    Health check dashboard displaying backend system metrics.
    """

    page_init(use_drawer=True)

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #ffffff;
            }
            .card {
                background-color: white;
                border-radius: 1rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                padding: 1.25rem;
                width: 100%;
                max-width: 100%;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }
            .status-dot {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                display: inline-block;
                margin-right: 6px;
            }
            .health-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
                gap: 1.25rem;
                width: 100%;
            }
            @media (max-width: 768px) {
                .health-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
        """
    )

    ui.label("System status").classes("text-3xl font-bold mb-4")

    @ui.refreshable
    def render_health():
        try:
            res = requests.get(
                settings.API_URL + "/api/v1/healthcheck",
                headers=get_auth_header(),
                timeout=5,
            )
            res.raise_for_status()
            data = res.json()["result"]
            backend_reachable = True
        except Exception:
            data = {}
            backend_reachable = False

        if not backend_reachable:
            ui.label("Backend is not reachable").classes("text-lg text-red-500")
            return

        with ui.element("div").classes("health-grid"):
            if not data:
                ui.label("No workers online.").classes("text-lg text-gray-600")
                return

            for host, samples in data.items():
                if not samples:
                    continue

                seen = samples[-1]["seen"]
                latest = samples[-1]

                load_vals = [s["load_avg"] for s in samples]
                mem_vals = [s["memory_usage"] for s in samples]

                if "gpu_usage" in samples[-1] and samples[-1]["gpu_usage"]:
                    gpu_cpu_vals = [
                        s["gpu_usage"][0]["utilization"]
                        for s in samples
                        if "gpu_usage" in s
                    ]
                    gpu_mem_vals = [
                        (
                            s["gpu_usage"][0]["memory_used"]
                            / s["gpu_usage"][0]["memory_total"]
                        )
                        * 100
                        for s in samples
                        if "gpu_usage" in s
                    ]

                times = [
                    datetime.fromtimestamp(s["seen"]).strftime("%H:%M:%S")
                    for s in samples
                ]

                with ui.card().classes("card"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(host).classes("text-lg font-medium")

                        status_color = (
                            "bg-red-500"
                            if (datetime.now().timestamp() - seen) > 30
                            else "bg-green-500"
                        )
                        status = (
                            "Offline"
                            if (datetime.now().timestamp() - seen) > 30
                            else "Online"
                        )

                        ui.html(
                            f'<span class="status-dot {status_color}"></span>{status}',
                            sanitize=False,
                        )

                    ui.label(
                        f"Load Avg: {latest['load_avg']:.1f} | Memory Usage: {latest['memory_usage']:.1f}%"
                    ).classes("text-sm text-gray-600 mb-2")

                    fig_cpu = go.Figure()
                    fig_cpu.add_trace(
                        go.Scatter(
                            x=times,
                            y=load_vals,
                            mode="lines",
                            name="Load Avg",
                            line=dict(color="#3b82f6", width=2.5, shape="spline"),
                            fill="tozeroy",
                            fillcolor="rgba(59, 130, 246, 0.1)",
                            hovertemplate="<b>Load</b>: %{y:.1f}<br><extra></extra>",
                        )
                    )
                    fig_cpu.add_trace(
                        go.Scatter(
                            x=times,
                            y=mem_vals,
                            mode="lines",
                            name="Memory %",
                            line=dict(color="#10b981", width=2.5, shape="spline"),
                            fill="tozeroy",
                            fillcolor="rgba(16, 185, 129, 0.1)",
                            hovertemplate="<b>Memory</b>: %{y:.1f}%<br><extra></extra>",
                        )
                    )
                    fig_cpu.update_layout(
                        margin=dict(l=40, r=20, t=30, b=40),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="center",
                            x=0.5,
                            font=dict(size=11),
                        ),
                        height=200,
                        template="plotly_white",
                        xaxis=dict(
                            title="Time",
                            showgrid=True,
                            gridcolor="rgba(0,0,0,0.05)",
                        ),
                        yaxis=dict(
                            title="%",
                            showgrid=True,
                            gridcolor="rgba(0,0,0,0.05)",
                            rangemode="tozero",
                        ),
                        font=dict(size=11),
                        plot_bgcolor="rgba(248, 250, 252, 0.5)",
                        hovermode="x unified",
                    )
                    ui.plotly(fig_cpu).classes("w-full")

                    if "gpu_usage" in samples[-1] and samples[-1]["gpu_usage"]:
                        fig_gpu = go.Figure()
                        fig_gpu.add_trace(
                            go.Scatter(
                                x=times[-len(gpu_cpu_vals) :],
                                y=gpu_cpu_vals,
                                mode="lines",
                                name="GPU Util%",
                                line=dict(color="#8b5cf6", width=2.5, shape="spline"),
                                fill="tozeroy",
                                fillcolor="rgba(139, 92, 246, 0.1)",
                                hovertemplate="<b>GPU Util</b>: %{y:.1f}%<br><extra></extra>",
                            )
                        )
                        fig_gpu.add_trace(
                            go.Scatter(
                                x=times[-len(gpu_mem_vals) :],
                                y=gpu_mem_vals,
                                mode="lines",
                                name="GPU Mem%",
                                line=dict(color="#f59e0b", width=2.5, shape="spline"),
                                fill="tozeroy",
                                fillcolor="rgba(245, 158, 11, 0.1)",
                                hovertemplate="<b>GPU Memory</b>: %{y:.1f}%<br><extra></extra>",
                            )
                        )

                        fig_gpu.update_layout(
                            margin=dict(l=40, r=20, t=30, b=40),
                            legend=dict(
                                orientation="h",
                                yanchor="bottom",
                                y=1.02,
                                xanchor="center",
                                x=0.5,
                                font=dict(size=11),
                            ),
                            height=200,
                            template="plotly_white",
                            xaxis=dict(
                                title="Time",
                                showgrid=True,
                                gridcolor="rgba(0,0,0,0.05)",
                            ),
                            yaxis=dict(
                                title="%",
                                showgrid=True,
                                gridcolor="rgba(0,0,0,0.05)",
                                rangemode="tozero",
                            ),
                            font=dict(size=11),
                            plot_bgcolor="rgba(248, 250, 252, 0.5)",
                            hovermode="x unified",
                        )
                        ui.plotly(fig_gpu).classes("w-full")

                    ui.label(f"Last updated: {times[-1]} UTC").classes(
                        "text-xs text-gray-400 mt-1"
                    )

    render_health()

    ui.timer(10.0, render_health.refresh)


def create_customer_dialog(page: callable) -> None:
    realms = _get_valid_realms()

    with ui.dialog() as create_customer_dialog:
        with ui.card().style("width: 600px; max-width: 90vw;"):
            ui.label("Create new customer").classes("text-2xl font-bold")

            customer_abbr = (
                ui.input("Customer abbreviation").classes("w-full").props("outlined")
            )
            partner_id_input = (
                ui.input("Kaltura Partner ID", value="N/A")
                .classes("w-full")
                .props("outlined")
            )
            name_input = ui.input("Customer name").classes("w-full").props("outlined")
            contact_email_input = (
                ui.input("Contact email").classes("w-full").props("outlined")
            )
            support_contact_email_input = (
                ui.input("Support contact email").classes("w-full").props("outlined")
            )

            priceplan_select = (
                ui.select(["fixed", "variable"], label="Price plan", value="variable")
                .classes("w-full")
                .props("outlined")
            )

            base_fee = (
                ui.input("Base fee", value="0")
                .classes("w-full")
                .props("outlined type=number min=0")
            )

            blocks_input = (
                ui.input("Blocks purchased (4000 min/block)", value="0")
                .classes("w-full")
                .props("outlined type=number min=0")
            )

            # Show/hide blocks input based on price plan
            def update_blocks_visibility():
                if priceplan_select.value == "fixed":
                    blocks_input.set_visibility(True)
                else:
                    blocks_input.set_visibility(False)
                    blocks_input.value = "0"

            priceplan_select.on(
                "update:model-value", lambda: update_blocks_visibility()
            )
            blocks_input.set_visibility(False)  # Initially hidden

            realm_select = (
                ui.select(
                    realms, label="Select existing realms", multiple=True, value=[]
                )
                .classes("w-full")
                .props("outlined")
            )

            new_realms_input = (
                ui.input("Add new realms (comma-separated)")
                .classes("w-full")
                .props("outlined")
            )

            notes_input = ui.textarea("Notes").classes("w-full").props("outlined")

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: create_customer_dialog.close())

                def create_customer():
                    if not partner_id_input.value.strip():
                        ui.notify("Kaltura Partner ID is required.", color="red")
                        return
                    if not name_input.value.strip():
                        ui.notify("Customer name is required.", color="red")
                        return

                    selected_realms = realm_select.value if realm_select.value else []
                    new_realms = [
                        r.strip()
                        for r in new_realms_input.value.split(",")
                        if r.strip()
                    ]
                    all_realms = list(set(selected_realms + new_realms))
                    realms_str = ",".join(all_realms)

                    try:
                        res = requests.post(
                            settings.API_URL + "/api/v1/admin/customers",
                            headers=get_auth_header(),
                            json={
                                "customer_abbr": customer_abbr.value,
                                "partner_id": partner_id_input.value,
                                "name": name_input.value,
                                "contact_email": contact_email_input.value,
                                "support_contact_email": support_contact_email_input.value,
                                "priceplan": priceplan_select.value,
                                "base_fee": int(base_fee.value)
                                if base_fee.value
                                else 0,
                                "blocks_purchased": int(blocks_input.value)
                                if blocks_input.value
                                else 0,
                                "realms": realms_str,
                                "notes": notes_input.value,
                            },
                        )

                        res.raise_for_status()
                    except requests.RequestException as e:
                        if res.status_code == 400:
                            error_msg = res.json().get("error", "Unknown error")
                            ui.notify(
                                f"Error creating customer: {error_msg}", color="red"
                            )
                            return
                        else:
                            ui.notify(f"Error creating customer: {e}", color="red")
                            return
                    else:
                        create_customer_dialog.close()
                        ui.navigate.to("/admin/customers")

                ui.button("Create").classes("default-style").props(
                    "color=black flat"
                ).on("click", create_customer)

        create_customer_dialog.open()


@ui.refreshable
@ui.page("/admin/customers/edit/{customer_id}")
def edit_customer(customer_id: str) -> None:
    """
    Page to edit a customer.
    """
    page_init(use_drawer=True)

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #ffffff;
            }
        </style>
        """
    )

    try:
        res = requests.get(
            settings.API_URL + f"/api/v1/admin/customers/{customer_id}",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        customer = res.json()["result"]

        realms = _get_valid_realms()
        customer_realms = [
            r.strip() for r in customer["realms"].split(",") if r.strip()
        ]

    except requests.RequestException as e:
        ui.label(f"Error fetching customer: {e}").classes("text-lg text-red-500")
        return

    ui.label(f"Edit customer: {customer['name']}").classes("text-3xl font-bold mb-4")

    with ui.card().style("width: 100%; box-shadow: none; align-self: center;"):
        with ui.column().classes("gap-4 w-full"):
            customer_abbr_input = (
                ui.input(
                    "Customer abbreviation", value=customer.get("customer_abbr", "")
                )
                .props("outlined")
                .classes("w-full")
            )
            partner_id_input = (
                ui.input("Kaltura Partner ID", value=customer["partner_id"])
                .props("outlined")
                .classes("w-full")
            )
            name_input = (
                ui.input("Customer name", value=customer["name"])
                .props("outlined")
                .classes("w-full")
            )
            contact_email_input = (
                ui.input("Contact email", value=customer.get("contact_email", ""))
                .props("outlined")
                .classes("w-full")
            )
            support_contact_email_input = (
                ui.input(
                    "Support contact email",
                    value=customer.get("support_contact_email", ""),
                )
                .props("outlined")
                .classes("w-full")
            )

            priceplan_select = (
                ui.select(
                    ["fixed", "variable"],
                    label="Price plan",
                    value=customer["priceplan"],
                )
                .classes("w-full")
                .props("outlined")
            )
            base_fee = (
                ui.input("Base fee", value=str(customer.get("base_fee", 0)))
                .classes("w-full")
                .props("outlined type=number min=0")
            )
            blocks_input = (
                ui.input(
                    "Blocks purchased (4000 min/block)",
                    value=str(customer.get("blocks_purchased", 0)),
                )
                .classes("w-full")
                .props("outlined type=number min=0")
            )

            # Show/hide blocks input based on price plan
            def update_blocks_visibility():
                if priceplan_select.value == "fixed":
                    blocks_input.set_visibility(True)
                else:
                    blocks_input.set_visibility(False)

            priceplan_select.on(
                "update:model-value", lambda: update_blocks_visibility()
            )
            update_blocks_visibility()

            realm_select = (
                ui.select(
                    realms,
                    label="Select existing realms",
                    multiple=True,
                    value=customer_realms,
                )
                .classes("w-full")
                .props("outlined use-chips")
            )

            new_realms_input = (
                ui.input("Add new realms (comma-separated)")
                .classes("w-full")
                .props("outlined")
            )

            notes_input = (
                ui.textarea("Notes", value=customer.get("notes", ""))
                .classes("w-full")
                .props("outlined")
            )

    with ui.row().style(
        "justify-content: flex-end; width: 100%; padding: 16px; gap: 8px;"
    ):
        ui.button("Save customer").classes("default-style").props(
            "color=black flat"
        ).style("width: 150px").on(
            "click",
            lambda: save_customer(
                customer_abbr_input.value,
                customer_id,
                partner_id_input.value,
                name_input.value,
                contact_email_input.value,
                support_contact_email_input.value,
                priceplan_select.value,
                base_fee.value,
                realm_select.value if realm_select.value else [],
                new_realms_input.value,
                notes_input.value,
                blocks_input.value,
            ),
        )
        ui.button("Cancel").classes("delete-style").props("color=black flat").on(
            "click", lambda: ui.navigate.to("/admin/customers")
        )


@ui.page("/admin/customers")
def customers() -> None:
    """
    Customer management page.
    """
    page_init(use_drawer=True)

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #ffffff;
            }
        </style>
        """
    )

    with ui.row().style(
        "justify-content: space-between; align-items: center; width: 100%;"
    ):
        with ui.element("div").style("display: flex; gap: 0px;"):
            if get_bofh_status():
                ui.label("Customers").classes("text-3xl font-bold")
            elif get_admin_status():
                ui.label("Account information").classes("text-3xl font-bold")
            else:
                pass

        with ui.element("div").style("display: flex; gap: 10px;"):
            if get_bofh_status():
                create = (
                    ui.button("Create new customer")
                    .classes("default-style")
                    .props("color=black flat")
                )
                create.on("click", lambda: create_customer_dialog(page=customers))

            # Export CSV button
            export_csv = (
                ui.button("Export CSV").classes("button-edit").props("color=white flat")
            )
            export_csv.on("click", lambda: export_customers_csv())

    customers_data = customers_get()

    if not customers_data or "result" not in customers_data:
        ui.label("No customers found. Create a new customer to get started.").classes(
            "text-lg"
        )
        return

    with ui.scroll_area().style("height: calc(100vh - 160px); width: 100%;"):
        customers_list = sorted(
            customers_data["result"], key=lambda x: x["name"].lower()
        )
        for customer in customers_list:
            c = Customer(
                customer_abbr=customer.get("customer_abbr", ""),
                customer_id=customer["id"],
                partner_id=customer["partner_id"],
                name=customer["name"],
                contact_email=customer.get("contact_email", ""),
                support_contact_email=customer.get("support_contact_email", ""),
                priceplan=customer["priceplan"],
                realms=customer["realms"],
                notes=customer.get("notes", ""),
                created_at=customer["created_at"],
                stats=customer.get("stats", {}),
                blocks_purchased=customer.get("blocks_purchased", 0),
                base_fee=customer["base_fee"],
            )
            c.create_card()


CONDITION_OPTIONS = {
    "equals": "Equals",
    "not_equals": "Not equals",
    "contains": "Contains",
    "not_contains": "Not contains",
    "starts_with": "Starts with",
    "ends_with": "Ends with",
    "regex_match": "Regex match",
}


def _get_valid_realms() -> list[str]:
    """
    Return realms that look like real domains (contain a dot for TLD).
    """

    return [r for r in realms_get() if r and "." in r]


def create_rule_dialog(page: callable) -> None:
    """
    Show a dialog to create a new attribute rule.
    """

    onboarding_attrs = attributes_get()
    attr_names = [a["name"] for a in onboarding_attrs]
    all_groups = groups_get()
    group_options = {}

    if all_groups and "result" in all_groups:
        group_options = {
            g["id"]: g["name"] for g in all_groups["result"] if g["name"] != "All users"
        }

    is_bofh = get_bofh_status()

    if not is_bofh:
        user_data = get_user_data() or {}
        admin_domains = user_data.get("admin_domains", "")
        allowed_realms = [
            d.strip() for d in admin_domains.split(",") if d.strip() and "." in d.strip()
        ]

    with ui.dialog() as dialog:
        with ui.card().style("width: 650px; max-width: 90vw;"):
            ui.label("Create provisioning rule").classes("text-2xl font-bold")

            name_input = ui.input("Rule name").classes("w-full").props("outlined")

            attr_select = (
                ui.select(attr_names, label="Attribute name", with_input=True)
                .classes("w-full")
                .props("outlined")
            )
            condition_select = (
                ui.select(CONDITION_OPTIONS, label="Condition")
                .classes("w-full")
                .props("outlined")
            )

            value_input = (
                ui.input("Attribute value").classes("w-full").props("outlined")
            )

            ui.label("Scope").classes("text-lg font-semibold mt-2")
            if is_bofh:
                all_realms = _get_valid_realms()
                realm_input = (
                    ui.select(
                        all_realms,
                        label="Realm",
                        multiple=True,
                        with_input=True,
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )
            else:
                realm_input = (
                    ui.select(
                        allowed_realms,
                        label="Realm",
                        multiple=True,
                        value=[allowed_realms[0]] if allowed_realms else [],
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )

            ui.label("Actions").classes("text-lg font-semibold mt-2")
            with ui.row().classes("w-full gap-4"):
                activate_cb = ui.checkbox("Activate user")
                deny_cb = ui.checkbox("Deactivate user")

            activate_cb.on_value_change(
                lambda e: deny_cb.set_value(False) if e.value else None
            )
            deny_cb.on_value_change(
                lambda e: activate_cb.set_value(False) if e.value else None
            )

            group_select = (
                ui.select(
                    group_options,
                    label="Assign user to group (optional)",
                    clearable=True,
                )
                .classes("w-full")
                .props("outlined")
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Create").classes("default-style").props(
                    "color=black flat"
                ).on(
                    "click",
                    lambda: (
                        _do_create_rule(
                            name=name_input.value,
                            attribute_name=attr_select.value,
                            attribute_condition=condition_select.value,
                            attribute_value=value_input.value,
                            realm=realm_input.value,
                            activate=activate_cb.value,
                            deny=deny_cb.value,
                            assign_to_group=group_select.value,
                        )
                        and (dialog.close(), ui.navigate.to("/admin/rules"))
                    ),
                )

        dialog.open()


def _do_create_rule(**kwargs) -> bool:
    """
    Helper to create a rule from dialog values. Returns True on success.
    """

    realm_val = kwargs["realm"]

    if not realm_val or (isinstance(realm_val, list) and len(realm_val) == 0):
        with ui.dialog() as warn_dlg, ui.card().classes("p-6"):
            ui.label("Realm required").classes("text-h6")
            ui.label("At least one realm must be selected.")
            ui.button("OK", on_click=warn_dlg.close).classes("mt-4 self-end")
        warn_dlg.open()

        return False

    data = {
        "name": kwargs["name"],
        "attribute_name": kwargs["attribute_name"],
        "attribute_condition": kwargs["attribute_condition"],
        "attribute_value": kwargs["attribute_value"],
        "realm": ",".join(realm_val) if isinstance(realm_val, list) else realm_val,
        "activate": kwargs["activate"],
        "deny": kwargs["deny"],
        "assign_to_group": str(kwargs["assign_to_group"])
        if kwargs["assign_to_group"]
        else None,
    }

    result = rule_create(data)

    if result:
        log_action("create_rule")
        ui.notify("Rule created successfully.", color="positive")
        return True

    ui.notify("Failed to create rule.", color="negative")

    return False


def edit_rule_dialog(rule: dict, page: callable) -> None:
    """
    Show a dialog to edit an existing attribute rule.
    """

    onboarding_attrs = attributes_get()
    attr_names = [a["name"] for a in onboarding_attrs]
    all_groups = groups_get()
    group_options = {}

    if all_groups and "result" in all_groups:
        group_options = {
            g["id"]: g["name"] for g in all_groups["result"] if g["name"] != "All users"
        }

    is_bofh = get_bofh_status()

    if not is_bofh:
        user_data = get_user_data() or {}
        admin_domains = user_data.get("admin_domains", "")
        allowed_realms = [
            d.strip() for d in admin_domains.split(",") if d.strip() and "." in d.strip()
        ]

    with ui.dialog() as dialog:
        with ui.card().style("width: 650px; max-width: 90vw;"):
            ui.label("Edit provisioning rule").classes("text-2xl font-bold")

            name_input = (
                ui.input("Rule name", value=rule["name"])
                .classes("w-full")
                .props("outlined")
            )

            attr_select = (
                ui.select(
                    attr_names,
                    label="Attribute name",
                    value=rule["attribute_name"],
                    with_input=True,
                )
                .classes("w-full")
                .props("outlined")
            )
            condition_select = (
                ui.select(
                    CONDITION_OPTIONS,
                    label="Condition",
                    value=rule["attribute_condition"],
                )
                .classes("w-full")
                .props("outlined")
            )

            value_input = (
                ui.input("Attribute value", value=rule["attribute_value"])
                .classes("w-full")
                .props("outlined")
            )

            ui.label("Scope").classes("text-lg font-semibold mt-2")
            existing_realms = [
                r.strip() for r in (rule.get("realm") or "").split(",") if r.strip()
            ]
            if is_bofh:
                all_realms = _get_valid_realms()
                realm_options = sorted(set(all_realms + existing_realms))
                realm_input = (
                    ui.select(
                        realm_options,
                        label="Realm",
                        multiple=True,
                        value=existing_realms,
                        with_input=True,
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )
            else:
                realm_options = sorted(set(allowed_realms + existing_realms))
                realm_input = (
                    ui.select(
                        realm_options,
                        label="Realm",
                        multiple=True,
                        value=existing_realms
                        or ([allowed_realms[0]] if allowed_realms else []),
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )

            ui.label("Actions").classes("text-lg font-semibold mt-2")
            with ui.row().classes("w-full gap-4"):
                activate_cb = ui.checkbox(
                    "Activate user", value=rule.get("activate", False)
                )
                deny_cb = ui.checkbox("Deactivate user", value=rule.get("deny", False))

            activate_cb.on_value_change(
                lambda e: deny_cb.set_value(False) if e.value else None
            )
            deny_cb.on_value_change(
                lambda e: activate_cb.set_value(False) if e.value else None
            )

            group_value = rule.get("assign_to_group")
            try:
                group_value = int(group_value) if group_value else None
            except (ValueError, TypeError):
                group_value = None

            group_select = (
                ui.select(
                    group_options,
                    label="Assign user to group (optional)",
                    value=group_value,
                    clearable=True,
                )
                .classes("w-full")
                .props("outlined")
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Save").classes("default-style").props("color=black flat").on(
                    "click",
                    lambda: (
                        _do_update_rule(
                            rule_id=rule["id"],
                            name=name_input.value,
                            attribute_name=attr_select.value,
                            attribute_condition=condition_select.value,
                            attribute_value=value_input.value,
                            realm=realm_input.value,
                            activate=activate_cb.value,
                            deny=deny_cb.value,
                            assign_to_group=group_select.value,
                        )
                        and (dialog.close(), ui.navigate.to("/admin/rules"))
                    ),
                )

        dialog.open()


def _do_update_rule(**kwargs) -> bool:
    """
    Helper to update a rule from dialog values. Returns True on success.
    """

    realm_val = kwargs["realm"]

    if not realm_val or (isinstance(realm_val, list) and len(realm_val) == 0):
        with ui.dialog() as warn_dlg, ui.card().classes("p-6"):
            ui.label("Realm required").classes("text-h6")
            ui.label("At least one realm must be selected.")
            ui.button("OK", on_click=warn_dlg.close).classes("mt-4 self-end")
        warn_dlg.open()

        return False

    data = {
        "name": kwargs["name"],
        "attribute_name": kwargs["attribute_name"],
        "attribute_condition": kwargs["attribute_condition"],
        "attribute_value": kwargs["attribute_value"],
        "realm": ",".join(realm_val) if isinstance(realm_val, list) else realm_val,
        "activate": kwargs["activate"],
        "deny": kwargs["deny"],
        "assign_to_group": str(kwargs["assign_to_group"])
        if kwargs["assign_to_group"]
        else None,
    }

    if rule_update(kwargs["rule_id"], data):
        log_action("edit_rule")
        ui.notify("Rule updated successfully.", color="positive")
        return True

    ui.notify("Failed to update rule.", color="negative")

    return False


def delete_rule_dialog(rule: dict) -> None:
    """
    Show confirmation dialog to delete a rule.
    """

    with ui.dialog() as dialog:
        with ui.card().style("width: 400px; max-width: 90vw;"):
            ui.label("Delete rule").classes("text-2xl font-bold")
            ui.label(f'Are you sure you want to delete rule "{rule["name"]}"?').classes(
                "text-body1"
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Delete").classes("delete-style").props("color=red flat").on(
                    "click",
                    lambda: (
                        _do_delete_rule(rule["id"]),
                        dialog.close(),
                        ui.navigate.to("/admin/rules"),
                    ),
                )
        dialog.open()


def _do_delete_rule(rule_id: int) -> None:
    """
    Helper to delete a rule.
    """

    if rule_delete(rule_id):
        log_action("delete_rule")
        ui.notify("Rule deleted.", color="positive")
    else:
        ui.notify("Failed to delete rule.", color="negative")


def add_attribute_dialog() -> None:
    """
    Show a dialog to add a new onboarding attribute.
    """

    with ui.dialog() as dialog:
        with ui.card().style("width: 450px; max-width: 90vw;"):
            ui.label("Add provisioning attribute").classes("text-2xl font-bold")
            name_input = ui.input("Attribute name").classes("w-full").props("outlined")
            desc_input = ui.input("Description").classes("w-full").props("outlined")
            example_input = (
                ui.input("Example value").classes("w-full").props("outlined")
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Add").classes("default-style").props("color=black flat").on(
                    "click",
                    lambda: (
                        _do_add_attribute(
                            name_input.value,
                            desc_input.value,
                            example_input.value,
                        ),
                        dialog.close(),
                        ui.navigate.to("/admin/rules"),
                    ),
                )
        dialog.open()


def _do_add_attribute(name: str, description: str, example: str) -> None:
    """
    Helper to add an onboarding attribute.
    """

    result = attribute_create(
        {"name": name, "description": description, "example": example}
    )

    if result:
        log_action("create_attribute")
        ui.notify("Attribute added.", color="positive")
    else:
        ui.notify("Failed to add attribute. It may already exist.", color="negative")


def _evaluate_condition(condition: str, actual_value: str, expected_value: str) -> bool:
    """
    Evaluate a rule condition against an actual attribute value.
    For list-type attributes (comma-separated), check if any item matches.
    """

    values = [v.strip() for v in actual_value.split(",")]

    for val in values:
        if condition == "equals" and val == expected_value:
            return True
        if condition == "not_equals" and val != expected_value:
            return True
        if condition == "contains" and expected_value in val:
            return True
        if condition == "not_contains" and expected_value not in val:
            return True
        if condition == "starts_with" and val.startswith(expected_value):
            return True
        if condition == "ends_with" and val.endswith(expected_value):
            return True
        if condition == "regex_match":
            try:
                if re.search(expected_value, val):
                    return True
            except re.error:
                return False

    return False


def test_rules_dialog(selected_rules: list[dict]) -> None:
    """
    Show a dialog where the user enters a value and tests it against the rule.
    The rule already defines which attribute and condition to use.
    For list-type values (e.g. affiliations), enter items separated by commas.
    """

    rule = selected_rules[0]
    attr_name = rule.get("attribute_name", "")
    condition = rule.get("attribute_condition", "")
    expected = rule.get("attribute_value", "")
    cond_label = CONDITION_OPTIONS.get(condition, condition)

    with ui.dialog() as dialog, ui.card().style("min-width: 600px; max-width: 800px;"):
        ui.label("Test rule").classes("text-xl font-bold")
        ui.label(f"{rule.get('name', '')}").classes("text-grey-7")
        ui.label(
            f"{attr_name} {cond_label} \"{expected}\""
        ).classes("text-grey-7 text-sm")

        ui.separator()

        test_input = ui.input(
            label=f"Value for {attr_name}",
            placeholder="For lists, separate with commas",
        ).classes("w-full").on("keydown.enter", lambda: run_test())

        result_container = ui.column().classes("w-full mt-2")

        def run_test() -> None:
            result_container.clear()
            actual = test_input.value or ""

            matched = _evaluate_condition(condition, actual, expected)

            with result_container:
                if matched:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("check_circle", color="positive").classes("text-lg")
                        ui.label("Match!").classes("text-positive font-bold")
                else:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("cancel", color="negative").classes("text-lg")
                        ui.label("No match.").classes("text-negative")

        with ui.row().classes("w-full justify-end mt-4 gap-2"):
            ui.button("Test", icon="science", on_click=run_test).props("color=primary")
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


def test_all_rules_dialog() -> None:
    """
    Show a dialog where the user enters attribute name/value pairs and
    simulates provisioning against all enabled rules.
    """

    rules_data = rules_get()
    all_rules = rules_data.get("result", []) if rules_data else []
    enabled_rules = [r for r in all_rules if r.get("enabled")]

    onboarding_attrs = attributes_get()
    attr_names = [a["name"] for a in onboarding_attrs] if onboarding_attrs else []

    all_groups = groups_get()
    group_names: dict[int, str] = {}
    if all_groups and "result" in all_groups:
        group_names = {g["id"]: g["name"] for g in all_groups["result"]}

    with ui.dialog() as dialog, ui.card().style("min-width: 600px; max-width: 800px;"):
        ui.label("Simulate provisioning").classes("text-xl font-bold")
        ui.label(
            "Enter attribute values to simulate what would happen when a user logs in."
        ).classes("text-grey-7")

        ui.separator()

        attr_rows: list[dict] = []
        attrs_container = ui.column().classes("w-full gap-2")

        def add_attr_row(name: str | None = None, value: str = "") -> None:
            row = {}
            with attrs_container:
                with ui.row().classes("w-full items-center gap-2") as row_el:
                    row["element"] = row_el
                    row["name"] = ui.select(
                        attr_names,
                        label="Attribute",
                        value=name,
                        with_input=True,
                        new_value_mode="add",
                    ).classes("w-1/3")
                    row["value"] = ui.input(
                        label="Value",
                        value=value,
                        placeholder="For lists, separate with commas",
                    ).classes("flex-grow").on("keydown.enter", lambda: run_test())
                    ui.button(
                        icon="close",
                        on_click=lambda r=row: remove_attr_row(r),
                    ).props("flat round dense color=grey-6 size=sm")
            attr_rows.append(row)

        def remove_attr_row(row: dict) -> None:
            if len(attr_rows) <= 1:
                return
            attrs_container.remove(row["element"])
            attr_rows.remove(row)

        add_attr_row()

        ui.button(
            "Add attribute", icon="add", on_click=lambda: add_attr_row()
        ).props("flat dense color=primary")

        result_container = ui.column().classes("w-full mt-2")

        def run_test() -> None:
            result_container.clear()

            user_attrs = {}
            for row in attr_rows:
                name = row["name"].value
                value = row["value"].value
                if name and value:
                    user_attrs[name] = value

            if not user_attrs:
                with result_container:
                    ui.label("Enter at least one attribute and value.").classes(
                        "text-negative"
                    )
                return

            matched_rules = []
            unmatched_rules = []

            for rule in enabled_rules:
                attr_name = rule.get("attribute_name", "")
                condition = rule.get("attribute_condition", "")
                expected = rule.get("attribute_value", "")

                actual = user_attrs.get(attr_name)
                if actual is not None and _evaluate_condition(
                    condition, actual, expected
                ):
                    matched_rules.append(rule)
                else:
                    unmatched_rules.append(rule)

            with result_container:
                for rule in matched_rules:
                    cond_label = CONDITION_OPTIONS.get(
                        rule.get("attribute_condition", ""),
                        rule.get("attribute_condition", ""),
                    )
                    actions = []
                    if rule.get("activate"):
                        actions.append("Activate")
                    if rule.get("deny"):
                        actions.append("Deactivate")
                    if rule.get("assign_to_group"):
                        actions.append("Assign to group")
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("check_circle", color="positive").classes("text-lg")
                        ui.label(f"{rule.get('name', '')}").classes(
                            "text-positive font-bold"
                        )
                        ui.label(
                            f'{rule.get("attribute_name")} {cond_label} '
                            f'"{rule.get("attribute_value")}"'
                        ).classes("text-grey-7 text-sm")
                    if actions:
                        ui.label(
                            f"Actions: {', '.join(actions)}"
                        ).classes("text-body2 text-grey-8 ml-8")

                for rule in unmatched_rules:
                    cond_label = CONDITION_OPTIONS.get(
                        rule.get("attribute_condition", ""),
                        rule.get("attribute_condition", ""),
                    )
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("cancel", color="negative").classes("text-lg")
                        ui.label(f"{rule.get('name', '')}").classes("text-negative")
                        ui.label(
                            f'{rule.get("attribute_name")} {cond_label} '
                            f'"{rule.get("attribute_value")}"'
                        ).classes("text-grey-7 text-sm")

                if not matched_rules and not unmatched_rules:
                    ui.label("No enabled rules to test.").classes("text-grey-7")

                # Final provisioning result summary
                ui.separator().classes("my-2")
                ui.label("Simulated result").classes("font-bold")
                if not matched_rules:
                    ui.label("None").classes("text-grey-7")
                else:
                    will_activate = any(r.get("activate") for r in matched_rules)
                    will_deny = any(r.get("deny") for r in matched_rules)
                    # Last matching rule with a group wins
                    final_group = None
                    for r in matched_rules:
                        grp = r.get("assign_to_group")
                        if grp:
                            try:
                                final_group = int(grp)
                            except (ValueError, TypeError):
                                pass

                    results = []
                    if will_deny:
                        results.append("User deactivated")
                    elif will_activate:
                        results.append("User activated")
                    if final_group and final_group in group_names:
                        results.append(
                            f"User assigned to group: {group_names[final_group]}"
                        )
                    if results:
                        for r in results:
                            ui.label(r)
                    else:
                        ui.label("None").classes("text-grey-7")

        with ui.row().classes("w-full justify-end mt-4 gap-2"):
            ui.button("Simulate", icon="science", on_click=run_test).props(
                "color=primary"
            )
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


def _show_rules_help() -> None:
    """
    Show a help dialog explaining how onboarding rules work.
    """

    with ui.dialog() as dialog, ui.card().style(
        "min-width: 550px; max-width: 700px; padding: 32px;"
    ):
        ui.label("How provisioning rules work").classes("text-2xl font-bold mb-4")

        with ui.column().classes("gap-4"):
            ui.label(
                "Provisioning rules automatically update user accounts based on "
                "attributes received at login. "
                "Rules are evaluated each time a user logs in."
            ).classes("text-body1")

            ui.separator()

            with ui.column().classes("gap-1"):
                ui.label("Rule matching").classes("text-lg font-semibold")
                ui.label(
                    "Each rule specifies an attribute name (for example "
                    "preferred_username, email, or domain), a condition (such as "
                    "equals, contains or starts with), and a value to compare against. "
                    "If the condition matches the user's attribute value, the rule's "
                    "actions are applied."
                ).classes("text-body2 text-grey-8")

            with ui.column().classes("gap-1"):
                ui.label("Available actions").classes("text-lg font-semibold")
                with ui.column().classes("gap-0 pl-2"):
                    for action, desc in [
                        ("Activate", "Automatically activate the user account."),
                        ("Deactivate", "Prevent the user from accessing the service."),
                        (
                            "Assign user to group",
                            "Place the user in a specific group.",
                        ),
                    ]:
                        with ui.row().classes("items-start gap-2"):
                            ui.label(f"• {action}").classes(
                                "text-body2 font-medium"
                            ).style("min-width: 140px;")
                            ui.label(f"— {desc}").classes("text-body2 text-grey-8")

            with ui.column().classes("gap-1"):
                ui.label("Scoping").classes("text-lg font-semibold")
                ui.label(
                    "The Realm field limits which login domains the rule applies to. "
                    "Local administrators can only create rules for the realms "
                    "assigned to their account."
                ).classes("text-body2 text-grey-8")

            with ui.column().classes("gap-1"):
                ui.label("Rule evaluation").classes("text-lg font-semibold")
                ui.label(
                    "All enabled rules are evaluated on every login. "
                    "If rules conflict:"
                ).classes("text-body2 text-grey-8")
                with ui.column().classes("gap-0 pl-2"):
                    for line in [
                        "Deactivate always wins over Activate.",
                        "For group assignment, the last matching rule wins. "
                        "A user can only belong to one group.",
                    ]:
                        ui.label(f"• {line}").classes("text-body2 text-grey-8")

            with ui.column().classes("gap-1"):
                ui.label("Manual override").classes("text-lg font-semibold")
                ui.label(
                    "If an administrator manually deactivates a user, provisioning "
                    "rules that would activate that user will not automatically "
                    "override that decision. "
                    "The user will remain deactivated until an administrator "
                    "reactivates the account."
                ).classes("text-body2 text-grey-8")

            with ui.column().classes("gap-1"):
                ui.label("Testing").classes("text-lg font-semibold")
                ui.label(
                    "Use the Test button on each rule to check whether a value would "
                    "match the rule. Enter the value you want to test against the "
                    "rule's attribute and condition. "
                    "For list-type attributes (for example affiliations), enter "
                    "multiple values separated by commas."
                ).classes("text-body2 text-grey-8")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


@ui.page("/admin/rules")
def rules_page() -> None:
    """
    Onboarding management page.
    """

    page_init(use_drawer=True)

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #ffffff;
            }
        </style>
        """
    )

    with ui.row().style(
        "justify-content: space-between; align-items: center; width: 100%;"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.label("User provisioning").classes("text-3xl font-bold")
            ui.button(icon="help_outline").props("flat round dense color=grey-7").on(
                "click", lambda: _show_rules_help()
            )
        with ui.element("div").style("display: flex; gap: 10px;"):
            ui.button("Add rule").classes("default-style").props(
                "color=black flat"
            ).style("min-width: 160px;").on(
                "click", lambda: create_rule_dialog(page=rules_page)
            )
            ui.button("Simulate provisioning").classes(
                "default-style"
            ).props("color=black flat").style("min-width: 160px; background-color: white;").on(
                "click", lambda: test_all_rules_dialog()
            )

    ui.label(
        "Rules are evaluated on every login. "
        "Deactivate overrides Activate. "
        "The last matching rule determines the user's group."
    ).classes("text-body2 text-black")

    rules_data = rules_get()
    rules_list = rules_data.get("result", []) if rules_data else []

    if not rules_list:
        ui.label("No provisioning rules defined yet.").classes("text-lg mt-4")
    else:
        for idx, rule in enumerate(rules_list):
            rule["_idx"] = idx
            actions = []
            if rule.get("activate"):
                actions.append("Activate")
            if rule.get("admin"):
                actions.append("Admin")
            if rule.get("deny"):
                actions.append("Deactivate")
            if rule.get("assign_to_group"):
                actions.append("Group")
            rule["actions_summary"] = ", ".join(actions) if actions else "None"
            rule["enabled_label"] = "Yes" if rule.get("enabled") else "No"
            cond = rule.get("attribute_condition", "")
            rule["condition_label"] = CONDITION_OPTIONS.get(cond, cond)

        rules_table = ui.table(
            columns=[
                {
                    "name": "name",
                    "label": "Name",
                    "field": "name",
                    "align": "left",
                    "sortable": True,
                },
                {
                    "name": "attribute_name",
                    "label": "Attribute",
                    "field": "attribute_name",
                    "align": "left",
                    "sortable": True,
                },
                {
                    "name": "condition_label",
                    "label": "Condition",
                    "field": "condition_label",
                    "align": "left",
                    "sortable": True,
                },
                {
                    "name": "attribute_value",
                    "label": "Value",
                    "field": "attribute_value",
                    "align": "left",
                    "sortable": True,
                },
                {
                    "name": "actions_summary",
                    "label": "Actions",
                    "field": "actions_summary",
                    "align": "left",
                },
                {
                    "name": "enabled_label",
                    "label": "Enabled",
                    "field": "enabled_label",
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
                    "name": "row_actions",
                    "label": "",
                    "field": "row_actions",
                    "align": "right",
                    "sortable": False,
                },
            ],
            rows=rules_list,
            row_key="id",
            pagination=20,
        ).style("width: 100%; box-shadow: none; font-size: 18px;")

        with rules_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                rules_table, "filter"
            ).add_slot("append"):
                ui.icon("search")

        rules_table.add_slot(
            "body-cell-enabled_label",
            r"""
            <q-td :props="props">
                <q-toggle
                    :model-value="props.row.enabled"
                    @update:model-value="val => $parent.$emit('toggle_enabled', {id: props.row.id, enabled: val})"
                    color="positive"
                    dense
                />
            </q-td>
            """,
        )

        def handle_toggle(msg) -> None:
            rule_id = msg.args["id"]
            new_enabled = msg.args["enabled"]
            result = rule_update(rule_id, {"enabled": new_enabled})
            if result:
                log_action("toggle_rule")
                ui.notify(
                    f"Rule {'enabled' if new_enabled else 'disabled'}.",
                    color="positive",
                )
                ui.navigate.to("/admin/rules")
            else:
                ui.notify("Failed to update rule.", color="negative")

        rules_table.on("toggle_enabled", handle_toggle)

        rules_table.add_slot(
            "body-cell-name",
            r"""
            <q-td :props="props">
                <a
                    class="cursor-pointer text-primary"
                    @click="$parent.$emit('edit_rule', props.row)"
                    style="text-decoration: underline;"
                >
                    {{ props.row.name }}
                </a>
            </q-td>
            """,
        )

        def handle_edit(msg) -> None:
            rule = msg.args
            edit_rule_dialog(rule, page=rules_page)

        rules_table.on("edit_rule", handle_edit)
        rules_table.add_slot(
            "body-cell-row_actions",
            r"""
            <q-td :props="props">
                <q-btn flat dense round icon="science" color="primary" size="sm"
                    @click="$parent.$emit('test_rule', props.row)"
                >
                    <q-tooltip>Test rule</q-tooltip>
                </q-btn>
                <q-btn flat dense round icon="delete" color="negative" size="sm"
                    @click="$parent.$emit('delete_rule', props.row)"
                >
                    <q-tooltip>Delete rule</q-tooltip>
                </q-btn>
            </q-td>
            """,
        )

        def handle_test(msg) -> None:
            test_rules_dialog([msg.args])

        def handle_delete(msg) -> None:
            delete_rule_dialog(msg.args)

        rules_table.on("test_rule", handle_test)
        rules_table.on("delete_rule", handle_delete)

    if get_bofh_status():
        ui.separator().classes("mt-6 mb-4")
        with ui.row().style(
            "justify-content: space-between; align-items: center; width: 100%;"
        ):
            ui.label("Attributes (BOFH)").classes("text-2xl font-bold")
            ui.button("Add attribute").classes("default-style").props(
                "color=black flat"
            ).style("min-width: 160px;").on("click", lambda: add_attribute_dialog())

        ui.label(
            "These are the known attribute names available when creating rules."
        ).classes("text-body2 text-grey-7 mb-2")

        attrs = attributes_get()
        if not attrs:
            ui.label("No attributes defined.").classes("text-lg")
        else:
            attrs_table = ui.table(
                columns=[
                    {
                        "name": "name",
                        "label": "Claim name",
                        "field": "name",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "description",
                        "label": "Description",
                        "field": "description",
                        "align": "left",
                    },
                    {
                        "name": "example",
                        "label": "Example",
                        "field": "example",
                        "align": "left",
                    },
                    {
                        "name": "attr_actions",
                        "label": "",
                        "field": "attr_actions",
                        "align": "right",
                        "sortable": False,
                    },
                ],
                rows=attrs,
                row_key="id",
                pagination=20,
            ).style("width: 100%; box-shadow: none; font-size: 18px;")

            attrs_table.add_slot(
                "body-cell-attr_actions",
                r"""
                <q-td :props="props">
                    <q-btn flat dense round icon="delete" color="negative" size="sm"
                        @click="$parent.$emit('delete_attr', props.row)"
                    >
                        <q-tooltip>Delete attribute</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )

            def handle_delete_attr(msg) -> None:
                _do_delete_attribute(msg.args)

            attrs_table.on("delete_attr", handle_delete_attr)


def _do_delete_attribute(attr: dict) -> None:
    """
    Delete a single onboarding attribute.
    """

    attribute_delete(attr["id"])

    log_action("delete_attribute")
    ui.notify(f"Deleted attribute '{attr['name']}'.", color="positive")
    ui.navigate.to("/admin/rules")


@ui.page("/admin/analytics")
def analytics() -> None:
    """
    Page view analytics dashboard. BOFH only.
    """

    page_init(use_drawer=True)

    if not get_bofh_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)
    ui.add_head_html("<style>body { background-color: #ffffff; }</style>")

    ui.label("Activity overview").classes("text-3xl font-bold mb-4")

    stats = get_total_stats()
    wow = get_week_over_week()

    if wow["change_pct"] is not None:
        sign = "+" if wow["change_pct"] >= 0 else ""
        wow_color = "#2e7d32" if wow["change_pct"] >= 0 else "#c62828"
        wow_display = f'{sign}{wow["change_pct"]}%'
    else:
        wow_color = "#757575"
        wow_display = "N/A"

    summary = get_page_views_summary()

    action_summary = [r for r in summary if r["path"].startswith("/action/")]
    action_labels = {
        "/action/upload": ("Uploads", "upload_file", "#2e7d32"),
        "/action/transcription": ("Transcriptions", "record_voice_over", "#1565c0"),
        "/action/bulk_transcription": (
            "Bulk Transcriptions",
            "dynamic_feed",
            "#6a1b9a",
        ),
        "/action/export": ("Exports", "download", "#e65100"),
        "/action/bulk_export": ("Bulk Exports", "folder_zip", "#00695c"),
        "/action/create_group": ("Groups Created", "group_add", "#00838f"),
        "/action/edit_group": ("Groups Edited", "edit", "#4527a0"),
        "/action/delete_group": ("Groups Deleted", "group_remove", "#b71c1c"),
        "/action/remove_user": ("Users Removed", "person_remove", "#c62828"),
        "/action/activate_user": ("Users Activated", "person_add", "#2e7d32"),
        "/action/deactivate_user": ("Users Deactivated", "person_off", "#e65100"),
        "/action/set_admin": ("Admin Granted", "admin_panel_settings", "#1565c0"),
        "/action/remove_admin": ("Admin Revoked", "remove_moderator", "#bf360c"),
        "/action/set_domains": ("Domains Updated", "domain", "#6a1b9a"),
    }
    action_map = {r["path"]: r for r in action_summary}

    # Peak hours heatmap + hourly distribution
    with ui.row().classes("w-full gap-4 q-mt-lg"):
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Peak hours (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )
            heatmap_data = get_hourly_heatmap(days=30)

            if heatmap_data:
                day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                hours = list(range(24))
                # Build a 7x24 matrix (rows=days, cols=hours)
                matrix = [[0] * 24 for _ in range(7)]
                for r in heatmap_data:
                    # PostgreSQL dow: 0=Sun, 1=Mon..6=Sat -> remap to Mon=0..Sun=6
                    day_idx = (r["dow"] - 1) % 7
                    matrix[day_idx][r["hour"]] = r["views"]

                fig = go.Figure(
                    data=go.Heatmap(
                        z=matrix,
                        x=[f"{h:02d}:00" for h in hours],
                        y=day_names,
                        colorscale=[
                            [0, "#f5f5f5"],
                            [0.25, "#bbdefb"],
                            [0.5, "#42a5f5"],
                            [0.75, "#1565c0"],
                            [1, "#0d47a1"],
                        ],
                        hovertemplate="Day: %{y}<br>Hour: %{x}<br>Views: %{z}<extra></extra>",
                        showscale=True,
                        colorbar=dict(title="Views", thickness=15),
                        xgap=2,
                        ygap=2,
                        texttemplate="%{z}",
                        textfont=dict(size=10),
                    )
                )
                fig.update_layout(
                    template="plotly_white",
                    height=350,
                    margin=dict(l=50, r=20, t=20, b=40),
                    xaxis_title="Hour of Day",
                    xaxis=dict(dtick=1),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Hourly distribution (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )
            hourly = get_hourly_distribution(days=30)

            if hourly:
                # Fill missing hours with 0
                hourly_map = {r["hour"]: r["views"] for r in hourly}
                all_hours = list(range(24))
                all_views = [hourly_map.get(h, 0) for h in all_hours]

                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=[f"{h:02d}:00" for h in all_hours],
                        y=all_views,
                        marker_color="#1565c0",
                    )
                )
                fig.update_layout(
                    xaxis_title="Hour of Day",
                    yaxis_title="Views",
                    template="plotly_white",
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

    # Charts
    with ui.row().classes("w-full gap-4 q-mt-lg"):
        # Line chart: page views per day per path
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Page views per day (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )
            page_views = get_page_views(days=30)

            if page_views:
                by_path = defaultdict(lambda: {"dates": [], "views": []})
                for row in page_views:
                    by_path[row["path"]]["dates"].append(row["date"])
                    by_path[row["path"]]["views"].append(row["views"])

                fig = go.Figure()
                for path, data in sorted(by_path.items()):
                    fig.add_trace(
                        go.Scatter(
                            x=data["dates"],
                            y=data["views"],
                            mode="lines+markers",
                            name=path,
                        )
                    )
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Views",
                    template="plotly_white",
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

        # Bar chart: total views per page
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Total views per page").classes("text-h6 font-semibold q-mb-md")
            if summary:
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=[r["path"] for r in summary],
                        y=[r["total_views"] for r in summary],
                        name="All Time",
                        marker_color="#082954",
                    )
                )
                fig.add_trace(
                    go.Bar(
                        x=[r["path"] for r in summary],
                        y=[r["views_30d"] for r in summary],
                        name="Last 30 Days",
                        marker_color="#4caf50",
                    )
                )
                fig.update_layout(
                    barmode="group",
                    xaxis_title="Page",
                    yaxis_title="Views",
                    template="plotly_white",
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

    # Daily traffic chart + recent views table
    with ui.row().classes("w-full gap-4 q-mt-lg items-stretch"):
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Total traffic per day (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )
            daily = get_views_per_day(days=30)

            if daily:
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=[r["date"] for r in daily],
                        y=[r["views"] for r in daily],
                        marker_color="#082954",
                    )
                )
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Page Views",
                    template="plotly_white",
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Last visited pages").classes("text-h6 font-semibold q-mb-md")
            recent = get_recent_views(limit=50)

            if recent:
                columns = [
                    {"name": "path", "label": "Page", "field": "path", "align": "left"},
                    {
                        "name": "timestamp",
                        "label": "Time",
                        "field": "timestamp",
                        "align": "left",
                    },
                ]
                ui.table(
                    columns=columns,
                    rows=recent,
                    row_key="timestamp",
                ).classes(
                    "w-full table-style"
                ).props("dense").style("max-height: 350px;")
            else:
                ui.label("No data yet.").classes("text-grey-6")

    # Action charts
    with ui.row().classes("w-full gap-4 q-mt-lg"):
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Actions per day (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )
            action_views = [
                r for r in get_page_views(days=30) if r["path"].startswith("/action/")
            ]

            if action_views:
                by_action = defaultdict(lambda: {"dates": [], "views": []})
                for row in action_views:
                    action_name = row["path"].replace("/action/", "")
                    by_action[action_name]["dates"].append(row["date"])
                    by_action[action_name]["views"].append(row["views"])

                fig = go.Figure()
                for action_name, data in sorted(by_action.items()):
                    fig.add_trace(
                        go.Bar(
                            x=data["dates"],
                            y=data["views"],
                            name=action_name,
                        )
                    )
                fig.update_layout(
                    barmode="stack",
                    xaxis_title="Date",
                    yaxis_title="Count",
                    template="plotly_white",
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No action data yet.").classes("text-grey-6")

        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Total actions by type").classes("text-h6 font-semibold q-mb-md")

            if action_summary:
                action_names = [
                    r["path"].replace("/action/", "") for r in action_summary
                ]
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=action_names,
                        y=[r["total_views"] for r in action_summary],
                        name="All Time",
                        marker_color="#082954",
                    )
                )
                fig.add_trace(
                    go.Bar(
                        x=action_names,
                        y=[r["views_30d"] for r in action_summary],
                        name="Last 30 Days",
                        marker_color="#4caf50",
                    )
                )
                fig.update_layout(
                    barmode="group",
                    xaxis_title="Action",
                    yaxis_title="Count",
                    template="plotly_white",
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No action data yet.").classes("text-grey-6")

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

from datetime import date, timedelta

import httpx

from nicegui import ui
from utils.common import add_timezone_to_timestamp, page_init, reload_on_theme_change
from utils.styles import default_styles
from utils.bar_chart import NBSP, amount, bar_chart, decimals_for, month_days, month_name, rounded
from utils.chart_tables import chart_section, head_html as chart_head, minutes_summary
from utils.helpers import (
    groups_get,
    save_group,
    set_admin_status,
    open_make_admin_dialog,
    user_statistics_get,
)
from utils.settings import get_settings
from utils.token import (
    get_auth_header,
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

            def do_create() -> None:
                # int(quota.value) raised a bare, unshown ValueError on
                # anything int() rejects -- a decimal, or the field left
                # empty -- and min=0 in props is decorative only, not
                # enforced. The user saw the dialog simply not close, with
                # no indication why (3.3.1).
                try:
                    quota_seconds = int(quota.value) * 60 if quota.value else 0
                except ValueError:
                    quota.props(
                        'error error-message="Monthly transcription limit '
                        'must be a whole number of minutes."'
                    )
                    quota.run_method("focus")
                    return
                quota.props(remove="error error-message")

                httpx.post(
                    settings.API_URL + "/api/v1/admin/groups",
                    headers=get_auth_header(),
                    json={
                        "name": name_input.value,
                        "description": description_input.value,
                        "quota_seconds": quota_seconds,
                    },
                )
                create_group_dialog.close()
                ui.navigate.to("/admin")

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: create_group_dialog.close())
                ui.button("Create").classes("default-style").props(
                    "color=black flat"
                ).on("click", do_create)

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

            # Quasar generates selection checkboxes from selection="multiple"
            # with no accessible name at all -- both the header "select all"
            # and each row's own checkbox are announced only as "checkbox".
            # These slots keep Quasar's own default selection behaviour
            # (v-model="props.selected") and add nothing but a name.
            admin_table.add_slot(
                "header-selection",
                """
                <q-checkbox v-model="props.selected" aria-label="Select all administrators" />
                """,
            )
            admin_table.add_slot(
                "body-selection",
                """
                <q-checkbox v-model="props.selected" :aria-label="'Select ' + props.row.username" />
                """,
            )

            with admin_table.add_slot("top-right"):
                with ui.input(placeholder="Search").props('type=search aria-label="Search administrators"').bind_value(
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
async def edit_group(group_id: str) -> None:
    """
    Page to edit a group.
    """
    user_data = await page_init(use_drawer=True, title="Edit group")
    # Plotly draws its charts in one theme's colours server-side and
    # cannot restyle itself, so this page reloads when the OS theme
    # changes. Only pages with charts do -- see reload_on_theme_change.
    reload_on_theme_change()

    if not (user_data or {}).get("admin"):
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
        ui.label(f"Edit group: {group['name']}").classes("text-3xl font-bold").props("role=heading aria-level=1")
        with ui.element("div").style("display: flex; gap: 8px;"):
            def do_save() -> None:
                # save_group's own int(quota_seconds) has the same unshown
                # ValueError as create_group_dialog's copy above -- see its
                # comment. Fixed the same way, against the field defined
                # further down (quota is still in scope by the time this
                # runs: the click can only happen once the whole page body,
                # quota included, has been built).
                try:
                    int(quota.value) if quota.value else 0
                except ValueError:
                    quota.props(
                        'error error-message="Monthly transcription limit '
                        'must be a whole number of minutes."'
                    )
                    quota.run_method("focus")
                    return
                quota.props(remove="error error-message")

                save_group(
                    users_table.selected,
                    name_input.value,
                    description_input.value,
                    group_id,
                    quota.value,
                )

            ui.button("Save group").classes("default-style").props(
                "color=black flat"
            ).style("width: 150px").on("click", do_save)
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

        # Quasar generates selection checkboxes from selection="multiple"
        # with no accessible name at all -- both the header "select all" and
        # each row's own checkbox are announced only as "checkbox". These
        # slots keep Quasar's own default selection behaviour
        # (v-model="props.selected") and add nothing but a name.
        users_table.add_slot(
            "header-selection",
            """
            <q-checkbox v-model="props.selected" aria-label="Select all group members" />
            """,
        )
        users_table.add_slot(
            "body-selection",
            """
            <q-checkbox v-model="props.selected" :aria-label="'Select ' + props.row.username" />
            """,
        )

        users_table.selected = [
            user for user in group["users"] if user.get("in_group", True)
        ]

        with users_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props('type=search aria-label="Search group members"').bind_value(
                users_table, "filter"
            ).add_slot("append"):
                ui.icon("search")


@ui.refreshable
@ui.page("/admin/stats/{group_id}")
async def statistics(group_id: str) -> None:
    """
    Page to show statistics of a group with improved layout and design.
    """
    user_data = await page_init(use_drawer=True, title="Group statistics")
    # The charts are drawn by the page in the theme's own custom properties
    # (utils/bar_chart.py), so a change of theme needs no reload here.

    if not (user_data or {}).get("admin"):
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)
    ui.add_head_html(chart_head())

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

    def files(count) -> str:
        return f"{count}{NBSP}file" if count == 1 else f"{count}{NBSP}files"

    # The months by name, from the days the figures are for (or today):
    # "this month" says less in a list of headings, and nothing once the
    # page has been left open past the turn of a month.
    def first_day(days: list, fallback: date) -> date:
        try:
            return date.fromisoformat(days[0])
        except (IndexError, ValueError):
            return fallback

    today = date.today()
    this_month = month_days(per_day.keys(), today)
    this_first = first_day(this_month, today.replace(day=1))
    previous_month = month_days(per_day_previous_month.keys(), this_first - timedelta(days=1))
    this_name = month_name(this_first.isoformat())
    previous_name = month_name(first_day(previous_month, this_first - timedelta(days=1)).isoformat())

    # One precision for the page (utils/bar_chart.py, decimals_for()): a
    # decimal when its largest day is under 10 minutes, none otherwise.
    # Only what is shown is rounded; every sum is of the figures as they are.
    decimals = decimals_for(list(per_day.values()) + list(per_day_previous_month.values()))

    def minutes_of(value) -> str:
        return amount(value, decimals=decimals)

    ui.label("Group statistics").classes("text-3xl font-bold mb-4").props("role=heading aria-level=1")

    with ui.element("div").classes("stats-container w-full"):
        # The summary as cards, like the files on /home: a name, and a line
        # or two under it. A list, so it is read as three of a kind.
        tiles = (
            ("Users", [f"{total_users}{NBSP}user in the group" if total_users == 1 else f"{total_users}{NBSP}users in the group"]),
            (
                this_name,
                [
                    f"{files(result.get('transcribed_files', 0))} transcribed",
                    minutes_of(result.get("total_transcribed_minutes", 0)),
                ],
            ),
            (
                previous_name,
                [
                    f"{files(result.get('transcribed_files_last_month', 0))} transcribed",
                    minutes_of(result.get("total_transcribed_minutes_last_month", 0)),
                ],
            ),
        )

        with ui.element("div").classes("stats-card stats-summary w-full"):
            with ui.element("ul").classes("stats-tiles"):
                for title, lines in tiles:
                    with ui.element("li"):
                        with ui.card().props("flat bordered").classes("stats-tile"):
                            ui.label(title).classes("stats-tile-name")

                            for line in lines:
                                ui.label(line).classes("stats-tile-meta")

        # Each chart is a heading, a sentence, the chart as a picture and
        # the same numbers as a table (utils/chart_tables.py): a chart alone
        # cannot be read without seeing it, nor its details without a mouse.
        #
        # Both months whole, on one scale: two charts of different widths
        # and ranges read as if the months were. Days still to come this
        # month are toned, with an edge where they begin; the table has the
        # days there are.
        highest = max(
            (value or 0 for days in (per_day, per_day_previous_month) for value in days.values()),
            default=0,
        )

        for minutes, days, name, under_way in (
            (per_day, this_month, this_name, True),
            (per_day_previous_month, previous_month, previous_name, False),
        ):
            heading = f"Transcribed minutes per day, {name}"

            with ui.element("div").classes("chart-container"):
                chart_section(
                    heading,
                    minutes_summary(minutes, decimals, so_far=under_way),
                    bar_chart(
                        days,
                        [{"name": heading, "values": [minutes.get(day) for day in days]}],
                        highest=highest,
                        decimals=decimals,
                        # The days still to come, toned, this month only.
                        future_after=today.isoformat() if under_way else None,
                    ),
                    table_summary=f"Show the minutes per day for {name} as a table",
                    caption=heading,
                    headers=("Date", "Minutes"),
                    rows=[(day, rounded(value, decimals)) for day, value in minutes.items()],
                    numeric=(1,),
                    empty=not any(value and value > 0 for value in minutes.values()),
                )

        if per_user:
            with ui.element("div").classes("table-container"):
                ui.label(f"Transcribed minutes per user, {this_name}").classes(
                    "text-xl font-semibold text-theme-primary"
                ).props("role=heading aria-level=2")
                user_rows = [
                    {"username": username, "minutes": rounded(minutes, decimals), "exact": minutes or 0}
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
                        # By the figure as it is: "<1" is not a number.
                        ":sort": "(a, b, rowA, rowB) => rowA.exact - rowB.exact",
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
                    with ui.input(placeholder="Search").props('type=search aria-label="Search users"').bind_value(
                        stats_table, "filter"
                    ).add_slot("append"):
                        ui.icon("search")

        if job_queue:
            with ui.element("div").classes("table-container"):
                ui.label("Job queue for group").classes(
                    "text-2xl font-bold mb-4 text-theme-primary"
                ).props("role=heading aria-level=2")
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
                    with ui.input(placeholder="Search").props('type=search aria-label="Search job queue"').bind_value(
                        stats_table, "filter"
                    ).add_slot("append"):
                        ui.icon("search")


def create() -> None:
    @ui.refreshable
    @ui.page("/admin")
    async def admin() -> None:
        """
        Main page of the application.
        """
        user_data = await page_init(use_drawer=True, title="Groups")
        # Plotly draws its charts in one theme's colours server-side and
        # cannot restyle itself, so this page reloads when the OS theme
        # changes. Only pages with charts do -- see reload_on_theme_change.
        reload_on_theme_change()

        if not (user_data or {}).get("admin"):
            ui.navigate.to("/home")
            return

        ui.add_head_html(default_styles)

        with ui.row().style(
            "justify-content: space-between; align-items: center; width: 100%;"
        ):
            with ui.element("div").style("display: flex; gap: 0px;"):
                ui.label("Groups").classes("text-3xl font-bold").props("role=heading aria-level=1")

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

                    if (user_data or {}).get("bofh"):
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

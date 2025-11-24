import plotly.graph_objects as go
import requests

from datetime import datetime
from nicegui import ui
from utils.common import default_styles, page_init
from utils.settings import get_settings
from utils.token import get_auth_header



settings = get_settings()


def groups_get() -> list:
    """
    Fetch all groups from backend.
    """

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/groups", headers=get_auth_header()
        )
        res.raise_for_status()

        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching groups: {e}")
        return []

def user_statistics_get(group_id: str) -> dict:
    """
    Fetch user statistics for a group from backend.
    """

    try:
        res = requests.get(
            settings.API_URL + f"/api/v1/admin/groups/{group_id}/stats", headers=get_auth_header()
        )
        res.raise_for_status()

        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching user statistics: {e}")
        return {}

def priceplan_get() -> dict:
    """
    Fetch price plan information from backend.
    """

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/priceplan", headers=get_auth_header()
        )
        res.raise_for_status()

        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching price plan: {e}")
        return None

def create_group_dialog(page: callable) -> None:
    with ui.dialog() as create_group_dialog:
        with ui.card().style("width: 500px; max-width: 90vw;"):
            ui.label("Create new group").classes("text-2xl font-bold")
            name_input = ui.input("Group name").classes("w-full").props("outlined")
            description_input = (
                ui.textarea("Group description").classes("w-full").props("outlined")
            )
            quota = ui.input("Monthly transcription limit (minutes, 0 = unlimited)", value=0).classes("w-full").props("outlined type=number min=0")

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
                        create_group_dialog.close(),
                        ui.navigate.to("/admin"))
                )

        create_group_dialog.open()


class Group:
    def __init__(self, group_id: str, name: str, description: str, created_at: str, users: dict, nr_users: int, stats: dict, quota_seconds: int) -> None:
        self.group_id = group_id
        self.name = name
        self.description = description
        self.created_at = created_at.split(".")[0]
        self.users = users
        self.nr_users = nr_users
        self.stats = stats
        self.quota_seconds = quota_seconds

    def edit_group(self) -> None:
        ui.navigate.to(f"/admin/edit/{self.group_id}")

    def delete_group_dialog(self) -> None:
        with ui.dialog() as delete_group_dialog:
            with ui.card().style("width: 400px; max-width: 90vw;"):
                ui.label("Delete group").classes("text-2xl font-bold")
                ui.label("Are you sure you want to delete this group? This action cannot be undone.").classes("my-4")
                with ui.row().style("justify-content: flex-end; width: 100%;"):
                    ui.button("Cancel").classes("button-close").props(
                        "color=black flat"
                    ).on("click", lambda: delete_group_dialog.close())
                    ui.button("Delete").classes("button-close").props(
                        "color=red flat"
                    ).on(
                        "click",
                        lambda: (
                            requests.delete(
                                settings.API_URL + f"/api/v1/admin/groups/{self.group_id}",
                                headers=get_auth_header(),
                            ),
                            delete_group_dialog.close(),
                            ui.navigate.to("/admin")
                        ),
                    )

            delete_group_dialog.open()

    def create_card(self):
        with ui.card().classes("my-2").style("width: 100%; box-shadow: none; border: 1px solid #e0e0e0; padding: 16px;"):
            with ui.row().style(
                "justify-content: space-between; align-items: center; width: 100%;"
            ):
                with ui.column().style("flex: 0 0 auto; min-width: 25%;"):
                    ui.label(f"{self.name}").classes("text-h5 font-bold")
                    ui.label(self.description).classes("text-md")

                    if self.name != "All users":
                        ui.label(f"Created {self.created_at}").classes("text-sm text-gray-500")

                    ui.label(f"{self.nr_users} members").classes("text-sm text-gray-500")
                    ui.label(f"Monthly transcription limit: {'Unlimited' if self.quota_seconds == 0 else str(self.quota_seconds // 60) + ' minutes'}").classes("text-sm text-gray-500")
                with ui.column().style("flex: 1;"):
                    ui.label("Statistics").classes("text-h6 font-bold")

                    with ui.row().classes("w-full gap-8"):
                        with ui.column().style("min-width: 30%;"):
                            ui.label("This month").classes("font-semibold")
                            ui.label(f"Transcribed files current month: {self.stats["transcribed_files"]}").classes("text-sm")
                            ui.label(f"Transcribed minutes current month: {self.stats["total_transcribed_minutes"]}").classes("text-sm")
                        with ui.column():
                            ui.label("Last month").classes("font-semibold")
                            ui.label(f"Transcribed files last month: {self.stats["transcribed_files_last_month"]}").classes("text-sm")
                            ui.label(f"Transcribed minutes last month: {self.stats["total_transcribed_minutes_last_month"]}m").classes("text-sm")

                with ui.column().style("flex: 0 0 auto;"):

                    statistics = ui.button("Statistics").classes("button-edit").props(
                        "color=white flat"
                    ).style("width: 100%")

                    statistics.on(
                        "click",
                        lambda: ui.navigate.to(f"/admin/stats/{self.group_id}")
                    )

                    if self.name == "All users":
                        return

                    edit = ui.button("Edit").classes("button-edit").props(
                        "color=white flat"
                    ).style("width: 100%")
                    delete = ui.button("Delete").classes("button-close").props(
                        "color=black flat"
                    ).style("width: 100%")

                    edit.on(
                        "click",
                        lambda e: self.edit_group()
                    )
                    delete.on(
                        "click",
                        lambda e: self.delete_group_dialog()
                    )

def save_group(selected_rows: list, name: str, description: str, group_id: str, quota_seconds: int) -> None:
    usernames = [row["username"] for row in selected_rows]

    try:
        res = requests.put(
            settings.API_URL + f"/api/v1/admin/groups/{group_id}",
            headers=get_auth_header(),
            json={
                "name": name,
                "description": description,
                "usernames": usernames,
                "quota_seconds": int(quota_seconds) * 60,
            }
        )
        res.raise_for_status()
        ui.navigate.to("/admin")
    except requests.RequestException as e:
        ui.notify(f"Error saving group: {e}", type="negative")

def set_active_status(selected_rows: list, make_active: bool) -> None:
    """
    Set or remove active status for selected users.
    """

    for user in selected_rows:
        try:
            res = requests.put(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
                json={"active": make_active}
            )
            res.raise_for_status()
            ui.navigate.to("/admin/users")
        except requests.RequestException as e:
            ui.notify(f"Error updating active status for {user['username']}: {e}", type="negative")

def set_admin_status(selected_rows: list, make_admin: bool, dialog: ui.dialog, group_id: str) -> None:
    """
    Set or remove admin status for selected users.
    """

    for user in selected_rows:
        try:
            res = requests.put(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
                json={"admin": make_admin}
            )
            res.raise_for_status()
            dialog.close()
            ui.navigate.to(f"/admin/edit/{group_id}")
        except requests.RequestException as e:
            ui.notify(f"Error updating admin status for {user['username']}: {e}", type="negative")

def save_domains(selected_rows: list, domains: str, dialog: ui.dialog) -> None:
    """
    Save allowed domains for selected users.
    """

    for user in selected_rows:
        try:
            res = requests.put(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
                json={"admin_domains": domains}
            )
            res.raise_for_status()
            ui.navigate.to("/admin/users")
        except requests.RequestException as e:
            ui.notify(f"Error updating domains for {user['username']}: {e}", type="negative")

    dialog.close()

def set_domains(selected_rows: list) -> None:
    """
    Show a dialog with an input to set allowed domains.
    Domains should be separated by commas.
    """

    with ui.dialog() as domain_dialog:
        with ui.card().style("width: 500px; max-width: 90vw;"):
            ui.label("Set domains the user can administer").classes("text-2xl font-bold")
            domain_input = ui.textarea("Allowed domains (separated by commas)", value=selected_rows[0]["admin_domains"]).classes("w-full").props("outlined")

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: domain_dialog.close())
                ui.button("Save").classes("default-style").props(
                    "color=black flat"
                ).on(
                    "click",
                    lambda: save_domains(selected_rows, domain_input.value, domain_dialog)
                )

        domain_dialog.open()

def admin_dialog(users: list, group_id: str) -> None:
    """
    Show a dialog with a table of users and buttons to ether make users administrator or remove administrator rights.
    """

    with ui.dialog() as dialog:
        with ui.card().style("width: 600px; max-width: 90vw; height: 75%;"):
            ui.label("Administrators").classes("text-2xl font-bold")
            admin_table = ui.table(
                columns=[
                    {"name": "username", "label": "Username", "field": "username", "align": "left", "sortable": True},
                    {"name": "role", "label": "Admin", "field": "admin", "align": "left", "sortable": True},
                ],
                rows=users,
                selection="multiple",
                pagination=20,
                on_select=lambda e: None,
            ).style("width: 100%; box-shadow: none; font-size: 18px; height: calc(100vh - 500px);")

            with admin_table.add_slot("top-right"):
                with ui.input(placeholder="Search").props("type=search").bind_value(
                    admin_table, "filter"
                ).add_slot("append"):
                    ui.icon("search")

            with ui.row().style("justify-content: flex-end; width: 100%; padding-top: 16px; gap: 8px;"):
                ui.button("Close").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Make admin").classes("default-style").props(
                    "color=black flat"
                ).on(
                    "click", lambda: set_admin_status(admin_table.selected, True, dialog, group_id)
                )
                ui.button("Remove admin").classes("button-close").props(
                    "color=black flat"
                ).on(
                    "click", lambda: set_admin_status(admin_table.selected, False, dialog, group_id)
                )
        dialog.open()


@ui.refreshable
@ui.page("/admin/edit/{group_id}")
def edit_group(group_id: str) -> None:
    """
    Page to edit a group.
    """
    page_init()

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #f5f5f5;
            }
        </style>
        """
    )

    try:
        res = requests.get(
            settings.API_URL + f"/api/v1/admin/groups/{group_id}", headers=get_auth_header()
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


    with ui.card().style("width: 100%; box-shadow: none; border: 1px solid #e0e0e0; align-self: center;"):
        ui.label(f"Edit group: {group['name']}").classes("text-3xl font-bold mb-4")
        with ui.row().classes("gap-4 w-full"):
            name_input = ui.input("Group name", value=group["name"]).props("outlined").classes("w-1/3")
            description_input = (
                ui.input("Group description", value=group["description"]).props("outlined").classes("w-1/2")
            )
            quota = ui.input("Monthly transcription limit (minutes, 0 = unlimited)", value=group["quota_seconds"] // 60).props("outlined type=number min=0").classes("w-1/2")

        ui.label("Select users to be included in group:").classes("text-xl font-semibold mt-4 mb-2")

        users_table = ui.table(
            columns=[
                {"name": "username", "label": "Username", "field": "username", "align": "left", "sortable": True},
                {"name": "role", "label": "Admin", "field": "admin", "align": "left", "sortable": True},
                {"name": "active", "label": "Active", "field": "active", "align": "left", "sortable": True},
            ],
            rows=group["users"],
            selection="multiple",
            pagination=20,
            on_select=lambda e: None,
        ).style("width: 100%; box-shadow: none; font-size: 18px; height: calc(100vh - 550px);")

        users_table.selected = [user for user in group["users"] if user.get("in_group", True)]

        with users_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                users_table, "filter"
            ).add_slot("append"):
                ui.icon("search")


    with ui.footer().style("background-color: #ffffff;"):
        with ui.row().style("justify-content: flex-left; width: 100%; padding: 16px; gap: 8px;"):
            ui.button("Save group").classes("default-style").props(
                "color=black flat"
            ).style("width: 150px").on("click", lambda: save_group(users_table.selected, name_input.value, description_input.value, group_id, quota.value))
            ui.button("Administrators").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px").on("click", lambda: admin_dialog(users_table.selected, group_id))
            ui.button("Cancel").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px;").on("click", lambda: ui.navigate.to("/admin"))


@ui.refreshable
@ui.page("/admin/stats/{group_id}")
def statistics(group_id: str) -> None:
    """
    Page to show statistics of a group with improved layout and design.
    """
    page_init()

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #f5f5f5;
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
        ui.label("Error fetching statistics.").classes("text-lg text-red-500 text-center mt-6")
        return

    result = stats["result"]

    per_day = result.get("transcribed_minutes_per_day", {})
    per_day_previous_month = result.get("transcribed_minutes_per_day_last_month", {})
    per_user = result.get("transcribed_minutes_per_user", {})
    job_queue = result.get("job_queue", [])
    total_users = result.get("total_users", 0)
    total_transcribed = result.get("total_transcribed_minutes", 0)

    with ui.element("div").classes("stats-container w-full"):
        with ui.element("div").classes("stats-card w-full"):
            ui.label("Group Statistics").classes("text-3xl font-bold mb-3 text-gray-800")
            ui.label(f"Number of users: {total_users}").classes("text-lg text-gray-600")
            ui.label(f"Transcribed files this month: {result.get('transcribed_files', 0)} files").classes("text-lg text-gray-600")
            ui.label(f"Transcribed files last month: {result.get('transcribed_files_last_month', 0)} files").classes("text-lg text-gray-600")
            ui.label(f"Transcribed minutes this month: {total_transcribed:.0f} minutes").classes("text-lg text-gray-600")
            ui.label(f"Transcribed minutes last month: {result.get('total_transcribed_minutes_last_month', 0):.0f} minutes").classes("text-lg text-gray-600")

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
                ui.label("Transcribed minutes per user this month").classes("text-2xl font-bold mb-4 text-gray-800")
                user_rows = [
                    {"username": username, "minutes": f"{minutes:.1f}"}
                    for username, minutes in per_user.items()
                ]

                user_columns = [
                    {"name": "username", "label": "Username", "field": "username", "align": "left", "sortable": True},
                    {"name": "minutes", "label": "Minutes", "field": "minutes", "align": "left", "sortable": True, ":sort": "(a, b, rowA, rowB) => a - b"},
                ]

                stats_table = ui.table(
                    columns=user_columns,
                    rows=user_rows,
                    pagination=20,
                ).style("width: 100%; box-shadow: none; font-size: 16px; margin: auto; height: calc(100vh - 160px);")

                with stats_table.add_slot("top-right"):
                    with ui.input(placeholder="Search").props("type=search").bind_value(
                        stats_table, "filter"
                    ).add_slot("append"):
                        ui.icon("search")

        if job_queue:
            with ui.element("div").classes("table-container"):
                ui.label("Job queue for group").classes("text-2xl font-bold mb-4 text-gray-800")
                queue_columns = [
                    {"name": "job_id", "label": "Job ID", "field": "job_id", "align": "left", "sortable": True},
                    {"name": "username", "label": "Username", "field": "username", "align": "left", "sortable": True},
                    {"name": "status", "label": "Status", "field": "status", "align": "left", "sortable": True},
                    {"name": "created_at", "label": "Created at", "field": "created_at", "align": "left", "sortable": True},
                ]

                stats_table = ui.table(
                    columns=queue_columns,
                    rows=job_queue,
                    pagination=20,
                ).style("width: 100%; box-shadow: none; font-size: 16px; margin: auto; height: calc(100vh - 160px);")

                with stats_table.add_slot("top-right"):
                    with ui.input(placeholder="Search").props("type=search").bind_value(
                        stats_table, "filter"
                    ).add_slot("append"):
                        ui.icon("search")


def create_priceplan_card() -> None:
    """
    Create a card to display price plan information for admins.
    """
    priceplan_data = priceplan_get()
    
    if not priceplan_data:
        return
    
    try:
        result = priceplan_data.get("result", {})
        plan_type = result.get("plan_type", "Unknown")
        plan_name = result.get("plan_name", "Unknown")
        blocks_remaining = result.get("blocks_remaining")
        total_blocks = result.get("total_blocks")
        
        with ui.card().classes("my-2").style("width: 100%; box-shadow: none; border: 2px solid #082954; padding: 16px; background-color: #f8f9fa;"):
            with ui.row().style("justify-content: space-between; align-items: center; width: 100%;"):
                with ui.column().style("flex: 1;"):
                    ui.label("Current Price Plan").classes("text-h5 font-bold").style("color: #082954;")
                    ui.label(f"Plan: {plan_name}").classes("text-lg font-medium")
                    ui.label(f"Type: {plan_type}").classes("text-md")
                    
                    # Display blocks remaining if it's a fixed plan
                    if plan_type.lower() == "fixed" and blocks_remaining is not None:
                        with ui.row().classes("items-center gap-2 mt-2"):
                            ui.icon("inventory_2").classes("text-2xl").style("color: #082954;")
                            if total_blocks is not None:
                                ui.label(f"Blocks remaining: {blocks_remaining} / {total_blocks}").classes("text-lg font-semibold").style("color: #082954;")
                            else:
                                ui.label(f"Blocks remaining: {blocks_remaining}").classes("text-lg font-semibold").style("color: #082954;")
                        
                        # Add a progress bar for visual representation
                        if total_blocks is not None and total_blocks > 0:
                            percentage = (blocks_remaining / total_blocks) * 100
                            with ui.column().style("width: 100%; mt-2;"):
                                ui.linear_progress(value=percentage/100).props(f"color={'positive' if percentage > 50 else 'warning' if percentage > 20 else 'negative'}")
                                
    except (KeyError, TypeError) as e:
        print(f"Error displaying price plan: {e}")


def create() -> None:
    @ui.refreshable
    @ui.page("/admin")
    def admin() -> None:
        """
        Main page of the application.
        """
        page_init()

        ui.add_head_html(default_styles)
        ui.add_head_html(
            """
            <style>
                body {
                    background-color: #f5f5f5;
                }
            </style>
            """
        )

        with ui.footer().style("background-color: #ffffff; color: black;"):
            with ui.row().style("justify-content: flex-left; width: 100%; padding: 16px; gap: 8px;"):
                ui.link("API Documentation", settings.API_URL + "/api/docs", new_tab=True)

        with ui.row().style(
            "justify-content: space-between; align-items: center; width: 100%;"
        ):
            with ui.element("div").style("display: flex; gap: 0px;"):
                ui.label("Admin controls").classes("text-3xl font-bold")

            with ui.element("div").style("display: flex; gap: 10px;"):
                create = (
                    ui.button("Create new group")
                    .classes("default-style")
                    .props("color=black flat")
                )
                create.on("click", lambda: create_group_dialog(page=admin))
                users = (
                    ui.button("Users")
                    .classes("button-edit")
                    .props("color=white flat")
                )
                users.on("click", lambda: ui.navigate.to("/admin/users"))
                customers = (
                    ui.button("Customers")
                    .classes("button-edit")
                    .props("color=white flat")
                )
                customers.on("click", lambda: ui.navigate.to("/admin/customers"))
                groups = groups_get()

            # Display price plan information
            create_priceplan_card()

            if not groups:
                ui.label("No groups found. Create a new group to get started.").classes("text-lg")
                return
            with ui.scroll_area().style("height: calc(100vh - 160px); width: 100%;"):
                groups = sorted(
                    groups_get()["result"],
                    key=lambda x: (x["name"].lower() != "all users", x["name"].lower())
                )
                for group in groups:
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
                    g.create_card()

@ui.page("/admin/users")
def users() -> None:
    """
    Page to show all users.
    """
    page_init()

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #f5f5f5;
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

    with ui.card().style("width: 100%; box-shadow: none; border: 1px solid #e0e0e0; align-self: center;"):
        ui.label("All users").classes("text-3xl font-bold mb-4")
        users_table = ui.table(
            columns=[
                {"name": "username", "label": "Username", "field": "username", "align": "left", "sortable": True},
                {"name": "realm", "label": "Realm", "field": "realm", "align": "left", "sortable": True},
                {"name": "role", "label": "Admin", "field": "admin", "align": "left", "sortable": True},
                {"name": "domains", "label": "Domains", "field": "admin_domains", "align": "left", "sortable": False, "style": "max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;"},
                {"name": "active", "label": "Active", "field": "active", "align": "left", "sortable": True},
            ],
            rows=users,
            selection="multiple",
            pagination=20,
            on_select=lambda e: None,
        ).style("width: 100%; box-shadow: none; font-size: 18px; height: calc(100vh - 300px);")

        with users_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                users_table, "filter"
            ).add_slot("append"):
                ui.icon("search")


    with ui.footer().style("background-color: #ffffff;"):
        with ui.row().style("justify-content: flex-left; width: 100%; padding: 16px; gap: 8px;"):
            ui.button("Back to groups").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px ").on("click", lambda: ui.navigate.to("/admin"))
            ui.button("Enable").classes("default-style").props(
                "color=black flat"
            ).style("width: 150px").on(
                "click", lambda: set_active_status(users_table.selected, True)
            )
            ui.button("Disable").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px").on(
                "click", lambda: set_active_status(users_table.selected, False)
            )
            ui.button("Domains").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px").on(
                "click", lambda: set_domains(users_table.selected)
            )


@ui.page("/health")
def health() -> None:
    """
    Health check dashboard displaying backend system metrics.
    """

    page_init()

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #f5f5f5;
            }
            .card {
                background-color: white;
                border-radius: 1rem;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                padding: 1.5rem;
                width: 100%;
                max-width: 50%;
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
        </style>
        """
    )

    ui.label("System Health Overview").classes("text-2xl font-semibold mb-4")

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

        with ui.element("div").style(
            "display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; width: 100%;"
        ):
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
                    gpu_cpu_vals = [s["gpu_usage"][0]["utilization"] for s in samples if "gpu_usage" in s]
                    gpu_mem_vals = [(s["gpu_usage"][0]["memory_used"] / s["gpu_usage"][0]["memory_total"]) * 100 for s in samples if "gpu_usage" in s]

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
                            f'<span class="status-dot {status_color}"></span>{status}', sanitize=False
                        )

                    ui.separator()
                    ui.label(
                        f"Load Avg: {latest['load_avg']:.1f} | Memory Usage: {latest['memory_usage']:.1f}%"
                    ).classes("text-sm text-gray-600 mb-2")

                    fig_cpu = go.Figure()
                    fig_cpu.add_trace(
                        go.Scatter(
                            x=times,
                            y=load_vals,
                            mode="lines+markers",
                            name="Load Avg",
                            line=dict(shape="spline"),
                        )
                    )
                    fig_cpu.add_trace(
                        go.Scatter(
                            x=times,
                            y=mem_vals,
                            mode="lines+markers",
                            name="Memory %",
                            line=dict(shape="spline"),
                        )
                    )
                    fig_cpu.update_layout(
                        margin=dict(l=20, r=20, t=20, b=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5),
                        height=250,
                        template="plotly_white",
                        xaxis_title="Time",
                        yaxis_title="%",
                    )
                    ui.plotly(fig_cpu).classes("w-full h-64")

                    if "gpu_usage" in samples[-1] and samples[-1]["gpu_usage"]:
                        fig_gpu = go.Figure()
                        fig_gpu.add_trace(
                            go.Scatter(
                                x=times[-len(gpu_cpu_vals):],
                                y=gpu_cpu_vals,
                                mode="lines+markers",
                                name="GPU CPU%",
                                line=dict(shape="spline"),
                            )
                        )
                        fig_gpu.add_trace(
                            go.Scatter(
                                x=times[-len(gpu_mem_vals):],
                                y=gpu_mem_vals,
                                mode="lines+markers",
                                name="GPU RAM%",
                                line=dict(shape="spline"),
                            )
                        )

                        fig_gpu.update_layout(
                            margin=dict(l=20, r=20, t=20, b=20),
                            legend=dict(orientation="h", yanchor="bottom", y=1.1, xanchor="center", x=0.5),
                            height=250,
                            template="plotly_white",
                            xaxis_title="Time",
                            yaxis_title="%",
                        )
                        ui.plotly(fig_gpu).classes("w-full h-64")

                    ui.label(f"Last updated: {times[-1]}").classes(
                        "text-xs text-gray-400 mt-1"
                    )

    render_health()

    ui.timer(10.0, render_health.refresh)

@ui.page("/admin/customers")
def customers() -> None:
    """
    Page to show all customers.
    """
    page_init()

    ui.add_head_html(default_styles)
    ui.add_head_html(
        """
        <style>
            body {
                background-color: #f5f5f5;
            }
        </style>
        """
    )

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/customers", headers=get_auth_header()
        )
        res.raise_for_status()
        customers = res.json()["result"]

    except requests.RequestException as e:
        ui.label(f"Error fetching customers: {e}").classes("text-lg text-red-500")
        return

    with ui.card().style("width: 100%; box-shadow: none; border: 1px solid #e0e0e0; align-self: center;"):
        ui.label("All customers").classes("text-3xl font-bold mb-4")
        customers_table = ui.table(
            columns=[
                {"name": "partner_id", "label": "Partner ID", "field": "customer_id", "align": "left", "sortable": True},
                {"name": "name", "label": "Name", "field": "name", "align": "left", "sortable": True},
                {"name": "created_at", "label": "Created at", "field": "created_at", "align": "left", "sortable": True},
            ],
            rows=customers,
            pagination=20,
        ).style("width: 100%; box-shadow: none; font-size: 18px; height: calc(100vh - 300px);")

        with customers_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                customers_table, "filter"
            ).add_slot("append"):
                ui.icon("search")


    with ui.footer().style("background-color: #ffffff;"):
        with ui.row().style("justify-content: flex-left; width: 100%; padding: 16px; gap: 8px;"):
            ui.button("Back to groups").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px ").on("click", lambda: ui.navigate.to("/admin"))
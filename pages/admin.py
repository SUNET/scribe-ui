import plotly.graph_objects as go
import requests

from nicegui import ui
from utils.common import add_timezone_to_timestamp, default_styles, page_init
from utils.common import realms_get
from utils.settings import get_settings
from utils.token import get_admin_status, get_auth_header, get_bofh_status

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
                            ui.label(f"Transcribed minutes current month: {self.stats["total_transcribed_minutes"]:.0f}").classes("text-sm")
                        with ui.column():
                            ui.label("Last month").classes("font-semibold")
                            ui.label(f"Transcribed files last month: {self.stats["transcribed_files_last_month"]}").classes("text-sm")
                            ui.label(f"Transcribed minutes last month: {self.stats["total_transcribed_minutes_last_month"]:.0f}").classes("text-sm")

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

            if dialog:
                dialog.close()
                ui.navigate.to(f"/admin/edit/{group_id}")
            else:
                ui.navigate.to("/admin/users")
        except requests.RequestException as e:
            ui.notify(f"Error updating admin status for {user['username']}: {e}", type="negative")

def save_domains(selected_rows: list, domains: list, domains_str: str, dialog: ui.dialog) -> None:
    """
    Save allowed domains for selected users.
    """

    selected_domains = domains if domains else []
    new_domains = [r.strip() for r in domains_str.split(",") if r.strip()]
    all_domains = list(set(selected_domains + new_domains))
    domains_str = ",".join(all_domains)

    for user in selected_rows:
        try:
            res = requests.put(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
                json={"admin_domains": domains_str}
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

    realms = realms_get()
    domains = []
    domains_str = ""

    for user in selected_rows:
        if not user.get("admin_domains"):
            continue
        for domain in user["admin_domains"].split(","):
            if domain.strip() in realms:
                domains.append(domain.strip())
            else:
                domains_str += domain.strip() + ", "

    with ui.dialog() as domain_dialog:
        with ui.card().style("width: 500px; max-width: 90vw;"):
            ui.label("Set domains the user can administer").classes("text-2xl font-bold")
            domains_select = ui.select(
                realms,
                label="Allowed domains (existing domains)",
                multiple=True,
                value=domains
            ).classes("w-full").props("outlined")

            domains_input = ui.input(
                "Add new domains (comma-separated)", value=domains_str.strip()
            ).classes("w-full").props("outlined")

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: domain_dialog.close())
                ui.button("Save").classes("default-style").props(
                    "color=black flat"
                ).on(
                    "click",
                    lambda: save_domains(selected_rows, domains_select.value, domains_input.value, domain_dialog)
                )

        domain_dialog.open()

def admin_dialog(users: list, group_id: str) -> None:
    """
    Show a dialog with a table of users and buttons to ether make users administrator or remove administrator rights.
    """

    with ui.dialog() as dialog:
        with ui.card().style("width: 600px; max-width: 90vw; "):
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
            ).style("width: 100%; box-shadow: none; font-size: 18px;")

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
            # ui.button("Administrators").classes("button-close").props(
            #     "color=black flat"
            # ).style("width: 150px").on("click", lambda: admin_dialog(users_table.selected, group_id))
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

    # Add timezone to created_at fields in job queue
    for job in job_queue:
        job["created_at"] = add_timezone_to_timestamp(job["created_at"])

    with ui.element("div").classes("stats-container w-full"):
        with ui.element("div").classes("stats-card w-full"):
            ui.label("Group Statistics").classes("text-3xl font-bold mb-3 text-gray-800")
            ui.label(f"Number of users: {total_users}").classes("text-lg text-gray-600")
            ui.label(f"Transcribed files this month: {result.get('transcribed_files', 0)} files").classes("text-lg text-gray-600")
            ui.label(f"Transcribed files last month: {result.get('transcribed_files_last_month', 0)} files").classes("text-lg text-gray-600")
            ui.label(f"Transcribed minutes this month: {result.get('total_transcribed_minutes', 0):.0f} minutes").classes("text-lg text-gray-600")
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
                ui.label("Transcribed minutes per user this month").classes("text-gray-800")
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

                if get_bofh_status():
                    customers = (
                        ui.button("Customers")
                        .classes("button-edit")
                        .props("color=white flat")
                    )
                    customers.on("click", lambda: ui.navigate.to("/admin/customers"))
                elif get_admin_status():
                    customers = (
                        ui.button("Account")
                        .classes("button-edit")
                        .props("color=white flat")
                    )
                    customers.on("click", lambda: ui.navigate.to("/admin/customers"))
                else:
                    pass

                groups = groups_get()

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
                {"name": "groups", "label": "Groups", "field": "groups", "align": "left", "sortable": True},
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
            ui.button("Enable").classes("button-close").props(
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
            ui.button("Make admin").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px").on(
                "click", lambda: set_admin_status(users_table.selected, True, None, "")
            )
            ui.button("Remove admin").classes("button-close").props(
                "color=black flat"
            ).style("width: 150px").on(
                "click", lambda: set_admin_status(users_table.selected, False, None, "")
            )





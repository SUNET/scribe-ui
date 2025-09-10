import requests

from nicegui import ui
from datetime import datetime
from utils.common import (
    page_init,
    default_styles,
)
from utils.token import get_admin_status
from utils.settings import get_settings
from utils.token import get_auth_header


settings = get_settings()


def get_statistics() -> dict:
    """
    Get statistics from the API.
    """
    response = requests.get(
        f"{settings.API_URL}/api/v1/admin", headers=get_auth_header()
    )
    response.raise_for_status()
    data = response.json()
    return data


def format_seconds_to_duration(seconds: int) -> str:
    """
    Convert seconds to human readable duration.
    """
    if seconds == 0:
        return "0 minutes"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if remaining_seconds > 0:
        parts.append(f"{remaining_seconds}s")

    return " ".join(parts)


def format_last_login(last_login_str: str) -> str:
    """
    Format last login time to relative time.
    """
    try:
        last_login = datetime.fromisoformat(last_login_str.replace("Z", "+00:00"))
        now = datetime.now(last_login.tzinfo)
        diff = now - last_login

        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600} hours ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60} minutes ago"
        else:
            return "Just now"
    except Exception:
        return last_login_str


def get_table_data() -> list:
    table_data = []

    try:
        statistics = get_statistics()
        result = statistics.get("result", {})

        total_users = result.get("total_users", 0)
        active_users = result.get("active_users", [])
        total_transcribed_seconds = result.get("total_transcribed_seconds", 0)

        for index, user in enumerate(active_users):
            table_data.append(
                {
                    "id": index,
                    "username": user.get("username", "N/A"),
                    "realm": user.get("realm", "N/A"),
                    "active": "Yes" if user.get("active", False) else "No",
                    "admin": "Admin" if user.get("admin", False) else "User",
                    "transcribed_seconds": format_seconds_to_duration(
                        int(user.get("transcribed_seconds", 0))
                    ),
                    "last_login": format_last_login(user.get("last_login", "Never")),
                }
            )
    except Exception:
        return None

    return total_users, active_users, total_transcribed_seconds, table_data


def handle_user_action(table: ui.table, action: str) -> None:
    """
    Handle user actions: enable, disable, toggle_admin.
    """
    if not table.selected:
        ui.notify("No users selected", type="warning")
        return

    for user in table.selected:
        username = user["username"]

        match action:
            case "enable":
                json_data = {"username": username, "active": True}
            case "disable":
                json_data = {"username": username, "active": False}
            case "enable_admin":
                json_data = {"username": username, "admin": True}
            case "disable_admin":
                json_data = {"username": username, "admin": False}

        try:
            response = requests.put(
                settings.API_URL + f"/api/v1/admin/{username}",
                headers=get_auth_header(),
                json=json_data,
            )
            response.raise_for_status()
            ui.notify(f"User {username} {action}d successfully", type="positive")
        except requests.exceptions.RequestException as e:
            ui.notify(f"Error {action}ing user {username}: {e}", type="error")

    table.update_rows(get_table_data()[-1])


def create() -> None:
    @ui.refreshable
    @ui.page("/admin")
    def home() -> None:
        """
        Admin dashboard page with statistics and charts.
        """
        if not get_admin_status():
            ui.navigate.to("/home")
            return

        page_init()
        ui.add_head_html(default_styles)

        columns = [
            {
                "name": "username",
                "label": "Username",
                "field": "username",
                "align": "left",
            },
            {
                "name": "realm",
                "label": "Realm",
                "field": "realm",
                "align": "left",
            },
            {
                "name": "active",
                "label": "Active",
                "field": "active",
                "align": "left",
            },
            {
                "name": "admin",
                "label": "Role",
                "field": "admin",
                "align": "left",
            },
            {
                "name": "transcribed_seconds",
                "label": "Total Transcription Time",
                "field": "transcribed_seconds",
                "align": "left",
            },
        ]

        (
            total_users,
            active_users,
            total_transcribed_seconds,
            table_data,
        ) = get_table_data()

        with ui.tabs() as tabs:
            tabs.classes("w-full h-full")
            ui.tab("users", label="Users", icon="people")
            ui.tab("transcriptions", label="Transcriptions", icon="credit_card")

        with ui.tab_panels(tabs, value="users").classes("w-full h-full"):
            with ui.tab_panel("users").classes("w-full h-full"):
                with ui.table(
                    columns=columns,
                    rows=table_data,
                    pagination=10,
                    selection="multiple",
                ) as table:
                    table.style(
                        "width: 100%; height: calc(100vh - 350px); box-shadow: none; font-size: 18px;"
                    )

                    with table.add_slot("top-right"):
                        with ui.input(placeholder="Search users...") as search:
                            search.bind_value_to(table, "filter")
                            search.classes("q-ma-md")
                            search.style("width: 500px;")

                with ui.row().classes("w-full mt-8 justify-end"):
                    with ui.button("Enable user") as button_enable:
                        button_enable.props("color=black flat")
                        button_enable.classes("button-user-status")
                        button_enable.on(
                            "click", lambda: handle_user_action(table, "enable")
                        )

                    with ui.button("Disable user") as button_disable:
                        button_disable.props("color=black flat")
                        button_disable.classes("button-user-status")
                        button_disable.on(
                            "click", lambda: handle_user_action(table, "disable")
                        )

                    with ui.button("Make admin") as button_make_admin:
                        button_make_admin.props("color=black flat")
                        button_make_admin.classes("button-user-status")
                        button_make_admin.on(
                            "click",
                            lambda: handle_user_action(table, "enable_admin"),
                        )

                    with ui.button("Remove admin") as button_remove_admin:
                        button_remove_admin.props("color=black flat")
                        button_remove_admin.classes("button-user-status")
                        button_remove_admin.on(
                            "click",
                            lambda: handle_user_action(table, "disable_admin"),
                        )

            with ui.tab_panel("transcriptions").classes("w-full h-full"):
                statistics = get_statistics()

                with ui.row().classes("w-full"):
                    transcriptions_per_day = statistics.get("result", {}).get(
                        "transcribed_seconds_per_day", {}
                    )

                    ui.echart(
                        {
                            "tooltip": {"trigger": "axis"},
                            "xAxis": {
                                "type": "category",
                                "data": list(transcriptions_per_day.keys()),
                            },
                            "yAxis": {"type": "value"},
                            "series": [
                                {
                                    "data": list(transcriptions_per_day.values()),
                                    "type": "bar",
                                    "smooth": True,
                                }
                            ],
                            "title": {"text": "Transcribed seconds per day"},
                        }
                    ).classes("w-full h-96")

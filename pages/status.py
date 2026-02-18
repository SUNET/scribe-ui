import requests

from nicegui import ui
from utils.settings import get_settings

settings = get_settings()


def create() -> None:
    @ui.page("/.system/.status")
    def status() -> None:
        """
        Status page showing health of backend, database, and frontend.
        """

        ui.add_head_html(
            """
            <style>
                .status-card {
                    padding: 24px;
                    border-radius: 8px;
                    margin-bottom: 16px;
                }
                .status-ok {
                    background-color: #e8f5e9;
                    border-left: 4px solid #4caf50;
                }
                .status-error {
                    background-color: #ffebee;
                    border-left: 4px solid #f44336;
                }
                .status-icon {
                    font-size: 24px;
                    margin-right: 12px;
                }
            </style>
            """
        )

        with ui.column().classes("w-full items-center").style("padding: 40px;"):
            ui.label("System Status").classes("text-h4").style("margin-bottom: 32px;")

            with ui.column().style("width: 100%; max-width: 600px;"):
                with ui.row().classes("status-card status-ok items-center w-full"):
                    ui.icon("check_circle", color="green").classes("status-icon")
                    with ui.column():
                        ui.label("Frontend").classes("text-h6")
                        ui.label("Working").classes("text-body2 text-grey-7")

                backend_card = ui.row().classes("status-card items-center w-full")
                database_card = ui.row().classes("status-card items-center w-full")
                workers_card = ui.row().classes("status-card items-center w-full")

                with backend_card:
                    backend_icon = ui.icon("hourglass_empty", color="grey").classes(
                        "status-icon"
                    )
                    with ui.column():
                        ui.label("Backend").classes("text-h6")
                        backend_status = ui.label("Checking...").classes(
                            "text-body2 text-grey-7"
                        )

                with database_card:
                    database_icon = ui.icon("hourglass_empty", color="grey").classes(
                        "status-icon"
                    )
                    with ui.column():
                        ui.label("Database").classes("text-h6")
                        database_status = ui.label("Checking...").classes(
                            "text-body2 text-grey-7"
                        )

                with workers_card:
                    workers_icon = ui.icon("hourglass_empty", color="grey").classes(
                        "status-icon"
                    )
                    with ui.column():
                        ui.label("Workers").classes("text-h6")
                        workers_status = ui.label("Checking...").classes(
                            "text-body2 text-grey-7"
                        )

                async def check_status() -> None:
                    try:
                        response = requests.get(
                            f"{settings.API_URL}/api/v1/status", timeout=5
                        )
                        data = response.json()

                        if data.get("backend") == "ok":
                            backend_card.classes(remove="status-error", add="status-ok")
                            backend_icon.props("name=check_circle color=green")
                            backend_status.set_text("Working")
                        else:
                            backend_card.classes(remove="status-ok", add="status-error")
                            backend_icon.props("name=error color=red")
                            backend_status.set_text("Error")

                        if data.get("database") == "ok":
                            database_card.classes(
                                remove="status-error", add="status-ok"
                            )
                            database_icon.props("name=check_circle color=green")
                            database_status.set_text("Working")
                        else:
                            database_card.classes(
                                remove="status-ok", add="status-error"
                            )
                            database_icon.props("name=error color=red")
                            database_status.set_text("Error")

                        workers_online = data.get("workers_online", 0)

                        if data.get("workers") == "ok":
                            workers_card.classes(remove="status-error", add="status-ok")
                            workers_icon.props("name=check_circle color=green")
                            workers_status.set_text(
                                f"{workers_online} worker(s) online"
                            )
                        else:
                            workers_card.classes(remove="status-ok", add="status-error")
                            workers_icon.props("name=error color=red")
                            workers_status.set_text("No workers online")

                    except Exception:
                        backend_card.classes(remove="status-ok", add="status-error")
                        backend_icon.props("name=error color=red")
                        backend_status.set_text("Unreachable")

                        database_card.classes(remove="status-ok", add="status-error")
                        database_icon.props("name=help_outline color=grey")
                        database_status.set_text("Unknown")

                        workers_card.classes(remove="status-ok", add="status-error")
                        workers_icon.props("name=help_outline color=grey")
                        workers_status.set_text("Unknown")

                ui.timer(0.1, check_status, once=True)
                ui.timer(30.0, check_status)

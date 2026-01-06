from fastapi import Request
from nicegui import app, ui
from pages.admin import create as create_admin
from pages.home import create as create_files_table
from pages.srt import create as create_srt
from pages.user import create as create_user_page
from utils.common import default_styles
from utils.settings import get_settings
from utils.token import get_user_status

settings = get_settings()

create_files_table()
create_srt()
create_admin()
create_user_page()


@ui.page("/")
async def index(request: Request) -> None:
    """
    Index page with login.
    """

    ui.add_head_html(default_styles)

    token = request.query_params.get("token")
    refresh_token = request.query_params.get("refresh_token")

    if refresh_token:
        app.storage.user["refresh_token"] = refresh_token

    if token:
        app.storage.user["token"] = token

    # Set the users timezone
    timezone = await ui.run_javascript(
        "Intl.DateTimeFormat().resolvedOptions().timeZone"
    )
    app.storage.user["timezone"] = timezone

    if (
        app.storage.user.get("token")
        and app.storage.user.get("refresh_token")
        and get_user_status()
    ):
        ui.navigate.to("/home")

    else:
        with ui.card() as card:
            card.style("width: 50%; align-self: center; height: 50vh; margin-top: 10%;")
            ui.label(settings.LANDING_TEXT).classes("text-h5").style(
                "margin: auto;"
            )
            ui.label(
                "You must ask your administrator for access before you can login."
            ).classes("text-subtitle2").style("margin: auto; margin-bottom: 10px;")
            ui.image("static/{}".format(settings.LOGO_LANDING)).style(
                "width: 25%; height: auto; margin: auto; magin-top: auto;"
            )
            ui.button(
                "Login with SSO",
                icon="login",
                on_click=lambda: ui.navigate.to(settings.OIDC_APP_LOGIN_ROUTE),
            ).style(
                "margin-top: auto; margin-bottom: 5px; align-self: center; width: 200px;"
            ).props(
                "flat color=white"
            ).classes(
                "button-default-style"
            )


@ui.page("/logout")
def logout() -> None:
    """
    Logout page.
    """

    app.storage.user["token"] = None
    app.storage.user["refresh_token"] = None

    ui.navigate.to("/")


app.add_static_files(url_path="/static", local_directory="static/")
ui.run(
    storage_secret="very_secret",
    title="Sunet Scribe",
    host="0.0.0.0",
    port=8888,
    favicon="static/favicon.ico",
)

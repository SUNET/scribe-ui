from fastapi import Request
from nicegui import ui, app
from pages.srt import create as create_srt
from pages.home import create as create_files_table
from pages.admin import create as create_admin
from pages.user import create as create_user_page
from utils.settings import get_settings
from utils.common import default_styles
from utils.token import get_user_status

settings = get_settings()

create_files_table()
create_srt()
create_admin()
create_user_page()


@ui.page("/")
def index(request: Request) -> None:
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

    if (
        app.storage.user.get("token")
        and app.storage.user.get("refresh_token")
        and get_user_status()
    ):
        ui.navigate.to("/home")

    if (
        app.storage.user.get("token")
        and app.storage.user.get("refresh_token")
        and not get_user_status()
    ):
        ui.navigate.to("/inactive")
    else:
        with ui.card() as card:
            card.style("width: 50%; align-self: center; height: 50vh; margin-top: 10%;")
            ui.label("Welcome to SUNET Transcriber").classes("text-h5").style(
                "margin: auto;"
            )
            ui.image("static/sunet_logo.svg").style(
                "width: 25%; height: auto; margin: auto; magin-top: auto;"
            )
            ui.button(
                "Login with SSO",
                icon="login",
                on_click=lambda: ui.navigate.to(settings.OIDC_APP_LOGIN_ROUTE),
            ).style("margin-top: auto; margin-bottom: 5px; align-self: center;").props(
                "flat"
            ).classes(
                "button-default-style"
            )


@ui.page("/inactive")
def inactive() -> None:
    """
    Inactive user page.
    """

    ui.add_head_html(default_styles)

    with ui.card() as card:
        card.style("width: 50%; align-self: center; height: 50vh; margin-top: 10%;")
        ui.label("Your account is inactive").classes("text-h5").style("margin: auto;")
        ui.image("static/sunet_logo.svg").style(
            "width: 25%; height: auto; margin: auto; magin-top: auto;"
        )
        ui.label("Please contact your administrator to activate your account.").classes(
            "text-subtitle1"
        ).style("margin: auto; margin-top: 20px;")
        ui.button(
            "Login with SSO",
            icon="login",
            on_click=lambda: ui.navigate.to(settings.OIDC_APP_LOGIN_ROUTE),
        ).style("margin-top: auto; margin-bottom: 5px; align-self: center;").props(
            "flat"
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
    title="SUNET Transcriber",
    port=8888,
    favicon="static/favicon.ico",
)

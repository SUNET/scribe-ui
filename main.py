from fastapi import Request
from nicegui import ui, app
from pages.srt import create as create_srt
from pages.home import create as create_files_table
from pages.txt import create as create_txt
from pages.admin import create as create_admin
from pages.user import create as create_user_page
from utils.settings import get_settings
from utils.common import default_styles

settings = get_settings()

create_files_table()
create_srt()
create_txt()
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
        ui.navigate.to("/home")

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


@ui.page("/logout")
def logout() -> None:
    """
    Logout page.
    """

    app.storage.user.clear()

    with ui.card() as card:
        card.style("width: 50%; align-self: center; height: 50vh; margin-top: 10%;")
        ui.label("You have been logged out").classes("text-h5").style("margin: auto;")
        ui.image("static/sunet_logo.svg").style(
            "width: 200px; height: auto; margin: auto; magin-top: auto;"
        )


app.add_static_files(url_path="/static", local_directory="static/")
ui.run(
    storage_secret="very_secret",
    title="SUNET Transcriber",
    port=8888,
)

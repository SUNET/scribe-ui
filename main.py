import requests

from fastapi import Request
from nicegui import app, ui
from pages.admin import create as create_admin
from pages.home import create as create_files_table
from pages.srt import create as create_srt
from pages.user import create as create_user_page
from utils.common import default_styles
from utils.settings import get_settings
from utils.token import get_auth_header, get_user_data, get_user_status

settings = get_settings()

create_files_table()
create_srt()
create_admin()
create_user_page()


def encryption_password_set(password: str) -> None:
    """
    Set the encryption password for the user.
    This is a placeholder function. Implement the logic to store
    the encryption password securely.
    """

    try:
        response = requests.put(
            f"{settings.API_URL}/api/v1/me",
            headers=get_auth_header(),
            data={"encryption": True, "encryption_password": password},
        )
        response.raise_for_status()
        data = response.json()

        return data["result"]

    except requests.exceptions.RequestException:
        return None


def encryption_password_verify(password: str) -> bool:
    """
    Verify the encryption password for the user.
    This is a placeholder function. Implement the logic to verify
    the encryption password with the backend.
    """

    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/me",
            headers=get_auth_header(),
            data={"encryption_password": password},
        )
        response.raise_for_status()

        return True

    except requests.exceptions.RequestException:
        return False


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
        user_data = get_user_data()

        if not user_data["user"]["encryption_settings"]:
            with ui.dialog() as dialog:
                with ui.card():
                    ui.label("Set your encryption password").classes("text-h6")
                    ui.label(
                        "This password will be used to encrypt your files. It cannot be recovered if lost."
                    ).classes("text-subtitle2").style("margin-bottom: 10px;")
                    password_input = ui.input(
                        "Encryption Password", password=True
                    ).style("width: 100%;")
                    confirm_password_input = ui.input(
                        "Confirm Encryption Password", password=True
                    ).style("width: 100%; margin-bottom: 10px;")

                    def set_encryption_password() -> None:
                        if (
                            password_input.value
                            and password_input.value == confirm_password_input.value
                        ):
                            try:
                                encryption_password_set(password_input.value)
                            except Exception:
                                ui.notify(
                                    "Failed to set encryption password.",
                                    color="negative",
                                )
                                return

                            ui.notify(
                                "Encryption password set successfully.",
                                color="positive",
                            )
                            dialog.close()
                            ui.navigate.to("/")

                        else:
                            ui.notify("Passwords do not match.", color="negative")

                    ui.button(
                        "Set Password",
                        on_click=set_encryption_password,
                    ).props(
                        "color=black"
                    ).style("margin-top: 10px;")
                dialog.open()
        else:
            # Ask the user to enter their encryption password
            with ui.dialog() as dialog:
                with ui.card():
                    ui.label("Enter your encryption password").classes("text-h6")
                    password_input = ui.input(
                        "Encryption Password", password=True
                    ).style("width: 100%; margin-bottom: 10px;")

                    def verify_encryption_password() -> None:
                        if password_input.value:
                            app.storage.user[
                                "encryption_password"
                            ] = password_input.value

                            if encryption_password_verify(password_input.value):
                                ui.navigate.to("/home")
                            else:
                                ui.notify(
                                    "Incorrect encryption password.", color="negative"
                                )

                        else:
                            ui.notify(
                                "Please enter your encryption password.",
                                color="negative",
                            )

                    ui.button(
                        "Verify Password",
                        on_click=verify_encryption_password,
                    ).props("color=black").style("margin-top: 10px;")
                dialog.open()

    else:
        with ui.card() as card:
            card.style("width: 50%; align-self: center; height: 50vh; margin-top: 10%;")
            ui.label("Welcome to Sunet Scribe").classes("text-h5").style(
                "margin: auto;"
            )
            ui.label(
                "You must ask your administrator for access before you can login."
            ).classes("text-subtitle2").style("margin: auto; margin-bottom: 10px;")
            ui.image("static/sunet_logo.png").style(
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

import os

from fastapi import Request
from nicegui import app, ui
from pages.admin import create as create_admin
from pages.home import create as create_files_table
from pages.srt import create as create_srt
from pages.user import create as create_user_page
from utils.common import default_styles
from utils.settings import get_settings
from utils.token import get_user_data, get_user_status
from utils.helpers import (
    encryption_password_set,
    encryption_password_verify,
    reset_password,
)

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
        user_data = get_user_data()

        if not user_data["encryption_settings"]:
            with ui.dialog() as dialog:
                with ui.card():
                    ui.label("Set your encryption passphrase").classes("text-h6")
                    ui.label(
                        "This passphrase will be used to encrypt your files. It cannot be recovered if lost."
                    ).classes("text-subtitle2").style("margin-bottom: 10px;")
                    ui.label(
                        "The passphrase must be at least 8 characters long."
                    ).classes("text-subtitle2").style("margin-bottom: 10px;")
                    password_input = ui.input(
                        "Encryption Passphrase", password=True
                    ).style("width: 100%;")
                    confirm_password_input = ui.input(
                        "Confirm Encryption Passphrase", password=True
                    ).style("width: 100%; margin-bottom: 10px;")
                    error_label = (
                        ui.label(
                            "Passphrases do not match or are less than 8 characters."
                        )
                        .classes("text-negative")
                        .style("margin-bottom: 10px;")
                    )
                    error_label.visible = False

                    def set_encryption_password() -> None:
                        if (
                            password_input.value == confirm_password_input.value
                        ) and len(password_input.value) >= 8:
                            try:
                                encryption_password_set(password_input.value)
                            except Exception:
                                ui.notify(
                                    "Failed to set encryption passphrase.",
                                    color="negative",
                                )
                                return

                            ui.notify(
                                "Encryption passphrase set successfully.",
                                color="positive",
                            )
                            dialog.close()
                            ui.navigate.to("/")

                        else:
                            error_label.visible = True

                    ui.button(
                        "Set Passphrase",
                        on_click=set_encryption_password,
                    ).props("color=black").style("margin-top: 10px;")
                dialog.open()
        else:
            # Ask the user to enter their encryption password
            with ui.dialog() as dialog:
                with ui.card() as card:
                    # Set the width
                    ui.label("Enter your encryption passphrase").classes("text-h6")
                    password_input = ui.input(
                        "Encryption Passphrase", password=True
                    ).style("width: 100%; margin-bottom: 10px;")
                    password_input.on(
                        "keydown.enter", lambda e: verify_encryption_password()
                    )

                    def verify_encryption_password() -> None:
                        if password_input.value:
                            app.storage.user[
                                "encryption_password"
                            ] = password_input.value

                            if encryption_password_verify(password_input.value):
                                ui.navigate.to("/home")
                            else:
                                ui.notify(
                                    "Incorrect encryption passphrase.", color="negative"
                                )

                        else:
                            ui.notify(
                                "Please enter your encryption passphrase.",
                                color="negative",
                            )

                    def help_password() -> None:
                        with ui.dialog() as help_dialog:
                            with ui.card():
                                ui.label("Help with Encryption Passphrase").classes(
                                    "text-h6"
                                )
                                ui.label(
                                    "Without the correct passphrase, you will not be able to access your encrypted files. You can reset your passphrase but all your previously encrypted files will be permanently deleted."
                                ).classes("text-subtitle2").style(
                                    "margin-bottom: 10px;"
                                )
                                with ui.row().classes("justify-between w-full"):
                                    ui.button(
                                        "Close", on_click=lambda: ui.navigate.to("/")
                                    ).props("color=black").style("margin-top: 10px;")
                                    ui.button(
                                        "Reset Passphrase",
                                        on_click=lambda: reset_password(),
                                    ).props("color=red").style("margin-top: 10px;")

                            help_dialog.open()

                    with ui.row().classes("justify-between w-full"):
                        ui.button(
                            "Unlock",
                            on_click=verify_encryption_password,
                        ).props(
                            "color=black"
                        ).style("margin-top: 10px;")
                        ui.button("Help", on_click=help_password).props(
                            "color=red"
                        ).style("margin-top: 10px;")
                dialog.open()

    else:
        with ui.card() as card:
            card.style("width: 50%; align-self: center; height: 50vh; margin-top: 10%;")
            ui.label(settings.LANDING_TEXT).classes("text-h5").style("margin: auto;")
            ui.label(
                "You must ask your administrator for access before you can login."
            ).classes("text-subtitle2").style("margin: auto; margin-bottom: 10px;")
            ui.image(f"static/{settings.LOGO_LANDING}").style(
                f"max-width: {settings.LOGO_LANDING_WIDTH}px; height: auto; margin: auto; magin-top: auto;"
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
    storage_secret=settings.STORAGE_SECRET,
    title="Sunet Scribe",
    host="0.0.0.0",
    port=8888,
    favicon=f"static/{settings.FAVICON}",
)

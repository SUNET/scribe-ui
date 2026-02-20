from fastapi import Request
from nicegui import app, ui
from pages.admin import create as create_admin
from pages.home import create as create_files_table
from pages.srt import create as create_srt
from pages.status import create as create_status
from pages.user import create as create_user_page
from utils.common import default_styles
from utils.settings import get_settings
from utils.storage import storage
from utils.token import exchange_code, get_user_data, get_user_status, get_token_is_valid
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
create_status()


@ui.page("/")
async def index(request: Request) -> None:
    """
    Index page with login.
    """

    ui.add_head_html(default_styles)

    code = request.query_params.get("code")

    if code:
        tokens = exchange_code(code)
        if tokens:
            storage["token"] = tokens.get("id_token")
            if tokens.get("refresh_token"):
                storage["refresh_token"] = tokens["refresh_token"]

    # Set the users timezone
    timezone = await ui.run_javascript(
        "Intl.DateTimeFormat().resolvedOptions().timeZone"
    )
    storage["timezone"] = timezone

    if (
        storage.get("token")
        and storage.get("refresh_token")
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
            with ui.dialog() as dialog:
                with ui.card():
                    ui.label("Enter your encryption passphrase").classes("text-h6")
                    password_input = ui.input(
                        "Encryption Passphrase", password=True
                    ).style("width: 100%; margin-bottom: 10px;")
                    password_input.on(
                        "keydown.enter", lambda e: verify_encryption_password()
                    )
                    password_input.props("autofocus")

                    def verify_encryption_password() -> None:
                        if password_input.value:
                            storage[
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
        has_token = bool(
            storage.get("token") and storage.get("refresh_token")
        )

        if has_token and not get_token_is_valid():
            return ui.navigate.to("/logout")

        is_not_activated = has_token and not get_user_status()

        with ui.column().classes("w-full h-screen items-center justify-center"):
            with ui.card().style(
                "width: 500px; max-width: 90%; padding: 40px; border: 0; box-shadow: none;"
            ):
                with ui.column().classes("w-full items-center gap-4"):
                    ui.image(f"static/{settings.LOGO_LANDING}").style(
                        f"max-width: {settings.LOGO_LANDING_WIDTH}px; height: auto;"
                    )

                    ui.label("Welcome to Sunet Scribe").classes(
                        "text-h5 text-center"
                    ).style("margin-top: 20px;")

                    if is_not_activated:
                        with ui.card().classes("w-full no-shadow").style(
                            "background-color: #fff3cd; border: 1px solid #ffc107; padding: 20px; margin-top: 20px; min-height: 160px;"
                        ):
                            with ui.column().classes("items-center gap-3"):
                                ui.icon("warning", size="lg").style("color: #ff9800;")
                                ui.label("Account Pending Activation").classes(
                                    "text-h6"
                                )
                                ui.label(
                                    "Your account has been created but is not yet activated. Please contact your administrator to enable access."
                                ).classes("text-body2 text-center")

                        with ui.row().classes("w-full gap-3 justify-center").style(
                            "margin-top: 30px;"
                        ):
                            ui.button(
                                "Try Again",
                                icon="refresh",
                                on_click=lambda: ui.navigate.to("/"),
                            ).props("flat color=white").classes("button-default-style")

                            ui.button(
                                "Logout",
                                icon="logout",
                                on_click=lambda: ui.navigate.to("/logout"),
                            ).props("flat color=black").classes("button-close")
                    else:
                        ui.button(
                            "Login with SSO",
                            icon="login",
                            on_click=lambda: ui.navigate.to(
                                settings.OIDC_APP_LOGIN_ROUTE
                            ),
                        ).props("flat color=white").classes(
                            "button-default-style"
                        ).style(
                            "width: 220px; height: 44px; margin-top: 30px;"
                        )


@ui.page("/logout")
def logout() -> None:
    """
    Logout page.
    """

    storage["token"] = None
    storage["refresh_token"] = None
    storage["encryption_password"] = None

    ui.navigate.to("/")


app.add_static_files(url_path="/static", local_directory="static/")
ui.run(
    title=f"{settings.TAB_TITLE}",
    storage_secret=settings.STORAGE_SECRET,
    host="0.0.0.0",
    port=8888,
    favicon=f"static/{settings.FAVICON}",
    reconnect_timeout=15,
)

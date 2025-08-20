import asyncio
import requests

from nicegui import app
from nicegui import ui
from typing import Optional
from utils.settings import get_settings
from utils.token import get_auth_header
from utils.token import token_refresh
from utils.token import get_admin_status
from starlette.formparsers import MultiPartParser


MultiPartParser.spool_max_size = 1024 * 1024 * 4096


settings = get_settings()
API_URL = settings.API_URL

jobs_columns = [
    {
        "name": "filename",
        "label": "Filename",
        "field": "filename",
        "align": "left",
        "classes": "text-weight-medium",
    },
    {
        "name": "created_at",
        "label": "Created",
        "field": "created_at",
        "align": "left",
    },
    {
        "name": "update_at",
        "label": "Modified",
        "field": "updated_at",
        "align": "left",
    },
    {
        "name": "deletetion_date",
        "label": "Scheduled deletion",
        "field": "deletion_date",
        "align": "left",
    },
    {
        "name": "status",
        "label": "Status",
        "field": "status",
        "align": "left",
    },
    {"name": "action", "label": "Action", "field": "action", "align": "center"},
]

default_styles = """
    <style>
        .default-style {
            background-color: #d3ecbe;
        }
        .delete-style {
            background-color: #ffffff;
            color: #721c24;
            border: 1px solid #000000;
            width: 150px;
        }
        .table-style th {
            font-size: 14px;
        }
        .table-style tr {
            font-size: 14px;
        }
        .cancel-style {
            background-color: #ffffff;
            color: #721c24;
            border: 1px solid #000000;
            width: 150px;
        }
        .upload-style {
            width: 100%;
            height: 200px;
        }
        .button-default-style {
            background-color: #082954 !important;
            color: #ffffff !important;
            width: 150px;
        }
        .button-replace {
            background-color: #ffffff;
            color: #082954 !important;
            border : 1px solid #082954;
            width: 150px;
        }
        .button-replace-current {
            background-color: #d3ecbe;
            color: #000000 !important;
            width: 150px;
        }
        .button-replace-prev-next {
            background-color: #ffffff;
            color: #082954 !important;
        }
        .button-close {
            background-color: #ffffff;
            color: #000000 !important;
            width: 150px;
        }
    </style>
"""


def logout() -> None:
    """
    Log out the user by clearing the token and navigating to the logout endpoint.
    """

    app.storage.user.clear()
    ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)


def page_init(header_text: Optional[str] = "") -> None:
    """
    Initialize the page with a header and background color.
    """

    def refresh():
        if not token_refresh():
            ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)

    if header_text:
        header_text = f" - {header_text}"

    is_admin = get_admin_status()
    if is_admin:
        header_text += " (ADMIN)"

    with ui.header().style(
        "justify-content: space-between; background-color: #ffffff;"
    ).classes("drop-shadow-md"):
        ui.label("Sunet Transcriber" + header_text).classes("text-h5 text-black")

        with ui.element("div").style("display: flex; gap: 0px;"):
            if is_admin:
                ui.button(
                    icon="settings",
                    on_click=lambda: ui.navigate.to("/admin"),
                ).props("flat color=red")
            ui.button(
                icon="home",
                on_click=lambda: ui.navigate.to("/home"),
            ).props("flat color=black")
            ui.button(
                icon="person",
                on_click=lambda: ui.navigate.to("/user"),
            ).props("flat color=black")
            ui.button(
                icon="help",
                on_click=lambda: ui.navigate.to("/home"),
            ).props("flat color=black")
            ui.button(
                icon="logout",
                on_click=lambda: ui.navigate.to("/logout"),
            ).props("flat color=black")

            ui.timer(30, refresh)
            ui.add_head_html("<style>body {background-color: #ffffff;}</style>")


def jobs_get() -> list:
    """
    Get the list of transcription jobs from the API.
    """
    jobs = []

    try:
        response = requests.get(
            f"{API_URL}/api/v1/transcriber", headers=get_auth_header()
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return []

    for idx, job in enumerate(response.json()["result"]["jobs"]):
        if job["status"] == "in_progress":
            job["status"] = "transcribing"

        # Conert job["deletion_date"] to a more readable format
        deletion_date = job["deletion_date"]

        if deletion_date:
            deletion_date = deletion_date.split(" ")[0]
        else:
            deletion_date = "N/A"

        job_data = {
            "id": idx,
            "uuid": job["uuid"],
            "filename": job["filename"],
            "created_at": job["created_at"].rsplit(":", 1)[0],
            "updated_at": job["updated_at"].rsplit(":", 1)[0],
            "deletion_date": deletion_date,
            "language": job["language"].capitalize(),
            "status": job["status"].capitalize(),
            "model_type": job["model_type"].capitalize(),
            "output_format": job["output_format"].upper(),
        }

        jobs.append(job_data)

    # Sort jobs by created_at in descending order
    jobs.sort(key=lambda x: x["created_at"], reverse=True)

    return jobs


def table_click(event) -> None:
    """
    Handle the click event on the table rows.
    """

    status = event.args["status"].lower()
    uuid = event.args["uuid"]
    filename = event.args["filename"]
    model_type = event.args["model_type"]
    language = event.args["language"]
    output_format = event.args.get("output_format")

    if status != "completed":
        return

    if output_format == "TXT":
        ui.navigate.to(
            f"/txt?uuid={uuid}&filename={filename}&model={model_type}&language={language}"
        )
    else:
        ui.navigate.to(
            f"/srt?uuid={uuid}&filename={filename}&model={model_type}&language={language}"
        )


def post_file(file: str, filename: str) -> None:
    """
    Post a file to the API.
    """
    files_json = {"file": (filename, file.read())}

    try:
        response = requests.post(
            f"{API_URL}/api/v1/transcriber", files=files_json, headers=get_auth_header()
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        ui.notify(
            f"Error when uploading file: {str(e)}", type="negative", position="top"
        )
        return

    return True


def table_upload(table) -> None:
    """
    Handle the click event on the Upload button with improved UX.
    """

    ui.add_head_html(default_styles)

    with ui.dialog() as dialog:
        with ui.card().style(
            "background-color: white; align-self: center; border: 0; width: 90%; max-width: 600px; min-height: 400px; padding: 24px;"
        ):
            ui.label("Select files").classes("text-h6")

            with ui.card().style(
                "background-color: #f8f9fa; border: 1px solid #e9ecef; padding: 16px; margin-bottom: 20px; width: 100%;"
            ):
                ui.label("How to upload:").style(
                    "font-weight: 600; margin-bottom: 8px; color: #495057;"
                )
                with ui.column().style("gap: 4px;"):
                    ui.label(
                        "• Click the '+' in the upload area below or drag and drop files"
                    ).style("color: #6c757d;")
                    ui.label("• You can select up to 5 files at once").style(
                        "color: #6c757d;"
                    )
                    ui.label(
                        "• Supported formats: MP3, WAV, FLAC, MP4, MKV, AVI"
                    ).style("color: #6c757d;")
                    ui.label(
                        "• When files are selected, click the button to the right of the upload button."
                    ).style("color: #6c757d;")

            with ui.upload(
                on_multi_upload=lambda files: handle_upload_with_feedback(
                    files, dialog
                ),
                multiple=True,
                max_files=5,
                label="",
            ) as upload:
                upload.classes("upload-style")
                upload.props("accept=.mp3,.wav,.flac,.mp4,.mkv,.avi color=black")

            with ui.row().style("justify-content: flex-end; gap: 12px;"):
                with ui.button(
                    "Cancel",
                    icon="cancel",
                    on_click=lambda: dialog.close(),
                ) as cancel:
                    cancel.props("color=black flat")
                    cancel.classes("cancel-style")

        dialog.open()


async def handle_upload_with_feedback(files, dialog):
    """
    Handle file uploads with user feedback and validation.
    """

    dialog.close()

    for file, name in zip(files.contents, files.names):
        try:
            await asyncio.to_thread(post_file, file, name)

            ui.notify(f"Successfully uploaded {name}", type="positive", timeout=3000)
        except Exception as e:
            ui.notify(
                f"Failed to upload {name}: {str(e)}", type="negative", timeout=5000
            )


def table_transcribe(selected_row) -> None:
    """
    Handle the click event on the Transcribe button.
    """
    with ui.dialog() as dialog:
        with ui.card().style(
            "background-color: white; align-self: center; border: 0; width: 80%;"
        ).classes("w-full no-shadow no-border"):
            with ui.row().classes("w-full"):
                ui.label("Transcription Settings").style("width: 100%;").classes(
                    "text-h6 q-mb-xl text-black"
                )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        value=settings.WHISPER_LANGUAGES[0],
                    ).classes("w-full")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Accuracy").classes("text-subtitle2 q-mb-sm")
                    model = ui.radio(
                        settings.WHISPER_MODELS, value=settings.WHISPER_MODELS[0]
                    )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers, automatic if not chosen").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0").classes("w-full")

            with ui.row().classes("justify-between w-full"):
                ui.label("Output format").classes("text-subtitle2 q-mb-sm")
                output_format = ui.radio(
                    ["Transcribed text", "Subtitles"],
                    value="Transcribed text",
                ).classes("w-full")

            with ui.row().classes("justify-between w-full"):
                with ui.button(
                    "Cancel",
                    icon="cancel",
                ) as cancel:
                    cancel.on("click", lambda: dialog.close())
                    cancel.props("color=black flat")
                    cancel.classes("cancel-style")

                with ui.button(
                    "Start transcribing",
                    on_click=lambda: start_transcription(
                        [selected_row],
                        language.value,
                        model.value,
                        speakers.value,
                        output_format.value,
                        dialog,
                    ),
                ) as start:
                    start.props("color=black flat")
                    start.classes("default-style")

            dialog.open()


def table_delete(selected_rows: list) -> None:
    """
    Handle the click event on the Delete button.
    """

    with ui.dialog() as dialog:
        with ui.card().style(
            "background-color: white; align-self: center; border: 0; width: 100%;"
        ):
            ui.label("Are you sure you want to delete the selected files?").classes(
                "text-h6 q-mb-md text-black"
            )
            ui.separator()
            with ui.row().classes("justify-between w-full"):
                ui.button(
                    "Cancel",
                ).on("click", lambda: dialog.close()).classes(
                    "cancel-style"
                ).props("color=black flat")
                ui.button(
                    "Delete",
                    on_click=lambda: __delete_files(selected_rows, dialog),
                ).props("color=black flat").classes("delete-style")

        dialog.open()


def __delete_files(rows: list, dialog: ui.dialog) -> bool:
    try:
        for row in rows:
            uuid = row["uuid"]
            response = requests.delete(
                f"{API_URL}/api/v1/transcriber/{uuid}",
                headers=get_auth_header(),
            )
            response.raise_for_status()
        ui.notify("Files deleted successfully", type="positive", position="top")
    except requests.exceptions.RequestException as e:
        ui.notify(
            f"Error: Failed to delete files: {str(e)}", type="negative", position="top"
        )
        return False

    dialog.close()


def start_transcription(
    rows: list,
    language: str,
    model: str,
    speakers: str,
    output_format: str,
    dialog: ui.dialog,
) -> None:
    # Get selected values
    selected_language = language
    selected_model = model

    if output_format == "Subtitles":
        output_format = "SRT"
    else:
        output_format = "TXT"

    try:
        for row in rows:
            uuid = row["uuid"]

            try:
                response = requests.put(
                    f"{API_URL}/api/v1/transcriber/{uuid}",
                    json={
                        "language": f"{selected_language}",
                        "model": f"{selected_model}",
                        "speakers": int(speakers),
                        "status": "pending",
                        "output_format": output_format,
                    },
                    headers=get_auth_header(),
                )
                response.raise_for_status()
            except requests.exceptions.RequestException:
                ui.notify(
                    "Error: Failed to start transcription.",
                    type="negative",
                    position="top",
                )
                return

        dialog.close()

    except Exception as e:
        ui.notify(f"Error: {str(e)}", type="negative", position="top")

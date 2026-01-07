import asyncio
import requests
import pytz
from datetime import datetime

from nicegui import ui, app
from starlette.formparsers import MultiPartParser
from typing import Optional
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
    get_bofh_status,
    token_refresh,
)


MultiPartParser.spool_max_size = 1024 * 1024 * 4096


settings = get_settings()

jobs_columns = [
    {
        "name": "filename",
        "label": "Filename",
        "field": "filename",
        "align": "left",
        "classes": "text-weight-medium",
    },
    {
        "name": "job_type",
        "label": "Type",
        "field": "job_type",
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
            border: 1px solid #000000;
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
            border: 1px solid #000000;
        }
        .button-user-status {
            background-color: #ffffff;
            width: 150px;
            border: 1px solid #000000;
        }
        .button-edit {
            background-color: #082954;
            color: #ffffff !important;
            width: 150px;
        }
    </style>
"""


def show_help_dialog() -> None:
    """
    Show a help dialog with information about the application.
    """

    with ui.dialog() as dialog:
        dialog.style("max-width: 75%; max-width: none;")
        with (
            ui.card()
            .style(
                "background-color: white; align-self: center; border: 0; width: 75%; max-width: none;"
            )
            .classes("w-full no-shadow no-border")
        ):
            ui.label("Help").style("width: 100%;").classes("text-h6 q-mb-xl text-black")

            ui.markdown(
                """
                ## About Sunet Scribe

                Sunet Scribe is a web application that allows users to upload audio and video files for transcription using OpenAI's Whisper model. The application supports multiple languages and provides options for transcription accuracy and output formats.

                ### Features

                - Upload audio and video files in various formats (mp3, wav, flac, mp4, mkv, avi, m4a, aiff, aif, mov, ogg, opus, webm, wma).
                - Choose transcription language from a wide range of supported languages.
                - Select transcription accuracy (model size) based on your needs.
                - Option to specify the number of speakers for better diarization.
                - Download transcriptions as plain text or subtitles (SRT format).
                - User authentication and role-based access control.

                ### Usage

                1. Log in using your institutional credentials.
                2. Upload your audio or video files using the upload button or drag-and-drop area.
                3. Select the desired transcription settings (language, model, speakers, output format).
                4. Start the transcription process and monitor the job status on the dashboard.
                5. Once completed, edit your transcriptions from the job list.

                ### Support

                For support or inquiries, please contact the IT department at your institution.

                ### Privacy

                All uploaded files and transcriptions are stored securely and are only accessible to the user who uploaded them. Files are automatically deleted after a specified retention period.

                ---
                """
            ).classes("text-body1 q-mb-xl text-black")

            with ui.row().classes("justify-end w-full"):
                with ui.button(
                    "Close",
                    on_click=lambda: dialog.close(),
                ) as close:
                    close.props("color=black flat")
                    close.classes("button-close")
        dialog.open()


def logout() -> None:
    """
    Log out the user by clearing the token and navigating to the logout endpoint.
    """

    ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)


def page_init(header_text: Optional[str] = "") -> None:
    """
    Initialize the page with a header and background color.
    """

    def refresh():
        if not token_refresh():
            ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)

    refresh()

    is_admin = get_admin_status()
    is_bofh = get_bofh_status()
    ui.timer(30, refresh)

    if header_text:
        header_text = f" - {header_text}"

    if is_admin:
        header_text += " (Administrator)"

    with (
        ui.header()
        .style("justify-content: space-between; background-color: #ffffff;")
        .classes("drop-shadow-md")
    ):
        with ui.element("div").style("display: flex; gap: 0px;"):
            ui.image(f"static/{settings.LOGO_TOPBAR}").classes("q-mr-sm").style(
                "height: 30px; width: 30px;"
            )
            ui.label(settings.TOPBAR_TEXT + header_text).classes("text-h6 text-black")

        with ui.element("div").style("display: flex; gap: 0px;"):
            if is_admin:
                with ui.button(
                    icon="settings",
                    on_click=lambda: ui.navigate.to("/admin"),
                ).props("flat color=red"):
                    ui.tooltip("Admin settings")

            if is_bofh:
                with ui.button(
                    icon="health_and_safety",
                    on_click=lambda: ui.navigate.to("/health"),
                ).props("flat color=red"):
                    ui.tooltip("System status")
            with ui.button(
                icon="home",
                on_click=lambda: ui.navigate.to("/home"),
            ).props("flat color=black"):
                ui.tooltip("Home")
            with ui.button(
                icon="person",
                on_click=lambda: ui.navigate.to("/user"),
            ).props("flat color=black"):
                ui.tooltip("User settings")
            with ui.button(
                icon="help",
                on_click=lambda: show_help_dialog(),
            ).props("flat color=black"):
                ui.tooltip("Help")
            with ui.button(
                icon="logout",
                on_click=lambda: ui.navigate.to("/logout"),
            ).props("flat color=black"):
                ui.tooltip("Logout")
            ui.add_head_html("<style>body {background-color: #ffffff;}</style>")


def add_timezone_to_timestamp(timestamp: str) -> str:
    """
    Convert a UTC timestamp to the user's local timezone.
    """
    user_timezone = app.storage.user.get("timezone", "UTC")
    utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
    utc_time = pytz.utc.localize(utc_time)
    local_tz = pytz.timezone(user_timezone)
    local_time = utc_time.astimezone(local_tz)

    return local_time.strftime("%Y-%m-%d %H:%M")


def jobs_get() -> list:
    """
    Get the list of transcription jobs from the API.
    """
    jobs = []

    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/transcriber", headers=get_auth_header()
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return []

    for idx, job in enumerate(response.json()["result"]["jobs"]):
        if job["status"] == "in_progress":
            job["status"] = "transcribing"

        deletion_date = add_timezone_to_timestamp(job["deletion_date"])
        created_at = add_timezone_to_timestamp(job["created_at"])
        updated_at = add_timezone_to_timestamp(job["updated_at"])

        if deletion_date:
            deletion_date = deletion_date.split(" ")[0]
        else:
            deletion_date = "N/A"

        if job["status"] != "completed":
            job_type = ""
        elif job["output_format"] == "txt":
            job_type = "Transcription"
        elif job["output_format"] == "srt":
            job_type = "Subtitles"
        else:
            job_type = "Transcription"

        job_data = {
            "id": idx,
            "uuid": job["uuid"],
            "filename": job["filename"],
            "created_at": created_at,
            "updated_at": updated_at,
            "deletion_date": deletion_date,
            "language": job["language"].capitalize(),
            "status": job["status"].capitalize(),
            "model_type": job["model_type"].capitalize(),
            "output_format": job["output_format"].upper(),
            "job_type": job_type,
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
            f"/srt?uuid={uuid}&filename={filename}&model={model_type}&language={language}&data_format=txt"
        )
    else:
        ui.navigate.to(
            f"/srt?uuid={uuid}&filename={filename}&model={model_type}&language={language}&data_format=srt"
        )


def post_file(filedata: bytes, filename: str) -> None:
    """
    Post a file to the API.
    """

    files_json = {"file": (filename, filedata)}

    try:
        response = requests.post(
            f"{settings.API_URL}/api/v1/transcriber",
            files=files_json,
            headers=get_auth_header(),
        )
        response.raise_for_status()

        if response.status_code != 200:
            raise requests.exceptions.RequestException(
                f"Upload failed, status code: {response.status_code}"
            )
    except requests.exceptions.RequestException as e:
        ui.notify(
            f"Error when uploading file: {str(e)}", type="negative", position="top"
        )
        return

    return True


def toggle_upload_status(upload_column, status_column):
    upload_column.visible = False
    status_column.visible = True


def table_upload(table) -> None:
    """
    Handle the click event on the Upload button with improved UX.
    """

    ui.add_head_html(default_styles)

    with ui.dialog() as dialog:
        with ui.card():
            with ui.column().classes("w-full items-center mt-10") as status_column:
                ui.label("Uploading files, please wait...").style(
                    "width: 100%;"
                ).classes("text-h6 q-mb-xl text-black")
                ui.spinner(size="50px", color="black")
                status_column.visible = False

            with ui.column().classes("w-full items-center mt-10") as upload_column:
                upload = ui.upload(
                    label="hidden",
                    on_multi_upload=lambda e: handle_upload_with_feedback(e, dialog),
                    auto_upload=True,
                    multiple=True,
                    max_files=5,
                ).props(
                    "hidden accept=.mp3,.wav,.flac,.mp4,.mkv,.avi,.m4a,.aiff,.aif,.mov,.ogg,.opus,.webm,.wma,.mpg,.mpeg"
                )

                upload.on(
                    "start",
                    lambda _: toggle_upload_status(upload_column, status_column),
                )
                upload.on("finish", lambda _: dialog.close())

                ui.html(
                    """
                    <div id="dropzone"
                         class="w-96 h-40 flex items-center justify-center
                                border-2 border-dashed border-gray-400
                                rounded-2xl bg-gray-50
                                hover:bg-gray-100 cursor-pointer text-gray-600">
                        Drag & drop files here or click to upload.
                        <br/><br/>
                        5 files at a maximum of 4GB can be uploaded at once.
                    </div>
                    """,
                    sanitize=False,
                )

                ui.run_javascript(
                    """
                        const dz = document.getElementById('dropzone');
                        const hiddenInput = dz.closest('body').querySelector('input[type=file][multiple]');
                        dz.addEventListener('click', () => hiddenInput.click());

                        dz.addEventListener('dragover', e => {
                            e.preventDefault();
                            dz.classList.add('bg-gray-200');
                        });

                        dz.addEventListener('dragleave', () => {
                            dz.classList.remove('bg-gray-200');
                        });

                        dz.addEventListener('drop', e => {
                            e.preventDefault();
                            dz.classList.remove('bg-gray-200');

                            // Create a DataTransfer to set multiple files
                            const dt = new DataTransfer();
                            for (const file of e.dataTransfer.files) {
                                dt.items.add(file);
                            }
                            hiddenInput.files = dt.files;

                            hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
                        });
                    """
                )
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

    for file in files.files:
        try:
            file_name = file.name
            file_data = await file.read()

            await asyncio.to_thread(post_file, file_data, file_name)

            ui.notify(
                f"Successfully uploaded {file_name}", type="positive", timeout=3000
            )
        except Exception as e:
            ui.notify(
                f"Error uploading {file_name}: {str(e)}", type="negative", timeout=5000
            )


def table_transcribe(selected_row) -> None:
    """
    Handle the click event on the Transcribe button.
    """
    with ui.dialog() as dialog:
        with (
            ui.card()
            .style(
                "background-color: white; align-self: center; border: 0; width: 80%;"
            )
            .classes("w-full no-shadow no-border")
        ):
            with ui.row().classes("w-full"):
                ui.label("Transcription Settings").style("width: 100%;").classes(
                    "text-h6 q-mb-xl text-black"
                )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Filename:").classes("text-subtitle2 q-mb-sm")
                    ui.label(f"{selected_row['filename']}")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        value=settings.WHISPER_LANGUAGES[0],
                    ).classes("w-full")

                # Remove the option to pick model for now. People always use the large models anyway.
                # with ui.column().classes("col-12 col-sm-24"):
                #     ui.label("Accuracy").classes("text-subtitle2 q-mb-sm")
                #     model = ui.radio(
                #         settings.WHISPER_MODELS, value=settings.WHISPER_MODELS[0]
                #     )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers, automatic if not chosen").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0").classes("w-full")

            with ui.row().classes("justify-between w-full"):
                ui.label("Output format").classes("text-subtitle2 q-mb-sm")
                output_format = (
                    ui.radio(
                        ["Transcribed text", "Subtitles"],
                        value="Transcribed text",
                    )
                    .classes("w-full")
                    .props("inline")
                )

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
                        # model.value,
                        speakers.value,
                        output_format.value,
                        dialog,
                    ),
                ) as start:
                    start.props("color=black flat")
                    start.classes("default-style")

            dialog.open()


def table_delete(table: ui.table) -> None:
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
                    on_click=lambda: __delete_files(table, dialog),
                ).props("color=black flat").classes("delete-style")

        dialog.open()


def __delete_files(table: ui.table, dialog: ui.dialog) -> bool:
    try:
        for row in table.selected:
            uuid = row["uuid"]
            response = requests.delete(
                f"{settings.API_URL}/api/v1/transcriber/{uuid}",
                headers=get_auth_header(),
            )
            response.raise_for_status()
        ui.notify("Files deleted successfully", type="positive", position="top")
    except requests.exceptions.RequestException as e:
        ui.notify(
            f"Error: Failed to delete files: {str(e)}", type="negative", position="top"
        )
        return False

    table.selected = []

    dialog.close()


def start_transcription(
    rows: list,
    language: str,
    # model: str,
    speakers: str,
    output_format: str,
    dialog: ui.dialog,
) -> None:
    selected_language = language
    # selected_model = model
    selected_model = "Slower transcription (higher accuracy)"
    error = ""

    if output_format == "Subtitles":
        output_format = "SRT"
    else:
        output_format = "TXT"

    for row in rows:
        uuid = row["uuid"]

        try:
            response = requests.put(
                f"{settings.API_URL}/api/v1/transcriber/{uuid}",
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
            if response.status_code == 403:
                error = response.json()["result"]["error"]
            else:
                error = "Error: Failed to start transcription."

        if error:
            with dialog:
                dialog.clear()

                with ui.card().style(
                    "background-color: white; align-self: center; border: 0; width: 50%;"
                ):
                    ui.label(error).classes("text-h6 q-mb-md text-black")
                    ui.button(
                        "Close",
                    ).on("click", lambda: dialog.close()).classes(
                        "button-close"
                    ).props("color=black flat")
                dialog.open()
        else:
            dialog.close()

        return

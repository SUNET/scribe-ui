import asyncio
import requests
import pytz
from datetime import datetime, timedelta

from nicegui import app, ui
from starlette.formparsers import MultiPartParser
from typing import Optional
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
    get_bofh_status,
    token_refresh,
)
from utils.storage import storage

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
        .default-style.disabled {
            background-color: #e0e0e0 !important;
            border: 1px solid #bdbdbd !important;
            opacity: 0.7;
        }
        .delete-style {
            background-color: #ffffff;
            color: #721c24;
            border: 1px solid #000000;
            width: 150px;
        }
        .delete-style.disabled {
            background-color: #e0e0e0 !important;
            border: 1px solid #bdbdbd !important;
            opacity: 0.7;
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
        .deletion-warning {
            color: #d32f2f;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .deletion-warning-icon {
            font-size: 18px;
        }
        .q-tooltip {
            font-size: 14px;
        }
    </style>
"""


def show_help_dialog() -> None:
    """
    Show a help dialog with information about the application.
    """

    with ui.dialog() as dialog:
        with (
            ui.card()
            .style(
                "max-width: 900px; padding: 32px; background: linear-gradient(to bottom, #ffffff 0%, #f8f9fa 100%);"
            )
            .classes("no-shadow")
        ):
            with ui.row().classes("w-full items-center justify-between mb-6"):
                ui.label("Help & Documentation").classes("text-h4 font-bold text-black")
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round dense color=grey-7"
                )

            with ui.column().classes("w-full gap-6"):
                with ui.card().classes("bg-blue-50 border-l-4").style(
                    "border-left-color: #082954; padding: 20px;"
                ):
                    ui.label("About Sunet Scribe").classes("text-h6 font-semibold mb-2")
                    ui.label(
                        "A powerful transcription service using Whisper AI models to convert audio and video files into searchable text or time-coded subtitles with high accuracy."
                    ).classes("text-body1")

                ui.label("Getting Started").classes("text-h6 font-bold mt-2")

                with ui.grid(columns=2).classes("w-full gap-4"):
                    for step_num, step_title, step_desc, step_icon in [
                        (
                            "1",
                            "Upload Files",
                            "Click Upload or drag & drop up to 5 files (max 4GB each). Supports MP3, WAV, MP4, MKV, AVI, and more.",
                            "upload_file",
                        ),
                        (
                            "2",
                            "Configure",
                            'Click the "Transcribe" button, select language, number of speakers, and output format (transcript or subtitles).',
                            "settings",
                        ),
                        (
                            "3",
                            "Monitor",
                            "Track job status on the dashboard. Jobs process in the background.",
                            "pending_actions",
                        ),
                        (
                            "4",
                            "Edit & Export",
                            "Click completed jobs to refine in the editor. Press ? for keyboard shortcuts.",
                            "edit_note",
                        ),
                    ]:
                        with ui.card().classes("p-4"):
                            with ui.row().classes("items-center gap-3 mb-2"):
                                ui.icon(step_icon, size="md").classes("text-blue-700")
                                ui.label(f"{step_num}. {step_title}").classes(
                                    "text-subtitle1 font-semibold"
                                )
                            ui.label(step_desc).classes("text-body2 text-grey-8")

                with ui.row().classes("w-full gap-4"):
                    with ui.card().classes("flex-1 bg-amber-50 p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("security", size="sm").classes("text-amber-800")
                            ui.label("Privacy").classes("text-subtitle1 font-semibold")
                        ui.label(
                            "Files are encrypted, only accessible to you, and auto-deleted after the scheduled deletion date."
                        ).classes("text-body2")

                    with ui.card().classes("flex-1 bg-green-50 p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("help", size="sm").classes("text-green-800")
                            ui.label("Support").classes("text-subtitle1 font-semibold")
                        ui.label(
                            "Contact your institution's IT department for technical support or questions."
                        ).classes("text-body2")

        dialog.open()


def logout() -> None:
    """
    Log out the user by clearing the token and navigating to the logout endpoint.
    """

    storage["token"] = None
    storage["refresh_token"] = None
    storage["encryption_password"] = None

    ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)


def page_init(header_text: Optional[str] = "") -> None:
    """
    Initialize the page with a header and background color.
    """

    def refresh():
        if not token_refresh():
            storage["token"] = None
            storage["refresh_token"] = None
            storage["encryption_password"] = None

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
    user_timezone = storage.get("timezone", "UTC")
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
            f"{settings.API_URL}/api/v1/transcriber",
            headers=get_auth_header(),
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return []

    # Get current time in user's timezone
    user_timezone = storage.get("timezone", "UTC")
    local_tz = pytz.timezone(user_timezone)
    current_time = datetime.now(local_tz)

    for idx, job in enumerate(response.json()["result"]["jobs"]):
        if job["status"] == "in_progress":
            job["status"] = "transcribing"

        deletion_date = add_timezone_to_timestamp(job["deletion_date"])
        created_at = add_timezone_to_timestamp(job["created_at"])
        updated_at = add_timezone_to_timestamp(job["updated_at"])

        # Check if deletion is approaching (within 24 hours)
        deletion_approaching = False
        if deletion_date:
            try:
                deletion_dt = datetime.strptime(deletion_date, "%Y-%m-%d %H:%M")
                deletion_dt = local_tz.localize(deletion_dt)
                time_until_deletion = deletion_dt - current_time
                # Default threshold: 24 hours
                deletion_approaching = time_until_deletion <= timedelta(hours=24)
            except (ValueError, AttributeError):
                pass

            deletion_date_display = deletion_date.split(" ")[0]
        else:
            deletion_date_display = "N/A"

        if job["status"] != "completed":
            job_type = ""
        elif job["output_format"] == "txt":
            job_type = "Transcript"
        elif job["output_format"] == "srt":
            job_type = "Subtitles"
        else:
            job_type = "Transcript"

        job_data = {
            "id": idx,
            "uuid": job["uuid"],
            "filename": job["filename"],
            "created_at": created_at,
            "updated_at": updated_at,
            "deletion_date": deletion_date_display,
            "deletion_approaching": deletion_approaching,
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
            json={"encryption_password": storage.get("encryption_password")},
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
                        ["Transcript", "Subtitles"],
                        value="Transcript",
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


def table_bulk_transcribe(table: ui.table) -> None:
    """
    Handle bulk transcription of selected uploaded jobs.
    Shows the same transcription settings dialog but applies to all selected rows.
    """
    selected = table.selected
    uploadable = [r for r in selected if r.get("status") == "Uploaded"]
    already_done = [r for r in selected if r.get("status") == "Completed"]
    if not uploadable:
        ui.notify("No uploaded files selected", type="warning", position="top")
        return

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

                with ui.column().classes("w-full q-mb-sm").style(
                    "background-color: #fff3e0; padding: 8px 12px; border-radius: 4px;"
                ):
                    with ui.row().classes("items-center"):
                        ui.icon("rtt", color="black").classes("text-body1")
                        ui.label(
                            f"{len(uploadable)} file(s) will be transcribed."
                        ).classes("text-body2 text-black")
                    if already_done:
                        with ui.row().classes("items-center"):
                            ui.icon("block", color="black").classes("text-body1")
                            ui.label(
                                f"{len(already_done)} completed file(s) will be skipped."
                            ).classes("text-body2 text-black")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        value=settings.WHISPER_LANGUAGES[0],
                    ).classes("w-full")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers, automatic if not chosen").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0").classes("w-full")

            with ui.row().classes("justify-between w-full"):
                ui.label("Output format").classes("text-subtitle2 q-mb-sm")
                output_format = (
                    ui.radio(
                        ["Transcript", "Subtitles"],
                        value="Transcript",
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
                        uploadable,
                        language.value,
                        speakers.value,
                        output_format.value,
                        dialog,
                        table,
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
                ).props("color=red").classes("delete-style")

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


def table_bulk_export(table: ui.table) -> None:
    """
    Handle bulk export of selected completed jobs as a zip file.
    All selected jobs must be of the same type (output_format).
    """

    selected = table.selected
    if not selected:
        ui.notify("No files selected", type="warning", position="top")
        return

    completed = [r for r in selected if r.get("status") == "Completed"]
    if not completed:
        ui.notify("No already completed files selected", type="warning", position="top")
        return

    formats = set(r.get("output_format", "") for r in completed)
    if len(formats) > 1:
        ui.notify(
            "All selected files must be of the same type",
            type="warning",
            position="top",
        )
        return

    source_format = formats.pop()
    data_format = "srt" if source_format == "SRT" else "txt"

    # Show progress dialog while fetching
    with ui.dialog() as progress_dialog:
        with ui.card().classes("p-6 items-center").style(
            "min-width: 400px; background-color: #ffffff;"
        ):
            ui.label("Preparing export...").classes("text-h6 text-black mb-2")
            progress_label = ui.label(f"Fetching file 0 of {len(completed)}").classes(
                "text-body2 mb-2"
            )
            progress = ui.linear_progress(value=0, show_value=False).classes("w-full")

    progress_dialog.open()

    async def fetch_and_show():
        from utils.srt import SRTEditor

        editors = []
        for i, row in enumerate(completed):
            uuid = row["uuid"]
            filename = row["filename"]
            progress_label.set_text(
                f"Fetching file {i + 1} of {len(completed)}: {filename}"
            )
            progress.set_value((i + 1) / len(completed))
            try:
                if data_format == "srt":
                    response = requests.get(
                        f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/srt",
                        headers=get_auth_header(),
                        json={
                            "encryption_password": storage.get("encryption_password")
                        },
                    )
                else:
                    response = requests.get(
                        f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/txt",
                        headers=get_auth_header(),
                        json={
                            "encryption_password": storage.get("encryption_password")
                        },
                    )
                response.raise_for_status()
                data = response.json()

                editor = SRTEditor(uuid, data_format, filename)
                if data_format == "srt":
                    editor.parse_srt(data["result"])
                else:
                    editor.parse_txt(data["result"])
                editors.append((filename, editor))
            except requests.exceptions.RequestException as e:
                progress_dialog.close()
                ui.notify(
                    f"Error fetching {filename}: {str(e)}",
                    type="negative",
                    position="top",
                )
                return

            await asyncio.sleep(0)  # yield to UI to update progress

        progress_dialog.close()
        # Use the first editor to show the export dialog with all editors
        first_filename, first_editor = editors[0]
        first_editor.show_export_dialog(first_filename, bulk_editors=editors)

    ui.timer(0.1, fetch_and_show, once=True)


def start_transcription(
    rows: list,
    language: str,
    # model: str,
    speakers: str,
    output_format: str,
    dialog: ui.dialog,
    table: ui.table = None,
) -> None:
    selected_language = language
    error = ""

    if output_format == "Subtitles":
        output_format = "SRT"
    elif output_format in ("Transcript", "Transcribed text"):
        output_format = "TXT"
    else:
        output_format = "TXT"

    for row in rows:
        uuid = row["uuid"]

        try:
            response = requests.put(
                f"{settings.API_URL}/api/v1/transcriber/{uuid}",
                json={
                    "language": f"{selected_language}",
                    "speakers": int(speakers),
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
            break

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
        if table is not None:
            table.selected = []
        dialog.close()

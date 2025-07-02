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
        "name": "created_at",
        "label": "Updated",
        "field": "updated_at",
        "align": "left",
    },
    {
        "name": "deletetion_date",
        "label": "Deletion date",
        "field": "deletion_date",
        "align": "left",
    },
    {
        "name": "model_type",
        "label": "Model",
        "field": "model_type",
        "align": "left",
    },
    {
        "name": "language",
        "label": "Language",
        "field": "language",
        "align": "left",
    },
    {
        "name": "status",
        "label": "Status",
        "field": "status",
        "align": "left",
    },
]


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

    with ui.header().style("justify-content: space-between;"):
        ui.label("Sunet Transcriber" + header_text).classes("text-h5 text-white")

        with ui.element("div").style("display: flex; gap: 0px;"):
            if is_admin:
                ui.button(
                    icon="settings",
                    on_click=lambda: ui.navigate.to("/admin"),
                ).props("flat color=red")
            ui.button(
                icon="home",
                on_click=lambda: ui.navigate.to("/home"),
            ).props("flat color=white")
            ui.button(
                icon="person",
                on_click=lambda: ui.navigate.to("/user"),
            ).props("flat color=white")
            ui.button(
                icon="help",
                on_click=lambda: ui.navigate.to("/home"),
            ).props("flat color=white")
            ui.button(
                icon="logout",
                on_click=lambda: ui.navigate.to("/logout"),
            ).props("flat color=white")

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
        }

        jobs.append(job_data)

    # Sort jobs by created_at in descending order
    jobs.sort(key=lambda x: x["created_at"], reverse=True)

    return jobs


def table_click(event) -> None:
    """
    Handle the click event on the table rows.
    """

    status = event.args[1]["status"].lower()
    uuid = event.args[1]["uuid"]
    filename = event.args[1]["filename"]
    model_type = event.args[1]["model_type"]
    language = event.args[1]["language"]

    if status != "completed":
        return

    # Dialog to pick which format to open, TXT or SRT
    with ui.dialog() as dialog:
        with ui.card().style(
            "background-color: white; align-self: center; border: 0; width: 100%;"
        ):
            # Information about the transcription
            ui.label(f"Transcription for {filename}").classes(
                "text-h6 q-mb-md text-primary"
            )
            ui.label(f"UUID: {uuid}")
            ui.label(f"Model: {model_type}")
            ui.label(f"Language: {language}")
            ui.label("Status: Completed")
            ui.label("Select the format to edit the transcription.").classes(
                "text-subtitle2 q-mb-md"
            )
            with ui.row().classes("justify-end"):
                ui.button(
                    "TXT",
                    icon="text_fields",
                    on_click=lambda: ui.navigate.to(
                        f"/txt?uuid={uuid}&filename={filename}&model={model_type}&language={language}"
                    ),
                ).props("color=primary")
                ui.button(
                    "SRT",
                    icon="subtitles",
                    on_click=lambda: ui.navigate.to(
                        f"/srt?uuid={uuid}&filename={filename}&model={model_type}&language={language}"
                    ),
                ).props("color=primary")
                ui.button(
                    "Close",
                    icon="cancel",
                ).on("click", lambda: dialog.close())
        dialog.open()


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
    with ui.dialog() as dialog:
        with ui.card().style(
            "background-color: white; align-self: center; border: 0; width: 90%; max-width: 600px; min-height: 400px; padding: 24px;"
        ):
            with ui.row().style(
                "width: 100%; margin-bottom: 20px; align-items: center;"
            ):
                ui.icon("cloud_upload", size="2em").style(
                    "color: #1976d2; margin-right: 12px;"
                )
                ui.label("Upload Media Files").style(
                    "font-size: 1.5em; font-weight: 600; color: #333;"
                )

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
                    files, dialog, upload_progress, status_label, upload
                ),
                multiple=True,
                max_files=5,
                label="",
            ) as upload:
                upload.style(
                    "width: 100%; min-height: 200px; border: 2px; border-radius: 12px; "
                    "background-color: #fafafa; transition: all 0.3s ease;"
                )
                upload.props("accept=.mp3,.wav,.flac,.mp4,.mkv,.avi")

            upload_progress = ui.linear_progress(value=0).style(
                "margin-top: 16px; display: none;"
            )

            status_label = ui.label("").style("margin-top: 8px; display: none;")
            ui.separator().style("margin: 24px 0;")

            with ui.row().style("justify-content: flex-end; gap: 12px;"):
                ui.button(
                    "Cancel",
                    icon="close",
                    on_click=lambda: dialog.close(),
                ).props("color=grey-7 flat").style("padding: 8px 16px;")

                ui.button(
                    "Done",
                    icon="check",
                    on_click=lambda: dialog.close(),
                ).props(
                    "color=primary"
                ).style("padding: 8px 16px;")

        dialog.open()


async def handle_upload_with_feedback(
    files, dialog, upload_progress, status_label, upload
):
    """
    Handle file uploads with user feedback and validation.
    """
    upload.visible = False
    upload_progress.style("display: block;")
    status_label.style("display: block;")
    total_files = len(files.names)
    i = 0

    for file, name in zip(files.contents, files.names):
        progress = (i + 1) / total_files
        status_label.set_text(f"Processing {name}... ({i + 1}/{total_files})")

        try:
            await asyncio.to_thread(post_file, file, name)

            ui.notify(f"Successfully uploaded {name}", type="positive", timeout=3000)
        except Exception as e:
            ui.notify(
                f"Failed to upload {name}: {str(e)}", type="negative", timeout=5000
            )

        upload_progress.set_value(progress)
        i += 1

    status_label.set_text("Upload complete!")
    dialog.close()


def table_transcribe(table) -> None:
    """
    Handle the click event on the Transcribe button.
    """
    selected_rows = table.selected
    with ui.dialog() as dialog:
        with ui.card().style(
            "background-color: white; align-self: center; border: 0;"
        ).classes("w-full no-shadow no-border"):
            with ui.row().classes("w-full"):
                ui.label("Transcription Settings").style("width: 100%;").classes(
                    "text-h6 q-mb-md text-primary"
                )
                ui.label(
                    "Select the language, model, and number of speakers for transcription."
                )
                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        label="Select language",
                    ).classes("w-full")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Model").classes("text-subtitle2 q-mb-sm")
                    model = ui.select(
                        settings.WHISPER_MODELS,
                        label="Select model",
                    ).classes("w-full")

                    with ui.expansion("Model Size Information", icon="info").classes(
                        "w-full"
                    ):
                        with ui.column().classes("q-pa-sm"):
                            ui.html(
                                """
                                <div style="font-size: 14px; line-height: 1.5;">
                                    <p><strong>Model sizes and performance:</strong></p>
                                    <ul style="margin: 8px 0; padding-left: 20px;">
                                        <li><strong>tiny:</strong> Fastest processing, lowest accuracy. Good for quick drafts or low-quality audio.</li>
                                        <li><strong>base:</strong> Balanced speed and accuracy. Suitable for most general use cases.</li>
                                        <li><strong>small:</strong> Better accuracy than base, moderate processing time. Good for important transcriptions.</li>
                                        <li><strong>medium:</strong> High accuracy, longer processing time. Recommended for professional work.</li>
                                        <li><strong>large:</strong> Highest accuracy, longest processing time. Best for critical transcriptions requiring maximum precision.</li>
                                    </ul>
                                    <p style="margin-top: 12px; color: #666; font-style: italic;">
                                        💡 <strong>Tip:</strong> Larger models provide significantly better results but will take considerably longer to process.
                                        Choose based on your quality requirements and available time.
                                    </p>
                                </div>
                            """
                            )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers (0 for automatic)").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0").classes("w-full")
                    ui.label(
                        "Set to 0 for automatic speaker detection, or specify the exact number if known"
                    ).classes("text-caption text-grey-6 q-mt-xs")

            with ui.row():
                ui.button(
                    "Start",
                    icon="play_circle_filled",
                    on_click=lambda: start_transcription(
                        selected_rows,
                        language.value,
                        model.value,
                        speakers.value,
                        dialog,
                    ),
                ).props("color=primary")
                ui.button(
                    "Cancel",
                    icon="cancel",
                ).on("click", lambda: dialog.close())
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
                "text-h6 q-mb-md text-primary"
            )
            ui.separator()
            with ui.row().classes("justify-end"):
                ui.button(
                    "Delete",
                    icon="delete",
                    on_click=lambda: __delete_files(selected_rows, dialog),
                ).props("color=negative")
                ui.button(
                    "Cancel",
                    icon="cancel",
                ).on("click", lambda: dialog.close())

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
    rows: list, language: str, model: str, speakers: str, dialog: ui.dialog
) -> None:
    # Get selected values
    selected_language = language
    selected_model = model

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

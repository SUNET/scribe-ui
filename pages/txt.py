import requests

from nicegui import ui
from utils.common import API_URL
from utils.common import get_auth_header
from utils.common import page_init
from utils.common import default_styles

from utils.video import create_video_proxy
from utils.transcript import TranscriptEditor

create_video_proxy()


def export_file(data: str, filename: str) -> None:
    ui.download.content(data, filename)


def save_file(job_id: str, data: str) -> None:
    data["format"] = "json"
    headers = get_auth_header()
    headers["Content-Type"] = "application/json"
    requests.put(
        f"{API_URL}/api/v1/transcriber/{job_id}/result",
        headers=headers,
        json=data,
    )

    ui.notify(
        "File saved successfully",
        type="positive",
        position="bottom",
        icon="check_circle",
    )


def create() -> None:
    @ui.page("/txt")
    def result(uuid: str, filename: str, language: str, model: str) -> None:
        page_init()

        ui.add_head_html(default_styles)

        try:
            response = requests.get(
                f"{API_URL}/api/v1/transcriber/{uuid}/result/txt",
                headers=get_auth_header(),
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            ui.notify(f"Error: Failed to get result: {e}", type="negative")
            return

        data = response.json()
        editor = TranscriptEditor(data["result"])

        ui.add_css(".q-editor__toolbar { display: none }")

        with ui.footer().style("background-color: #f5f5f5;"):
            with ui.row().classes("justify-end w-full gap-2"):
                with ui.button("Close", icon="close").props("flat") as close_button:
                    close_button.classes("cancel-style")
                    close_button.on("click", lambda: ui.navigate.to("/home"))

                ui.button("Save", icon="save").on_click(
                    lambda: save_file(uuid, editor.get_json_data())
                ).classes("button-default-style")
                ui.button("Export", icon="share").style("width: 150px;").on_click(
                    lambda: export_file(
                        editor.get_export_data(),
                        f"{filename}.txt",
                    )
                ).classes("button-default-style")

        with ui.splitter(value=60).classes("w-full h-screen") as splitter:
            with splitter.before:
                with ui.scroll_area().style("height: calc(100vh - 200px);"):
                    editor.render()

            with splitter.after:
                with ui.card().classes("w-full h-full"):
                    video = ui.video(
                        f"/video/{uuid}",
                        controls=True,
                        autoplay=False,
                        loop=False,
                    ).classes("w-full")

                    editor.set_video_player(video)
                    video.on(
                        "timeupdate",
                        lambda: editor.select_segment_from_video(autoscroll.value),
                    )
                    autoscroll = ui.switch("Autoscroll")
                    video.style("align-self: flex-start;")

                    ui.label(filename).classes("text-h6").style("align-self: center;")
                    ui.html(f"<b>Transcription language:</b> {language}").classes(
                        "text-sm"
                    )
                    ui.html(f"<b>Transcription accuracy:</b> {model}").classes(
                        "text-sm"
                    )

import requests

from nicegui import ui
from utils.common import API_URL
from utils.common import get_auth_header
from utils.common import page_init
from utils.common import default_styles
from utils.video import create_video_proxy
from utils.srt import SRTEditor

create_video_proxy()


def save_srt(job_id: str, data: str, editor: SRTEditor) -> None:
    jsondata = {"format": "srt", "data": data}
    headers = get_auth_header()
    headers["Content-Type"] = "application/json"
    requests.put(
        f"{API_URL}/api/v1/transcriber/{job_id}/result",
        headers=headers,
        json=jsondata,
    )

    ui.notify(
        "File saved successfully",
        type="positive",
        position="bottom",
        icon="check_circle",
    )


def create() -> None:
    @ui.page("/srt")
    def result(uuid: str, filename: str, model: str, language: str) -> None:
        """
        Display the result of the transcription job.
        """
        page_init()

        ui.add_head_html(default_styles)

        try:
            response = requests.get(
                f"{API_URL}/api/v1/transcriber/{uuid}/result/srt",
                headers=get_auth_header(),
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            ui.notify(f"Error: Failed to get result: {e}")
            return

        with ui.footer().style("background-color: #f5f5f5;"):

            def export(srt_format: str):
                if srt_format == "srt":
                    srt_content = editor.export_srt()
                elif srt_format == "vtt":
                    srt_content = editor.export_vtt()

                ui.download(srt_content.encode(), filename=f"{filename}.{srt_format}")
                ui.notify("File exported successfully", type="positive")

            with ui.row().classes("justify-end w-full gap-2"):
                with ui.button("Close", icon="close").props("flat") as close_button:
                    close_button.classes("cancel-style")
                    close_button.on("click", lambda: ui.navigate.to("/home"))

                with ui.button("Save", icon="save") as save_button:
                    save_button.classes("button-default-style")
                    save_button.props("flat")
                    save_button.on(
                        "click",
                        lambda: save_srt(uuid, editor.export_srt(), editor),
                    )
                    save_button.props("color=primary flat")

                with ui.dropdown_button("Export", icon="share") as export_button:
                    export_button.props("flat")
                    export_button.classes("button-default-style")

                    export_button_srt = ui.button("Export as SRT", icon="share")
                    export_button_srt.props("flat")
                    export_button_srt.classes("button-default-style")
                    export_button_srt.on("click", lambda: export("srt"))

                    export_button_vtt = ui.button("Export as VTT", icon="share").style(
                        "width: 150px;"
                    )
                    export_button_vtt.props("flat")
                    export_button_vtt.classes("button-default-style")
                    export_button_vtt.on("click", lambda: export("vtt"))

                with ui.button("Validate", icon="check").props(
                    "flat"
                ) as validate_button:
                    validate_button.classes("button-default-style")
                    validate_button.on(
                        "click",
                        lambda: editor.validate_captions(),
                    )

        with ui.splitter(value=60).classes("w-full h-full") as splitter:
            with splitter.before:
                with ui.card().classes("w-full h-full"):
                    editor = SRTEditor()
                    editor.create_search_panel()
                    with ui.scroll_area().style("height: calc(100vh - 200px);"):
                        editor.main_container = ui.column().classes("w-full h-full")
                    editor.parse_srt(data["result"])
                    editor.refresh_display()
                with splitter.after:
                    with ui.card().classes("w-full h-full"):
                        video = ui.video(
                            f"/video/{uuid}",
                            controls=True,
                            autoplay=False,
                            loop=False,
                        ).classes("w-full h-full")
                        editor.set_video_player(video)
                        video.on(
                            "timeupdate",
                            lambda: editor.select_caption_from_video(autoscroll.value),
                        )
                        autoscroll = ui.switch("Autoscroll")
                        with ui.column().classes("bg-gray-100 p-4 w-full"):
                            ui.label(filename).classes("text-h6").style(
                                "align-self: center;"
                            )
                            ui.html(
                                f"<b>Transcription language:</b> {language}"
                            ).classes("text-sm")
                            ui.html(f"<b>Transcription accuracy:</b> {model}").classes(
                                "text-sm"
                            )
                            html_wpm = ui.html(
                                f"<b>Words per minute:</b> {editor.get_words_per_minute():.2f}"
                            ).classes("text-sm")
                            editor.set_words_per_minute_element(html_wpm)

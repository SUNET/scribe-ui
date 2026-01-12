import requests

from nicegui import app, ui
from utils.common import default_styles
from utils.common import get_auth_header
from utils.common import page_init
from utils.settings import get_settings
from utils.srt import SRTEditor
from utils.video import create_video_proxy

create_video_proxy()

settings = get_settings()


def save_srt(job_id: str, data: str, editor: SRTEditor, data_format: str) -> None:
    try:
        jsondata = {"format": data_format, "data": data}

        headers = get_auth_header()
        headers["Content-Type"] = "application/json"
        res = requests.put(
            f"{settings.API_URL}/api/v1/transcriber/{job_id}/result",
            headers=headers,
            json=jsondata,
        )
        res.raise_for_status()
    except requests.exceptions.RequestException as e:
        ui.notify(f"Error: Failed to save file: {e}", type="negative")
        return

    ui.notify(
        "File saved successfully",
        type="positive",
        position="bottom",
        icon="check_circle",
    )


def create() -> None:
    @ui.page("/srt")
    def result(
        uuid: str, filename: str, model: str, language: str, data_format: str
    ) -> None:
        """
        Display the result of the transcription job.
        """
        page_init()
        editor = SRTEditor(uuid, data_format)
        editor.setup_beforeunload_warning()

        ui.add_head_html(
            f"<link rel='preload' as='video' href='/video/{uuid}' type='video/mp4'>"
        )
        ui.add_head_html(default_styles)
        ui.keyboard(on_key=editor.handle_key_event)

        try:
            if data_format == "srt":
                response = requests.get(
                    f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/srt",
                    headers=get_auth_header(),
                    json={
                        "encryption_password": app.storage.user.get(
                            "encryption_password"
                        )
                    },
                )
            else:
                response = requests.get(
                    f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/txt",
                    headers=get_auth_header(),
                    json={
                        "encryption_password": app.storage.user.get(
                            "encryption_password"
                        )
                    },
                )

            response.raise_for_status()
            data = response.json()

        except requests.exceptions.RequestException as e:
            ui.notify(f"Error: Failed to get result: {e}")
            return

        with ui.footer().style("background-color: #f5f5f5;"):

            def export(srt_format: str):
                match srt_format:
                    case "srt":
                        srt_content = editor.export_srt()
                    case "vtt":
                        srt_content = editor.export_vtt()
                    case "txt":
                        srt_content = editor.export_txt()
                    case "json":
                        srt_content = editor.export_json()
                    case "rtf":
                        srt_content = editor.export_rtf()
                    case "csv":
                        srt_content = editor.export_csv()
                    case "tsv":
                        srt_content = editor.export_tsv()

                ui.download(
                    str(srt_content).encode(), filename=f"{filename}.{srt_format}"
                )

                ui.notify("File exported successfully", type="positive")

        with ui.row().classes("justify-between w-full gap-2"):
            with ui.column().classes("flex-row items-center"):
                editor.create_undo_redo_panel()
                with ui.button("Save", icon="save") as save_button:
                    if data_format == "srt":
                        save_button.on(
                            "click",
                            lambda: save_srt(
                                uuid,
                                editor.export_srt(),
                                editor,
                                data_format,
                            ),
                        )
                    else:
                        save_button.on(
                            "click",
                            lambda: save_srt(
                                uuid,
                                editor.export_json(),
                                editor,
                                "json",
                            ),
                        )

                    save_button.props("color=black flat")

                with ui.dropdown_button("Export", icon="download") as export_button:
                    export_button.props("flat color=black")

                    if data_format == "srt":
                        export_button_srt = ui.button("Export as SRT", icon="download")
                        export_button_srt.props("flat color=white")
                        export_button_srt.classes("button-default-style")
                        export_button_srt.on("click", lambda: export("srt"))

                        export_button_vtt = ui.button(
                            "Export as VTT", icon="download"
                        ).style("width: 150px;")
                        export_button_vtt.props("flat color=white")
                        export_button_vtt.classes("button-default-style")
                        export_button_vtt.on("click", lambda: export("vtt"))
                    else:
                        export_button_txt = ui.button("Export as TXT", icon="download")
                        export_button_txt.props("flat color=white")
                        export_button_txt.classes("button-default-style")
                        export_button_txt.on("click", lambda: export("txt"))

                        export_button_json = ui.button(
                            "Export as JSON", icon="download"
                        )
                        export_button_json.props("flat color=white")
                        export_button_json.classes("button-default-style")
                        export_button_json.on("click", lambda: export("json"))

                        export_button_rtf = ui.button("Export as RTF", icon="download")
                        export_button_rtf.props("flat color=white")
                        export_button_rtf.classes("button-default-style")
                        export_button_rtf.on("click", lambda: export("rtf"))

                        export_button_csv = ui.button("Export as CSV", icon="download")
                        export_button_csv.props("flat color=white")
                        export_button_csv.classes("button-default-style")
                        export_button_csv.on("click", lambda: export("csv"))

                        export_button_tsv = ui.button("Export as TSV", icon="download")
                        export_button_tsv.props("flat color=white")
                        export_button_tsv.classes("button-default-style")
                        export_button_tsv.on("click", lambda: export("tsv"))

                if data_format == "srt":
                    with ui.button("Validate", icon="check").props(
                        "flat color=black"
                    ) as validate_button:
                        validate_button.on(
                            "click",
                            lambda: editor.validate_captions(),
                        )
                editor.create_search_panel()
            with ui.column().classes("flex-row items-center"):
                with ui.row().classes("gap-2"):
                    with ui.button("", icon="close").props(
                        "flat color=black"
                    ) as close_button:
                        close_button.classes("cancel-style").style("border: 0;")
                        close_button.on("click", lambda: editor.close_editor("/home"))

        with ui.splitter(value=60).classes("w-full h-full") as splitter:
            with splitter.before:
                with ui.card().classes("w-full h-full"):
                    with ui.scroll_area().style("height: calc(90vh - 200px);"):
                        editor.main_container = ui.column().classes("w-full h-full")

                    if data_format == "srt":
                        editor.parse_srt(data["result"])
                    else:
                        editor.parse_txt(data["result"])

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
                        video.props("preload='auto'")
                        video.on(
                            "timeupdate",
                            lambda: editor.select_caption_from_video(),
                        )
                        autoscroll = ui.switch("Autoscroll")
                        autoscroll.on(
                            "click", lambda: editor.set_autoscroll(autoscroll.value)
                        )
                        with ui.column().classes("bg-gray-100 p-4 w-full"):
                            ui.label(filename).classes("text-h6").style(
                                "align-self: center;"
                            )
                            ui.html(
                                f"<b>Transcription language:</b> {language}",
                                sanitize=False,
                            ).classes("text-sm")
                            html_wpm = ui.html(
                                f"<b>Words per minute:</b> {editor.get_words_per_minute():.2f}",
                                sanitize=False,
                            ).classes("text-sm")
                            editor.set_words_per_minute_element(html_wpm)

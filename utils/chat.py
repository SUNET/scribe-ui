import asyncio
import json
import ssl
import websockets

from nicegui import app, ui
from utils.settings import get_settings

settings = get_settings()


class InferenceActions:
    """
    Action buttons component for performing inference tasks on transcription data.
    """

    ACTIONS = {
        "summarize": {
            "label": "Summarize",
            "icon": "summarize",
            "prompt": "Please provide a concise summary of the following transcription:",
        },
        "key_points": {
            "label": "Key Points",
            "icon": "list",
            "prompt": "Extract the key points and main topics from this transcription:",
        },
        "action_items": {
            "label": "Action Items",
            "icon": "checklist",
            "prompt": "Identify any action items, tasks, or to-dos mentioned in this transcription:",
        },
    }

    def __init__(self, data: dict, language: str = "en"):
        self.data = data
        self.language = language
        self.result_container = None
        self.loading = False

    def create_ui(self) -> None:
        """
        Create the action buttons UI.
        """
        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("w-full gap-2 flex-wrap"):
                for action_key, action_config in self.ACTIONS.items():
                    ui.button(
                        action_config["label"],
                        icon=action_config["icon"],
                        on_click=lambda a=action_key: self._execute_action(a),
                    ).props("flat color=primary")

            self.result_container = (
                ui.column()
                .classes("w-full gap-2 p-2 bg-gray-50 rounded")
                .style("min-height: 100px; max-height: 300px; overflow-y: auto;")
            )

    async def _execute_action(self, action_key: str) -> None:
        """
        Execute an inference action.
        """
        if self.loading:
            ui.notify("Please wait for the current action to complete", type="warning")
            return

        self.loading = True
        action = self.ACTIONS[action_key]

        self.result_container.clear()
        with self.result_container:
            spinner = ui.spinner("dots", size="lg")
            ui.label(f"Processing {action['label'].lower()}...")

        # Prepare the data
        data_str = self.data if isinstance(self.data, str) else json.dumps(self.data)
        message = f"{action['prompt']} Respond in the language: {self.language}\n\n{data_str}"

        token = app.storage.user.get("token")
        if not token:
            self._show_result("Error: Not authenticated", is_error=True)
            self.loading = False
            return

        ws_url = f"{settings.API_WS_URL}/api/v1/inference?token={token}"

        try:
            if "wss" in ws_url:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            else:
                ssl_context = None

            async with websockets.connect(ws_url, ssl=ssl_context) as websocket:
                await websocket.send(json.dumps({"message": message}))
                response = await asyncio.wait_for(websocket.recv(), timeout=600.0)

                data = json.loads(response)
                result = data.get("result", "No response")
                self._show_result(result)
        except asyncio.TimeoutError:
            self._show_result("Error: Request timed out", is_error=True)
        except Exception as e:
            self._show_result(f"Error: {str(e)}", is_error=True)
        finally:
            self.loading = False

    def _show_result(self, content: str, is_error: bool = False) -> None:
        """
        Display the result in the result container.
        """
        if not self.result_container:
            return

        self.result_container.clear()

        with self.result_container:
            if is_error:
                ui.label(content).classes("text-red-700 text-sm")
            else:
                ui.markdown(content).classes("text-sm")

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

    BASE_PROMPT = """Do not ask if I have any further questions or further details. "
You are assisting with producing clear and neutral written documentation based on spoken academic content.

The content may originate from a lecture, a discussion, a presentation or an interview.

The output is intended for internal use in a university context and should be easy to read, review, and edit.

Output requirements:
- Write only the requested content.
- Do not include greetings, introductions, or meta commentary.
- Do not explain what the text is or what you are about to do.
- Start directly with the content itself.
"""

    ACTIONS = {
        "summarize": {
            "label": "Summary",
            "icon": "summarize",
            "prompt": BASE_PROMPT
            + "Please provide a concise summary of the following transcription:",
        },
        "key_points": {
            "label": "Key Points",
            "icon": "list",
            "prompt": BASE_PROMPT
            + "Extract the key points and main topics from this transcription:",
        },
        "action_items": {
            "label": "Action Items",
            "icon": "checklist",
            "prompt": BASE_PROMPT
            + "Identify any action items, tasks, or to-dos mentioned in this transcription:",
        },
        "study_notes": {
            "label": "Study Notes",
            "icon": "school",
            "prompt": BASE_PROMPT
            + """You are writing study notes based on a university lecture.

The notes are intended to help a student understand and review the material afterwards.
They should be clear, practical, and easy to revisit.

Base the notes strictly on the provided transcript.
Do not add interpretations, opinions, or external knowledge.
If something is unclear or unfinished in the lecture, reflect that uncertainty rather than filling in gaps.

Focus on:
key concepts and definitionsexplanations and reasoningexamples explicitly mentioned by the lecturerhow ideas relate to each other

Use bullet points and short paragraphs.
Write in a clear, informal-academic tone suitable for study notes.
Avoid formal report or protocol language.

Write only the notes themselves.
Do not include introductions, greetings, or meta commentary.
Start directly with the content.""",
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
        with ui.column().classes("w-full h-full gap-2"):
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
                .style("min-height: 100px; flex: 1; overflow-y: auto;")
            )

            ui.label(
                "Note: AI-generated content may contain errors or misinterpretations. "
                "Always verify against the original recording or transcript."
            ).classes("text-xs text-gray-500 italic mt-2")

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
            ui.spinner("dots", size="lg")
            ui.label(f"Generating {action['label'].lower()}...")

        # Prepare the data
        try:
            data_str = json.loads(self.data["result"])
            data_str = data_str["full_transcription"]
        except Exception:
            data_str = self.data["result"]

        message = (
            f" Respond in {self.language} and follow these rules: {action['prompt']}"
        )
        message += f"\n\n{data_str}"

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

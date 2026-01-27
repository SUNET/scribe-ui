import asyncio
import websockets

from nicegui import app, ui
from utils.settings import get_settings

settings = get_settings()


class InferenceChat:
    """
    Chat component for communicating with the inference WebSocket endpoint.
    """

    def __init__(self, data: str):
        self.messages: list[dict] = []
        self.message_container = None
        self.input_field = None
        self.connected = False
        self.ws_task = None
        self.data = data

    def create_ui(self) -> None:
        """
        Create the chat UI components.
        """
        with ui.column().classes("w-full gap-2"):
            self.message_container = (
                ui.column()
                .classes("w-full gap-2 p-2 bg-gray-50 rounded")
                .style("height: 200px; overflow-y: auto;")
            )

            with ui.row().classes("w-full gap-2"):
                self.input_field = (
                    ui.input(placeholder="Type a message...")
                    .classes("flex-grow")
                    .on("keydown.enter", self._send_message)
                )
                ui.button(icon="send", on_click=self._send_message).props(
                    "flat color=primary"
                )

    async def _send_message(self) -> None:
        """
        Send a message to the inference endpoint via WebSocket.
        """
        if isinstance(self.data, dict):
            # Convert dict to string
            self.data = str(self.data)

        message = (
            "This is the initial data: "
            + self.data
            + "Now the message from the user follows: "
        )
        message = self.input_field.value
        if not message or not message.strip():
            return

        self.input_field.value = ""

        # Add user message to chat
        self._add_message("user", message)

        # Send via WebSocket
        token = app.storage.user.get("token")
        if not token:
            self._add_message("system", "Error: Not authenticated")
            return

        ws_url = f"{settings.API_WS_URL}/api/v1/inference?token={token}"

        try:
            async with websockets.connect(ws_url) as websocket:
                await websocket.send('{"message": "' + message + '"}')
                response = await asyncio.wait_for(websocket.recv(), timeout=300.0)

                import json

                data = json.loads(response)
                result = data.get("result", "No response")
                self._add_message("assistant", result)
        except asyncio.TimeoutError:
            self._add_message("system", "Error: Request timed out")
        except Exception as e:
            self._add_message("system", f"Error: {str(e)}")

    def _add_message(self, role: str, content: str) -> None:
        """
        Add a message to the chat display.

        Parameters:
            role (str): The role of the message sender (user, assistant, system).
            content (str): The message content.
        """
        self.messages.append({"role": role, "content": content})
        self._refresh_messages()

    def _refresh_messages(self) -> None:
        """
        Refresh the message display.
        """
        if not self.message_container:
            return

        self.message_container.clear()

        with self.message_container:
            for msg in self.messages:
                role = msg["role"]
                content = msg["content"]

                if role == "user":
                    with ui.row().classes("w-full justify-end"):
                        ui.label(content).classes(
                            "bg-blue-100 p-2 rounded-lg max-w-xs text-sm"
                        )
                elif role == "assistant":
                    with ui.row().classes("w-full justify-start"):
                        ui.label(content).classes(
                            "bg-green-100 p-2 rounded-lg max-w-xs text-sm"
                        )
                else:
                    with ui.row().classes("w-full justify-center"):
                        ui.label(content).classes(
                            "bg-red-100 p-2 rounded-lg max-w-xs text-sm text-red-700"
                        )

            # Scroll to bottom
            ui.run_javascript(
                f"document.querySelector(\"[id='{self.message_container.id}']\").scrollTop = "
                f"document.querySelector(\"[id='{self.message_container.id}']\").scrollHeight"
            )

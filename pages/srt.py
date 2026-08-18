# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import httpx

from html import escape as html_escape
from uuid import UUID

from nicegui import app, ui
from utils.common import get_auth_header
from utils.styles import default_styles
from utils.common import page_init
from utils.helpers import storage_decrypt
from utils.settings import get_settings
from utils.srt import (
    AUTOSCROLL_KEY,
    DEFAULT_REVIEW_SENSITIVITY,
    EDITS_SHOW_KEY,
    REVIEW_SENSITIVITY_KEY,
    REVIEW_SHOW_KEY,
    SRTEditor,
)
from utils.transcript_editor import TranscriptEditor
from utils.video import create_video_proxy

create_video_proxy()

settings = get_settings()


def create() -> None:
    @ui.page("/srt")
    def result(
        uuid: str, filename: str, model: str, language: str, data_format: str
    ) -> None:
        """
        Display the result of the transcription job.
        """
        page_init(use_drawer=True)

        try:
            UUID(uuid)
        except (ValueError, TypeError):
            ui.label("Invalid job identifier.").classes("text-h6")
            return

        editor = SRTEditor(uuid, data_format, filename)
        editor.setup_beforeunload_warning()

        ui.add_head_html(
            f"<link rel='preload' as='video' href='/video/{uuid}' type='video/mp4'>"
        )
        ui.add_head_html(
            """
        <script>
        window.addEventListener('keydown', function(e) {
            // Block Cmd + z / Ctrl + z for undo
            if ((e.metaKey || e.ctrlKey) && ! e.shiftKey && e.key.toLowerCase() === 'z') {
                e.preventDefault();
            }

            // Block Cmd + s / Ctrl + s, which would save the page
            if ((e.metaKey || e.ctrlKey) && ! e.shiftKey && e.key.toLowerCase() === 's') {
                e.preventDefault();
            }

            // Block Cmd + y / Ctrl + y for redo
            if ((e.metaKey || e.ctrlKey) && ! e.shiftKey && e.key.toLowerCase() === 'y') {
                e.preventDefault();
            }

            // Block Cmd + Shift + z / Ctrl + Shift + z for redo
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'z') {
                e.preventDefault();
            }

            // Block Ctrl + f / Cmd + f for find
            if ((e.metaKey || e.ctrlKey) && ! e.shiftKey && e.key.toLowerCase() === 'f') {
                e.preventDefault();
            }

            // Block Ctrl + e / Cmd + e for search
            if ((e.metaKey || e.ctrlKey) && ! e.shiftKey && e.key.toLowerCase() === 'e') {
                e.preventDefault();
            }

            // Handle Escape key globally (even when video player has focus)
            if (e.key === 'Escape' && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
                // Blur active element
                if (document.activeElement && typeof document.activeElement.blur === 'function') {
                    document.activeElement.blur();
                }
                // Dispatch custom event that Python can listen to
                window.dispatchEvent(new CustomEvent('escape-pressed'));
            }
        }, true);
        </script>
        """
        )
        ui.add_head_html(default_styles)
        ui.keyboard(on_key=editor.handle_key_event, ignore=[])

        try:
            if data_format == "srt":
                response = httpx.request(
                    "GET",
                    f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/srt",
                    headers=get_auth_header(),
                    json={
                        "encryption_password": storage_decrypt(
                            app.storage.user.get("encryption_password"),
                        )
                    },
                )
            else:
                response = httpx.request(
                    "GET",
                    f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/txt",
                    headers=get_auth_header(),
                    json={
                        "encryption_password": storage_decrypt(
                            app.storage.user.get("encryption_password"),
                        )
                    },
                )

            response.raise_for_status()
            data = response.json()

        except httpx.HTTPError as e:
            ui.notify(f"Error: Failed to get result: {e}")
            return

        # Per-word timings are optional: jobs transcribed before they existed
        # simply have none, and the editor stays fully usable without them.
        try:
            words_response = httpx.request(
                "GET",
                f"{settings.API_URL}/api/v1/transcriber/{uuid}/words",
                headers=get_auth_header(),
                json={
                    "encryption_password": storage_decrypt(
                        app.storage.user.get("encryption_password"),
                    )
                },
            )
            words_response.raise_for_status()
            editor.load_words(words_response.json().get("result"))
        except (httpx.HTTPError, ValueError):
            editor.load_words(None)

        # Restore the review preferences before the captions are rendered, so
        # the first paint already reflects them rather than flashing unmarked.
        editor.restore_review_state(
            app.storage.user.get(REVIEW_SHOW_KEY, False),
            app.storage.user.get(REVIEW_SENSITIVITY_KEY, DEFAULT_REVIEW_SENSITIVITY),
            app.storage.user.get(EDITS_SHOW_KEY, False),
        )
        editor.set_autoscroll(app.storage.user.get(AUTOSCROLL_KEY, False))
        editor.set_highlight_word(editor.autoscroll)

        with ui.row().classes("justify-between w-full gap-2"):
            with ui.column().classes("flex-row items-center"):
                editor.create_undo_redo_panel()
                with ui.button("Save", icon="save") as save_button:
                    save_button.on("click", lambda: editor.save_srt_changes())
                    save_button.props("flat").classes("editor-btn editor-toolbar-btn")

                # Export button - opens dialog
                ui.button("Export", icon="download").props("flat").classes(
                    "editor-btn editor-toolbar-btn"
                ).on("click", lambda: editor.show_export_dialog(filename))

                if data_format == "srt":
                    with ui.button("Validate", icon="check").props(
                        "flat"
                    ).classes("editor-btn editor-toolbar-btn") as validate_button:
                        validate_button.on(
                            "click",
                            lambda: editor.validate_captions(),
                        )
                editor.create_search_panel()
                editor.show_keyboard_shortcuts()
            with ui.button("Close editor", icon="close").props(
                "flat"
            ).classes("editor-btn editor-toolbar-btn") as close_button:
                close_button.on("click", lambda: editor.close_editor("/home"))

        # Subtitles get the caption editor; transcriptions get the document
        # editor. Two different jobs, so two different surfaces.
        transcript = TranscriptEditor(editor) if data_format == "txt" else None

        with ui.splitter(value=60).classes("w-full h-full") as splitter:
            with splitter.before:
                with ui.card().classes("w-full h-full"):
                    with ui.scroll_area().style("height: calc(90vh - 100px);"):
                        editor.main_container = ui.column().classes("w-full h-full")

                        if data_format == "srt":
                            editor.parse_srt(data["result"])
                            editor.refresh_display()
                        else:
                            editor.parse_txt(data["result"])
                            transcript.build()
                            # Apply the restored autoscroll preference to the
                            # new editor, not just to later clicks.
                            transcript.set_follow(editor.autoscroll)
                            transcript.body.set_highlight_word(editor.highlight_word)
                            transcript.body.set_show_edits(editor.show_my_edits)
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
                        if transcript is None:
                            video.on(
                                "timeupdate",
                                lambda: editor.select_caption_from_video(),
                            )
                        else:

                            async def follow_transcript() -> None:
                                if not editor.autoscroll:
                                    return

                                await transcript.follow_video()

                            video.on("timeupdate", follow_transcript)
                        # Stays None when the result carries no confidence
                        # scores, which is what hides the review controls.
                        uncertain_switch = None

                        with ui.row().classes("items-center gap-4"):

                            def save_follow(event) -> None:
                                value = bool(event.sender.value)
                                editor.set_autoscroll(value)
                                app.storage.user[AUTOSCROLL_KEY] = value

                                if transcript is not None:
                                    transcript.set_follow(value)
                                    transcript.set_highlight_word(value)

                            # Scrolling to the block and marking the word in it
                            # are two halves of one thing -- following the
                            # recording -- so the transcription editor offers
                            # them as one switch. The subtitle editor has no
                            # word marking, so it keeps plain Autoscroll.
                            following_words = transcript is not None and editor.words

                            follow = ui.switch(
                                "Follow audio" if following_words else "Autoscroll",
                                value=editor.autoscroll,
                            )
                            follow.on("click", save_follow)

                            if following_words:
                                with follow:
                                    ui.tooltip(
                                        "Scroll to the block being played and "
                                        "highlight each word as it is spoken"
                                    )

                            # Only offered when the result carries confidence
                            # scores; older jobs have none to show.
                            if editor.has_confidence:

                                def save_show_uncertain(event) -> None:
                                    value = bool(event.sender.value)
                                    editor.set_show_uncertain_words(value)
                                    app.storage.user[REVIEW_SHOW_KEY] = value

                                uncertain_switch = ui.switch(
                                    "Uncertain words",
                                    value=editor.show_uncertain_words,
                                ).classes("review-switch")
                                uncertain_switch.on("click", save_show_uncertain)
                                with uncertain_switch:
                                    ui.tooltip(
                                        "Highlight words that may need review"
                                    )

                            # Offered wherever there are transcribed words to
                            # compare against, with or without confidence
                            # scores: knowing which words came from the
                            # recording is enough to know which ones did not.
                            if editor.words:

                                def save_show_edits(event) -> None:
                                    value = bool(event.sender.value)

                                    if transcript is not None:
                                        transcript.set_show_my_edits(value)
                                    else:
                                        editor.set_show_my_edits(value)

                                    app.storage.user[EDITS_SHOW_KEY] = value

                                edits_switch = ui.switch(
                                    "My edits",
                                    value=editor.show_my_edits,
                                ).classes("edits-switch")
                                edits_switch.on("click", save_show_edits)
                                with edits_switch:
                                    ui.tooltip(
                                        "Highlight words you have changed"
                                    )

                        if uncertain_switch is not None:
                            # Sensitivity only means anything while the
                            # highlighting is on, so it travels with it.
                            with ui.row().classes(
                                "items-center gap-2"
                            ) as sensitivity_row:
                                ui.label("Sensitivity:").classes("text-sm")

                                def save_sensitivity(event) -> None:
                                    editor.set_review_sensitivity(event.sender.value)
                                    # Persist what the editor accepted, so an
                                    # unrecognised value cannot be stored.
                                    app.storage.user[REVIEW_SENSITIVITY_KEY] = (
                                        editor.review_sensitivity
                                    )

                                sensitivity = ui.toggle(
                                    {
                                        "low": "Low",
                                        "medium": "Medium",
                                        "high": "High",
                                    },
                                    value=editor.review_sensitivity,
                                ).props(
                                    "dense unelevated no-caps "
                                    "toggle-color=review-accent "
                                    "toggle-text-color=review-accent-fg"
                                )
                                sensitivity.on("update:model-value", save_sensitivity)
                                with sensitivity:
                                    ui.tooltip(
                                        "How much of the transcription to flag "
                                        "for review"
                                    )

                                flagged = ui.label().classes(
                                    "text-sm text-theme-muted review-count"
                                )
                                editor.set_flagged_count_element(flagged)

                            sensitivity_row.bind_visibility_from(
                                uncertain_switch, "value"
                            )
                        with ui.column().classes("srt-info-panel p-4 w-full"):
                            ui.label(filename).classes("text-h6").style(
                                "align-self: center;"
                            )
                            ui.html(
                                f"<b>Transcription language:</b> {html_escape(language)}",
                                sanitize=False,
                            ).classes("text-sm")
                            html_wpm = ui.html(
                                f"<b>Words per minute:</b> {editor.get_words_per_minute():.2f}",
                                sanitize=False,
                            ).classes("text-sm")
                            editor.set_words_per_minute_element(html_wpm)

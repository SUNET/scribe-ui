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
    OVERLAY_SHOW_KEY,
    REVIEW_SENSITIVITY_KEY,
    REVIEW_SHOW_KEY,
    SRTEditor,
    TIMELINE_SHOW_KEY,
)
from utils.speech_timeline import SpeechTimeline
from utils.transcript_editor import TranscriptEditor
from utils.video import create_video_proxy

create_video_proxy()

settings = get_settings()


def create() -> None:
    # A long reconnect window, unlike every other page: the captions being
    # edited live in this client's own SRTEditor on the server, and when the
    # socket stays down past reconnect_timeout NiceGUI deletes that content
    # and the browser reloads itself when it comes back -- taking every
    # unsaved edit with it. A closed laptop lid, a wifi hop or an idle proxy
    # is enough at the default 15 seconds. Five minutes covers those without
    # keeping abandoned editors alive for long.
    @ui.page("/srt", reconnect_timeout=300)
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

            // Space plays and pauses, unless something is being typed into.
            // Handled here rather than through the page's keyboard handler
            // so that the player answers immediately, with no round trip --
            // and so the check for "is the reader typing" can be made
            // against the real focus, which only the browser knows.
            //
            // A button keeps its own space: a focused button is activated by
            // it, and taking that would break every dialog on the page.
            if (e.key === ' ' && !e.metaKey && !e.ctrlKey && !e.altKey) {
                const active = document.activeElement;
                const typing = active && (
                    active.isContentEditable
                    || ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(active.tagName)
                );

                if (!typing) {
                    const video = document.querySelector('video');

                    if (video) {
                        e.preventDefault();
                        video.paused ? video.play() : video.pause();
                    }
                }
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
            app.storage.user.get(OVERLAY_SHOW_KEY, True),
            app.storage.user.get(TIMELINE_SHOW_KEY, True),
        )
        editor.set_autoscroll(app.storage.user.get(AUTOSCROLL_KEY, False))
        editor.set_highlight_word(editor.autoscroll)

        # Grouped by what each action acts on rather than left as one row of
        # identically sized buttons: history, then the document itself, then
        # the actions that only look at it. Save is the one filled button --
        # it is what the reader came here to do.
        with ui.row().classes(
            "editor-toolbar justify-between w-full gap-2 items-center"
        ):
            with ui.row().classes("editor-toolbar-group"):
                editor.create_undo_redo_panel()

                ui.separator().props("vertical")

                with ui.row().classes("editor-toolbar-group"):
                    with ui.button("Save", icon="save") as save_button:
                        save_button.on("click", lambda: editor.save_srt_changes())
                        save_button.props("flat").classes(
                            "editor-btn editor-toolbar-btn"
                        )

                    # Export button - opens dialog
                    ui.button("Export", icon="download").props("flat").classes(
                        "editor-btn editor-toolbar-btn"
                    ).on("click", lambda: editor.show_export_dialog(filename))

                ui.separator().props("vertical")

                with ui.row().classes("editor-toolbar-group"):
                    editor.create_search_panel()
                    if data_format == "srt":
                        with ui.button("Validate", icon="check").props(
                            "flat"
                        ).classes("editor-btn editor-toolbar-btn") as validate_button:
                            validate_button.on(
                                "click",
                                lambda: editor.validate_captions(),
                            )
                    editor.show_keyboard_shortcuts()

                    # What is open and what is in it. A dialog rather than a
                    # strip of the toolbar: it is read when a reader wonders,
                    # not while they work, and the figures are far easier to
                    # label properly with room to put the labels in.
                    with ui.dialog() as info_dialog, ui.card().classes(
                        "editor-info-card"
                    ):
                        ui.label("Video information").classes("text-h6")
                        ui.separator()

                        figures = {}

                        # Each row is a name, a value and what the value
                        # means. The last three move as the reader edits;
                        # the first two never do.
                        with ui.column().classes("editor-info-rows"):
                            for label, value, explanation in (
                                ("File", filename, None),
                                (
                                    "Language",
                                    language,
                                    "What the recording was transcribed in.",
                                ),
                                (
                                    "Captions",
                                    "captions",
                                    "How many captions the file has."
                                    if data_format == "srt"
                                    else "How many blocks the transcription has.",
                                ),
                                (
                                    "Length",
                                    "duration",
                                    "Where the last caption ends -- which can "
                                    "be short of the recording itself."
                                    if data_format == "srt"
                                    else "Where the last block ends.",
                                ),
                                (
                                    "Reading speed",
                                    "wpm",
                                    "Across the whole result. Around 150 "
                                    "words per minute is ordinary speech.",
                                ),
                            ):
                                with ui.row().classes("editor-info-row"):
                                    ui.label(label).classes("editor-info-label")

                                    with ui.column().classes("editor-info-value"):
                                        # A figure the editor keeps up to
                                        # date is registered by name; the
                                        # fixed ones are drawn as they are.
                                        if value in ("captions", "duration", "wpm"):
                                            figures[value] = ui.label().classes(
                                                "editor-info-figure"
                                            )
                                        else:
                                            ui.label(value).classes(
                                                "editor-info-figure"
                                            )

                                        if explanation:
                                            ui.label(explanation).classes(
                                                "editor-info-explanation"
                                            )

                        editor.set_status_elements(**figures)

                        with ui.row().classes("w-full justify-end"):
                            ui.button("Close", on_click=info_dialog.close).props(
                                "flat"
                            ).classes("editor-btn")

                    ui.button("Info", icon="info").props("flat").classes(
                        "editor-btn editor-toolbar-btn"
                    ).on("click", info_dialog.open)


            with ui.button("Close editor", icon="close").props(
                "flat"
            ).classes("editor-btn editor-toolbar-btn") as close_button:
                close_button.on("click", lambda: editor.close_editor("/home"))

        # One document editor for both formats now; subtitleMode (set in
        # TranscriptEditor.build) is what tells it to drop the speaker margin
        # for a length guideline and a per-caption delete action.
        transcript = TranscriptEditor(editor)

        with ui.splitter(value=60).classes("w-full h-full") as splitter:
            with splitter.before:
                with ui.card().classes("editor-panel w-full h-full"):
                    with ui.scroll_area().style("height: calc(90vh - 100px);"):
                        if data_format == "srt":
                            editor.parse_srt(data["result"])
                        else:
                            editor.parse_txt(data["result"])

                        transcript.build()
                        # Apply the restored autoscroll preference to the new
                        # editor, not just to later clicks.
                        transcript.set_follow(editor.autoscroll)
                        transcript.body.set_highlight_word(editor.highlight_word)
                        transcript.body.set_show_edits(editor.show_my_edits)

                with splitter.after:
                    with ui.card().classes("editor-panel w-full h-full"):
                        with ui.element("div").classes("video-frame w-full h-full"):
                            video = ui.video(
                                f"/video/{uuid}",
                                controls=True,
                                autoplay=False,
                                loop=False,
                            ).classes("w-full h-full")
                            editor.set_video_player(video)
                            video.props("preload='auto'")

                            # Subtitles only -- a transcription's own
                            # blocks are a speaker's whole turn, not a
                            # short timed cue, and would cover half the
                            # video rather than read like a real subtitle.
                            if data_format == "srt":
                                overlay = ui.element("div").classes(
                                    "video-subtitle-overlay"
                                )
                                # The overlay sizes its own type so a line
                                # of the guideline's full length still fits
                                # the frame on one line -- the limit itself
                                # is a setting, so the stylesheet is told
                                # what it is rather than hard-coding it.
                                overlay.style(
                                    "--subtitle-char-limit: "
                                    f"{settings.CHARACTER_LIMIT}"
                                )
                                overlay.set_visibility(False)
                                transcript.set_overlay(overlay)

                                # The overlay clears the player's own control
                                # bar while that bar is up, and drops to the
                                # bottom of the frame -- where a viewer would
                                # actually see it -- once it goes away.
                                #
                                # A browser offers no signal for that, so the
                                # same rules it draws the bar by are followed
                                # here: controls are up while the recording
                                # is paused, and while the pointer has moved
                                # over the frame within the last few seconds.
                                ui.add_head_html(
                                    """
                                    <script>
                                    (function () {
                                      const HIDE_AFTER = 2600;

                                      function wire() {
                                        const frame =
                                          document.querySelector(".video-frame");
                                        const video =
                                          frame && frame.querySelector("video");

                                        if (!video) return false;

                                        let idle = null;

                                        const show = () => {
                                          frame.classList.add(
                                            "video-controls-visible"
                                          );
                                        };
                                        const hide = () => {
                                          if (video.paused) return;
                                          frame.classList.remove(
                                            "video-controls-visible"
                                          );
                                        };

                                        const stir = () => {
                                          show();
                                          clearTimeout(idle);
                                          idle = setTimeout(hide, HIDE_AFTER);
                                        };

                                        frame.addEventListener("mousemove", stir);
                                        frame.addEventListener("mouseleave", hide);
                                        video.addEventListener("pause", show);
                                        video.addEventListener("play", stir);

                                        // Paused when the page opens, so the
                                        // bar is up.
                                        show();

                                        return true;
                                      }

                                      if (!wire()) {
                                        // The player is drawn after this
                                        // script arrives.
                                        const waiting = setInterval(() => {
                                          if (wire()) clearInterval(waiting);
                                        }, 200);
                                        setTimeout(
                                          () => clearInterval(waiting), 10000
                                        );
                                      }
                                    })();
                                    </script>
                                    """
                                )
                                transcript.set_overlay_enabled(
                                    editor.show_subtitle_overlay
                                )

                        # Where speech is, under the video: drawn from the
                        # word timings rather than from the audio, so it
                        # costs no decoding and no second download of the
                        # recording. Nothing to draw without them.
                        #
                        # Subtitles only, the same as the overlay: this is a
                        # tool for timing short cues against speech, and a
                        # transcription's blocks are a speaker's whole turn
                        # -- there is no cue timing to do there, and the
                        # brackets would be minutes wide.
                        timeline = None

                        if data_format == "srt" and editor.words:
                            timeline = SpeechTimeline().classes("w-full")
                            transcript.set_timeline(timeline)
                            # Restored before the first paint, so a reader
                            # who turned it off does not see it flash past.
                            timeline.set_visibility(editor.show_timeline)

                        # Always run, independent of the autoscroll switch
                        # below -- follow_video only moves the editor's own
                        # active block when that is on, but the overlay is
                        # a preview of what a viewer sees, not tied to it.
                        video.on("timeupdate", transcript.follow_video)

                        # The controls under the video are grouped by what
                        # each one affects -- following the recording, and
                        # what the editor marks in the text -- rather than
                        # left as one undifferentiated row of switches with
                        # the sensitivity selector orphaned below them.
                        with ui.column().classes("editor-settings w-full"):
                            with ui.row().classes("items-center gap-4"):

                                def save_follow(event) -> None:
                                    value = bool(event.sender.value)
                                    editor.set_autoscroll(value)
                                    app.storage.user[AUTOSCROLL_KEY] = value
                                    transcript.set_follow(value)
                                    transcript.set_highlight_word(value)

                                # Scrolling to the block and marking the word
                                # in it are two halves of one thing --
                                # following the recording -- so the switch
                                # offers them as one when there is word-level
                                # data to follow, and plain Autoscroll (block
                                # only) when there is not.
                                following_words = bool(editor.words)

                                follow = ui.switch(
                                    "Follow audio" if following_words else "Autoscroll",
                                    value=editor.autoscroll,
                                ).props("dense").classes("editor-switch")
                                follow.on("click", save_follow)

                                if following_words:
                                    with follow:
                                        ui.tooltip(
                                            "Follow playback and highlight the "
                                            "current word."
                                        )

                                # Subtitles only, the same as the overlay
                                # itself. It shows what a viewer sees while
                                # the recording plays, so it belongs here
                                # rather than with the editor's own marking.
                                if data_format == "srt":

                                    def save_show_overlay(event) -> None:
                                        value = bool(event.sender.value)
                                        editor.show_subtitle_overlay = value
                                        app.storage.user[OVERLAY_SHOW_KEY] = value
                                        transcript.set_overlay_enabled(value)

                                    overlay_switch = ui.switch(
                                        "Subtitle overlay",
                                        value=editor.show_subtitle_overlay,
                                    ).props("dense").classes("editor-switch")
                                    overlay_switch.on("click", save_show_overlay)
                                    with overlay_switch:
                                        ui.tooltip(
                                            "Show captions as an overlay on the "
                                            "video."
                                        )

                                # Only when there is a strip to hide: it is
                                # drawn from word timings, and subtitles
                                # only.
                                if timeline is not None:

                                    def save_show_timeline(event) -> None:
                                        value = bool(event.sender.value)
                                        editor.show_timeline = value
                                        app.storage.user[TIMELINE_SHOW_KEY] = value
                                        timeline.set_visibility(value)

                                    timeline_switch = ui.switch(
                                        "Timeline",
                                        value=editor.show_timeline,
                                    ).props("dense").classes("editor-switch")
                                    timeline_switch.on("click", save_show_timeline)
                                    with timeline_switch:
                                        ui.tooltip(
                                            "Show the caption timeline under "
                                            "the video."
                                        )

                                # Offered wherever there are transcribed
                                # words to compare against, with or without
                                # confidence scores: knowing which words came
                                # from the recording is enough to know which
                                # ones did not.
                                if editor.words:

                                    def save_show_edits(event) -> None:
                                        value = bool(event.sender.value)
                                        transcript.set_show_my_edits(value)
                                        app.storage.user[EDITS_SHOW_KEY] = value

                                    edits_switch = ui.switch(
                                        "My edits",
                                        value=editor.show_my_edits,
                                    ).props("dense").classes("editor-switch edits-switch")
                                    edits_switch.on("click", save_show_edits)
                                    with edits_switch:
                                        ui.tooltip(
                                            "Highlight words you have added or "
                                            "changed"
                                        )

                            # One control rather than a switch plus a level:
                            # "off" is just the lowest setting of the same
                            # thing, and splitting them meant two places to
                            # look to find out whether anything was being
                            # flagged at all. Only offered when the result
                            # carries confidence scores; older jobs have none
                            # to show.
                            if editor.has_confidence:
                                ui.separator().classes("my-1")

                                with ui.row().classes("items-center gap-2"):
                                    ui.label("Uncertain words:").classes(
                                        "text-sm text-theme-secondary"
                                    )

                                    def paint_sensitivity(choice) -> None:
                                        """
                                        The review violet belongs to the
                                        levels, not to "Off" -- one
                                        toggle-color paints whichever
                                        segment is selected, which made the
                                        loudest thing in the panel the
                                        setting that marks nothing at all.
                                        """

                                        off = choice == "off"

                                        sensitivity.props(
                                            remove=(
                                                "toggle-color=toggle-off "
                                                "toggle-text-color=toggle-off-fg"
                                                if not off
                                                else "toggle-color=review-accent "
                                                "toggle-text-color=review-accent-fg"
                                            )
                                        )
                                        sensitivity.props(
                                            "toggle-color=toggle-off "
                                            "toggle-text-color=toggle-off-fg"
                                            if off
                                            else "toggle-color=review-accent "
                                            "toggle-text-color=review-accent-fg"
                                        )

                                    def save_sensitivity(event) -> None:
                                        choice = event.sender.value

                                        paint_sensitivity(choice)

                                        # "off" is not one of the editor's own
                                        # sensitivities -- it is the marking
                                        # turned off, with whatever level was
                                        # last chosen left untouched underneath
                                        # so that coming back lands where the
                                        # reader left it.
                                        editor.set_show_uncertain_words(
                                            choice != "off"
                                        )
                                        app.storage.user[REVIEW_SHOW_KEY] = (
                                            choice != "off"
                                        )

                                        if choice == "off":
                                            return

                                        editor.set_review_sensitivity(choice)
                                        # Persist what the editor accepted, so
                                        # an unrecognised value cannot be
                                        # stored.
                                        app.storage.user[REVIEW_SENSITIVITY_KEY] = (
                                            editor.review_sensitivity
                                        )

                                    sensitivity = ui.toggle(
                                        {
                                            "off": "Off",
                                            "low": "Low",
                                            "medium": "Medium",
                                            "high": "High",
                                        },
                                        value=(
                                            editor.review_sensitivity
                                            if editor.show_uncertain_words
                                            else "off"
                                        ),
                                    ).props("dense unelevated no-caps")
                                    paint_sensitivity(
                                        editor.review_sensitivity
                                        if editor.show_uncertain_words
                                        else "off"
                                    )
                                    sensitivity.on(
                                        "update:model-value", save_sensitivity
                                    )
                                    with sensitivity:
                                        ui.tooltip(
                                            "Higher levels also highlight words "
                                            "the model is more certain about."
                                        )

                                    flagged = ui.label().classes(
                                        "text-sm text-theme-muted review-count"
                                    )
                                    editor.set_flagged_count_element(flagged)

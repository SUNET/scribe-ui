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
from utils.common import get_auth_header, page_init
from utils.helpers import storage_decrypt
from utils.settings import get_settings
from utils.srt import SRTEditor
from utils.styles import default_styles
from utils.video import create_video_proxy

create_video_proxy()

settings = get_settings()


# Reading along on a phone: the player at the top, the transcription under
# it, the passage being played marked, and the list scrolled to keep it in
# sight. Written in the page rather than driven from the server, which is
# what the editor does with the same job -- a round trip several times a
# second to move a highlight is not worth taking, and nothing here changes
# any state the server holds.
FOLLOW_SCRIPT = """
<script>
(function () {
  function wire(tries) {
    const video = document.querySelector("video");
    const list = document.querySelector(".view-captions");

    if (!video || !list) {
      if (tries > 0) requestAnimationFrame(() => wire(tries - 1));

      return;
    }

    const captions = Array.from(list.querySelectorAll(".view-caption"));
    let playing = null;

    // A tap on a passage plays it. Its start, not its middle: the reader
    // is asking to hear what it says, and landing halfway through means
    // the first half is never heard without seeking back by hand.
    captions.forEach((caption) => {
      caption.addEventListener("click", () => {
        video.currentTime = parseFloat(caption.dataset.start);
        video.play();
      });
    });

    function mark() {
      const at = video.currentTime;
      const found = captions.find(
        (caption) =>
          at >= parseFloat(caption.dataset.start) &&
          at < parseFloat(caption.dataset.end)
      );

      if (found === playing) return;

      if (playing) playing.classList.remove("is-playing");

      playing = found || null;

      if (!playing) return;

      playing.classList.add("is-playing");

      // Only while the reader has asked to be followed: scrolling the
      // list under somebody who is reading somewhere else in it is the
      // one thing this must not do.
      if (document.body.classList.contains("view-follow")) {
        playing.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    }

    video.addEventListener("timeupdate", mark);
    video.addEventListener("seeked", mark);
  }

  wire(120);
})();
</script>
"""


def create() -> None:
    @ui.page("/view")
    def view(
        uuid: str, filename: str, model: str, language: str, data_format: str
    ) -> None:
        """
        Show a finished transcription without offering to change it.

        What a phone is for here is recording something and starting a
        transcription of it; the editor needs a desk. Reading one back
        does not, so a phone gets this instead of nothing: the recording,
        the text, and a tap on a passage to hear it. Nothing on this page
        writes anything -- there is no editor on the server behind it and
        no save.
        """

        page_init(use_drawer=True)

        try:
            UUID(uuid)
        except (ValueError, TypeError):
            ui.label("Invalid job identifier.").classes("text-h6")
            return

        ui.add_head_html(default_styles)

        # The same fetch the editor makes, and the same parsing: what a
        # caption is -- its timing, its speaker, where the paragraphs fall
        # -- is decided in one place for both pages.
        try:
            route = "srt" if data_format == "srt" else "txt"
            response = httpx.request(
                "GET",
                f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/{route}",
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

        reader = SRTEditor(uuid, data_format, filename)

        if data_format == "srt":
            reader.parse_srt(data["result"])
        else:
            reader.parse_txt(data["result"])

        with ui.column().classes("view-page w-full"):
            with ui.row().classes("view-header w-full items-center"):
                ui.button(
                    icon="arrow_back", on_click=lambda: ui.navigate.to("/home")
                ).props("flat round color=black").tooltip("Back to my files")
                ui.label(filename).classes("view-title")

            with ui.element("div").classes("view-video w-full"):
                # playsinline, or iOS plays every video fullscreen --
                # which on this page means the transcription disappears
                # the moment a passage is tapped, since tapping one plays
                # it. webkit-playsinline is the same thing for older
                # iOS. Both are attributes on the <video> itself; NiceGUI
                # passes anything it does not know as a fallthrough attr.
                ui.video(
                    f"/video/{uuid}", controls=True, autoplay=False, loop=False
                ).classes("w-full").props(
                    "playsinline webkit-playsinline preload='auto'"
                )

            with ui.row().classes("view-controls w-full items-center"):
                follow = ui.switch("Follow audio", value=True)
                follow.on_value_change(
                    lambda event: ui.run_javascript(
                        "document.body.classList.toggle("
                        f"'view-follow', {str(event.value).lower()})"
                    )
                )

                # Said plainly rather than left to be discovered by a
                # reader looking for a way to fix a word: this page shows
                # the transcription, and changing it is a computer's job.
                ui.label("Read-only — open on a computer to edit.").classes(
                    "view-note"
                )

            with ui.column().classes("view-captions w-full"):
                for caption in reader.captions:
                    block = (
                        ui.element("div")
                        .classes("view-caption")
                        .props(
                            f"data-start={caption.get_start_seconds():.3f} "
                            f"data-end={caption.get_end_seconds():.3f}"
                        )
                    )

                    with block:
                        # A subtitle is found by its number and its
                        # timing; a transcription by who is speaking. The
                        # placeholder for a block nobody was assigned to
                        # is not a name and is not shown as one.
                        if data_format == "srt":
                            ui.label(
                                f"#{caption.index}  {caption.start_time}"
                            ).classes("view-caption-meta")
                        elif caption.speaker and caption.speaker != "UNKNOWN":
                            ui.label(caption.speaker).classes("view-caption-meta")

                        # A label, never ui.html: a caption is somebody's
                        # speech, not markup to trust.
                        ui.label(caption.text).classes("view-caption-text")

        # The switch starts on, so the class it toggles has to start on
        # with it -- the page is drawn before any change event fires.
        ui.add_head_html(FOLLOW_SCRIPT)
        ui.add_body_html(
            "<script>document.body.classList.add('view-follow');</script>"
        )

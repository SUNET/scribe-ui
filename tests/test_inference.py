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

"""
What gets sent off to be analysed, and what comes back.

The parts worth pinning down are the two ends: the text taken out of the
editor (subtitles are cut to fit a screen and have to be joined back into
prose, a transcription's speakers carry most of its meaning), and the
answer on the way in, which is a model's reading of somebody's speech and
must never reach the page as markup.
"""

from utils.caption import SRTCaption
from utils.inference import (
    NOTES_SUFFIX,
    answer_language,
    export_document,
    hub_base,
    hub_url,
    plain_text,
    transcript_text,
)
from utils.inference_panel import InferencePanel, safe_markup
from utils.settings import get_settings
from utils.srt import SRTEditor

settings = get_settings()


def editor(data_format: str, *captions: SRTCaption) -> SRTEditor:
    editor = SRTEditor("job-uuid", data_format, "file")
    editor.data_format = data_format
    editor.captions = list(captions)

    return editor


def caption(index: int, text: str, speaker: str = "") -> SRTCaption:
    return SRTCaption(
        index=index,
        start_time="00:00:00,000",
        end_time="00:00:02,000",
        text=text,
        speaker=speaker,
    )


def test_subtitles_are_joined_back_into_prose():
    # A caption break is a line that fits on a screen, not a sentence
    # ending. Sent as lines, the model is handed a column of fragments.
    text = transcript_text(
        editor(
            "srt",
            caption(1, "We begin with\nthe first point"),
            caption(2, "and then move on."),
        )
    )

    assert text == "We begin with the first point and then move on."


def test_empty_captions_are_left_out():
    text = transcript_text(
        editor("srt", caption(1, "Something."), caption(2, "   "), caption(3, "Else."))
    )

    assert text == "Something. Else."


def test_transcription_keeps_its_speakers():
    text = transcript_text(
        editor(
            "txt",
            caption(1, "Shall we start?", speaker="Chair"),
            caption(2, "Please do.", speaker="Guest"),
        )
    )

    assert text == "Chair: Shall we start?\n\nGuest: Please do."


def test_unknown_speaker_is_not_named():
    # "UNKNOWN" is the editor's placeholder for a block nobody has assigned.
    # Sending it would have the model attribute half the meeting to a person
    # called Unknown.
    text = transcript_text(editor("txt", caption(1, "Just text.", speaker="UNKNOWN")))

    assert text == "Just text."


def test_hub_url_follows_the_api(monkeypatch):
    # Empty INFERENCE_URL means "same name as the API", which is how it is
    # behind a reverse proxy.
    monkeypatch.setattr(settings, "INFERENCE_WS_URL", "", raising=False)
    monkeypatch.setattr(settings, "INFERENCE_URL", "", raising=False)
    monkeypatch.setattr(settings, "API_URL", "https://scribe.example.se", raising=False)

    assert hub_url() == "wss://scribe.example.se/api/v1/ws/inference"

    monkeypatch.setattr(settings, "API_URL", "http://localhost:8000/", raising=False)

    assert hub_url() == "ws://localhost:8000/api/v1/ws/inference"


def test_hub_on_its_own_port_is_asked_directly(monkeypatch):
    # Development has no proxy: the API on 8000 answers 404 for anything
    # inference asks it, so both the REST call and the socket have to go to
    # the hub's own port.
    monkeypatch.setattr(settings, "INFERENCE_WS_URL", "", raising=False)
    monkeypatch.setattr(settings, "INFERENCE_URL", "http://localhost:8001", raising=False)
    monkeypatch.setattr(settings, "API_URL", "http://localhost:8000", raising=False)

    assert hub_base() == "http://localhost:8001"
    assert hub_url() == "ws://localhost:8001/api/v1/ws/inference"


def test_configured_hub_url_wins(monkeypatch):
    monkeypatch.setattr(
        settings, "INFERENCE_WS_URL", "wss://hub.example.se/ws", raising=False
    )

    assert hub_url() == "wss://hub.example.se/ws"


def test_model_output_cannot_bring_markup_with_it():
    # The answer describes a transcript, and a transcript is whatever
    # somebody said into a microphone -- including, one day, a tag.
    rendered = safe_markup("<script>alert(1)</script> and <b>bold</b>")

    assert "<script>" not in rendered
    assert "<b>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_markdown_still_works_after_escaping():
    rendered = safe_markup("# Heading\n\n- point one\n- point two\n\n**bold**")

    assert rendered.startswith("# Heading")
    assert "- point one" in rendered
    assert "**bold**" in rendered


def test_the_analyse_strip_uses_theme_tokens_not_fixed_colours():
    """
    The strip sits inside the editor's own card and is read in both themes.
    Every colour it names has to be a custom property, since those are what
    dark mode redefines -- a literal would survive the theme switch and
    leave a light pill on a black card.
    """

    import re

    from utils.styles import default_styles

    css = re.sub(r"/\*.*?\*/", "", default_styles, flags=re.S)

    for match in re.finditer(r"([^{}]*inference[^{}]*)\{([^{}]*)\}", css):
        for declaration in match.group(2).split(";"):
            if ":" not in declaration:
                continue

            name, _, value = declaration.partition(":")

            if name.strip() in ("color", "background", "background-color"):
                assert "var(--color-" in value, f"{match.group(1)}: {declaration}"


def test_every_task_the_hub_offers_gets_a_button_icon():
    # The four modes SUNET/scribe-ui#75 asks for. A task with no icon still
    # gets a button, but these are the row a reader actually sees and each
    # should read at a glance rather than as another similar word.
    from utils.inference_panel import TASK_ICONS

    assert set(TASK_ICONS) == {
        "summary",
        "key_points",
        "action_items",
        "study_notes",
    }
    assert set(TASK_ICONS) == set(NOTES_SUFFIX)


def test_the_download_is_named_after_the_task_that_produced_it():
    class Stub:
        filename = "lecture 3 (final).mp4"
        current_task = "study_notes"

        _download_name = InferencePanel._download_name

    # Never the transcript's own name: the two land in the same downloads
    # folder and an assistant's notes must not be mistakable for the
    # transcription.
    assert Stub()._download_name("txt") == "lecture 3 (final)-study-notes.txt"
    assert Stub()._download_name("md") == "lecture 3 (final)-study-notes.md"


def test_the_job_language_is_cut_back_to_the_language_itself():
    # "(verbatim)" is a transcription mode and "(Experimental)" is a note
    # about our support for the language. Neither is something to ask a
    # model to write in.
    assert answer_language("Swedish") == "Swedish"
    assert answer_language("Swedish (verbatim)") == "Swedish"
    assert answer_language("Northern Sámi (Experimental)") == "Northern Sámi"


def test_a_job_with_no_language_names_none():
    # The hub then falls back to asking for the transcript's own language,
    # which is the weaker instruction but the only one available.
    assert answer_language("") is None
    assert answer_language(None) is None


def test_the_language_survives_the_hub_pattern():
    # The hub refuses a language that does not match its own pattern, so a
    # name this side produces must get through it.
    import re

    pattern = re.compile(r"^[\w \-()]{1,32}$", re.UNICODE)

    for name in get_settings().WHISPER_LANGUAGES:
        cleaned = answer_language(name)
        assert cleaned and pattern.match(cleaned), name


def test_markdown_becomes_readable_plain_text():
    # A .txt full of ## and ** is a worse read than the page it came from:
    # the marks are instructions to a renderer, not content.
    text = plain_text("## Metoden\n\n*   **Acceptera** det\n-   Börja *smått*\n")

    assert "Metoden" in text
    assert "#" not in text
    assert "*" not in text
    assert "- Acceptera det" in text
    assert "- Börja smått" in text


def test_the_export_says_what_it_is():
    # Acceptance criterion in SUNET/scribe-ui#75: exported assistant output
    # has to be clearly separated from the transcript, and the file has to
    # say so by itself -- away from the page that produced it.
    for plain in (True, False):
        document = export_document(
            task_label="Action items",
            filename="board meeting.mp4",
            answer="- Book the room",
            plain=plain,
        )

        assert "Action items" in document
        assert "board meeting.mp4" in document
        assert "Not part of the transcript." in document
        assert "Book the room" in document

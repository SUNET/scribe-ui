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
    JUMP_MIN_TERMS,
    add_usage,
    usage_line,
    usage_of,
    NOTES_SUFFIX,
    answer_language,
    export_document,
    hub_base,
    hub_url,
    fold,
    locate_caption,
    plain_text,
    transcript_text,
)
from utils.inference_panel import (
    IDLE_HINT,
    JUMP_HINT,
    MARKDOWN_EXTRAS,
    NOT_FOUND,
    NOT_SAVED,
    REVIEW_HINT,
    InferencePanel,
    is_diagram,
    prepare_answer,
    split_answer,
    text_blocks,
)
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


def test_a_mermaid_click_directive_is_dropped():
    # Mermaid can bind a node to a Javascript call. It needs mermaid to be
    # initialised with securityLevel "loose", which it is not -- but the
    # answer is written by a model reading somebody else's speech, and a
    # directive that only fails to run because of a setting somewhere else
    # is not a defence.
    answer = prepare_answer(
        "```mermaid\ngraph LR\n  A --> B\n  click A \"javascript:alert(1)\"\n```"
    )

    assert "click A" not in answer
    assert "A --> B" in answer


def test_the_diagram_itself_survives():
    # The arrows are the diagram. Escaping them, which is what this code
    # used to do to every angle bracket, left mermaid nothing to draw.
    answer = prepare_answer("```mermaid\ngraph TD\n  A[Start] --> B[End]\n```")

    assert "-->" in answer
    assert "&gt;" not in answer


def test_mathematics_is_left_alone():
    answer = prepare_answer("The bound is $a < b$ and $$\\int_0^1 x^2\\,dx$$")

    assert "$a < b$" in answer
    assert "\\int_0^1" in answer


def test_the_renderer_is_asked_for_maths_and_diagrams():
    # Without these extras the answer shows the LaTeX and the mermaid
    # source as text, which is worse than not offering them at all.
    assert "latex" in MARKDOWN_EXTRAS
    assert "mermaid" in MARKDOWN_EXTRAS


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

            if name.strip() not in ("color", "background", "background-color"):
                continue

            # Keywords that carry no colour of their own are theme-safe by
            # definition -- a transparent ground is whatever is behind it.
            if value.strip() in ("transparent", "none", "inherit", "currentColor"):
                continue

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


def test_a_diagram_is_taken_out_of_the_prose():
    # They are drawn by different things: prose by ui.markdown, which
    # sanitises the HTML it produces, and a diagram by ui.mermaid, which
    # never becomes HTML on this side at all.
    parts = split_answer(
        "Before.\n\n```mermaid\ngraph LR\n  A --> B\n```\n\nAfter."
    )

    assert parts == [
        ("text", "Before."),
        ("mermaid", "graph LR\n  A --> B"),
        ("text", "After."),
    ]


def test_prose_in_a_mermaid_fence_stays_prose():
    # A model writing sentences into a mermaid fence gets an error box
    # where the diagram should be. Shown as the code block it really is.
    answer = "```mermaid\nThe speaker explains the process\n```"

    assert split_answer(answer) == [("text", answer)]
    assert is_diagram("The speaker explains the process") is False
    assert is_diagram("sequenceDiagram\n  A->>B: hi") is True


def test_an_answer_with_no_diagram_is_left_whole():
    assert split_answer("Just prose.") == [("text", "Just prose.")]


def test_a_diagram_survives_the_text_export():
    # The source is the diagram. Stripping what looks like markup out of it
    # exports something that no longer draws -- and the reader downloaded it
    # precisely to keep what they saw.
    text = plain_text(
        "**Process:**\n\n```mermaid\ngraph LR\n  A[Start] --> B[End]\n```\n"
    )

    assert "```mermaid" in text
    assert "A[Start] --> B[End]" in text
    assert "**Process:**" not in text


def test_mathematics_survives_the_text_export():
    text = plain_text("The bound is $E = mc^2$ here.")

    assert "$E = mc^2$" in text


def test_expanding_folds_the_player_away_and_brings_it_back():
    """
    The answer shares a pane with the video and gets a few lines of it.
    Expanding hands it the whole pane; collapsing puts the player back.
    """

    shown = []

    class FakeButton:
        def props(self, value):
            self.last = value

    class FakeTooltip:
        text = ""

        def set_text(self, value):
            self.text = value

    panel = InferencePanel(
        editor=None, filename="x.mp4", language="Swedish", on_expand=shown.append
    )
    panel.expand_button = FakeButton()
    panel.expand_tooltip = FakeTooltip()

    panel.toggle_expand()

    assert panel.expanded is True
    assert shown == [False]
    assert "close_fullscreen" in panel.expand_button.last
    assert panel.expand_tooltip.text == "Show the video again"

    panel.toggle_expand()

    assert panel.expanded is False
    assert shown == [False, True]
    assert "open_in_full" in panel.expand_button.last


def test_a_failing_callback_does_not_take_the_socket_down():
    """
    A callback draws into the page, and drawing can fail for reasons that
    have nothing to do with the connection -- as it did when every message
    from the hub arrived on a background task with no slot stack. Left
    unguarded, one such failure ended the read loop and every later message
    with it.
    """

    from utils.inference import InferenceClient

    def explode(_):
        raise RuntimeError("the current slot cannot be determined")

    delivered = []

    handlers = {"on_delta": explode, "on_done": lambda: delivered.append("done")}

    InferenceClient._deliver(handlers, "on_delta", "some text")
    InferenceClient._deliver(handlers, "on_done")

    assert delivered == ["done"]


def test_a_passage_is_traced_back_to_the_caption_it_came_from():
    """
    The answer quotes nothing -- it is a model's own wording -- so a line is
    followed back by the words it and the transcription share, weighted so
    that a rare one counts and "and" does not.
    """

    transcription = editor(
        "txt",
        caption(1, "Today we look at photosynthesis in higher plants."),
        caption(2, "The budget for the coming year is set in November."),
        caption(3, "Chlorophyll absorbs light and the leaf stores the sugar."),
    )

    found = locate_caption(
        "- Photosynthesis in plants was the subject of the lecture.",
        transcription.captions,
    )

    assert found is not None
    assert found.index == 1


def test_a_line_in_the_models_own_words_is_not_placed():
    # A heading, or a sentence of the model's own, belongs to no caption.
    # Moving the reader somewhere on a coincidence is worse than saying so.
    transcription = editor(
        "txt",
        caption(1, "Today we look at photosynthesis in higher plants."),
        caption(2, "The budget for the coming year is set in November."),
    )

    assert locate_caption("## Key points", transcription.captions) is None
    assert locate_caption("", transcription.captions) is None
    assert locate_caption("Anything at all", []) is None


def test_one_shared_word_is_a_coincidence():
    # However rare it is. A jump has to rest on more than a single word.
    transcription = editor("txt", caption(1, "The budget is set in November."))

    assert JUMP_MIN_TERMS >= 2
    assert locate_caption("Budget.", transcription.captions) is None


def test_a_line_about_a_stretch_of_speech_is_placed_at_its_start():
    """
    A bullet summarises a passage, not a sentence of it -- and in a
    transcription a caption is a whole speaker turn, so the words behind one
    line of the answer are routinely spread over two or three of them.
    Scored one caption at a time, no single one accounts for enough of the
    line and it is not placed at all, which is how the jump usually missed.
    """

    transcription = editor(
        "txt",
        caption(1, "Any questions before we carry on with the next part?"),
        caption(2, "Chlorophyll absorbs light in the blue and the red bands."),
        caption(3, "The energy then builds sugar out of carbon dioxide and water."),
        caption(4, "The budget for the coming year is set in November."),
    )

    found = locate_caption(
        "- Chlorophyll absorbs light, and that energy builds sugar from carbon "
        "dioxide.",
        transcription.captions,
    )

    assert found is not None

    # The start of the stretch, not the caption that happens to account for
    # most of it: landing halfway through means the first half is never
    # heard without seeking back by hand.
    assert found.index == 2


def test_an_inflected_word_is_the_same_word():
    """
    The recordings are mostly Swedish, where the definite article is a
    suffix -- "budget" is "budgeten" the second time it is mentioned -- and
    a model writing about the transcript uses whichever form its own
    sentence wants. Compared on the surface form, the two texts share far
    less than they really do.
    """

    assert fold("budgeten") == fold("budget")
    assert fold("växterna") == fold("växter")
    assert fold("colouring") == fold("colours")

    transcription = editor(
        "txt",
        caption(1, "Stomata reglerar hur mycket koldioxid som kommer in."),
        caption(2, "Nästa vecka går vi igenom cellandningen i stället."),
    )

    found = locate_caption(
        "- Stomatan reglerade koldioxiden.", transcription.captions
    )

    assert found is not None
    assert found.index == 1


def test_words_the_whole_transcription_uses_are_not_evidence():
    """
    A sentence of the model's own about the answer itself shares nothing
    with the transcription but words every caption uses. Those are all of
    it that the transcription uses at all, so scored by weight alone the
    line accounts for everything and is placed, confidently, somewhere
    arbitrary.
    """

    transcription = editor(
        "txt",
        caption(1, "The first thing that was said in the recording."),
        caption(2, "The second thing that was said in the recording."),
        caption(3, "The third thing that was said in the recording."),
    )

    assert (
        locate_caption(
            "This answer was generated from the recording.",
            transcription.captions,
        )
        is None
    )


def test_a_line_that_fits_one_caption_is_not_spread_over_three():
    # A longer run covers more of any passage simply by being longer, so it
    # only wins when it genuinely accounts for more.
    transcription = editor(
        "txt",
        caption(1, "Brooks theorem bounds the chromatic number for most graphs."),
        caption(2, "Any questions before the break? Back in ten minutes."),
        caption(3, "The exam covers everything up to chapter seven."),
    )

    found = locate_caption(
        "- Brooks theorem bounds the chromatic number.", transcription.captions
    )

    assert found is not None
    assert found.index == 1


def test_the_answer_is_cut_into_the_lines_a_reader_clicks():
    # A bullet is about one moment in the recording; the notes as a whole
    # are about all of them, so the list cannot be one target.
    blocks = text_blocks(
        "## Key points\n\n"
        "- The first thing said\n"
        "- The second thing said\n\n"
        "A closing paragraph\nwrapped over two lines."
    )

    assert blocks == [
        "## Key points",
        "- The first thing said",
        "- The second thing said",
        "A closing paragraph\nwrapped over two lines.",
    ]


def test_a_code_fence_stays_whole():
    # Its blank lines are part of it, not passage boundaries.
    blocks = text_blocks("Before.\n\n```\nfirst\n\nsecond\n```\n\nAfter.")

    assert blocks == ["Before.", "```\nfirst\n\nsecond\n```", "After."]


def test_clicking_a_line_moves_the_transcription_to_it():
    jumped = []

    panel = InferencePanel(
        editor=editor(
            "txt",
            caption(1, "Chlorophyll absorbs light in the leaf."),
            caption(2, "The budget for the year is set in November."),
        ),
        filename="lecture.mp4",
        on_jump=jumped.append,
    )

    panel.jump_to("- The budget is set in November.")

    assert [found.index for found in jumped] == [2]


def test_the_hint_is_only_given_where_there_is_somewhere_to_go():
    # The strip draws the passages either way; without a way to ask the
    # page to move, they are not clickable and saying so would be a lie.
    assert JUMP_HINT not in InferencePanel(editor=None, filename="x")._finished_line()

    with_jump = InferencePanel(editor=None, filename="x", on_jump=lambda _: None)

    assert with_jump._finished_line() == f"{NOT_SAVED} {JUMP_HINT}"


def test_subtitles_are_not_analysed():
    """
    A caption is a line cut to fit a screen, and the file is the same
    speech the reader already has in front of them. The page does not build
    the strip for subtitles at all, and the strip refuses to draw itself
    there even if something did.
    """

    from pathlib import Path

    page = Path("pages/srt.py").read_text()

    assert 'settings.INFERENCE_ENABLED and data_format != "srt"' in page

    panel = InferencePanel(editor=editor("srt", caption(1, "A line.")), filename="x")
    panel.build()

    assert panel.panel is None


class FakePassage:
    """
    Stands in for a passage element: what is asked of it is which classes it
    ends up carrying.
    """

    def __init__(self):
        self.marks = set()

    def classes(self, add=None, remove=None):
        if add:
            self.marks.update(add.split())

        if remove:
            self.marks.difference_update(remove.split())

        return self


def test_the_line_the_reader_followed_stays_marked():
    """
    A dozen bullets look alike, and the transcription was moved for exactly
    one of them. Following another moves the mark rather than leaving two.
    """

    panel = InferencePanel(
        editor=editor(
            "txt",
            caption(1, "Chlorophyll absorbs light in the leaf."),
            caption(2, "The budget for the year is set in November."),
        ),
        filename="x",
        on_jump=lambda _: None,
    )

    first = FakePassage()
    second = FakePassage()

    panel.jump_to("- The budget is set in November.", first)

    assert "is-followed" in first.marks

    panel.jump_to("- Chlorophyll absorbs the light.", second)

    assert "is-followed" in second.marks
    assert "is-followed" not in first.marks


def test_a_line_that_could_not_be_placed_is_not_marked(monkeypatch):
    # Nothing was moved, so a mark here would claim the transcription is
    # showing where the line came from -- which is what could not be
    # worked out.
    said = []

    monkeypatch.setattr("utils.inference_panel.ui.notify", said.append)

    panel = InferencePanel(
        editor=editor("txt", caption(1, "The budget is set in November.")),
        filename="x",
        on_jump=lambda _: None,
    )

    passage = FakePassage()
    panel.jump_to("## Key points", passage)

    assert passage.marks == set()
    assert said == [NOT_FOUND]


class TestWhatAnAnswerCost:
    """
    Tokens in, tokens out and the GPU time behind them. Otherwise visible
    only to an operator reading the usage table, though it is the reader's
    own question that ran the GPU.
    """

    def test_the_figures_come_off_the_done_message(self):
        usage = usage_of(
            {
                "type": "done",
                "input_tokens": 1240,
                "output_tokens": 380,
                "gpu_seconds": 4.25,
            }
        )

        assert usage == {
            "input_tokens": 1240,
            "output_tokens": 380,
            "gpu_seconds": 4.25,
        }

    def test_a_worker_that_reports_nothing_leaves_zeros(self):
        # One shape for the caller to deal with, whatever the worker sent.
        assert usage_of({}) == {
            "input_tokens": 0,
            "output_tokens": 0,
            "gpu_seconds": 0.0,
        }
        assert usage_of({"input_tokens": "nonsense"})["input_tokens"] == 0

    def test_the_line_names_all_three(self):
        line = usage_line(
            {"input_tokens": 12345, "output_tokens": 380, "gpu_seconds": 4.25}
        )

        assert "tokens in" in line
        assert "380 out" in line
        assert "4.2" in line
        # Thin spaces, since a five-figure token count cannot be read
        # without them.
        assert "12\u2009345" in line

    def test_nothing_reported_says_nothing(self):
        # A row of zeros says less than no row.
        assert usage_line({}) == ""
        assert usage_line(usage_of({})) == ""

    def test_a_worker_with_no_gpu_timing_still_reports_its_tokens(self):
        line = usage_line({"input_tokens": 10, "output_tokens": 2, "gpu_seconds": 0})

        assert "10 tokens in · 2 out" == line

    def test_several_answers_add_up(self):
        total = add_usage(
            {"input_tokens": 100, "output_tokens": 20, "gpu_seconds": 1.5},
            usage_of({"input_tokens": 50, "output_tokens": 5, "gpu_seconds": 0.5}),
        )

        assert total == {
            "input_tokens": 150,
            "output_tokens": 25,
            "gpu_seconds": 2.0,
        }


class FakeElement:
    """
    Stands in for one of the strip's own elements. What is asked of these
    is what ended up shown, enabled and said -- not how they are drawn.
    """

    def __init__(self):
        self.visible = True
        self.enabled = True
        self.text = ""
        self.marks = set()

    def set_visibility(self, visible):
        self.visible = visible

    def set_enabled(self, enabled):
        self.enabled = enabled

    def set_text(self, text):
        self.text = text

    def props(self, *args, **kwargs):
        return self

    def classes(self, add=None, remove=None):
        if add:
            self.marks.update(add.split())

        if remove:
            self.marks.difference_update(remove.split())

        return self


def strip_with_review(on_review=None):
    """
    A strip whose elements are stand-ins, with a task pill and the Review
    pill already in the row.
    """

    panel = InferencePanel(
        editor=editor("txt", caption(1, "A line.")),
        filename="lecture.mp4",
        on_review=on_review,
    )

    panel.buttons = {"summary": FakeElement()}
    panel.review_button = FakeElement()
    panel.review_slot = FakeElement()
    panel.body = FakeElement()
    panel.status = FakeElement()
    panel.stop_button = FakeElement()
    panel.copy_button = FakeElement()
    panel.download_button = FakeElement()

    return panel


class TestTheReviewPill:
    """
    A review is another thing asked of the same recording, so it is asked
    for from the same row of pills -- not from the toolbar, and not into a
    dialog of its own.
    """

    def test_it_is_a_pill_in_the_same_row_as_the_tasks(self):
        from pathlib import Path

        source = Path("utils/inference_panel.py").read_text()

        # Drawn inside self.actions, and drawn last: after the tasks the
        # hub named, since it is not one of them.
        row = source.index("with self.actions:")
        pill = source.index('ui.button(\n                    "Review"')
        loop = source.index('for task in tasks:')

        assert row < loop < pill
        assert "inference-chip" in source[pill:pill + 400]

    def test_it_is_hidden_until_the_hub_can_review(self):
        # A hub with no worker connected names its domains all the same,
        # and a pill that apologises one click later is worse than none.
        panel = strip_with_review()

        panel._sync_review()

        assert panel.review_button.visible is False

        panel.set_review_available(True)

        assert panel.review_button.visible is True

    def test_it_is_disabled_while_an_answer_is_generating(self):
        panel = strip_with_review()
        panel.set_review_available(True)

        panel._set_running(True)

        assert panel.review_button.enabled is False

        panel._set_running(False)

        assert panel.review_button.enabled is True

    def test_a_hub_with_no_tasks_still_draws_the_strip_for_it(self):
        # The hub's two review tasks carry offered=False, so a deployment
        # offering nothing else has an empty task list and a Review pill.
        from pathlib import Path

        source = Path("utils/inference_panel.py").read_text()

        assert "if not tasks and not self.review_available:" in source


class TestTheReviewTakesTheAnswersPlace:
    """
    One of the two at a time. The review is drawn where an answer is
    drawn -- which is what lets it be read against the transcription
    instead of over it -- so the answer area steps aside and comes back
    afterwards.
    """

    def review(self, panel):
        import asyncio

        asyncio.run(panel.start_review())

    def test_the_answer_area_steps_aside_and_comes_back(self):
        asked = []

        async def open_review():
            asked.append(True)

        panel = strip_with_review(on_review=open_review)
        panel.set_review_available(True)
        panel.answer = "The summary."

        self.review(panel)

        assert asked == [True]
        assert panel.reviewing is True
        assert panel.body.visible is False
        assert panel.review_slot.visible is True
        assert panel.status.text == REVIEW_HINT

        panel.end_review()

        assert panel.reviewing is False
        assert panel.review_slot.visible is False
        # The answer was not thrown away by the review standing in its
        # place, so it is shown again as it was.
        assert panel.body.visible is True
        assert panel.status.text == panel._finished_line()

    def test_an_unused_strip_goes_back_to_its_own_hint(self):
        async def open_review():
            return None

        panel = strip_with_review(on_review=open_review)
        panel.set_review_available(True)

        self.review(panel)
        panel.end_review()

        assert panel.body.visible is False
        assert panel.status.text == IDLE_HINT

    def test_the_tasks_cannot_be_asked_for_while_reviewing(self):
        # Pressing Summary mid-review would draw an answer over the
        # suggestion being decided on, and throw away the decisions made
        # so far with it.
        async def open_review():
            return None

        panel = strip_with_review(on_review=open_review)
        panel.set_review_available(True)
        panel.answer = "The summary."

        self.review(panel)

        assert panel.buttons["summary"].enabled is False
        assert panel.review_button.enabled is False
        # Nothing to copy or download either: neither acts on what is on
        # show.
        assert panel.copy_button.visible is False
        assert panel.download_button.visible is False

        panel.end_review()

        assert panel.buttons["summary"].enabled is True
        assert panel.review_button.enabled is True
        assert panel.copy_button.visible is True

    def test_the_page_lends_the_assistant_the_strips_slot_and_socket(self):
        # Neither exists before the strip is built, so the page puts the
        # two together afterwards -- and the assistant hands the slot back
        # when the review ends.
        from pathlib import Path

        page = Path("pages/srt.py").read_text()

        assert "assistant.client = inference.client" in page
        assert "assistant.container = inference.review_slot" in page
        assert "assistant.on_close = inference.end_review" in page
        assert "on_review=assistant.open," in page

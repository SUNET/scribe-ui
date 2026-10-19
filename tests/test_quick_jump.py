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

import asyncio
import pathlib
import re

import pytest

from utils.caption import SRTCaption
from utils.quick_jump import (
    HINT,
    KIND_BLOCK,
    KIND_RELATIVE,
    KIND_TIME,
    JumpError,
    parse_jump,
    parse_time,
)
from utils.srt import SRTEditor
from utils.transcript_editor import TranscriptEditor


class TestParseTime:
    @pytest.mark.parametrize(
        "text,seconds",
        [
            # Colons: hours:minutes:seconds, counted from the right.
            ("01:15:23", 4523),
            ("1:15:23", 4523),
            ("1:15", 75),
            ("0:05", 5),
            # An empty field is zero.
            ("10:", 600),
            ("1::", 3600),
            ("10::", 36000),
            ("1::30", 3630),
            (":", 0),
            ("::", 0),
            # No colons: digits two at a time from the right.
            ("5", 5),
            ("90", 90),
            ("123", 83),
            ("1234", 754),
            ("011523", 4523),
            ("123456", 45296),
            ("0", 0),
            # A field that overflows is added up.
            ("1:90", 150),
            ("75", 75),
            # Decimals in the seconds, so a label copied from the editor works.
            ("1:15.5", 75.5),
            ("00:01:15.400", 75.4),
            ("1:15,5", 75.5),
            ("90.5", 90.5),
            # Around it.
            ("  1:15  ", 75),
        ],
    )
    def test_it_reads_the_time_the_way_it_is_spoken(self, text, seconds):
        assert parse_time(text) == pytest.approx(seconds)

    @pytest.mark.parametrize(
        "text", ["abc", "1:2:3:4", "1:ab", "ab:1", "1.2.3", "1 5", "5.", "-"]
    )
    def test_anything_else_is_refused(self, text):
        with pytest.raises(JumpError):
            parse_time(text)


class TestParseJump:
    def test_a_block(self):
        assert parse_jump("#123") == (KIND_BLOCK, 123)
        assert parse_jump("  # 7 ") == (KIND_BLOCK, 7)

    @pytest.mark.parametrize("text", ["#", "#0", "#abc", "#1:15", "#-3", "# "])
    def test_a_bad_block_is_refused(self, text):
        with pytest.raises(JumpError):
            parse_jump(text)

    def test_a_time(self):
        assert parse_jump("1:15") == (KIND_TIME, 75)

    def test_relative_times_are_signed(self):
        assert parse_jump("+30") == (KIND_RELATIVE, 30)
        assert parse_jump("-1:05") == (KIND_RELATIVE, -65)
        assert parse_jump("+ 2") == (KIND_RELATIVE, 2)

    @pytest.mark.parametrize("text", ["+", "-", "+abc", "-1:2:3:4"])
    def test_a_bad_relative_time_is_refused(self, text):
        with pytest.raises(JumpError):
            parse_jump(text)

    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_nothing_typed_is_refused_with_a_hint(self, text):
        with pytest.raises(JumpError, match="Type a time"):
            parse_jump(text)

    def test_the_kinds_are_told_apart_by_their_first_character(self):
        kinds = {parse_jump(text)[0] for text in ("#5", "+5", "-5", "5")}

        assert kinds == {KIND_BLOCK, KIND_RELATIVE, KIND_TIME}

    def test_every_example_in_the_hint_parses(self):
        """
        The hint is what the reader is told to type.
        """

        examples = re.findall(r"[#+-]?[\d:]+", HINT)

        assert examples
        for example in examples:
            parse_jump(example)

    def test_the_messages_are_for_the_reader(self):
        for text in ("abc", "#0", "+", ""):
            with pytest.raises(JumpError) as raised:
                parse_jump(text)

            assert str(raised.value)
            assert "Traceback" not in str(raised.value)


WORDS = {
    "version": 1,
    "words": [
        {"t": "ett", "s": 0.0, "e": 0.5},
        {"t": "två", "s": 0.6, "e": 1.0},
        {"t": "tre", "s": 1.1, "e": 1.5},
        {"t": "fyra", "s": 5.0, "e": 5.4},
        {"t": "fem", "s": 5.5, "e": 5.9},
        {"t": "sex", "s": 6.0, "e": 6.5},
        {"t": "sju", "s": 10.0, "e": 10.5},
    ],
}


def build(data_format="srt"):
    editor = SRTEditor("job-uuid", data_format, "file")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *a, **k: None)

    editor.load_words(WORDS)
    editor.captions = [
        SRTCaption(1, "00:00:00,000", "00:00:02,000", "ett två tre"),
        SRTCaption(2, "00:00:05,000", "00:00:07,000", "fyra fem sex"),
        SRTCaption(3, "00:00:10,000", "00:00:11,000", "sju"),
    ]

    return editor


class Journal:
    """
    What a jump did to the player and the editor, in order.
    """

    def __init__(self, view, playhead=None):
        self.events = []
        self.playhead = playhead
        view.editor.seek_video = lambda s: self.events.append(("seek", s))
        view.moved_to = lambda s: self.events.append(("moved", s))
        view.focus = lambda *a, **k: self.events.append(("focus", a, k))

    def focused(self):
        return [e for e in self.events if e[0] == "focus"][-1]


@pytest.fixture
def view(monkeypatch):
    view = TranscriptEditor(build())
    monkeypatch.setattr("utils.transcript_editor.ui.notify", lambda *a, **k: None)

    return view


def jump(view, text, playhead=None):
    journal = Journal(view)

    async def fake_js(script, **kwargs):
        return playhead

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("utils.transcript_editor.ui.run_javascript", fake_js)
        result = asyncio.run(view.quick_jump(text))

    return result, journal


class TestJumpingToATime:
    def test_the_player_goes_to_the_time_typed(self, view):
        result, journal = jump(view, "0:08")

        assert result is None
        assert ("seek", 8.0) in journal.events

    def test_the_caret_goes_to_the_word_being_spoken(self, view):
        # 5.6 is inside "fem", the second word of the second caption.
        _, journal = jump(view, "5.6")

        assert journal.focused()[1][0] == 2
        assert journal.focused()[1][1] == len("fyra ")

    def test_before_the_first_word_of_a_caption_it_is_the_first_word(self, view):
        _, journal = jump(view, "4.8")

        assert journal.focused()[1][:2] == (2, 0)

    def test_a_time_in_a_gap_goes_to_the_nearest_caption(self, view):
        # 2.5 is closer to the end of #1 (2.0) than the start of #2 (5.0).
        _, journal = jump(view, "2.5")

        assert journal.focused()[1][0] == 1
        # And in it, to the last word, which has started by then.
        assert journal.focused()[1][1] == len("ett två ")

    def test_a_time_nearer_the_next_caption_goes_there(self, view):
        _, journal = jump(view, "4.5")

        assert journal.focused()[1][0] == 2

    def test_an_equally_near_time_goes_to_the_one_about_to_start(self, view):
        # 3.5: 1.5 s from the end of #1 and from the start of #2.
        _, journal = jump(view, "3.5")

        assert journal.focused()[1][0] == 2

    def test_past_the_end_it_is_the_end(self, view):
        result, journal = jump(view, "99:00")

        assert result is None
        # Clamped to the last moment of the last caption.
        assert ("seek", 11.0) in journal.events
        assert journal.focused()[1][0] == 3

    def test_the_known_length_of_the_recording_is_the_limit(self, view):
        view.editor.media_seconds = 30.0

        _, journal = jump(view, "1:00")

        assert ("seek", 30.0) in journal.events

    def test_the_caret_is_centred_and_the_marker_follows(self, view):
        _, journal = jump(view, "5.6")

        assert journal.focused()[2] == {"center": True}
        assert ("moved", 5.6) in journal.events

    def test_without_word_timings_it_is_the_start_of_the_caption(self, view):
        view.editor.load_words({"version": 1, "words": []})

        _, journal = jump(view, "5.6")

        assert journal.focused()[1][:2] == (2, 0)

    def test_nothing_to_jump_to(self, view):
        view.editor.captions = []

        result, journal = jump(view, "1:00")

        assert "no captions" in result
        assert journal.events == []

    def test_it_is_not_an_edit(self, view):
        saved = []
        view.editor.save_state_for_undo = lambda *a, **k: saved.append(1)

        jump(view, "5.6")

        assert saved == []


class TestJumpingRelatively:
    def test_forward_from_the_playhead(self, view):
        _, journal = jump(view, "+3", playhead=2.0)

        assert ("seek", 5.0) in journal.events
        assert journal.focused()[1][0] == 2

    def test_back_from_the_playhead(self, view):
        _, journal = jump(view, "-1", playhead=6.0)

        assert ("seek", 5.0) in journal.events

    def test_before_the_start_it_is_the_start(self, view):
        _, journal = jump(view, "-99", playhead=2.0)

        assert ("seek", 0.0) in journal.events

    def test_without_a_player_it_counts_from_the_caret_caption(self, view):
        view.caret_block = 2

        _, journal = jump(view, "+1", playhead=None)

        assert ("seek", 6.0) in journal.events

    def test_without_a_player_or_a_caret_it_counts_from_the_start(self, view):
        view.caret_block = None

        _, journal = jump(view, "+1", playhead=None)

        assert ("seek", 1.0) in journal.events


class TestJumpingToABlock:
    def test_it_goes_to_the_start_of_the_caption(self, view):
        result, journal = jump(view, "#2")

        assert result is None
        assert ("seek", 5.0) in journal.events
        assert journal.focused()[1][:2] == (2, 0)

    def test_a_block_past_the_last_goes_to_the_last(self, view):
        """
        As a time past the end goes to the end: both mean "far ahead".
        """

        result, journal = jump(view, "#9")

        assert result is None
        assert ("seek", view.editor.captions[-1].get_start_seconds()) in journal.events
        assert journal.focused()[1][:2] == (3, 0)

    def test_a_block_far_past_the_last_goes_to_the_last_too(self, view):
        result, journal = jump(view, "#900")

        assert result is None
        assert journal.focused()[1][0] == 3

    def test_the_last_block_itself_is_just_that_block(self, view):
        _, journal = jump(view, "#3")

        assert journal.focused()[1][0] == 3

    def test_a_block_number_below_one_is_still_refused(self, view):
        result, journal = jump(view, "#0")

        assert "from 1" in result
        assert journal.events == []

    def test_with_no_captions_there_is_nothing_to_jump_to(self, view):
        view.editor.captions = []

        result, journal = jump(view, "#2")

        assert result == "There are no captions to jump to"
        assert journal.events == []

    def test_a_transcription_has_no_block_numbers_to_type(self):
        view = TranscriptEditor(build("txt"))
        result, journal = jump(view, "#2")

        assert "only shown in subtitles" in result
        assert journal.events == []

    def test_a_transcription_still_takes_times(self):
        view = TranscriptEditor(build("txt"))

        result, journal = jump(view, "5.6")

        assert result is None
        assert journal.focused()[1][0] == 2


class TestABadJump:
    def test_it_says_what_is_wrong_and_goes_nowhere(self, view):
        result, journal = jump(view, "banana")

        assert "not a time" in result
        assert journal.events == []


class TestTheKey:
    def test_the_editor_opens_the_prompt_for_ctrl_and_cmd_g(self):
        class Modifiers:
            def __init__(self, **kw):
                self.ctrl = kw.get("ctrl", False)
                self.meta = kw.get("meta", False)
                self.shift = kw.get("shift", False)
                self.alt = kw.get("alt", False)

        class Event:
            def __init__(self, key, **kw):
                self.key = key
                self.modifiers = Modifiers(**kw)

                class Action:
                    keydown = True

                self.action = Action()

        editor = build()
        opened = []
        editor.on_quick_jump = lambda: opened.append(1)

        async def press(key, **kw):
            await editor.handle_key_event(Event(key, **kw))

        asyncio.run(press("g", ctrl=True))
        asyncio.run(press("g", meta=True))
        asyncio.run(press("g", ctrl=True, shift=True))
        assert len(opened) == 3

        # Plain g is a letter, and Alt makes it something else.
        asyncio.run(press("g"))
        asyncio.run(press("g", ctrl=True, alt=True))
        assert len(opened) == 3

    def test_without_a_prompt_the_key_does_nothing(self):
        editor = build()

        assert editor.on_quick_jump is None

    def test_the_view_registers_itself(self):
        source = pathlib.Path("utils/transcript_editor.py").read_text()

        assert "self.editor.on_quick_jump = self.open_quick_jump" in source

    def test_the_browsers_own_find_next_is_blocked_on_the_page(self):
        source = pathlib.Path("pages/srt.py").read_text()

        assert "e.key.toLowerCase() === 'g'" in source


class TestThePrompt:
    def source(self):
        return pathlib.Path("utils/transcript_editor.py").read_text()

    def build_body(self):
        source = self.source()
        body = source[source.index("    def build_quick_jump(self)"):]

        return body[: body.index("\n    def return_to_text")]

    def test_it_is_a_prompt_not_a_modal(self):
        body = self.build_body()

        # No backdrop; Quasar must not put focus back by itself, since the
        # caret is put back explicitly.
        assert "seamless" in body
        assert "no-refocus" in body
        assert 'aria-label="Quick Jump"' in body

    def test_it_has_no_ok_or_cancel(self):
        assert "ui.button" not in self.build_body()

    def test_enter_goes_and_escape_closes(self):
        body = self.build_body()

        assert 'field.on("keydown.enter", submit)' in body
        assert 'field.on("keydown.escape", close)' in body

    def test_a_good_jump_closes_it_and_a_bad_one_keeps_it_open(self):
        body = self.build_body()
        submit = body[body.index("async def submit"):body.index("def close")]

        assert submit.index("if problem:") < submit.index("dialog.close()")
        assert "return" in submit[: submit.index("dialog.close()")]

    def test_the_field_and_the_message_are_announced(self):
        body = self.build_body()

        assert "aria-labelledby" in body
        assert "aria-describedby" in body
        assert 'role="alert"' in body

    def test_closing_without_a_jump_puts_the_caret_back(self):
        body = self.build_body()
        close = body[body.index("def close"):body.index('field.on("keydown.enter"')]

        assert "self.return_to_text()" in close

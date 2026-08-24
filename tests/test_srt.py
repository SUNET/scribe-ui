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

import pathlib

from utils.srt import SRTCaption, SRTEditor, UndoRedoManager


class TestSRTCaption:
    """
    Test cases for SRTCaption class.
    """

    def test_init(self):
        """
        Test caption initialization.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        
        assert caption.index == 1
        assert caption.start_time == "00:00:10,000"
        assert caption.end_time == "00:00:15,500"
        assert caption.text == "Hello world"
        assert caption.speaker == "John"
        assert caption.is_selected is False
        assert caption.is_highlighted is False
        assert caption.is_valid is True

    def test_init_default_speaker(self):
        """
        Test caption initialization with default speaker.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world"
        )
        
        assert caption.speaker == "UNKNOWN"

    def test_init_empty_speaker(self):
        """
        Test caption initialization with empty speaker string.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker=""
        )
        
        assert caption.speaker == "UNKNOWN"

    def test_copy(self):
        """
        Test caption copy method.
        """
        original = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        original.is_selected = True
        original.is_highlighted = True
        original.is_valid = False
        
        copied = original.copy()
        
        assert copied.index == original.index
        assert copied.start_time == original.start_time
        assert copied.end_time == original.end_time
        assert copied.text == original.text
        assert copied.speaker == original.speaker
        assert copied.is_selected == original.is_selected
        assert copied.is_highlighted == original.is_highlighted
        assert copied.is_valid == original.is_valid
        
        # Ensure it's a deep copy
        assert copied is not original

    def test_to_dict(self):
        """
        Test caption to_dict method.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        
        result = caption.to_dict()
        
        assert result["speaker"] == "John"
        assert result["text"] == "Hello world"
        assert result["start"] == 10.0
        assert result["end"] == 15.5
        assert result["duration"] == 5.5

    def test_to_srt_format(self):
        """
        Test caption to_srt_format method.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,500",
            text="Hello world",
            speaker="John"
        )
        
        result = caption.to_srt_format()
        expected = "1\n00:00:10,000 --> 00:00:15,500\nHello world\n"
        
        assert result == expected

    def test_get_start_seconds(self):
        """
        Test conversion of start time to seconds.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,500",
            end_time="00:00:15,000",
            text="Hello world"
        )
        
        assert caption.get_start_seconds() == 10.5

    def test_get_start_seconds_with_hours(self):
        """
        Test conversion of start time with hours to seconds.
        """
        caption = SRTCaption(
            index=1,
            start_time="01:30:45,250",
            end_time="01:30:50,000",
            text="Hello world"
        )
        
        # 1 hour = 3600 seconds, 30 minutes = 1800 seconds, 45.25 seconds
        expected = 3600 + 1800 + 45.25
        assert caption.get_start_seconds() == expected

    def test_get_end_seconds(self):
        """
        Test conversion of end time to seconds.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,750",
            text="Hello world"
        )
        
        assert caption.get_end_seconds() == 15.75

    def test_get_end_seconds_with_hours(self):
        """
        Test conversion of end time with hours to seconds.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="02:15:30,500",
            text="Hello world"
        )
        
        # 2 hours = 7200 seconds, 15 minutes = 900 seconds, 30.5 seconds
        expected = 7200 + 900 + 30.5
        assert caption.get_end_seconds() == expected

    def test_matches_search_case_insensitive(self):
        """
        Test case-insensitive search matching.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="Hello World"
        )
        
        assert caption.matches_search("hello", case_sensitive=False) is True
        assert caption.matches_search("WORLD", case_sensitive=False) is True
        assert caption.matches_search("world", case_sensitive=False) is True
        assert caption.matches_search("goodbye", case_sensitive=False) is False

    def test_matches_search_case_sensitive(self):
        """
        Test case-sensitive search matching.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="Hello World"
        )
        
        assert caption.matches_search("Hello", case_sensitive=True) is True
        assert caption.matches_search("World", case_sensitive=True) is True
        assert caption.matches_search("hello", case_sensitive=True) is False
        assert caption.matches_search("WORLD", case_sensitive=True) is False

    def test_matches_search_empty_term(self):
        """
        Test search matching with empty search term.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="Hello World"
        )
        
        assert caption.matches_search("", case_sensitive=False) is False
        assert caption.matches_search("", case_sensitive=True) is False

    def test_matches_search_partial_match(self):
        """
        Test partial string matching in search.
        """
        caption = SRTCaption(
            index=1,
            start_time="00:00:10,000",
            end_time="00:00:15,000",
            text="The quick brown fox"
        )
        
        assert caption.matches_search("quick", case_sensitive=False) is True
        assert caption.matches_search("brown fox", case_sensitive=False) is True
        assert caption.matches_search("slow", case_sensitive=False) is False


class TestUndoRedoManager:
    """
    Test cases for UndoRedoManager class.
    """

    def test_init(self):
        """
        Test manager initialization.
        """
        manager = UndoRedoManager()
        
        assert manager.max_history == 50
        assert len(manager.undo_stack) == 0
        assert len(manager.redo_stack) == 0

    def test_init_custom_max_history(self):
        """
        Test manager initialization with custom max history.
        """
        manager = UndoRedoManager(max_history=10)
        
        assert manager.max_history == 10

    def test_save_state(self):
        """
        Test saving state to undo stack.
        """
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "First caption"),
            SRTCaption(2, "00:00:15,000", "00:00:20,000", "Second caption")
        ]
        
        manager.save_state(captions)
        
        assert len(manager.undo_stack) == 1
        assert len(manager.redo_stack) == 0
        assert len(manager.undo_stack[0].captions) == 2

    def test_save_state_clears_redo(self):
        """
        Test that saving state clears redo stack.
        """
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "First caption")
        ]
        
        manager.save_state(captions)
        manager.redo_stack.append(captions)  # Manually add to redo
        
        assert len(manager.redo_stack) == 1
        
        manager.save_state(captions)
        
        assert len(manager.redo_stack) == 0

    def test_save_state_deep_copy(self):
        """
        Test that save_state creates deep copy of captions.
        """
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "First caption")
        ]
        
        manager.save_state(captions)
        
        # Modify original
        captions[0].text = "Modified"
        
        # Saved state should be unchanged
        assert manager.undo_stack[0].captions[0].text == "First caption"

    def test_save_state_max_history_limit(self):
        """
        Test that history is limited to max_history.
        """
        manager = UndoRedoManager(max_history=3)
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        # Save 4 states
        for i in range(4):
            captions[0].text = f"Caption {i}"
            manager.save_state(captions)
        
        assert len(manager.undo_stack) == 3
        # First state should be removed
        assert manager.undo_stack[0].captions[0].text == "Caption 1"

    def test_undo(self):
        """
        Test undo functionality.
        """
        manager = UndoRedoManager()
        
        # Create initial state
        captions_v1 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 1")
        ]
        manager.save_state(captions_v1)
        
        # Create modified state
        captions_v2 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 2")
        ]
        
        result = manager.undo(captions_v2)
        
        assert result is not None
        assert result.captions[0].text == "Version 1"
        assert len(manager.undo_stack) == 0
        assert len(manager.redo_stack) == 1

    def test_undo_empty_stack(self):
        """
        Test undo with empty stack.
        """
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        result = manager.undo(captions)
        
        assert result is None

    def test_redo(self):
        """
        Test redo functionality.
        """
        manager = UndoRedoManager()
        
        # Create initial state and save
        captions_v1 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 1")
        ]
        manager.save_state(captions_v1)
        
        # Create modified state
        captions_v2 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 2")
        ]
        
        # Undo to move v2 to redo stack
        manager.undo(captions_v2)
        
        # Redo
        result = manager.redo(captions_v1)
        
        assert result is not None
        assert result.captions[0].text == "Version 2"
        assert len(manager.redo_stack) == 0
        assert len(manager.undo_stack) == 1

    def test_redo_empty_stack(self):
        """
        Test redo with empty stack.
        """
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        result = manager.redo(captions)
        
        assert result is None

    def test_can_undo(self):
        """
        Test can_undo method.
        """
        manager = UndoRedoManager()
        
        assert manager.can_undo() is False
        
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        manager.save_state(captions)
        
        assert manager.can_undo() is True

    def test_can_redo(self):
        """
        Test can_redo method.
        """
        manager = UndoRedoManager()
        
        assert manager.can_redo() is False
        
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        manager.redo_stack.append(captions)
        
        assert manager.can_redo() is True

    def test_clear(self):
        """
        Test clear method.
        """
        manager = UndoRedoManager()
        captions = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Caption")
        ]
        
        manager.save_state(captions)
        manager.redo_stack.append(captions)
        
        assert len(manager.undo_stack) > 0
        assert len(manager.redo_stack) > 0
        
        manager.clear()
        
        assert len(manager.undo_stack) == 0
        assert len(manager.redo_stack) == 0

    def test_undo_redo_sequence(self):
        """
        Test a complete undo/redo sequence.
        """
        manager = UndoRedoManager()
        
        # Save state 1
        captions_v1 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 1")
        ]
        manager.save_state(captions_v1)
        
        # Save state 2
        captions_v2 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 2")
        ]
        manager.save_state(captions_v2)
        
        # Current state 3
        captions_v3 = [
            SRTCaption(1, "00:00:10,000", "00:00:15,000", "Version 3")
        ]
        
        # Undo twice
        result = manager.undo(captions_v3)
        assert result.captions[0].text == "Version 2"
        
        result = manager.undo(result.captions)
        assert result.captions[0].text == "Version 1"
        
        # Redo once
        result = manager.redo(result.captions)
        assert result.captions[0].text == "Version 2"
        
        # Redo again
        result = manager.redo(result.captions)
        assert result.captions[0].text == "Version 3"


class TestSpeakersTravelWithHistory:
    """
    A state is both halves: the captions, and the speaker list they name.

    The list cannot be recomputed from the captions on the way back -- a
    speaker can legitimately exist with no block using it ("Add new", or every
    block reassigned away) -- so it has to be snapshotted alongside. Restoring
    only the captions left a block naming a speaker the list had never heard
    of, and the rename menu then refused to act on that name at all.
    """

    def captions(self, speaker):
        return [SRTCaption(1, "00:00:00,000", "00:00:02,000", "text", speaker)]

    def test_the_speaker_list_is_restored_with_the_captions(self):
        manager = UndoRedoManager()

        manager.save_state(self.captions("Speaker 1"), {"Speaker 1", "Speaker 2"})
        result = manager.undo(self.captions("Alice"), {"Alice", "Speaker 2"})

        assert result.speakers == {"Speaker 1", "Speaker 2"}

    def test_redo_carries_it_back_the_other_way(self):
        manager = UndoRedoManager()

        manager.save_state(self.captions("Speaker 1"), {"Speaker 1"})
        manager.undo(self.captions("Alice"), {"Alice"})
        result = manager.redo(self.captions("Speaker 1"), {"Speaker 1"})

        assert result.speakers == {"Alice"}

    def test_the_snapshot_is_a_copy(self):
        """
        Shared, a later edit to the live set would reach back into a state
        already on the stack -- the same reason the captions are copied.
        """

        manager = UndoRedoManager()
        speakers = {"Speaker 1"}

        manager.save_state(self.captions("Speaker 1"), speakers)
        speakers.add("Added later")

        assert manager.undo_stack[0].speakers == {"Speaker 1"}

    def test_a_state_saved_without_speakers_carries_none(self):
        """
        Left as None rather than an empty set, so restoring it leaves whatever
        the editor already has alone instead of emptying the list.
        """

        manager = UndoRedoManager()

        manager.save_state(self.captions("Speaker 1"))

        assert manager.undo_stack[0].speakers is None


class TestValidateShortcut:
    """
    Ctrl+Shift+V validates. Subtitles only -- a transcription has neither a
    line-length guideline nor a line count to exceed -- and Ctrl rather than
    Cmd, since Cmd+Shift+V is paste-without-formatting on a Mac.
    """

    def editor(self, data_format):
        editor = SRTEditor("job-uuid", data_format, "file")
        editor.data_format = data_format
        editor.captions = []

        return editor

    def press(self, editor, key, ctrl=False, meta=False, shift=False):
        import asyncio
        from types import SimpleNamespace

        event = SimpleNamespace(
            key=key,
            action=SimpleNamespace(keydown=True),
            modifiers=SimpleNamespace(ctrl=ctrl, meta=meta, shift=shift, alt=False),
        )
        asyncio.run(editor.handle_key_event(event))

    def test_it_validates_a_subtitle(self):
        editor = self.editor("srt")
        called = []
        editor.validate_captions = lambda *a, **k: called.append(True)

        self.press(editor, "v", ctrl=True, shift=True)

        assert called == [True]

    def test_a_transcription_is_left_alone(self):
        editor = self.editor("txt")
        called = []
        editor.validate_captions = lambda *a, **k: called.append(True)

        self.press(editor, "v", ctrl=True, shift=True)

        assert called == []

    def test_the_command_key_is_not_taken(self):
        editor = self.editor("srt")
        called = []
        editor.validate_captions = lambda *a, **k: called.append(True)

        self.press(editor, "v", meta=True, shift=True)

        assert called == []

    def test_plain_ctrl_v_still_pastes(self):
        """
        Without Shift this is the browser's own paste, which the editor must
        not intercept.
        """

        editor = self.editor("srt")
        called = []
        editor.validate_captions = lambda *a, **k: called.append(True)

        self.press(editor, "v", ctrl=True)

        assert called == []


class TestSplitWithoutACaret:
    """
    A split with no caret halves the caption, and the break has to fall
    between two words. It used to search backwards only and give up on the
    bare middle when it found nothing, which cut through the first word of
    any caption with no space before its midpoint.
    """

    def editor(self, text):
        editor = SRTEditor("job-uuid", "srt", "file.srt")

        for name in ("refresh_display", "update_words_per_minute",
                     "mark_as_changed", "update_beforeunload_state",
                     "update_flagged_count"):
            setattr(editor, name, lambda *a, **k: None)

        editor.data_format = "srt"
        editor.captions = [
            SRTCaption(1, "00:00:00,000", "00:00:04,000", text)
        ]

        return editor

    def halves(self, text, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor(text)
        editor.split_caption(editor.captions[0])

        return [caption.text for caption in editor.captions]

    def test_it_breaks_between_words(self, monkeypatch):
        assert self.halves("Hello there wonderful world", monkeypatch) == [
            "Hello there",
            "wonderful world",
        ]

    def test_a_long_first_word_is_not_cut_through(self, monkeypatch):
        """
        The reported bug: nothing to find searching backwards from the
        middle, and it settled for the middle itself.
        """

        assert self.halves("internationalization matters", monkeypatch) == [
            "internationalization",
            "matters",
        ]

    def test_it_takes_the_nearest_gap_either_way(self, monkeypatch):
        assert self.halves("a verylongsingleword here", monkeypatch) == [
            "a verylongsingleword",
            "here",
        ]

    def test_no_word_survives_the_split(self, monkeypatch):
        """
        Whatever the text, every word in it has to come out whole on one
        side or the other.
        """

        for text in [
            "Hello there wonderful world",
            "internationalization matters",
            "a verylongsingleword here",
            "one two three four five six seven",
            "Kort text har",
        ]:
            first, second = self.halves(text, monkeypatch)

            assert first.split() + second.split() == text.split(), text

    def test_a_single_word_has_no_gap_to_find(self):
        """
        Nothing better is available there, and every real caption has a gap.
        """

        assert SRTEditor.split_point("onlyoneword") == len("onlyoneword") // 2

    def test_the_same_text_always_breaks_the_same_way(self):
        """
        Ties go to the earlier gap rather than to whichever side happened to
        be searched first.
        """

        text = "aa bb cc"

        assert SRTEditor.split_point(text) == SRTEditor.split_point(text)
        assert text[SRTEditor.split_point(text)].isspace()

    def test_a_caret_split_is_still_honoured_exactly(self, monkeypatch):
        """
        A position the reader chose means what it says, mid-word or not --
        only the made-up ones get snapped.
        """

        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor = self.editor("Hello there wonderful world")
        editor.split_caption(editor.captions[0], cursor_position=13)

        assert [c.text for c in editor.captions] == ["Hello there w", "onderful world"]


class TestInformationDialog:
    """
    What is open and what is in it, behind a button rather than across the
    toolbar: it is read when a reader wonders, not while they work.
    """

    def page(self) -> str:
        import pathlib

        return pathlib.Path("pages/srt.py").read_text()

    def test_a_button_opens_it(self):
        page = self.page()

        assert 'ui.button("Info", icon="info")' in page
        assert '.on("click", info_dialog.open)' in page

    def test_it_names_what_it_shows(self):
        """
        A row of bare numbers explains nothing; with room for labels, each
        figure can say what it means outright rather than on hover.
        """

        page = self.page()

        for label in ("File", "Language", "Reading speed"):
            assert f'"{label}",' in page

    def test_the_count_is_worded_for_the_format(self):
        """
        A reader editing a transcription has paragraphs in front of them,
        not captions -- and "block" is neither.
        """

        page = self.page()

        assert '"Captions" if data_format == "srt" else "Paragraphs"' in page
        assert "How many paragraphs the " in page
        assert "blocks the transcription" not in page

    def test_it_does_not_say_where_the_last_caption_ends(self):
        """
        The running time was where the subtitles stop, not how long the
        recording is, which is not what a reader reads that row as.
        """

        page = self.page()

        assert '"Length",' not in page
        assert '"duration"' not in page

    def test_the_moving_figures_are_registered(self):
        """
        The count and the reading speed change as the reader edits; the file
        name and the language never do.
        """

        page = self.page()

        assert 'if value in ("captions", "wpm"):' in page
        assert "editor.set_status_elements(**figures)" in page


class TestSpacePlaysAndPauses:
    """
    Space plays and pauses the recording unless something is being typed
    into. Handled in the page's own head script rather than through the
    keyboard handler: the player answers with no round trip, and whether the
    reader is typing is a question only the browser can answer.
    """

    def page(self) -> str:
        import pathlib

        return pathlib.Path("pages/srt.py").read_text()

    def test_it_asks_what_has_focus(self):
        page = self.page()

        assert "active.isContentEditable" in page
        assert "'INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'" in page

    def test_a_focused_button_keeps_its_own_space(self):
        """
        Space activates a focused button; taking that would break every
        dialog on the page.
        """

        page = self.page()
        handler = page[page.index("if (e.key === ' '"):]
        handler = handler[: handler.index("// Handle Escape")]

        assert "BUTTON" in handler

    def test_it_toggles_the_player_directly(self):
        page = self.page()

        assert "video.paused ? video.play() : video.pause();" in page

    def test_the_modified_shortcut_is_still_there(self):
        """
        Ctrl+Space reaches the editor's own handler, which is what a reader
        with the caret in a caption uses -- a bare space there is a space.
        """

        source = pathlib.Path("utils/srt.py").read_text()

        assert "Play/pause video, Ctrl+Space" in source


class TestStatusLine:
    """
    The figures in the video information dialog: how many captions there
    are, how far the last one runs to, and how fast the result reads. Each
    is a label of its own, registered by name, so the editor can keep them
    up to date as the reader works.
    """

    class Label:
        text = None

        def set_text(self, value):
            self.text = value

    def editor(self, *captions) -> SRTEditor:
        editor = SRTEditor("job-uuid", "srt", "file.srt")
        editor.data_format = "srt"
        editor.captions = list(captions)

        return editor

    def figures(self, editor) -> dict:
        labels = {name: self.Label() for name in ("captions", "duration", "wpm")}
        editor.set_status_elements(**labels)

        return labels

    def test_each_figure_gets_its_own_value(self):
        editor = self.editor(
            SRTCaption(1, "00:00:00,000", "00:00:02,000", "Hej pa dig"),
            SRTCaption(2, "00:00:02,000", "00:01:05,000", "Hej igen"),
        )

        labels = self.figures(editor)

        assert labels["captions"].text == "2 captions"
        assert labels["duration"].text == "1:05"
        assert labels["wpm"].text.endswith("wpm")

    def test_a_transcription_counts_paragraphs(self):
        """
        The figure says the same noun the dialog's own row label does.
        """

        editor = self.editor(
            SRTCaption(1, "00:00:00,000", "00:00:02,000", "Hej pa dig"),
            SRTCaption(2, "00:00:02,000", "00:01:05,000", "Hej igen"),
        )
        editor.data_format = "txt"

        assert self.figures(editor)["captions"].text == "2 paragraphs"

    def test_one_caption_is_singular(self):
        labels = self.figures(
            self.editor(SRTCaption(1, "00:00:00,000", "00:00:02,000", "Hej"))
        )

        assert labels["captions"].text == "1 caption"
        assert labels["duration"].text == "0:02"

    def test_an_hour_long_recording_says_hours(self):
        assert SRTEditor.format_duration(3725) == "1:02:05"

    def test_a_short_one_does_not(self):
        assert SRTEditor.format_duration(65) == "1:05"

    def test_parsing_fills_it_in(self):
        """
        The page registers its figures while building the toolbar, which is
        before the captions have been parsed -- so the line reported an
        empty editor for the whole session until the first edit. Parsing
        renumbers the captions, and renumbering redraws the line.
        """

        editor = self.editor()
        labels = self.figures(editor)

        assert labels["captions"].text == "0 captions"

        editor.parse_srt(
            "1\n00:00:00,000 --> 00:00:02,000\nHej pa dig\n\n"
            "2\n00:00:02,000 --> 00:00:06,000\nHej igen\n"
        )

        assert labels["captions"].text == "2 captions"
        assert labels["duration"].text == "0:06"
        assert labels["wpm"].text != "0 wpm"

    def test_it_follows_an_edit(self):
        """
        Every edit already refreshes the words-per-minute figure, and the
        caption count and running time change at exactly those moments.
        """

        editor = self.editor(SRTCaption(1, "00:00:00,000", "00:00:02,000", "Hej"))
        labels = self.figures(editor)

        editor.captions.append(
            SRTCaption(2, "00:00:02,000", "00:00:06,000", "Hej igen")
        )
        editor.update_words_per_minute()

        assert labels["captions"].text == "2 captions"
        assert labels["duration"].text == "0:06"

    def test_no_captions_reports_no_running_time(self):
        labels = self.figures(self.editor())

        assert labels["captions"].text == "0 captions"
        assert labels["duration"].text == ""

    def test_a_figure_the_page_does_not_show_is_simply_absent(self):
        """
        The dialog registers the figures it drew; nothing here assumes all
        of them exist.
        """

        editor = self.editor(SRTCaption(1, "00:00:00,000", "00:00:02,000", "Hej"))
        only = self.Label()
        editor.set_status_elements(wpm=only)

        assert only.text.endswith("wpm")

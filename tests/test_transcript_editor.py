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
The transcription editor's server side: speakers, timings and the block
structure. The contenteditable itself needs a browser, but everything it
reports back is handled here and can be tested directly.
"""


import pytest

from utils.caption import SRTCaption
from utils.srt import SRTEditor
from utils.transcript_editor import TranscriptEditor, format_time_label


SEGMENTS = [
    {"speaker": "Speaker 1", "text": "ett.", "start": 0.0, "end": 1.0},
    {"speaker": "Speaker 2", "text": "tva.", "start": 1.0, "end": 2.0},
    {"speaker": "Speaker 2", "text": "tre.", "start": 2.0, "end": 3.0},
    {"speaker": "Speaker 3", "text": "fyra.", "start": 3.0, "end": 4.0},
]


@pytest.fixture
def editor():
    editor = SRTEditor("job-uuid", "txt", "file.txt")

    for name in ("refresh_display", "update_words_per_minute",
                 "save_state_for_undo", "mark_as_changed"):
        setattr(editor, name, lambda *a, **k: None)

    # One caption per segment, so runs of the same speaker can be exercised.
    editor.captions = [
        SRTCaption(
            i + 1,
            editor.seconds_to_timestamp(s["start"]),
            editor.seconds_to_timestamp(s["end"]),
            s["text"],
            speaker=s["speaker"],
        )
        for i, s in enumerate(SEGMENTS)
    ]
    editor.speakers = {s["speaker"] for s in SEGMENTS}

    return editor


@pytest.fixture
def view(editor, monkeypatch):
    view = TranscriptEditor(editor)
    # No component attached, so refreshing is a no-op and notifications are
    # swallowed; the state changes are what matter here.
    monkeypatch.setattr("utils.transcript_editor.ui.notify", lambda *a, **k: None)

    return view


def speakers(editor):
    return [caption.speaker for caption in editor.captions]


class TestAssignSpeaker:
    """
    Clicking a name in the menu moves this block to that speaker. One block:
    who said this is a different question from what a speaker is called.
    """

    def test_assigns_one_block(self, view, editor):
        view.assign_speaker({"id": 2, "speaker": "Speaker 3"})

        assert speakers(editor) == ["Speaker 1", "Speaker 3", "Speaker 2", "Speaker 3"]

    def test_name_is_trimmed(self, view, editor):
        view.assign_speaker({"id": 1, "speaker": "  Speaker 3  "})

        assert editor.captions[0].speaker == "Speaker 3"

    def test_a_name_not_yet_known_is_remembered(self, view, editor):
        view.assign_speaker({"id": 1, "speaker": "Ida"})

        assert "Ida" in editor.speakers

    def test_same_speaker_is_a_no_op(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.assign_speaker({"id": 1, "speaker": "Speaker 1"})

        assert marked == []

    @pytest.mark.parametrize(
        "args",
        [None, "nonsense", {}, {"id": 1}, {"id": 1, "speaker": None},
         {"id": 1, "speaker": "  "}, {"id": 9999, "speaker": "Ida"}],
    )
    def test_bad_payload_is_ignored(self, view, editor, args):
        before = speakers(editor)

        view.assign_speaker(args)

        assert speakers(editor) == before


class TestRenameSpeaker:
    """
    The pencil renames a speaker wherever it appears -- what a diarisation
    label needs, since "Speaker 2" is one person throughout.
    """

    def test_renames_every_block_with_that_name(self, view, editor):
        view.rename_speaker("Speaker 2", "Ida")

        assert speakers(editor) == ["Speaker 1", "Ida", "Ida", "Speaker 3"]

    def test_old_name_leaves_the_list(self, view, editor):
        view.rename_speaker("Speaker 2", "Ida")

        assert "Speaker 2" not in editor.speakers
        assert "Ida" in editor.speakers

    def test_renaming_onto_an_existing_name_is_refused(self, view, editor):
        """
        Merging two speakers is a different act; doing it silently here would
        make the old name unrecoverable.
        """

        view.rename_speaker("Speaker 2", "Speaker 1")

        assert speakers(editor) == ["Speaker 1", "Speaker 2", "Speaker 2", "Speaker 3"]

    @pytest.mark.parametrize("new", ["", "   ", None])
    def test_blank_name_is_refused(self, view, editor, new):
        view.rename_speaker("Speaker 2", new)

        assert "Speaker 2" in editor.speakers

    def test_renaming_to_itself_is_a_no_op(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.rename_speaker("Speaker 2", "Speaker 2")

        assert marked == []

    def test_rename_of_an_unused_speaker_touches_no_blocks(self, view, editor):
        editor.speakers.add("Leftover")
        before = speakers(editor)

        view.rename_speaker("Leftover", "Ida")

        assert speakers(editor) == before
        assert "Ida" in editor.speakers

    @pytest.mark.parametrize(
        "args", [None, "nonsense", {}, {"speaker": None}, {"speaker": "Nobody"}]
    )
    def test_bad_rename_payload_is_ignored(self, view, editor, args):
        before = speakers(editor)

        view.prompt_rename(args)

        assert speakers(editor) == before


class TestAddSpeaker:
    def test_adds_a_name_without_touching_blocks(self, view, editor):
        before = speakers(editor)

        view.add_speaker("Ida")

        assert "Ida" in editor.speakers
        assert speakers(editor) == before

    def test_duplicate_is_refused(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.add_speaker("Speaker 1")

        assert marked == []

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_is_refused(self, view, editor, name):
        before = set(editor.speakers)

        view.add_speaker(name)

        assert editor.speakers == before

    def test_name_is_trimmed(self, view, editor):
        view.add_speaker("  Ida  ")

        assert "Ida" in editor.speakers


class TestBuildSyncsShowEdits:
    """
    "My edits" is a saved preference, restored onto the editor (see
    restore_review_state in pages/srt.py) before build() ever runs.
    TranscriptBody itself always starts a fresh client with showEdits off,
    so without syncing it here, opening the page with the preference
    already on left the live, while-typing marking invisible until some
    unrelated real render happened to call set_show_my_edits and catch the
    two up -- an edit right after opening the page looked unmarked for no
    visible reason.
    """

    def test_the_client_prop_matches_the_restored_preference(self, editor):
        editor.show_my_edits = True

        view = TranscriptEditor(editor)
        view.build()

        assert view.body._props["showEdits"] is True

    def test_off_stays_off(self, editor):
        editor.show_my_edits = False

        view = TranscriptEditor(editor)
        view.build()

        assert view.body._props["showEdits"] is False


class TestBlocks:
    def test_one_block_per_caption(self, view, editor):
        assert len(view.blocks()) == len(editor.captions)

    def test_block_carries_speaker_and_labels(self, view):
        block = view.blocks()[0]

        assert block["speaker"] == "Speaker 1"
        assert block["start_label"] == "00:00:00.000"
        assert block["end_label"] == "00:00:01.000"

    def test_ids_match_caption_indices(self, view, editor):
        assert [b["id"] for b in view.blocks()] == [c.index for c in editor.captions]

    def test_transcription_blocks_have_no_line_counts(self, view):
        """
        A transcription has no length guideline to show, so blocks() must
        not attach one -- see TestSubtitleBlocks for the format that does.
        """

        assert "line_counts" not in view.blocks()[0]


class TestSubtitleLineCounts:
    """
    caption_line_counts is what blocks() surfaces in the margin next to each
    line of a subtitle -- one entry per line, in place of a single combined
    count a transcription has no equivalent of.
    """

    def subtitle_editor(self) -> SRTEditor:
        editor = SRTEditor("job-uuid", "srt", "file.srt")
        editor.data_format = "srt"

        return editor

    def test_one_entry_per_line(self):
        editor = self.subtitle_editor()
        caption = SRTCaption(1, "00:00:00,000", "00:00:02,000", "en rad\ntva rad")

        counts = editor.caption_line_counts(caption)

        assert [c["length"] for c in counts] == [len("en rad"), len("tva rad")]

    def test_a_long_line_is_flagged_alone(self):
        editor = self.subtitle_editor()
        long_line = "x" * 50
        caption = SRTCaption(1, "00:00:00,000", "00:00:02,000", f"{long_line}\nkort")

        counts = editor.caption_line_counts(caption)

        assert [c["exceeded"] for c in counts] == [True, False]

    def test_too_many_lines_flags_no_line(self):
        """
        A count answers for its own line's length and nothing else. A
        caption with more lines than the guideline allows once turned every
        count in it red, which said those lines were too long when they
        were not -- "Validate" is what reports the line count, and the
        tooltip still names it.
        """

        editor = self.subtitle_editor()
        caption = SRTCaption(1, "00:00:00,000", "00:00:02,000", "en\ntva\ntre")

        counts = editor.caption_line_counts(caption)

        assert [c["exceeded"] for c in counts] == [False, False, False]
        assert "3 lines in this caption" in counts[0]["tooltip"]

    def test_the_tooltip_names_the_guideline(self):
        editor = self.subtitle_editor()
        caption = SRTCaption(1, "00:00:00,000", "00:00:02,000", "kort rad")

        tooltip = editor.caption_line_counts(caption)[0]["tooltip"]

        assert "42" in tooltip
        assert "2 lines" in tooltip


class TestSubtitleBlocks:
    """
    blocks() only attaches line_counts for subtitles -- a transcription has
    no length guideline to show, per TestBlocks above.
    """

    def test_subtitle_blocks_carry_line_counts(self, editor, view):
        editor.data_format = "srt"
        editor.captions[0].text = "en rad\ntva rad"

        block = view.blocks()[0]

        assert [c["length"] for c in block["line_counts"]] == [
            len("en rad"),
            len("tva rad"),
        ]


class TestEventPayloads:
    """
    Everything here arrives from the browser, so nothing is trusted.
    """

    @pytest.mark.parametrize(
        "args", [None, "nonsense", {}, {"id": "1"}, {"id": None}, 42]
    )
    def test_bad_block_id_is_ignored(self, view, args):
        assert view.block_id(args) is None
        assert view.caption(view.block_id(args)) is None

    def test_unknown_block_id_is_ignored(self, view):
        assert view.caption(9999) is None

    def test_set_text_ignores_a_non_string(self, view, editor):
        before = editor.captions[0].text

        view.set_text({"id": 1, "text": None})

        assert editor.captions[0].text == before

    def test_set_text_applies(self, view, editor):
        view.set_text({"id": 1, "text": "annat."})

        assert editor.captions[0].text == "annat."

    def test_split_ignores_a_non_numeric_offset(self, view, editor):
        before = len(editor.captions)

        view.split({"id": 1, "offset": "two"})

        assert len(editor.captions) == before


class TestTimeLabel:
    @pytest.mark.parametrize(
        "seconds,expected",
        [
            (0.0, "00:00:00.000"),
            (1226.86, "00:20:26.860"),
            (3599.9999, "01:00:00.000"),
            (-5.0, "00:00:00.000"),
        ],
    )
    def test_matches_the_reference_format(self, seconds, expected):
        assert format_time_label(seconds) == expected


class TestEnterAtBlockEnd:
    """
    Enter at the end of a block has nothing to divide, so it starts a new
    block -- what Enter does at the end of a paragraph anywhere else. The
    subtitle editor's split is unaffected.
    """

    def test_new_block_is_added_after(self, view, editor):
        target = editor.captions[0]

        view.split({"id": target.index, "offset": len(target.text)})

        assert [c.text for c in editor.captions] == ["ett.", "", "tva.", "tre.", "fyra."]

    def test_new_block_inherits_the_speaker(self, view, editor):
        target = editor.captions[0]

        view.split({"id": target.index, "offset": len(target.text)})

        assert editor.captions[1].speaker == "Speaker 1"

    def test_a_new_block_takes_only_the_room_it_has(self, view, editor):
        """
        It starts where the block before it ended, and never runs into the
        one after it -- inserted between two back-to-back blocks there is no
        room at all, and it keeps the zero length a new block always used to
        have. It can be widened by dragging it on the timeline or typing its
        timing.
        """

        target = editor.captions[0]

        view.split({"id": target.index, "offset": len(target.text)})
        added = editor.captions[1]

        assert added.get_start_seconds() == pytest.approx(1.0)
        assert added.get_end_seconds() == pytest.approx(1.0)

    def test_a_new_block_at_the_end_runs_for_a_second(self, view, editor):
        """
        Nothing after it to run into, so it takes NEW_CAPTION_SECONDS. A
        zero-length caption is invisible on the timeline, has nothing to take
        hold of there, and "Validate" objects to it -- a second of room is a
        better starting point when there is a second to give.
        """

        from utils.settings import get_settings

        last = editor.captions[-1]
        boundary = last.get_end_seconds()

        view.split({"id": last.index, "offset": len(last.text)})
        added = editor.captions[-1]

        assert added.text == ""
        assert added.get_start_seconds() == pytest.approx(boundary)
        assert added.get_end_seconds() == pytest.approx(
            boundary + get_settings().NEW_CAPTION_SECONDS
        )

    def test_a_new_block_is_clamped_to_a_narrow_gap(self, view, editor):
        """
        Half a second of silence before the next block means half a second of
        caption, not a second overlapping it.
        """

        first, second = editor.captions[0], editor.captions[1]
        second.start_time = editor.seconds_to_timestamp(
            first.get_end_seconds() + 0.5
        )

        view.split({"id": first.index, "offset": len(first.text)})
        added = editor.captions[1]

        assert added.get_end_seconds() == pytest.approx(
            first.get_end_seconds() + 0.5
        )
        assert added.get_end_seconds() <= second.get_start_seconds()

    def test_blocks_are_renumbered(self, view, editor):
        view.split({"id": editor.captions[0].index, "offset": 4})

        assert [c.index for c in editor.captions] == list(
            range(1, len(editor.captions) + 1)
        )

    def test_trailing_whitespace_counts_as_the_end(self, view, editor):
        target = editor.captions[0]
        target.text = "ett. "

        view.split({"id": target.index, "offset": 4})

        assert editor.captions[1].text == ""

    def test_caret_inside_the_text_still_splits(self, view, editor):
        target = editor.captions[3]
        target.text = "fyra fem"

        view.split({"id": target.index, "offset": 4})

        assert [c.text for c in editor.captions[3:]] == ["fyra", "fem"]
        assert "" not in [c.text for c in editor.captions]


class TestSplitFocus:
    """
    Splitting mid-text leaves the caret at the start of the new second
    block afterward -- the same place a reader who just pressed Enter
    mid-sentence anywhere else expects to keep typing. Unlike a merge's
    removal, the first block keeps its own identity and DOM node here, so
    this is not about the caret ending up somewhere broken without it, just
    about landing where the reader would.
    """

    def focused(self, view) -> list:
        calls = []

        class FakeBody:
            def focus_block(self, block_id, offset=0):
                calls.append((block_id, offset))

            def set_blocks(self, blocks):
                pass

            def set_speakers(self, *args, **kwargs):
                pass

        view.body = FakeBody()
        return calls

    def test_it_focuses_the_start_of_the_new_second_block(self, view, editor):
        target = editor.captions[0]
        calls = self.focused(view)

        view.split({"id": target.index, "offset": 2})

        second = editor.captions[1]
        assert second.text == "t."
        assert calls == [(second.index, 0)]

    def test_a_refused_split_focuses_nothing(self, view, editor):
        """
        Nothing before the caret (see split_caption's own docstring) means
        no second block was ever created -- there is nothing to move the
        caret to, and it is left wherever it already was.
        """

        target = editor.captions[0]
        calls = self.focused(view)

        view.split({"id": target.index, "offset": 0})

        assert calls == []

    def test_the_end_of_block_branch_is_unaffected(self, view, editor):
        """
        insert_block_after already focuses the block it starts -- this
        class only covers the mid-text branch, but a regression here would
        show up as a second, conflicting focus_block call for the same
        split.
        """

        target = editor.captions[0]
        calls = self.focused(view)

        view.split({"id": target.index, "offset": len(target.text)})

        assert calls == [(editor.captions[1].index, 0)]


class TestBlockShortcuts:
    """
    Ctrl/Cmd with the caret in a block: split, merge, delete, add after and
    handing a word across a boundary. One list per format
    (`subtitleShortcut`, `transcriptionShortcut`), kept apart so a key given
    to one cannot silently reach the other -- they agree today, add-after
    aside, since a paragraph is split, merged, deleted and trimmed exactly
    as a caption is. They live in the component rather than the page's own
    document-level keyboard handler because each has to know which block the
    caret is in.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def method(self, name: str) -> str:
        """
        The named method's own source. Anchored on the definition -- its own
        indented line -- rather than the first mention of the name, which is
        a call site inside onKeydown for every one of these.
        """

        source = self.source()
        body = source[source.index(f"\n    {name}(event") + 1:]

        return body[: body.index("\n    },\n")]

    def body(self) -> str:
        return self.method("onKeydown")

    def subtitles(self) -> str:
        return self.method("subtitleShortcut")

    def transcription(self) -> str:
        return self.method("transcriptionShortcut")

    def test_they_are_gated_on_a_modifier_alone(self):
        assert "if (event.ctrlKey || event.metaKey) {" in self.body()

    def test_the_format_picks_which_list_answers(self):
        body = self.body()

        assert "this.subtitleMode" in body
        assert "? this.subtitleShortcut(event, at)" in body
        assert ": this.transcriptionShortcut(event, at)" in body

    def test_add_caption_after_is_shift_enter_and_subtitles_only(self):
        """
        It is the keyboard's half of the caption row's own "+", and a
        transcription has no such row.
        """

        subtitles = self.subtitles()

        assert 'if (event.key === "Enter" && event.shiftKey) {' in subtitles
        assert 'this.report(event, "addblock", { id: at.id })' in subtitles
        assert "addblock" not in self.transcription()

    def test_add_is_checked_before_the_plain_split(self):
        """
        Ctrl/Cmd+Shift+Enter would otherwise fall through to the split,
        which only looks for Enter with a modifier and would not notice the
        Shift.
        """

        body = self.body()

        assert body.index("this.subtitleShortcut") < body.index('$emit("splitblock"')

    def test_the_word_moves_report_their_direction_in_both(self):
        for keys in (self.subtitles(), self.transcription()):
            assert 'if (event.key === "ArrowUp") {' in keys
            assert (
                'this.report(event, "moveword", { id: at.id, direction: "previous" })'
                in keys
            )
            assert 'if (event.key === "ArrowDown") {' in keys
            assert (
                'this.report(event, "moveword", { id: at.id, direction: "next" })'
                in keys
            )

    def test_merge_and_delete_refuse_the_command_key_in_both(self):
        """
        Cmd+D and Cmd+M are the browser's own bookmark and minimise on a
        Mac, and taking them would be taking them from the whole window.
        """

        for keys in (self.subtitles(), self.transcription()):
            assert 'if (key === "m" && !event.metaKey) {' in keys
            assert 'if (key === "d" && !event.metaKey) {' in keys

    def test_merge_goes_to_the_next_block_in_both(self):
        for keys in (self.subtitles(), self.transcription()):
            branch = keys[keys.index('if (key === "m"'):]

            assert (
                'this.report(event, "mergeblock", { id: at.id, direction: "next" })'
                in branch
            )

    def test_delete_reports_the_block_the_caret_is_in_in_both(self):
        for keys in (self.subtitles(), self.transcription()):
            branch = keys[keys.index('if (key === "d"'):]

            assert 'this.report(event, "deleteblock", { id: at.id })' in branch

    def test_neither_list_claims_a_key_it_does_not_handle(self):
        """
        Falling through to false is what lets Ctrl/Cmd+Enter reach the split
        branch below, and leaves every other modifier combination to the
        page's own document-level handler.
        """

        for keys in (self.subtitles(), self.transcription()):
            assert keys.rstrip().endswith("return false;")

    def test_each_one_stops_the_browser_and_flushes_first(self):
        """
        A pending edit has to reach the server before the structure changes
        under it, and every one of these keys means something to the browser
        too. Both lists report through the same helper, so this is asserted
        once, on it.
        """

        report = self.method("report")

        assert "event.preventDefault()" in report
        assert report.index("this.flush()") < report.index("this.$emit(name, payload)")

        for keys in (self.subtitles(), self.transcription()):
            assert "event.preventDefault()" not in keys
            assert "this.flush()" not in keys


class TestTheMusicNote:
    """
    A caption of song, or of music under the picture, is written with a
    music note -- and it is not a character any keyboard offers.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_it_rides_the_same_row_as_the_other_caption_actions(self):
        source = self.source()

        assert "transcript-action transcript-action-note" in source
        assert "<q-tooltip>Insert music note</q-tooltip>" in source

    def test_the_button_wears_the_character_it_inserts(self):
        """
        There is no icon for it, and the character is the clearest possible
        label for the button.
        """

        source = self.source()

        assert '<span class="transcript-note-glyph">♪</span>' in source

    def test_pressing_the_icon_does_not_move_the_caret(self):
        """
        Pressing the mouse down anywhere moves the caret, and by the time
        the click arrived the reader's own caret was gone -- every note
        landed at the end of the caption because the fallback was all that
        was left. The split icon reads the caret too, and needs the same.
        """

        source = self.source()

        for action in ("transcript-action-note", "transcript-action-split"):
            branch = source[source.index(action):]
            branch = branch[: branch.index("</div>")]

            assert "@mousedown.prevent.stop" in branch, action

    def test_it_lands_at_the_caret(self):
        body = self.method("insertNote")

        assert "if (at && at.id === id) {" in body
        assert "this.writeNote(NOTE)" in body

        writing = self.method("writeNote")

        assert "const node = document.createTextNode(text);" in writing
        assert "range.insertNode(node)" in writing

    def test_a_caret_elsewhere_wraps_the_whole_caption(self):
        """
        The reader clicked the icon without ever putting the caret in this
        caption, so the note belongs to the caption as a whole -- and a
        caption that is all music is written with one at each end,
        "♪ Lyrics ♪".
        """

        body = self.method("insertNote")

        end = body.index("this.placeCaretAt(block, text.length)")
        start = body.index("this.placeCaretAt(block, 0)")

        # The end first, or the opening note moves it along and the length
        # read before either insert is stale.
        assert end < start

        assert 'this.writeNote(`${/\\s$/.test(text) ? "" : " "}${NOTE}`)' in body
        assert 'this.writeNote(`${NOTE}${/^\\s/.test(text) ? "" : " "}`)' in body

    def test_an_empty_caption_gets_one_note_rather_than_a_pair(self):
        """
        A pair with nothing between them is not what "this caption is
        music" looks like.
        """

        body = self.method("insertNote")

        assert "if (!text.trim()) {" in body
        assert body.index("if (!text.trim()) {") < body.index(
            "this.placeCaretAt(block, 0)"
        )

    def test_it_is_reported_as_an_ordinary_edit(self):
        """
        It is a character like any other once it is in: the same onInput
        that follows a keystroke carries it to the server, marks it as the
        reader's own and redraws the character counts. Once per click,
        including the wrapping pair -- two would be two undo steps for one
        gesture.
        """

        body = self.method("insertNote")

        assert body.count("this.onInput();") == 3
        assert "this.onInput();" not in self.method("writeNote")

    def method(self, name: str) -> str:
        source = self.source()
        body = source[source.index(f"\n    {name}(") + 1:]

        return body[: body.index("\n    },")]


class TestMoveWordIsWired:
    """
    The editor has had move_first_word_to_previous/move_last_word_to_next
    for a while, but nothing called them -- there was no event for the
    client to raise.
    """

    def test_the_event_reaches_the_view(self):
        import pathlib

        source = pathlib.Path("utils/transcript_editor.py").read_text()

        assert 'self.body.on("moveword", lambda event: self.move_word(event.args))' in source

    def test_previous_moves_the_first_word_back(self, view, editor, monkeypatch):
        moved = []
        monkeypatch.setattr(
            editor, "move_first_word_to_previous", lambda c: moved.append(c.index)
        )
        view.focus = lambda *a, **k: None

        view.move_word({"id": editor.captions[1].index, "direction": "previous"})

        assert moved == [editor.captions[1].index]

    def test_next_moves_the_last_word_on(self, view, editor, monkeypatch):
        moved = []
        monkeypatch.setattr(
            editor, "move_last_word_to_next", lambda c: moved.append(c.index)
        )
        view.focus = lambda *a, **k: None

        view.move_word({"id": editor.captions[0].index, "direction": "next"})

        assert moved == [editor.captions[0].index]

    def test_an_unknown_direction_does_nothing(self, view, editor, monkeypatch):
        calls = []
        monkeypatch.setattr(editor, "move_first_word_to_previous", lambda c: calls.append(c))
        monkeypatch.setattr(editor, "move_last_word_to_next", lambda c: calls.append(c))

        view.move_word({"id": editor.captions[0].index, "direction": "sideways"})

        assert calls == []

    def test_an_unknown_block_is_harmless(self, view, editor):
        view.move_word({"id": 9999, "direction": "next"})

    def test_the_caret_stays_in_the_caption_being_trimmed(self, view, editor, monkeypatch):
        """
        Following the word across would make a second press mean something
        different from the first.
        """

        monkeypatch.setattr(editor, "move_last_word_to_next", lambda c: None)
        focused = []
        view.focus = lambda index, *a, **k: focused.append(index)

        view.move_word({"id": editor.captions[0].index, "direction": "next"})

        assert focused == [editor.captions[0].index]


class TestSubtitleEnter:
    """
    Enter means the same thing in both modes: Enter starts a new caption (a
    new block, in a transcription) and Shift+Enter breaks the line inside
    the one being edited -- what Enter does in a document, and what
    Shift+Enter does in most things that have both. See the onKeydown
    routing itself, since only the client-side gate decides which one a
    keypress reaches.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def keydown_body(self) -> str:
        source = self.source()
        body = source[source.index("onKeydown(event) {"):]

        return body[: body.index("\n    },\n")]

    def test_shift_enter_breaks_the_line(self):
        body = self.keydown_body()

        assert (
            'event.key === "Enter" && event.shiftKey && !event.ctrlKey && !event.metaKey'
            in body
        )
        assert "this.insertLineBreak()" in body

    def test_the_line_break_is_checked_before_the_split(self):
        """
        The split branch only asks for Enter, and would otherwise swallow
        Shift+Enter along with it.
        """

        body = self.keydown_body()

        assert body.index("this.insertLineBreak()") < body.index(
            '$emit("splitblock"'
        )

    def test_a_bare_enter_starts_a_new_caption(self):
        """
        The text after the caret goes into it; at the end of a caption there
        is nothing to move and a new empty one is started instead.
        """

        body = self.keydown_body()
        split = body[body.index('if (event.key === "Enter") {'):]

        assert '$emit("splitblock", { id: at.id, offset: at.offset })' in split

    def test_ctrl_enter_still_splits(self):
        """
        What it meant when Enter itself was the line break. Nothing
        intercepts it, so it falls through to the same branch.
        """

        body = self.keydown_body()
        line_break = body[body.index("this.insertLineBreak()") - 400:]
        gate = line_break[: line_break.index("this.insertLineBreak()")]

        assert "!event.ctrlKey && !event.metaKey" in gate

    def insert_line_break_body(self) -> str:
        source = self.source()
        body = source[source.index("insertLineBreak() {"):]

        return body[: body.index("\n    },\n")]

    def test_it_builds_a_real_text_node_rather_than_execcommand(self):
        """
        document.execCommand("insertText", ..., "\\n") looked like the
        natural fit but corrupted surrounding content in testing -- went as
        far as deleting it -- so this is spliced in by hand with the Range
        API instead.
        """

        body = self.insert_line_break_body()

        assert "execCommand" not in body
        assert "document.createTextNode(" in body
        assert "range.insertNode(node)" in body

    def test_it_reports_the_change_itself(self):
        """
        Inserting through the DOM this way fires no input event, so onInput's
        own bookkeeping never runs unless this calls it directly.
        """

        body = self.insert_line_break_body()

        assert "this.onInput()" in body

    def test_a_break_at_the_true_end_gets_a_caret_anchor(self):
        """
        A "\\n" with nothing after it gets no line box at all in most
        browsers -- a forced break needs real content following it to be
        reserved room for -- so a break landing at the very end of the
        caption's text carries a zero-width space along with it, giving the
        browser something to hang a caret on for that now-empty last line.
        A break in the middle of existing text needs none of this: the text
        after it already earns the line box.
        """

        body = self.insert_line_break_body()

        assert 'atEnd ? "\\n\\u200B" : "\\n"' in body
        assert "this.plainText(rest.toString()).length === 0" in body

    def test_the_caret_lands_after_the_break_either_way(self):
        """
        setStart(node, 1) means "right after the break" whether or not the
        zero-width space was added -- position 1 is the end of a bare "\\n"
        and the midpoint of "\\n\\u200B" alike.
        """

        body = self.insert_line_break_body()

        assert "range.setStart(node, 1)" in body


class TestPaste:
    """
    A contenteditable inserts the clipboard's HTML flavour unless told
    otherwise -- markup from whatever page the reader copied from, and an
    <img onerror=...> in it runs its handler on insertion, in this origin,
    with this session. The editor only ever keeps plain text, so paste is
    reduced to the text/plain flavour before anything reaches the DOM.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def paste_body(self) -> str:
        source = self.source()
        body = source[source.index("onPaste(event) {"):]

        return body[: body.index("\n    },")]

    def test_the_editor_intercepts_paste_and_drop(self):
        source = self.source()

        assert '@paste="onPaste"' in source
        # The same HTML flavour arrives by drag as by paste.
        assert "@drop.prevent" in source
        assert "@dragover.prevent" in source

    def test_only_the_plain_text_flavour_is_read(self):
        body = self.paste_body()

        assert "event.preventDefault()" in body
        assert 'getData("text/plain")' in body
        assert "getData(\"text/html\")" not in body

    def test_it_is_inserted_as_a_text_node_not_markup(self):
        """
        The same Range splice insertLineBreak uses -- never innerHTML, never
        execCommand, so the pasted characters can only ever be characters.
        """

        body = self.paste_body()

        assert "document.createTextNode(" in body
        assert "innerHTML" not in body
        assert "execCommand" not in body

    def test_the_edit_is_reported_like_typing(self):
        """
        A programmatic insertion fires no input event, so onInput is called
        by hand -- the same bookkeeping a keystroke gets.
        """

        body = self.paste_body()

        assert "this.onInput()" in body

    def test_a_selection_into_another_block_goes_to_the_server(self):
        """
        Deleting across blocks here would take the blocks' own structure
        with it -- the gutters between are not editable text -- so the
        whole gesture is reported as one deleterange carrying the pasted
        text, and the server sends a fresh set of blocks back.
        """

        body = self.paste_body()

        assert "const span = this.selectionSpan();" in body
        assert 'this.$emit("deleterange", { ...span, text });' in body

    def test_a_trailing_newline_still_earns_its_line_box(self):
        """
        insertLineBreak's own rule: a "\n" with nothing after it gets no
        line box, so a zero-width space follows it -- and plainText strips
        that back out before the text is read for anything.
        """

        body = self.paste_body()

        assert 'text.endsWith("\\n") && atEnd' in body
        assert "\\u200B" in body


class TestPlainText:
    """
    The zero-width space insertLineBreak plants at a caption's true end
    (see TestSubtitleEnter) is a rendering aid only -- caret(), which
    split-at-cursor and the Backspace/Delete edge checks all read, and
    onInput's own report to the server both have to see the caption's real
    text, not that placeholder.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_it_strips_the_zero_width_space(self):
        source = self.source()
        body = source[source.index("plainText(text) {"):]
        body = body[: body.index("\n    },\n")]

        assert 'replace(/\\u200B/g, "")' in body

    def test_caret_reads_through_it(self):
        source = self.source()
        body = source[source.index("caret() {"):]
        body = body[: body.index("\n    },\n")]

        assert "this.offsetIn(block, range.startContainer, range.startOffset)" in body
        assert "this.plainText(block.textContent).length" in body

        measured = source[source.index("offsetIn(block, container, offset) {"):]
        measured = measured[: measured.index("\n    },\n")]

        assert "this.plainText(measure.toString()).length" in measured

    def test_the_reported_edit_reads_through_it(self):
        source = self.source()
        body = source[source.index("onInput() {"):]
        body = body[: body.index("\n    },\n")]

        assert "this.plainText(at.block.textContent)" in body


class TestCaretSurvivesUndo:
    """
    A block that was typed into and never got a real render in between (see
    the revision watcher's own comment on why undo, most of all, is when
    that happens) gets its DOM element thrown away and rebuilt once undo
    finally does force one -- changing its key is what makes Vue rebuild
    rather than patch it. A caret anchored inside the old element does not
    survive that: the browser collapses it to the very start of the
    contenteditable, which reads as the cursor jumping to the top of the
    page. Reading it before the rebuild and restoring it after is what
    keeps the reader where undo actually put them.

    A block that keeps its own key is not exempt either -- undoing a merge
    patches the survivor's runs back down to fewer spans than it had a
    moment ago, and a caret anchored in one of the spans that patch removes
    is lost the same way, so this is not restricted to blocks known to be
    dirty; every render tries, and a block whose content did not change
    under the caret just gets put back where it already was.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def revision_watcher_body(self) -> str:
        source = self.source()
        body = source[source.index("revision() {"):]

        return body[: body.index("\n    },\n")]

    def test_the_caret_is_read_before_the_block_is_keyed_away(self):
        body = self.revision_watcher_body()

        before_rekey = body[: body.index("this.dirty.forEach(")]

        assert "const restoring = this.caret();" in before_rekey

    def test_it_is_restored_after_the_rebuild_not_before(self):
        body = self.revision_watcher_body()

        next_tick = body[body.index("this.$nextTick(() => {"):]

        assert "this.placeCaretAt(block, offset)" in next_tick

    def test_the_offset_is_carried_by_the_blocks_own_change_in_length(self):
        """
        Undo (most of all) changes the very text the caret's offset was
        measured against -- restoring that offset unchanged into a block
        that shrank lands past the word the caret was actually at, into
        whatever now sits where the old, larger offset used to point,
        which is exactly how a word one over from the one just undone
        started reading as edited: the reader kept typing where they
        thought the caret still was, and it was not. Carrying the block's
        own change in length along with the offset is what keeps it at the
        same word regardless of which way the text moved.
        """

        body = self.revision_watcher_body()

        next_tick = body[body.index("this.$nextTick(() => {"):]

        assert "const newLength = this.plainText(block.textContent).length;" in next_tick
        assert (
            "const offset = Math.max(\n"
            "              0,\n"
            "              restoring.offset + (newLength - restoring.length)\n"
            "            );"
            in next_tick
        )

    def test_editing_word_is_reset_along_with_the_rest(self):
        """
        Left stale it would still compare unequal to whatever wordAt finds
        next -- a detached node matches nothing -- so this changes no
        behaviour by itself; it just keeps nothing pointing at an element
        that no longer exists, the same reasoning newWordBoundary and
        liveCounts are already reset here for.
        """

        body = self.revision_watcher_body()

        before_rebuild = body[: body.index("this.$nextTick(() => {")]

        assert "this.editingWord = null;" in before_rebuild

    def test_synthetic_space_is_reset_along_with_the_rest(self):
        """
        A block that was typed into is rebuilt from scratch on a real
        render, same as editingWord and newWordBoundary above -- whatever
        synthetic separator effectiveSpan's headMatch branch left standing
        in the old DOM is about to stop existing along with it.
        """

        body = self.revision_watcher_body()

        before_rebuild = body[: body.index("this.$nextTick(() => {")]

        assert "this.syntheticSpace = null;" in before_rebuild

    def test_place_caret_at_falls_back_to_the_end(self):
        """
        The block undo sent down can be shorter than where the caret was --
        collapsing to the end rather than failing is what a caption that
        shrank out from under the caret needs.
        """

        source = self.source()
        body = source[source.index("placeCaretAt(block, offset) {"):]
        body = body[: body.index("\n    },\n")]

        assert "range.selectNodeContents(block);" in body
        assert "range.collapse(false);" in body


class TestSubtitleMargin:
    """
    A subtitle's margin carries only its index and its per-line character
    counts -- the timing moved into the cell, over the text it times, so it
    is no longer something the margin shows at all. See TestTiming for
    that, and caption_line_counts on the Python side for what feeds the
    counts here (redrawn live from the typed text by computeLineCounts --
    see TestLiveLineCounts).
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_the_index_is_in_the_margin(self):
        source = self.source()
        gutter = source[source.index('class="transcript-gutter"'):]
        gutter = gutter[: gutter.index("</div><div")]

        assert "#{{ block.id }}" in gutter

    def test_one_count_per_line(self):
        source = self.source()

        assert "transcript-subtitle-counts" in source
        assert (
            "v-for=\"(count, i) in (liveCounts[block.id] || block.line_counts)\""
            in source
        )


class TestLiveLineCounts:
    """
    The character-count guideline in the margin has to move as the caption
    is typed into, not just at the next real render -- set_text deliberately
    does not trigger one (see its own docstring), so nothing would update
    the counts at all if this did not exist. Mirrors caption_line_counts on
    the Python side; TestSubtitleLineCounts covers the guideline logic
    itself; this just checks the two stay wired the same way.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_on_input_recomputes_live_counts_for_subtitles_only(self):
        source = self.source()
        body = source[source.index("onInput() {"):]
        body = body[: body.index("\n    },\n")]

        assert "if (this.subtitleMode)" in body
        assert "this.liveCounts = { ...this.liveCounts, [at.id]: this.computeLineCounts(text) };" in body

    def test_a_real_render_clears_the_guess(self):
        """
        Once the server has answered with its own authoritative counts, the
        local guess has to step aside for them -- otherwise a stale guess
        could keep showing after an undo or a split changes the text some
        other way than typing into it.
        """

        source = self.source()
        watcher = source[source.index("revision() {"):]
        watcher = watcher[: watcher.index("this.$nextTick(() => {")]

        assert "this.liveCounts = {};" in watcher

    def test_the_guideline_settings_are_props_not_hardcoded(self):
        source = self.source()

        assert "characterLimit: { type: Number, default: 42 }" in source
        assert "maxSubtitleLines: { type: Number, default: 2 }" in source


class TestCaretBlockTracking:
    """
    Which caption the caret is in, tracked only so the editor can show it --
    separate from activeId, which is the caption being played.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_the_cell_marks_itself(self):
        source = self.source()

        assert "'transcript-cell-editing': block.id === caretId" in source

    def test_the_caret_is_re_read_rather_than_tracked(self):
        """
        The caret moves for reasons nothing in the component hears about --
        an arrow key, a click, a drag -- so it is read from the selection
        rather than followed through every edit.
        """

        source = self.source()
        body = source[source.index("updateCaretBlock() {"):]
        body = body[: body.index("\n    },")]

        assert "const at = this.caret();" in body
        assert "this.caretId = at ? at.id : null;" in body

    def test_arrow_keys_move_it_too(self):
        source = self.source()

        assert '@keyup="updateCaretBlock"' in source

    def test_leaving_the_editor_clears_it(self):
        """
        Nothing is being edited once the caret is gone, and the pending edit
        still has to be sent -- which is what @blur did before this.
        """

        source = self.source()
        body = source[source.index("onBlur() {"):]
        body = body[: body.index("\n    },")]

        assert "this.flush();" in body
        assert "this.caretId = null;" in body


class TestTiming:
    """
    A caption's start and end are edited directly where they are shown, in
    the cell above the text they time -- no dialog, in either mode. See
    retime() on the Python side for what a typed value reaches.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_the_timing_sits_over_the_text_not_the_margin(self):
        source = self.source()

        assert "transcript-subtitle-content" in source
        gutter = source[source.index('class="transcript-gutter"'):]
        gutter = gutter[: gutter.index("</div><div")]

        assert "transcript-time-input" not in gutter

    def test_it_is_a_plain_input_not_a_dialog_trigger(self):
        """
        No @click handler opening a slider dialog anywhere -- that dialog
        does not exist any more, in either mode -- and one input pair for
        each of the two branches, transcription and subtitle.
        """

        source = self.source()

        assert source.count("transcript-time-input") >= 4
        assert "timeclick" not in source

    def test_typing_in_it_does_not_reach_the_document_handler(self):
        """
        Enter in this input commits the edit; Enter in the document at large
        splits a caption. Without stopping propagation, typing a time would
        also be typing into whichever handler reads document-level keydowns.
        """

        source = self.source()
        body = source[source.index("onTimeInputKeydown(event) {"):]
        body = body[: body.index("\n    },\n")]

        assert "event.stopPropagation()" in body

    def test_it_is_marked_dirty_before_reporting(self):
        """
        A reply that leaves the value exactly as it was -- a mistyped time
        is refused, not guessed at -- is an unchanged prop, which is a patch
        Vue's own diff skips. Without forcing a fresh remount the input
        would keep showing whatever was typed, never having actually saved
        it.
        """

        source = self.source()
        body = source[source.index("retimeBlock(id, edge, event) {"):]
        body = body[: body.index("\n    },\n")]

        assert "this.dirty.add(id)" in body
        assert "$emit(\"retime\"" in body

    def test_the_actions_ride_the_timing_row(self):
        """
        The four caption actions act on this specific caption, the same as
        the timing itself, so they ride the row it sits on rather than
        sitting beside the text below.
        """

        source = self.source()
        time_row = source[source.index('class="transcript-subtitle-time"'):]
        time_row = time_row[: time_row.index("</div></div><div")]

        assert "transcript-cell-actions" in time_row
        assert "transcript-action-split" in time_row
        assert "transcript-action-merge" in time_row
        assert "transcript-action-add" in time_row
        assert "transcript-action-delete" in time_row
        assert "transcript-action-merge" in time_row
        assert "transcript-action-add" in time_row
        assert "transcript-action-delete" in time_row


class TestRetime:
    """
    retime() is what a time typed directly into its input reaches, in
    either mode -- there is no dialog any more.
    """

    def test_a_valid_value_is_applied(self, view, editor):
        from utils.transcript_editor import format_time_label

        target = editor.captions[0]

        view.retime({
            "id": target.index,
            "edge": "start",
            "value": format_time_label(0.5),
        })

        assert target.get_start_seconds() == pytest.approx(0.5)

    def test_the_other_edge_is_left_alone(self, view, editor):
        target = editor.captions[0]
        original_end = target.get_end_seconds()

        view.retime({
            "id": target.index,
            "edge": "start",
            "value": "00:00:00.500",
        })

        assert target.get_end_seconds() == pytest.approx(original_end)

    def test_unparsable_text_is_refused(self, view, editor):
        target = editor.captions[0]
        original_start = target.start_time

        view.retime({"id": target.index, "edge": "start", "value": "garbage"})

        assert target.start_time == original_start

    def test_an_end_before_the_start_is_refused(self, view, editor):
        target = editor.captions[0]
        original_end = target.end_time

        view.retime({
            "id": target.index,
            "edge": "end",
            "value": "00:00:00.000",
        })

        assert target.end_time == original_end

    def test_an_unknown_block_is_harmless(self, view):
        view.retime({"id": 9999, "edge": "start", "value": "00:00:01.000"})

    def test_an_unknown_edge_is_harmless(self, view, editor):
        target = editor.captions[0]
        before = (target.start_time, target.end_time)

        view.retime({"id": target.index, "edge": "middle", "value": "00:00:01.000"})

        assert (target.start_time, target.end_time) == before


class TestParseTimeLabel:
    """
    The inverse of format_time_label -- what a typed value in the margin is
    read back as.
    """

    def test_it_round_trips_format_time_label(self):
        from utils.transcript_editor import format_time_label, parse_time_label

        assert parse_time_label(format_time_label(92.44)) == pytest.approx(92.44)

    def test_a_comma_is_accepted_as_the_decimal_point(self):
        """
        SRT itself writes a comma, and it is the first thing a Swedish
        keyboard offers -- refusing it reverted the whole edit with no
        explanation.
        """

        from utils.transcript_editor import parse_time_label

        assert parse_time_label("00:00:23,340") == pytest.approx(23.34)

    def test_fewer_than_three_decimals_are_accepted(self):
        """
        "00:00:23.4" means 23.4 seconds -- decimals, not a count of
        milliseconds. Requiring exactly three digits threw the value away
        instead.
        """

        from utils.transcript_editor import parse_time_label

        assert parse_time_label("00:00:23.4") == pytest.approx(23.4)
        assert parse_time_label("00:00:23.04") == pytest.approx(23.04)

    def test_a_value_typed_with_a_space_still_parses(self):
        """
        The editor drew the milliseconds set apart ("00:00:01 .500") for a
        long time, so a reader who types the space out of habit -- or pastes
        a timestamp from an older screenshot -- is still understood.
        """

        from utils.transcript_editor import parse_time_label

        assert parse_time_label("00:00:01 .500") == pytest.approx(1.5)

    def test_garbage_is_refused(self):
        from utils.transcript_editor import parse_time_label

        assert parse_time_label("not a time") is None
        assert parse_time_label("") is None
        assert parse_time_label(None) is None


class TestSplitWithNoOffset:
    """
    The server half of the same fix: no offset means no caret, so the
    caption is halved rather than cut at a position nobody chose.
    """

    def test_no_offset_halves_the_caption(self, view, editor, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor.captions[0].text = "internationalization matters"
        view.focus = lambda *a, **k: None

        view.split({"id": editor.captions[0].index, "offset": None})

        assert editor.captions[0].text == "internationalization"
        assert editor.captions[1].text == "matters"

    def test_an_offset_of_zero_is_not_mistaken_for_no_offset(self, view, editor):
        """
        0 is falsy but is a real caret position -- at the very start, where
        there is nothing on one side and the split is refused.
        """

        before = len(editor.captions)
        view.focus = lambda *a, **k: None

        view.split({"id": editor.captions[0].index, "offset": 0})

        assert len(editor.captions) == before

    def test_a_non_numeric_offset_is_still_ignored(self, view, editor):
        before = len(editor.captions)

        view.split({"id": editor.captions[0].index, "offset": "middle"})

        assert len(editor.captions) == before

    def test_the_new_second_block_is_focused(self, view, editor, monkeypatch):
        monkeypatch.setattr("utils.srt.ui.notify", lambda *a, **k: None)
        editor.captions[0].text = "one two three four"
        focused = []
        view.focus = lambda index, *a, **k: focused.append(index)

        view.split({"id": editor.captions[0].index, "offset": None})

        assert focused == [editor.captions[1].index]


class TestSplitButton:
    """
    The split icon in a caption's own action row, alongside add and delete --
    the mouse equivalent of Ctrl/Cmd+Enter. A click carries no cursor
    position of its own, so it prefers the caret when it is already in this
    caption, and otherwise sends none at all and lets the server halve the
    caption between two words.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def split_at_body(self) -> str:
        source = self.source()
        body = source[source.index("splitAt(id) {"):]

        return body[: body.index("\n    },\n")]

    def test_the_icon_is_wired_to_splitat(self):
        assert '@click.stop="splitAt(block.id)"' in self.source()

    def test_it_prefers_the_caret_already_in_this_caption(self):
        body = self.split_at_body()

        assert "at.id === id" in body
        assert "at.offset" in body

    def test_it_sends_no_offset_when_the_caret_is_elsewhere(self):
        """
        It used to send the middle of the text as though it were a caret,
        which made a made-up position indistinguishable from one the reader
        chose -- and a chosen one is honoured to the character, so the break
        landed inside whatever word the middle fell in. With no offset the
        server halves the caption instead, between two words.
        """

        body = self.split_at_body()

        assert "at && at.id === id ? at.offset : null" in body
        assert "Math.floor(text.length / 2)" not in body

    def test_it_flushes_before_splitting(self):
        """
        Any edit still pending in this caption's text has to reach the
        server before the split does, or it is lost -- the same reasoning
        Ctrl/Cmd+Enter's own path follows.
        """

        body = self.split_at_body()

        assert "this.flush()" in body
        assert '$emit("splitblock"' in body


class TestMergeButton:
    """
    The merge icon in a caption's own action row, alongside split, add and
    delete -- the mouse equivalent of Delete at the end of its text. Always
    merges with the caption after this one: reuses the existing
    mergeblock/direction:"next" event that key already emits, rather than a
    new server-side method, and offering only one direction keeps the row
    from needing an icon per direction for what a reader can already reach
    the other way from the neighbouring caption.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/transcript_editor.js").read_text()

    def merge_with_next_body(self) -> str:
        source = self.source()
        body = source[source.index("mergeWithNext(id) {"):]

        return body[: body.index("\n    },\n")]

    def test_the_icon_is_wired_to_mergewithnext(self):
        assert '@click.stop="mergeWithNext(block.id)"' in self.source()

    def test_it_merges_with_the_next_caption(self):
        body = self.merge_with_next_body()

        assert '$emit("mergeblock"' in body
        assert '"next"' in body

    def test_it_flushes_before_merging(self):
        assert "this.flush()" in self.merge_with_next_body()


class TestMergeFocus:
    """
    Enter at the end of a block starts a new one (see TestEnterAtBlockEnd);
    Backspace at its start merges it away again. Merging previous removes
    that very block -- the one the caret was in -- and the browser does not
    leave the caret anywhere sensible once its own DOM node is gone: it was
    reported landing in the block after, unrelated to either side of the
    merge. Refocusing the surviving block at the seam between the two texts
    is what a backspace-merge reads as anywhere else a caret keeps working
    after one.
    """

    def focused(self, view) -> list:
        calls = []

        class FakeBody:
            def focus_block(self, block_id, offset=0):
                calls.append((block_id, offset))

            def set_blocks(self, blocks):
                pass

            def set_speakers(self, *args, **kwargs):
                pass

        view.body = FakeBody()
        return calls

    def test_merging_an_empty_caption_previous_focuses_the_plain_end(self, view, editor):
        """
        Enter at the end starts an empty block (see TestEnterAtBlockEnd);
        Backspace right away merges it straight back out. Nothing on that
        side means merge_with_previous adds no separator (see its own
        comment), so the seam is just the survivor's own end, not one past
        it -- landing one further would have been past the survivor's own
        text, wherever the fallback in placeCaretAt happens to send it.
        """

        first = editor.captions[0]
        view.split({"id": first.index, "offset": len(first.text)})
        added = editor.captions[1]
        calls = self.focused(view)

        view.merge({"id": added.index, "direction": "previous"})

        assert calls == [(first.index, len("ett."))]
        assert first.text == "ett."

    def test_merging_a_real_caption_previous_focuses_past_the_join(self, view, editor):
        first = editor.captions[0]
        second = editor.captions[1]
        calls = self.focused(view)

        view.merge({"id": second.index, "direction": "previous"})

        assert calls == [(first.index, len("ett.") + len("\n"))]
        assert first.text == "ett.\ntva."

    def test_merging_next_focuses_the_survivor_at_its_old_end(self, view, editor):
        first = editor.captions[0]
        second = editor.captions[1]
        calls = self.focused(view)

        view.merge({"id": first.index, "direction": "next"})

        assert calls == [(first.index, len("ett."))]
        assert first.text == "ett.\ntva."
        assert second not in editor.captions

    def test_merging_at_the_very_start_is_harmless(self, view, editor):
        calls = self.focused(view)

        view.merge({"id": editor.captions[0].index, "direction": "previous"})

        assert calls == []

    def test_merging_at_the_very_end_is_harmless(self, view, editor):
        calls = self.focused(view)

        view.merge({"id": editor.captions[-1].index, "direction": "next"})

        assert calls == []


class TestMergeEmptyCaption:
    """
    "Add caption after" then Backspace right away merges the empty caption
    it just started straight back out (Backspace at the start of an empty
    block merges previous). Joining with "\n" unconditionally left that
    newline on the original caption even though there was nothing on the
    other side for it to separate -- a blank line the reader never typed,
    appended to a caption they never touched.
    """

    def test_merging_an_empty_caption_previous_adds_no_newline(self, editor):
        first, second = editor.captions[0], editor.captions[1]
        second.text = ""

        editor.merge_with_previous(second)

        assert first.text == "ett."

    def test_merging_an_empty_caption_next_adds_no_newline(self, editor):
        first, second = editor.captions[0], editor.captions[1]
        second.text = ""

        editor.merge_with_next(first)

        assert first.text == "ett."

    def test_two_real_captions_still_join_with_a_newline(self, editor):
        first, second = editor.captions[0], editor.captions[1]

        editor.merge_with_next(first)

        assert first.text == "ett.\ntva."

    def test_merging_into_an_empty_caption_previous_takes_the_other_text(self, editor):
        first, second = editor.captions[0], editor.captions[1]
        first.text = ""

        editor.merge_with_previous(second)

        assert first.text == "tva."

    def test_merging_into_an_empty_caption_next_takes_the_other_text(self, editor):
        first, second = editor.captions[0], editor.captions[1]
        first.text = ""

        editor.merge_with_next(first)

        assert first.text == "tva."


class TestDeleteCaption:
    """
    Deleting a caption removes its own DOM node -- refresh() takes care of
    that -- but a caret that was inside it does not survive the removal:
    the browser collapses the now-invalid selection to the start of the
    contenteditable instead of anywhere near where it just was, which reads
    as the cursor jumping to the top of the page. Refocusing a neighbour
    afterward, the same as add_after already does for the caption it
    starts, is what keeps the caret somewhere sensible.
    """

    def focused(self, view) -> list:
        calls = []

        class FakeBody:
            def focus_block(self, block_id, offset=0):
                calls.append((block_id, offset))

            def set_blocks(self, blocks):
                pass

            def set_speakers(self, *args, **kwargs):
                pass

        view.body = FakeBody()
        return calls

    def test_it_removes_the_caption(self, view, editor):
        target = editor.captions[1]

        view.delete({"id": target.index})

        assert target not in editor.captions

    def test_it_focuses_the_caption_that_took_its_place(self, view, editor):
        calls = self.focused(view)
        target = editor.captions[1]

        view.delete({"id": target.index})

        assert calls == [(editor.captions[1].index, 0)]

    def test_deleting_the_last_caption_focuses_the_new_last_one(self, view, editor):
        calls = self.focused(view)
        target = editor.captions[-1]

        view.delete({"id": target.index})

        assert calls == [(editor.captions[-1].index, 0)]

    def test_an_unknown_block_is_harmless(self, view, editor):
        calls = self.focused(view)
        before = list(editor.captions)

        view.delete({"id": 9999})

        assert editor.captions == before
        assert calls == []


class TestEditorContract:
    """
    The transcription editor drives the SRTEditor rather than duplicating it,
    so it depends on a set of methods there. Nothing else checks that they
    exist: a missing one only shows up as an AttributeError when a user clicks
    the thing that needs it. This caught seek_video going missing in a revert.
    """

    def required(self):
        import re
        from pathlib import Path

        source = Path("utils/transcript_editor.py").read_text()

        return sorted(set(re.findall(r"self\.editor\.(\w+)", source)))

    def test_every_member_it_uses_exists(self, editor):
        missing = [
            name
            for name in self.required()
            if not hasattr(editor, name)
        ]

        assert missing == [], f"SRTEditor is missing {missing}"

    def test_it_uses_more_than_nothing(self):
        """
        Guards the guard: a regex that stopped matching would pass silently.
        """

        assert len(self.required()) > 8

    def test_seeking_reaches_the_player(self, view, editor):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        editor.set_video_player(Player())

        view.seek({"id": editor.captions[1].index})

        assert sought == [pytest.approx(1.0)]

    def test_seeking_without_a_player_is_harmless(self, view, editor):
        view.seek({"id": editor.captions[0].index})

    def test_seeking_an_unknown_block_is_harmless(self, view, editor):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        editor.set_video_player(Player())

        view.seek({"id": 9999})

        assert sought == []


async def _async_result(value):
    return value


class FakeBody:
    def __init__(self):
        self.active = []

    def set_active(self, block_id):
        self.active.append(block_id)


class FakeOverlay:
    """
    Stands in for the overlay container. draw_overlay clears it and adds one
    label per line of the caption, so what this captures is the lines
    themselves rather than one blob of text.
    """

    def __init__(self):
        self.lines = []
        self.visible = None

    def clear(self):
        self.lines = []

    def set_visibility(self, visible):
        self.visible = visible

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text(self):
        return "\n".join(self.lines) if self.lines else None


class TestFollowVideoOverlay:
    """
    follow_video draws the caption playing right now over the video, the
    same way a real subtitle track would -- independent of whether the
    editor's own active-block highlight (autoscroll) is also following it,
    since a reader with that switch off still wants to see what plays.
    """

    @pytest.fixture
    def overlay(self, view, monkeypatch):
        """
        An overlay container wired to the view, with ui.label redirected into
        it -- draw_overlay builds real labels, which need a page context this
        test has no use for.
        """

        container = FakeOverlay()

        class Line:
            def __init__(self, text):
                container.lines.append(text)

            def classes(self, *a, **k):
                return self

        monkeypatch.setattr("utils.transcript_editor.ui.label", Line)
        view.set_overlay(container)

        return container

    def at(self, monkeypatch, seconds):
        monkeypatch.setattr(
            "utils.transcript_editor.ui.run_javascript",
            lambda *a, **k: _async_result(seconds),
        )

    def run(self, view):
        import asyncio

        asyncio.run(view.follow_video())

    def test_the_caption_playing_now_is_drawn(
        self, view, editor, overlay, monkeypatch
    ):
        self.at(monkeypatch, 1.5)
        view.body = FakeBody()

        self.run(view)

        assert overlay.text == "tva."
        assert overlay.visible is True

    def test_each_line_of_the_caption_gets_its_own_element(
        self, view, editor, overlay, monkeypatch
    ):
        """
        A caption's own line breaks are part of it, so the overlay shows the
        same lines the editor does rather than one run-together line -- split
        here rather than left to CSS white-space.
        """

        editor.captions[1].text = "first line\nsecond line"
        self.at(monkeypatch, 1.5)
        view.body = FakeBody()

        self.run(view)

        assert overlay.lines == ["first line", "second line"]

    def test_a_blank_line_still_takes_up_a_line(
        self, view, editor, overlay, monkeypatch
    ):
        """
        Dropped instead, the lines below it move up and stop matching the
        editor's own.
        """

        editor.captions[1].text = "top\n\nbottom"
        self.at(monkeypatch, 1.5)
        view.body = FakeBody()

        self.run(view)

        assert len(overlay.lines) == 3

    def test_hidden_between_captions(self, view, editor, overlay, monkeypatch):
        """
        No caption covers this moment -- a gap, or past the last one -- so
        there is nothing for a real subtitle track to show either.
        """

        self.at(monkeypatch, 100.0)
        view.body = FakeBody()

        self.run(view)

        assert overlay.visible is False

    def test_the_overlay_does_not_need_autoscroll_on(
        self, view, editor, overlay, monkeypatch
    ):
        editor.autoscroll = False
        self.at(monkeypatch, 1.5)
        view.body = FakeBody()

        self.run(view)

        assert overlay.text == "tva."
        assert view.body.active == []

    def test_the_active_block_still_follows_when_autoscroll_is_on(
        self, view, editor, overlay, monkeypatch
    ):
        editor.autoscroll = True
        self.at(monkeypatch, 1.5)
        view.body = FakeBody()

        self.run(view)

        assert view.body.active == [editor.captions[1].index]

    def test_no_overlay_container_is_harmless(self, view, editor, monkeypatch):
        self.at(monkeypatch, 1.5)
        view.body = FakeBody()

        self.run(view)

    def test_the_switch_turns_it_off(self, view, editor, overlay, monkeypatch):
        """
        Off hides whatever is showing at once rather than at the next
        timeupdate -- the video is very often paused while this is toggled.
        """

        self.at(monkeypatch, 1.5)
        view.body = FakeBody()
        self.run(view)
        assert overlay.visible is True

        view.set_overlay_enabled(False)

        assert overlay.visible is False
        assert overlay.lines == []

    def test_the_switch_turns_it_back_on_while_paused(
        self, view, editor, overlay, monkeypatch
    ):
        """
        Nothing redraws it but this -- a paused video sends no timeupdate --
        so the caption it was last on has to be remembered.
        """

        self.at(monkeypatch, 1.5)
        view.body = FakeBody()
        self.run(view)
        view.set_overlay_enabled(False)

        view.set_overlay_enabled(True)

        assert overlay.visible is True
        assert overlay.text == "tva."

    def test_editing_the_caption_being_shown_moves_the_overlay(
        self, view, editor, overlay, monkeypatch
    ):
        """
        The reader is very often paused while editing, and timeupdate -- the
        only other thing that redraws the overlay -- does not fire then, so
        the overlay would otherwise keep showing the text as it was before
        the edit.
        """

        self.at(monkeypatch, 1.5)
        view.body = FakeBody()
        self.run(view)
        assert overlay.text == "tva."

        editor.captions[1].text = "edited text"
        view.changed()

        assert overlay.text == "edited text"

    def test_editing_a_different_caption_leaves_it_alone(
        self, view, editor, overlay, monkeypatch
    ):
        self.at(monkeypatch, 1.5)
        view.body = FakeBody()
        self.run(view)

        editor.captions[3].text = "somewhere else"
        view.changed()

        assert overlay.text == "tva."

    def test_a_structural_change_redraws_it_too(
        self, view, editor, overlay, monkeypatch
    ):
        """
        refresh() covers what changed() does not -- a split, merge, delete,
        retime or undo can change which caption covers the moment being
        played, not just what that caption says.
        """

        self.at(monkeypatch, 1.5)
        view.body = FakeBody()
        self.run(view)

        # The caption covering 1.5s is deleted, so its neighbour's window is
        # what now covers that moment.
        editor.captions[1].start_time = editor.seconds_to_timestamp(0.0)
        editor.captions[1].text = "grew backwards"
        del editor.captions[0]
        view.body.set_blocks = lambda *a, **k: None
        view.body.set_speakers = lambda *a, **k: None
        view.refresh()

        assert overlay.text == "grew backwards"

    def test_nothing_redraws_before_the_video_has_reported_a_time(
        self, view, editor, overlay
    ):
        """
        refresh_overlay has no time to work a caption out from until the
        first timeupdate, and must not guess at one.
        """

        editor.captions[1].text = "edited before playing"
        view.changed()

        assert overlay.visible is None

    def test_it_is_not_redrawn_while_the_caption_has_not_changed(
        self, view, editor, overlay, monkeypatch
    ):
        """
        timeupdate fires several times a second and mostly lands on the same
        caption; rebuilding the DOM each time would be pure churn.
        """

        self.at(monkeypatch, 1.5)
        view.body = FakeBody()
        self.run(view)

        overlay.visible = None
        self.run(view)

        assert overlay.visible is None


class TestSpeakerListSurvivesUndo:
    """
    Renaming or assigning a speaker changes two things -- the captions, and
    the editor's own speaker list -- and undo has to take both back. It once
    took only the captions, which left a block naming a speaker the list no
    longer held: the menu highlighted nothing as current, the old name could
    not be renamed back (prompt_rename refuses a name not in the list), and
    the new one lingered as unused forever.
    """

    @pytest.fixture
    def editor(self, monkeypatch):
        """
        A real undo stack, unlike the shared fixture -- that one stubs
        save_state_for_undo out, so nothing would ever be recorded to undo.
        Only the parts that reach the browser are stubbed here.
        """

        editor = SRTEditor("job-uuid", "txt", "file.txt")

        for name in ("refresh_display", "update_words_per_minute",
                     "mark_as_changed", "update_beforeunload_state",
                     "update_flagged_count"):
            setattr(editor, name, lambda *a, **k: None)

        editor.data_format = "txt"
        editor.captions = [
            SRTCaption(
                i + 1,
                editor.seconds_to_timestamp(s["start"]),
                editor.seconds_to_timestamp(s["end"]),
                s["text"],
                speaker=s["speaker"],
            )
            for i, s in enumerate(SEGMENTS)
        ]
        editor.speakers = {s["speaker"] for s in SEGMENTS}

        return editor

    @pytest.fixture
    def view(self, editor, monkeypatch):
        monkeypatch.setattr(
            "utils.transcript_editor.ui.notify", lambda *a, **k: None
        )
        view = TranscriptEditor(editor)
        view.refresh = lambda *a, **k: None
        view.changed = lambda *a, **k: None

        return view

    def test_renaming_and_undoing_leaves_the_two_agreeing(self, view, editor):
        view.rename_speaker("Speaker 1", "Alice")
        editor.undo()

        assert editor.speakers == {"Speaker 1", "Speaker 2", "Speaker 3"}
        assert {caption.speaker for caption in editor.captions} <= editor.speakers

    def test_redo_puts_the_rename_back_on_both(self, view, editor):
        view.rename_speaker("Speaker 1", "Alice")
        editor.undo()
        editor.redo()

        assert "Alice" in editor.speakers
        assert "Speaker 1" not in editor.speakers
        assert editor.captions[0].speaker == "Alice"

    def test_assigning_a_new_speaker_and_undoing_drops_it(self, view, editor):
        """
        Left behind it shows up as an unused speaker nobody ever added.
        """

        view.assign_speaker({"id": editor.captions[0].index, "speaker": "Bob"})
        editor.undo()

        assert "Bob" not in editor.speakers

    def test_adding_a_speaker_is_its_own_undo_step(self, view, editor):
        """
        The list rides the undo snapshot, so without a history entry of its
        own this change is not undoable *and* the next unrelated undo takes
        it back silently.
        """

        editor.update_caption_text(editor.captions[0], "changed text")
        view.add_speaker("Brand New")

        editor.undo()

        assert "Brand New" not in editor.speakers
        assert editor.captions[0].text == "changed text"

    def test_dropping_an_unused_speaker_is_its_own_undo_step(self, view, editor):
        editor.speakers.add("Unused One")
        editor.update_caption_text(editor.captions[0], "changed text")
        view.remove_speaker("Unused One")

        editor.undo()

        assert "Unused One" in editor.speakers
        assert editor.captions[0].text == "changed text"

    def test_redo_puts_an_added_speaker_back(self, view, editor):
        view.add_speaker("Brand New")
        editor.undo()
        editor.redo()

        assert "Brand New" in editor.speakers

    def test_a_state_saved_without_speakers_leaves_the_list_alone(
        self, view, editor
    ):
        """
        restore_speakers takes None as "this state has nothing to say about
        the speakers" rather than as an empty list to apply.
        """

        before = set(editor.speakers)
        editor.undo_redo_manager.save_state(editor.captions)
        editor.captions[0].text = "changed"
        editor.undo()

        assert editor.speakers == before


class TestRemoveSpeaker:
    """
    A speaker can only leave the list once nothing is attributed to it.
    Removing one that is still in use would leave those blocks pointing at a
    name the transcription no longer knows.
    """

    def test_unused_speaker_is_removed(self, view, editor):
        editor.speakers.add("Unused")

        assert view.remove_speaker("Unused") is True
        assert "Unused" not in editor.speakers

    def test_speaker_in_use_is_refused(self, view, editor):
        assert view.remove_speaker("Speaker 1") is False
        assert "Speaker 1" in editor.speakers

    def test_speaker_used_by_one_block_is_refused(self, view, editor):
        """
        The last block of a speaker still counts as in use.
        """

        assert view.speaker_in_use("Speaker 3") is True
        assert view.remove_speaker("Speaker 3") is False

    def test_unknown_name_is_refused(self, view, editor):
        assert view.remove_speaker("Nobody") is False

    @pytest.mark.parametrize("name", ["", "   ", None])
    def test_blank_name_is_refused(self, view, name):
        assert view.remove_speaker(name) is False

    def test_name_is_trimmed_before_matching(self, view, editor):
        editor.speakers.add("Unused")

        assert view.remove_speaker("  Unused  ") is True

    def test_removal_marks_the_transcription_changed(self, view, editor):
        """
        The number of speakers is part of what gets saved, so this is not a
        display-only change.
        """

        marked = []
        editor.mark_as_changed = lambda: marked.append(True)
        editor.speakers.add("Unused")

        view.remove_speaker("Unused")

        assert marked == [True]

    def test_refused_removal_marks_nothing(self, view, editor):
        marked = []
        editor.mark_as_changed = lambda: marked.append(True)

        view.remove_speaker("Speaker 1")

        assert marked == []

    def test_a_speaker_freed_by_renaming_can_then_be_removed(self, view, editor):
        """
        The realistic route: two labels are the same person, so one is renamed
        onto the other and the empty label is tidied away.
        """

        view.assign_speaker({"id": 4, "speaker": "Speaker 1"})

        assert view.speaker_in_use("Speaker 3") is False
        assert view.remove_speaker("Speaker 3") is True

    def test_speaker_in_use_is_exact(self, view, editor):
        assert view.speaker_in_use("Speaker") is False
        assert view.speaker_in_use("speaker 1") is False


class TestSeekToCaret:
    """
    Clicking in the text moves the recording to the word the caret landed on,
    so pressing play carries on from there rather than from the top of the
    block.
    """

    @pytest.fixture
    def timed(self, editor):
        editor.captions = [
            SRTCaption(1, "00:00:10,000", "00:00:20,000", "Vi har demokratin idag")
        ]
        editor.load_words({"version": 1, "words": [
            {"t": "Vi", "s": 10.0, "e": 10.4},
            {"t": "har", "s": 10.5, "e": 10.9},
            {"t": "demokratin", "s": 11.0, "e": 12.2},
            {"t": "idag", "s": 12.5, "e": 13.0},
        ]})

        return editor

    def test_caret_maps_to_the_word_it_is_in(self, view, timed):
        caption = timed.captions[0]

        assert view.time_at_offset(caption, 0) == pytest.approx(10.0)
        assert view.time_at_offset(caption, 4) == pytest.approx(10.5)
        assert view.time_at_offset(caption, 10) == pytest.approx(11.0)
        assert view.time_at_offset(caption, 20) == pytest.approx(12.5)

    def test_right_edge_of_a_word_plays_that_word(self, view, timed):
        """
        Clicking a word's right hand side puts the caret at its end. That has
        to play that word, not the next one.
        """

        assert view.time_at_offset(timed.captions[0], 2) == pytest.approx(10.0)
        assert view.time_at_offset(timed.captions[0], 6) == pytest.approx(10.5)

    def test_caret_in_the_space_plays_the_following_word(self, view, timed):
        assert view.time_at_offset(timed.captions[0], 3) == pytest.approx(10.5)

    def test_past_the_end_plays_the_last_word(self, view, timed):
        caption = timed.captions[0]

        assert view.time_at_offset(caption, len(caption.text)) == pytest.approx(12.5)
        assert view.time_at_offset(caption, 9999) == pytest.approx(12.5)

    @pytest.mark.parametrize("offset", [None, "nonsense", -5])
    def test_an_unusable_offset_falls_back_to_the_block(self, view, timed, offset):
        assert view.time_at_offset(timed.captions[0], offset) == pytest.approx(10.0)

    def test_without_word_data_it_falls_back_to_the_block(self, view, timed):
        timed.load_words(None)

        assert view.time_at_offset(timed.captions[0], 10) == pytest.approx(10.0)

    def test_an_edited_word_has_no_time_to_move_to(self, view, timed):
        """
        Nothing in the recording corresponds to a word the reader wrote, so
        there is no honest place to move to.
        """

        caption = timed.captions[0]
        caption.text = "Vi har DEMOKRATI idag"

        # Caret inside the edited word.
        assert view.time_at_offset(caption, 10) is None

    def test_the_words_around_an_edit_still_have_their_own(self, view, timed):
        caption = timed.captions[0]
        caption.text = "Vi har DEMOKRATI idag"

        assert view.time_at_offset(caption, 0) == pytest.approx(10.0)
        assert view.time_at_offset(caption, 4) == pytest.approx(10.5)
        assert view.time_at_offset(caption, 20) == pytest.approx(12.5)

    def test_the_editor_follows_a_seek_it_asked_for_itself(self, view, timed):
        """
        Setting currentTime to the value the player already holds moves
        nothing and so fires no timeupdate, and the first caption of a
        recording usually starts at 0 -- exactly where a freshly opened
        player sits. Waiting to be told where the recording is left that one
        caption drawing no overlay and lighting no block, while every other
        caption worked.
        """

        timed.captions[0].start_time = "00:00:00,000"
        timed.load_words({"version": 1, "words": [
            {"t": "Vi", "s": 0.0, "e": 0.4},
        ]})
        timed.captions[0].text = "Vi"

        view.seek({"id": 1, "offset": 0})

        assert view.overlay_seconds == pytest.approx(0.0)
        assert view.overlay_text == "Vi"

    def test_a_caption_whose_every_word_is_untimed_falls_back_to_its_start(
        self, view, timed
    ):
        """
        A caption dragged out on the timeline over speech that had none: it
        covers the words under it, but its text was typed by hand and so
        aligns with none of them -- every entry comes back None. Its own
        start is the answer, exactly as for a job with no word data.

        Without this, clicking such a caption in the text moved the
        recording nowhere at all, so the subtitle overlay went on showing
        whatever the player was still parked in -- or nothing, when that was
        a stretch no caption covers.
        """

        made = SRTCaption(2, "00:00:10,500", "00:00:12,000", "Ny text")
        timed.captions.append(made)

        assert view.time_at_offset(made, 0) == pytest.approx(10.5)
        assert view.time_at_offset(made, 5) == pytest.approx(10.5)

    def test_a_caption_over_no_words_at_all_does_too(self, view, timed):
        """
        The other way there: dragged out of a silent stretch, so there are
        no words under it to align against in the first place.
        """

        made = SRTCaption(2, "00:00:30,000", "00:00:32,000", "Ny text")
        timed.captions.append(made)

        assert view.time_at_offset(made, 0) == pytest.approx(30.0)

    def test_an_empty_caption_does_too(self, view, timed):
        made = SRTCaption(2, "00:00:30,000", "00:00:32,000", "")
        timed.captions.append(made)

        assert view.time_at_offset(made, 0) == pytest.approx(30.0)

    def test_a_word_with_no_time_still_takes_you_to_the_caption(
        self, view, timed
    ):
        """
        Coming from somewhere else, a click on a caption is asking for that
        caption: there is no position within it to refine, and refusing to
        move meant the click was silently ignored -- no seek, no overlay, no
        active block, which reads as the editor having missed it entirely.
        """

        caption = timed.captions[0]
        caption.text = "Vi har DEMOKRATI idag"

        sought = []
        timed.seek_video = lambda seconds: sought.append(seconds)

        # The recording is elsewhere -- a caption just made further along.
        view.overlay_seconds = 30.0

        view.seek({"id": 1, "offset": 10})

        assert sought == [pytest.approx(10.0)], "the caption's own start"

    def test_but_not_while_the_recording_is_inside_that_caption(
        self, view, timed
    ):
        """
        The case the rule was written for: a reader listening to a caption
        clicks a word in it that they changed. Jumping back to the caption's
        first word is worse than staying put.
        """

        caption = timed.captions[0]
        caption.text = "Vi har DEMOKRATI idag"

        sought = []
        timed.seek_video = lambda seconds: sought.append(seconds)

        view.overlay_seconds = 11.5

        view.seek({"id": 1, "offset": 10})

        assert sought == []

    def test_clicking_an_edited_word_leaves_the_recording_alone(self, view, timed):
        """
        Reported from a screenshot: clicking a word carrying "You changed this
        word" moved the recording to the word before it, and the word-follower
        then lit that word up as though it were the one clicked.
        """

        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())
        timed.captions[0].text = "Vi har DEMOKRATI idag"

        view.seek({"id": 1, "offset": 10})

        assert sought == []

    def test_clicking_an_untouched_word_still_seeks(self, view, timed):
        """
        Guards the guard above: the seek must not have stopped working.
        """

        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())
        timed.captions[0].text = "Vi har DEMOKRATI idag"

        view.seek({"id": 1, "offset": 4})

        assert sought == [pytest.approx(10.5)]

    def test_empty_block_falls_back_to_the_block(self, view, timed):
        caption = timed.captions[0]
        caption.text = ""

        assert view.time_at_offset(caption, 0) == pytest.approx(10.0)

    def test_click_seeks_the_player(self, view, timed):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())

        view.seek({"id": 1, "offset": 10})

        assert sought == [pytest.approx(11.0)]

    def test_click_without_an_offset_seeks_the_block_start(self, view, timed):
        sought = []

        class Player:
            def seek(self, seconds):
                sought.append(seconds)

        timed.set_video_player(Player())

        view.seek({"id": 1})

        assert sought == [pytest.approx(10.0)]


class TestSpeakerMenuIcons:
    """
    The rename control in the speaker menu.
    """

    def template(self) -> str:
        from pathlib import Path

        source = Path("utils/transcript_editor.js").read_text()
        start = source.index("template: `")

        return source[start:source.index("`,", start)]

    def rename_icon(self) -> str:
        template = self.template()
        start = template.index("renamespeaker")
        # Back up to the element the handler is on.
        opening = template.rindex("<q-icon", 0, start)

        return template[opening:template.index("</q-icon>", start) + len("</q-icon>")]

    def test_rename_uses_the_person_edit_icon(self):
        assert 'name="sym_o_person_edit"' in self.rename_icon()

    def test_it_asks_for_it_from_the_symbols_set(self):
        """
        person_edit only exists in Material Symbols, not in Material Icons.
        Without Quasar's sym_o_ prefix the name is not an icon at all and the
        ligature text renders in its place. Both fonts ship with NiceGUI.
        """

        icon = self.rename_icon()

        assert "person_edit" in icon
        assert "sym_o_person_edit" in icon, "needs the Material Symbols prefix"

    def test_it_says_what_it_does(self):
        assert "<q-tooltip>Rename speaker</q-tooltip>" in self.rename_icon()

    def test_the_tooltip_is_anchored_to_the_icon(self):
        """
        Inside the element, so Quasar anchors it there rather than to the row.
        """

        icon = self.rename_icon()

        assert icon.endswith("<q-tooltip>Rename speaker</q-tooltip></q-icon>")

    def test_it_still_only_renames(self):
        """
        The row underneath assigns the speaker, so the icon has to keep
        swallowing the click.
        """

        icon = self.rename_icon()

        assert "@click.stop=" in icon
        assert "renamespeaker" in icon


class TestTheShortcutsDialog:
    """
    The dialog is worded for whichever format is open. A reader editing
    subtitles works on captions and a reader editing a transcription on
    paragraphs; a list that says "block" says it to neither of them. Its
    contents come from keyboard_shortcut_groups(), separate from the dialog
    that draws them so the wording can be read without a UI.
    """

    def editor(self, data_format: str) -> SRTEditor:
        """
        As the page builds it: constructed and asked straight away, with
        nothing parsed yet. The toolbar is built before any content is
        fetched, so the dialog has to know the format from the editor's own
        construction -- data_format read None here for the whole session
        once, and every list came out worded for a transcription.
        """

        return SRTEditor("job-uuid", data_format, f"file.{data_format}")

    def actions(self, data_format: str) -> dict:
        groups = self.editor(data_format).keyboard_shortcut_groups()

        return {
            action: keys for _, rows in groups for action, keys in rows
        }

    def test_the_format_is_known_before_anything_is_parsed(self):
        assert SRTEditor("job-uuid", "srt", "file.srt").data_format == "srt"
        assert SRTEditor("job-uuid", "txt", "file.txt").data_format == "txt"

    def test_it_names_the_format_in_its_own_title(self):
        assert self.editor("srt").keyboard_shortcuts_title() == (
            "Subtitle keyboard shortcuts"
        )
        assert self.editor("txt").keyboard_shortcuts_title() == (
            "Transcription keyboard shortcuts"
        )

    def test_the_editing_rows_are_worded_for_what_is_open(self):
        captions = self.actions("srt")
        paragraphs = self.actions("txt")

        assert captions["Split caption at cursor"] == "Enter"
        assert captions["Merge with next"] == "Ctrl + M"
        assert captions["Delete caption"] == "Ctrl + D"

        assert paragraphs["Split paragraph at cursor"] == "Enter"
        assert paragraphs["Merge with next"] == "Ctrl + M"
        assert paragraphs["Delete paragraph"] == "Ctrl + D"

    def test_neither_list_uses_the_other_ones_noun(self):
        assert not any("paragraph" in action for action in self.actions("srt"))
        assert not any("caption" in action for action in self.actions("txt"))

    def test_the_transcription_list_is_exactly_these_and_nothing_else(self):
        """
        A transcription's own list is a closed set: the keys it has, in
        order, with nothing extra. The Backspace/Delete joins are not on it
        -- they are what those keys do in any text, not a shortcut worth
        naming -- and the caption row's own icons do not exist here at all.
        """

        groups = self.editor("txt").keyboard_shortcut_groups()

        assert groups == [
            (
                "Editing",
                [
                    ("Split paragraph at cursor", "Enter"),
                    ("New line", "Shift + Enter"),
                    ("Move first word to previous paragraph", "Ctrl/⌘ + ↑"),
                    ("Move last word to next paragraph", "Ctrl/⌘ + ↓"),
                    ("Merge with next", "Ctrl + M"),
                    ("Delete paragraph", "Ctrl + D"),
                ],
            ),
            (
                "File operations",
                [
                    ("Save file", "Ctrl/⌘ + S"),
                    ("Export file", "Ctrl/⌘ + E"),
                    ("Find", "Ctrl/⌘ + F"),
                ],
            ),
            (
                "History",
                [
                    ("Undo", "Ctrl/⌘ + Z"),
                    ("Redo", "Ctrl + Y / ⌘ + Shift + Z"),
                ],
            ),
            (
                "Transport",
                [
                    ("Play/Pause", "Ctrl + Space"),
                ],
            ),
        ]

    def test_the_subtitle_list_is_exactly_these_and_nothing_else(self):
        """
        A closed set, the same as the transcription's own. Add-after and
        validate are the two rows a transcription does not get: one is the
        keyboard's half of a caption row it has no equivalent of, and the
        other checks guidelines only subtitles are held to. The
        Backspace/Delete joins and the caption row's mouse icons still do
        what they do, but neither is named here.
        """

        groups = self.editor("srt").keyboard_shortcut_groups()

        assert groups == [
            (
                "Editing",
                [
                    ("Split caption at cursor", "Enter"),
                    ("New line", "Shift + Enter"),
                    ("Move first word to previous caption", "Ctrl/⌘ + ↑"),
                    ("Move last word to next caption", "Ctrl/⌘ + ↓"),
                    ("Merge with next", "Ctrl + M"),
                    ("Add caption after", "Ctrl/⌘ + Shift + Enter"),
                    ("Delete caption", "Ctrl + D"),
                ],
            ),
            (
                "File operations",
                [
                    ("Save file", "Ctrl/⌘ + S"),
                    ("Export file", "Ctrl/⌘ + E"),
                    ("Find", "Ctrl/⌘ + F"),
                    ("Validate captions", "Ctrl + Shift + V"),
                ],
            ),
            (
                "History",
                [
                    ("Undo", "Ctrl/⌘ + Z"),
                    ("Redo", "Ctrl + Y / ⌘ + Shift + Z"),
                ],
            ),
            (
                "Transport",
                [
                    ("Play/Pause", "Ctrl + Space"),
                ],
            ),
        ]

    def test_add_after_and_validate_are_subtitles_only(self):
        """
        Add-after is the keyboard's half of a caption row a transcription
        does not have, and validate checks guidelines only subtitles are
        held to.
        """

        captions = self.actions("srt")
        paragraphs = self.actions("txt")

        assert captions["Add caption after"] == "Ctrl/⌘ + Shift + Enter"
        assert captions["Validate captions"] == "Ctrl + Shift + V"

        assert not any("Add " in action for action in paragraphs)
        assert not any("Validate" in action for action in paragraphs)

    def test_the_keys_that_both_formats_share_agree(self):
        captions = self.actions("srt")
        paragraphs = self.actions("txt")

        for action in ("Undo", "Redo", "Play/Pause"):
            assert captions[action] == paragraphs[action]


class TestRetimingReorders:
    """
    A caption's number is its position in the list, and the list is the
    order it was parsed in. Dragging one on the strip -- or typing a time
    into it -- can move it past a neighbour, and nothing put the list back
    in the order it plays in: the text editor went on showing the caption
    where it used to be, under a number matching neither the timing beside
    it nor the bracket on the strip.
    """

    def starts(self, editor) -> list:
        return [caption.get_start_seconds() for caption in editor.captions]

    def numbers(self, editor) -> list:
        return [caption.index for caption in editor.captions]

    def test_dragging_a_caption_back_moves_it_up_the_list(self, view, editor):
        third = editor.captions[2]

        view.retime_span({"id": third.index, "start": 0.5, "end": 0.9})

        assert editor.captions[1] is third
        assert self.starts(editor) == sorted(self.starts(editor))

    def test_the_numbers_follow_the_order(self, view, editor):
        view.retime_span({"id": editor.captions[2].index, "start": 0.5, "end": 0.9})

        assert self.numbers(editor) == [1, 2, 3, 4]

    def test_a_typed_time_reorders_the_same_way(self, view, editor):
        first = editor.captions[0]

        # The end first: a start typed past the end it still has would be
        # refused for ending before it starts.
        view.retime({"id": first.index, "edge": "end", "value": "00:01:00.000"})
        view.retime({"id": first.index, "edge": "start", "value": "00:00:59.000"})

        assert editor.captions[-1] is first
        assert self.numbers(editor) == [1, 2, 3, 4]

    def test_a_refused_retime_leaves_the_order_alone(self, view, editor):
        before = list(editor.captions)

        view.retime_span({"id": editor.captions[1].index, "start": 5.0, "end": 1.0})

        assert editor.captions == before

    def test_captions_starting_together_keep_their_order(self, editor):
        editor.captions[1].start_time = editor.captions[0].start_time
        first, second = editor.captions[0], editor.captions[1]

        editor.sort_captions()

        assert editor.captions[0] is first
        assert editor.captions[1] is second

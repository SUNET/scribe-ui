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
The switch that hides the reader's highlights.

Hiding draws nothing and reads out nothing, but keeps every highlight in the
data. What cannot be seen is never taken away: the highlight command turns the
display back on instead, and says so.
"""

import pathlib

import pytest

from test_highlights import FakeBody, make_editor

from utils.srt import HIGHLIGHTS_SHOW_KEY
from utils.transcript_editor import TranscriptEditor


@pytest.fixture
def editor(monkeypatch):
    notices = []
    monkeypatch.setattr(
        "utils.srt.ui.notify",
        lambda message, **kwargs: notices.append((message, kwargs)),
    )
    built = make_editor()
    built.notices = notices
    built.refreshes = 0

    def refresh(*args, **kwargs):
        built.refreshes += 1

    built.refresh_display = refresh

    return built


def hidden(editor):
    editor.set_show_highlights(False)
    editor.refreshes = 0
    editor.snapshots = 0
    editor.changed = 0
    editor.notices.clear()

    return editor


class TestThePreference:
    def test_they_are_shown_unless_the_reader_has_said_otherwise(self, editor):
        assert editor.show_highlights is True

        editor.restore_review_state(False, "low")

        assert editor.show_highlights is True

    def test_a_stored_choice_is_applied_before_the_first_render(self, editor):
        editor.restore_review_state(False, "low", False, True, True, False)

        assert editor.show_highlights is False

        editor.restore_review_state(False, "low", False, True, True, True)

        assert editor.show_highlights is True

    def test_it_is_stored_under_its_own_key(self):
        assert HIGHLIGHTS_SHOW_KEY == "srt_show_highlights"

    def test_switching_redraws(self, editor):
        editor.set_show_highlights(False)

        assert editor.show_highlights is False
        assert editor.refreshes == 1


class TestDrawing:
    def test_hidden_highlights_are_not_runs(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        hidden(editor)

        runs = editor.review_runs(first)

        assert not any(run.get("hl") for run in runs)
        assert runs == [{"t": "ett två tre", "flag": False}]

    def test_the_space_between_hidden_words_is_not_drawn_either(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 1, 2}
        hidden(editor)

        assert not any(run.get("hl") for run in editor.review_runs(first))

    def test_they_come_back_as_they_were(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        hidden(editor)
        editor.set_show_highlights(True)

        runs = editor.review_runs(first)

        assert [run["t"] for run in runs if run.get("hl")] == ["två"]

    def test_the_data_is_untouched_while_hidden(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 2}
        hidden(editor)

        assert first.highlighted_words == {0, 2}

    def test_they_are_still_saved_while_hidden(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 2}
        hidden(editor)

        assert first.to_dict()["highlighted"] == [0, 2]

    def test_other_markings_are_not_affected(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        editor.show_my_edits = True
        hidden(editor)

        runs = editor.review_runs(first)

        assert not any(run.get("hl") for run in runs)
        # One run per word is still what the edit marking needs.
        assert [run["t"] for run in runs if run["t"].strip()] == [
            "ett",
            "två",
            "tre",
        ]

    def test_hidden_highlights_do_not_force_a_run_per_word(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        hidden(editor)

        assert len(editor.review_runs(first)) == 1


class TestTheCommandWhileTheyAreShown:
    def test_it_adds_and_removes_as_before_with_no_notice(self, editor):
        first = editor.captions[0]

        assert editor.toggle_highlight([(first, 4, 7)]) == "added"
        assert editor.toggle_highlight([(first, 4, 7)]) == "removed"

        assert editor.notices == []


class TestTheCommandWhileTheyAreHidden:
    def test_with_nothing_there_it_adds_one_and_shows_them(self, editor):
        first = editor.captions[0]
        hidden(editor)

        assert editor.toggle_highlight([(first, 4, 7)]) == "added"

        assert first.highlighted_words == {1}
        assert editor.show_highlights is True
        assert editor.changed == 1
        assert editor.snapshots == 1

    def test_over_a_hidden_highlight_it_only_shows_and_removes_nothing(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        hidden(editor)

        assert editor.toggle_highlight([(first, 4, 7)]) == "shown"

        assert first.highlighted_words == {1}
        assert editor.show_highlights is True
        # Nothing changed, so nothing to save and nothing to undo.
        assert editor.changed == 0
        assert editor.snapshots == 0

    def test_the_next_press_is_the_one_that_removes(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        hidden(editor)

        editor.toggle_highlight([(first, 4, 7)])

        assert editor.toggle_highlight([(first, 4, 7)]) == "removed"
        assert first.highlighted_words == set()

    def test_a_mixed_selection_adds_to_the_words_lacking_one_and_removes_none(
        self, editor
    ):
        first = editor.captions[0]
        first.highlighted_words = {0}
        hidden(editor)

        assert editor.toggle_highlight([(first, 0, 11)]) == "added"

        assert first.highlighted_words == {0, 1, 2}
        assert editor.show_highlights is True

    def test_across_captions_it_never_removes(self, editor):
        first, second = editor.captions
        first.highlighted_words = {1, 2}
        second.highlighted_words = {0}
        hidden(editor)

        assert editor.toggle_highlight([(first, 4, 11), (second, 0, 4)]) == "shown"

        assert first.highlighted_words == {1, 2}
        assert second.highlighted_words == {0}
        assert editor.show_highlights is True

    def test_nothing_selected_says_so_and_leaves_them_hidden(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        hidden(editor)

        assert editor.toggle_highlight([(first, 3, 4)]) == ""

        assert editor.show_highlights is False
        assert first.highlighted_words == {1}
        assert [n[0] for n in editor.notices] == [
            "Select the words to highlight first"
        ]

    def test_subtitles_still_get_none(self, editor):
        subtitles = make_editor("srt")
        subtitles.show_highlights = False
        caption = subtitles.captions[0]

        assert subtitles.toggle_highlight([(caption, 4, 7)]) == ""
        assert caption.highlighted_words == set()


class TestWhatTheReaderIsTold:
    def notice(self, editor):
        assert len(editor.notices) == 1

        return editor.notices[0]

    def test_over_a_hidden_highlight(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {1}
        hidden(editor)

        editor.toggle_highlight([(first, 4, 7)])

        assert self.notice(editor)[0] == (
            "Highlights were hidden and are shown again. "
            "Press again to remove this highlight."
        )

    def test_when_a_highlight_was_added(self, editor):
        first = editor.captions[0]
        hidden(editor)

        editor.toggle_highlight([(first, 4, 7)])

        assert self.notice(editor)[0] == (
            "Highlight added. Highlights were hidden and are shown again."
        )

    def test_when_some_words_already_had_one(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0}
        hidden(editor)

        editor.toggle_highlight([(first, 0, 11)])

        assert self.notice(editor)[0] == (
            "Highlights were hidden and are shown again, and the words "
            "without one were highlighted."
        )

    def test_it_stays_until_closed_like_the_other_notices(self, editor):
        first = editor.captions[0]
        hidden(editor)

        editor.toggle_highlight([(first, 4, 7)])

        kwargs = self.notice(editor)[1]

        assert kwargs["timeout"] is None
        assert kwargs["close_button"] == "Close"

    def test_nothing_is_said_when_they_are_shown(self, editor):
        first = editor.captions[0]

        editor.toggle_highlight([(first, 4, 7)])

        assert editor.notices == []

    def test_the_switch_is_told_so_it_follows(self, editor):
        first = editor.captions[0]
        told = []
        editor.on_highlights_shown = lambda: told.append(True)
        hidden(editor)

        editor.toggle_highlight([(first, 4, 7)])

        assert told == [True]

    def test_the_switch_is_not_told_when_the_reader_flips_it(self, editor):
        told = []
        editor.on_highlights_shown = lambda: told.append(True)

        editor.set_show_highlights(False)
        editor.set_show_highlights(True)

        assert told == []


class TestEditingWhileHidden:
    """
    Hidden is only about drawing: the marks follow the text as they always do,
    and nothing is said about it.
    """

    def test_splitting_divides_them_between_the_halves(self, editor):
        first = editor.captions[0]
        first.highlighted_words = {0, 2}
        hidden(editor)

        editor.split_caption(first, cursor_position=7)

        assert editor.captions[0].highlighted_words == {0}
        assert editor.captions[1].highlighted_words == {0}
        assert editor.notices == []
        assert editor.show_highlights is False

    def test_a_word_moved_takes_its_highlight_along(self, editor):
        first, second = editor.captions
        second.highlighted_words = {0}
        hidden(editor)

        editor.move_first_word_to_previous(second)

        assert first.highlighted_words == {3}
        assert second.highlighted_words == set()
        assert editor.notices == []

    def test_merging_joins_them(self, editor):
        first, second = editor.captions
        first.highlighted_words = {2}
        second.highlighted_words = {0}
        hidden(editor)

        editor.merge_with_next(first)

        assert editor.captions[0].highlighted_words == {2, 3}
        assert editor.show_highlights is False

    def test_a_word_typed_inside_one_joins_it(self, editor):
        carried = editor.carry_highlights("ett två tre", "ett nytt två tre", {0, 1, 2})

        assert carried == {0, 1, 2, 3}


class TestThroughTheView:
    @pytest.fixture
    def view(self, editor):
        view = TranscriptEditor(editor)
        view.body = FakeBody()
        view.refreshed = 0
        view.saved = 0
        view.refresh = lambda *a, **k: setattr(view, "refreshed", view.refreshed + 1)
        view.changed = lambda *a, **k: setattr(view, "saved", view.saved + 1)

        return view

    def test_showing_them_again_is_not_a_change_to_save(self, view, editor):
        editor.captions[0].highlighted_words = {1}
        hidden(editor)

        view.toggle_highlight({"spans": [{"id": 1, "start": 4, "end": 7}]})

        assert editor.show_highlights is True
        assert view.saved == 0
        assert view.refreshed == 1
        # The selection is put back so the next press acts on the same words.
        assert view.body.selected == [(1, 4, 1, 7)]

    def test_adding_while_hidden_is_a_change_to_save(self, view, editor):
        hidden(editor)

        view.toggle_highlight({"spans": [{"id": 1, "start": 4, "end": 7}]})

        assert editor.captions[0].highlighted_words == {1}
        assert view.saved == 1

    def test_the_view_passes_the_switch_on(self, view, editor):
        view.set_show_highlights(False)

        assert editor.show_highlights is False


class TestTheSwitch:
    def page(self):
        return pathlib.Path("pages/srt.py").read_text()

    def js(self):
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_it_sits_beside_my_edits_and_only_for_transcriptions(self):
        source = self.page()
        edits = source.index('"My edits"')
        highlights = source.index('"Highlights"')
        guard = source.rindex('if data_format != "srt":', 0, highlights)

        assert edits < guard < highlights

    def test_it_is_a_saved_preference_like_the_others(self):
        source = self.page()

        assert "app.storage.user[HIGHLIGHTS_SHOW_KEY] = value" in source
        assert "app.storage.user.get(HIGHLIGHTS_SHOW_KEY, True)" in source

    def test_it_listens_for_the_keyboard_too(self):
        assert '"update:model-value", save_show_highlights' in self.page()

    def test_the_command_can_move_the_switch(self):
        source = self.page()

        assert "editor.on_highlights_shown = highlights_shown" in source
        assert "highlights_switch.value = True" in source

    def test_the_page_does_not_redraw_twice_when_the_command_moved_it(self):
        assert "if value != editor.show_highlights:" in self.page()

    def test_the_component_needs_no_flag_of_its_own(self):
        # The server leaves hidden highlights out of the runs, so nothing is
        # drawn and nothing is a role=mark; with none drawn the script has no
        # neighbour to copy when a word is typed.
        assert "showHighlights" not in self.js()

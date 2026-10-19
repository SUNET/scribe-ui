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
The switch that hides the reader's comments.

Hiding draws nothing and reads out nothing, and puts the comments card away,
but keeps every comment on its words. What cannot be seen is never changed:
the comment command turns the display back on and then does what it always
does.
"""

import pathlib

import pytest

from tests.test_comments import (  # noqa: F401  (fixtures)
    FakeBody,
    comment,
    editor,
    panel,
    shape,
    view,
)
from utils.srt import COMMENTS_SHOW_KEY


@pytest.fixture
def notices(editor, monkeypatch):
    """
    Every notice with its options, whoever raises it.
    """

    seen = []
    monkeypatch.setattr(
        "utils.comments_panel.ui.notify",
        lambda message, **kwargs: seen.append((message, kwargs)),
    )
    editor.refreshes = 0

    def refresh(*args, **kwargs):
        editor.refreshes += 1

    editor.refresh_display = refresh

    return seen


def hide(view, editor):
    view.set_show_comments(False)
    editor.refreshes = 0
    editor.snapshots = 0


class TestThePreference:
    def test_they_are_shown_unless_the_reader_has_said_otherwise(self, editor):
        assert editor.show_comments is True

        editor.restore_review_state(False, "low")

        assert editor.show_comments is True

    def test_a_stored_choice_is_applied_before_the_first_render(self, editor):
        editor.restore_review_state(False, "low", comments=False)

        assert editor.show_comments is False

        editor.restore_review_state(False, "low", comments=True)

        assert editor.show_comments is True

    def test_it_is_stored_under_its_own_key(self):
        assert COMMENTS_SHOW_KEY == "srt_show_comments"

    def test_switching_redraws(self, editor, notices):
        editor.set_show_comments(False)

        assert editor.show_comments is False
        assert editor.refreshes == 1


class TestDrawing:
    def test_hidden_comments_are_not_runs(self, view, editor, notices):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "there")]
        hide(view, editor)

        runs = editor.review_runs(first)

        assert not any("cm" in run for run in runs)
        assert not any("ct" in run for run in runs)
        assert runs == [{"t": "ett två tre", "flag": False}]

    def test_the_space_inside_a_hidden_comment_is_not_drawn_either(
        self, view, editor, notices
    ):
        first = editor.captions[0]
        first.comments = [comment({0, 1, 2}, "there")]
        hide(view, editor)

        assert not any("cm" in run for run in editor.review_runs(first))

    def test_they_come_back_as_they_were(self, view, editor, notices):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "there")]
        hide(view, editor)
        view.set_show_comments(True)

        runs = editor.review_runs(first)

        assert [run["t"] for run in runs if "cm" in run and run["t"].strip()] == [
            "två",
            "tre",
        ]
        assert [run["ct"] for run in runs if run.get("cf")] == ["there"]

    def test_the_data_is_untouched_while_hidden(self, view, editor, notices):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "there")]
        hide(view, editor)

        assert shape(first) == [([1, 2], "there")]
        assert first.to_dict()["comments"]

    def test_highlights_are_not_affected(self, view, editor, notices):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "there")]
        first.highlighted_words = {0}
        hide(view, editor)

        runs = editor.review_runs(first)

        assert [run["t"] for run in runs if run.get("hl")] == ["ett"]

    def test_hidden_comments_do_not_force_a_run_per_word(
        self, view, editor, notices
    ):
        first = editor.captions[0]
        first.comments = [comment({1, 2}, "there")]
        hide(view, editor)

        assert len(editor.review_runs(first)) == 1


class TestHidingPutsTheCardAway:
    def test_an_open_card_is_shut(self, view, panel, editor, notices):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        panel.open_for(editor.captions[0], 5, 5)

        view.set_show_comments(False)

        assert panel.container.visible is False
        assert panel.current is None
        assert view.body.comment_mark == (-1, -1)

    def test_what_was_typed_is_kept_like_when_the_card_is_closed(
        self, view, panel, editor, notices
    ):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        panel.open_for(editor.captions[0], 5, 5)
        panel.text.value = "there, and more"

        view.set_show_comments(False)

        assert shape(editor.captions[0]) == [([1, 2], "there, and more")]

    def test_a_comment_being_written_is_kept_too(
        self, view, panel, editor, notices
    ):
        panel.open_for(editor.captions[0], 5, 9)
        panel.text.value = "new"

        view.set_show_comments(False)

        assert shape(editor.captions[0]) == [([1, 2], "new")]
        assert panel.pending is None

    def test_an_empty_new_comment_is_simply_dropped(
        self, view, panel, editor, notices
    ):
        panel.open_for(editor.captions[0], 5, 9)

        view.set_show_comments(False)

        assert editor.captions[0].comments == []
        assert panel.container.visible is False

    def test_showing_them_does_not_open_the_card(self, view, panel, editor, notices):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        hide(view, editor)

        view.set_show_comments(True)

        assert panel.container.visible is False

    def test_a_file_opened_with_comments_shows_no_card_while_hidden(
        self, view, panel, editor, notices
    ):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        editor.show_comments = False

        panel.open_first()

        assert panel.container.visible is False

    def test_the_caret_in_a_hidden_comment_opens_nothing(
        self, view, panel, editor, notices
    ):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        editor.show_comments = False

        view.caret_comment({"id": 1, "cm": 0, "click": True})

        assert panel.container.visible is False


class TestTheCommandWhileTheyAreShown:
    def test_it_opens_the_card_as_before_with_no_notice(
        self, view, panel, editor, notices
    ):
        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert panel.container.visible is True
        assert notices == []


class TestTheCommandWhileTheyAreHidden:
    def test_over_a_hidden_comment_it_shows_them_and_opens_that_one(
        self, view, panel, editor, notices
    ):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        hide(view, editor)

        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert editor.show_comments is True
        assert panel.current[1] is editor.captions[0].comments[0]
        assert panel.text.value == "there"
        assert panel.container.visible is True

    def test_it_changes_nothing_in_the_data(self, view, panel, editor, notices):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        hide(view, editor)

        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert shape(editor.captions[0]) == [([1, 2], "there")]
        assert editor.snapshots == 0

    def test_over_words_without_one_it_shows_them_and_opens_a_new_one(
        self, view, panel, editor, notices
    ):
        hide(view, editor)

        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert editor.show_comments is True
        assert panel.pending == (editor.captions[0], 4, 11)
        # Nothing is made until it is saved.
        assert editor.captions[0].comments == []

    def test_saving_it_then_adds_the_comment(self, view, panel, editor, notices):
        hide(view, editor)
        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})
        panel.text.value = "new"

        panel.save()

        assert shape(editor.captions[0]) == [([1, 2], "new")]

    def test_nothing_selected_says_so_and_leaves_them_hidden(
        self, view, panel, editor, notices
    ):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        hide(view, editor)

        view.open_comment({"spans": []})

        assert editor.show_comments is False
        # Only the usual warning: nothing was turned on, so nothing is said
        # about it.
        assert [n[0] for n in notices] == ["Select the words to comment on first"]

    def test_a_caret_between_words_leaves_them_hidden(
        self, view, panel, editor, notices
    ):
        editor.captions[0].text = "ett  tre"
        hide(view, editor)

        view.open_comment({"spans": [{"id": 1, "start": 4, "end": 4}]})

        assert editor.show_comments is False
        assert [n[0] for n in notices] == ["Select the words to comment on first"]

    def test_a_selection_across_paragraphs_leaves_them_hidden(
        self, view, panel, editor, notices
    ):
        hide(view, editor)

        view.open_comment(
            {
                "spans": [
                    {"id": 1, "start": 4, "end": 11},
                    {"id": 2, "start": 0, "end": 4},
                ]
            }
        )

        assert editor.show_comments is False
        assert panel.container.visible is False

    def test_a_second_press_with_them_shown_is_the_normal_command(
        self, view, panel, editor, notices
    ):
        editor.captions[0].comments = [comment({1, 2}, "there")]
        hide(view, editor)
        args = {"spans": [{"id": 1, "start": 5, "end": 9}]}

        view.open_comment(args)
        notices.clear()
        view.open_comment(args)

        assert notices == []
        assert panel.current[1] is editor.captions[0].comments[0]


class TestWhatTheReaderIsTold:
    def test_the_notice(self, view, panel, editor, notices):
        hide(view, editor)

        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert [n[0] for n in notices] == ["Comments were hidden and are shown again."]

    def test_it_stays_until_closed_like_the_other_notices(
        self, view, panel, editor, notices
    ):
        hide(view, editor)

        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert notices[0][1]["timeout"] is None
        assert notices[0][1]["close_button"] == "Close"

    def test_the_switch_is_told_so_it_follows(self, view, panel, editor, notices):
        told = []
        editor.on_comments_shown = lambda: told.append(True)
        hide(view, editor)

        view.open_comment({"spans": [{"id": 1, "start": 5, "end": 9}]})

        assert told == [True]

    def test_the_switch_is_not_told_when_the_reader_flips_it(
        self, view, panel, editor, notices
    ):
        told = []
        editor.on_comments_shown = lambda: told.append(True)

        view.set_show_comments(False)
        view.set_show_comments(True)

        assert told == []


class TestEditingWhileHidden:
    """
    Hidden is only about drawing: the comments follow the text as they always
    do, and nothing is said about it.
    """

    def test_splitting_divides_them_between_the_halves(
        self, view, editor, notices
    ):
        first = editor.captions[0]
        first.comments = [comment({0}, "one"), comment({2}, "three")]
        hide(view, editor)

        editor.split_caption(first, cursor_position=7)

        assert shape(editor.captions[0]) == [([0], "one")]
        assert shape(editor.captions[1]) == [([0], "three")]
        assert notices == []
        assert editor.show_comments is False

    def test_a_word_moved_takes_its_comment_along(self, view, editor, notices):
        first, second = editor.captions
        second.comments = [comment({0}, "moves")]
        hide(view, editor)

        editor.move_first_word_to_previous(second)

        assert shape(first) == [([3], "moves")]
        assert second.comments == []
        assert notices == []

    def test_merging_joins_them(self, view, editor, notices):
        first, second = editor.captions
        first.comments = [comment({2}, "a")]
        second.comments = [comment({0}, "b")]
        hide(view, editor)

        editor.merge_with_next(first)

        assert shape(editor.captions[0]) == [([2], "a"), ([3], "b")]
        assert editor.show_comments is False


class TestTheSwitch:
    def page(self):
        return pathlib.Path("pages/srt.py").read_text()

    def js(self):
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_it_sits_beside_my_edits_and_only_for_transcriptions(self):
        source = self.page()
        edits = source.index('"My edits"')
        comments = source.index('"Comments"')
        guard = source.rindex('if data_format != "srt":', 0, comments)

        assert edits < guard < comments

    def test_it_is_a_saved_preference_like_the_others(self):
        source = self.page()

        assert "app.storage.user[COMMENTS_SHOW_KEY] = value" in source
        assert "app.storage.user.get(COMMENTS_SHOW_KEY, True)" in source

    def test_it_listens_for_the_keyboard_too(self):
        assert '"update:model-value", save_show_comments' in self.page()

    def test_the_command_can_move_the_switch(self):
        source = self.page()

        assert "editor.on_comments_shown = comments_shown" in source
        assert "comments_switch.value = True" in source

    def test_the_page_does_not_redraw_twice_when_the_command_moved_it(self):
        assert "if value != editor.show_comments:" in self.page()

    def test_the_component_needs_no_flag_of_its_own(self):
        # The server leaves hidden comments out of the runs, so nothing is
        # drawn, nothing carries data-comment or an aria-description, and the
        # caret has no commented word to report.
        assert "showComments" not in self.js()

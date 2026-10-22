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
The editor's settings, in the menu the gear in the toolbar opens.

They used to be a row of switches under the video. They are set now and then
rather than used all the time, so like Shortcuts and Info they are an icon in
the toolbar, and the row is the menu's content, one to a row. What is pinned
down here is what could silently be undone by a later edit: where the gear
is and what it is called, that it says what it opens and whether it is open,
that every switch is in the menu (the timeline's among them) and none is left
under the video, and that each still re-focuses itself after a change (F-74).
"""

import pathlib


def page() -> str:
    return pathlib.Path("pages/srt.py").read_text()


def stylesheet() -> str:
    from utils.styles import default_styles

    return default_styles


def gear() -> str:
    source = page()
    start = source.index('with ui.button(icon="settings")')

    return source[start : source.index("settings_menu.on_value_change", start)]


class TestTheGear:
    def test_it_is_in_the_toolbar_after_information_and_before_the_rule(self):
        source = page()
        info = source.index('ui.button(icon="info")')
        settings = source.index('with ui.button(icon="settings")')
        rule = source.index('ui.separator().props("vertical")', settings)
        export = source.index('ui.button("Export"')

        assert info < settings < rule < export

    def test_it_is_called_editor_settings(self):
        text = gear()

        assert 'aria-label="Editor settings"' in text
        assert 'ui.tooltip("Editor settings")' in text

    def test_it_says_it_opens_something_and_whether_it_is_open(self):
        source = page()
        text = gear()

        assert "aria-haspopup=dialog" in text
        assert "aria-expanded=false" in text
        toggled = source[source.index("def settings_menu_toggled") :]
        toggled = toggled[: toggled.index("settings_menu.on_value_change")]

        assert '"aria-expanded=" + ("true" if event.value else "false")' in toggled
        assert "settings_menu.on_value_change(settings_menu_toggled)" in source

    def test_the_menu_is_a_dialog_with_a_name_not_a_list_of_menu_items(self):
        """
        Quasar gives a menu role="menu", which promises menu items; this holds
        switches.
        """

        text = gear()

        assert "'role=dialog aria-label=\"Editor settings\"'" in text
        assert "ui.menu()" in text

    def test_it_looks_like_the_icons_beside_it(self):
        text = gear()

        assert '.classes("editor-btn editor-icon")' in text
        assert "flat" in text


class TestWhatIsInTheMenu:
    def menu_start(self) -> int:
        return page().index("with settings_menu, ui.column().classes(")

    def test_the_settings_are_built_into_the_menu(self):
        source = page()

        assert self.menu_start() > source.index("settings_menu = ui.menu()")
        assert 'classes("editor-settings w-full")' not in source

    def test_every_switch_is_in_the_menu_and_none_is_left_under_the_video(self):
        source = page()
        start = self.menu_start()

        assert source.count("ui.switch(") >= 6
        assert source.index("ui.switch(") > start
        assert 'with ui.row().classes("items-center gap-4"):' not in source

    def test_the_timeline_is_among_them(self):
        source = page()
        start = self.menu_start()

        assert source.index('"Timeline",', start) > start
        assert "timeline_switch" in source[start:]

    def test_the_switches_are_still_all_there(self):
        source = page()[self.menu_start() :]

        for label in (
            '"Follow audio" if following_words else "Autoscroll"',
            '"Subtitle overlay"',
            '"Timeline"',
            '"My edits"',
            '"Highlights"',
            '"Comments"',
        ):
            assert label in source

    def test_one_to_a_row(self):
        source = page()
        group = source[source.index("def settings_group") :]
        group = group[: group.index("return group")]

        assert '"editor-settings-group items-start gap-1"' in group
        assert 'with ui.column().classes("items-start gap-1"):' not in source

    def test_uncertain_words_still_reads_as_one_row(self):
        """
        The label, the Off / Low / Medium / High choice and the count, as it
        did under the video.
        """

        source = page()[self.menu_start() :]
        row = source[source.index('uncertain_label = ui.label("Uncertain words:")') :]

        assert 'with ui.row().classes("items-center gap-2"):' in source
        for choice in (
            '"off": "Off"',
            '"low": "Low"',
            '"medium": "Medium"',
            '"high": "High"',
        ):
            assert choice in row
        assert "flagged = ui.label()" in row

    def test_each_switch_still_refocuses_itself_after_a_change(self):
        """
        F-74: a click can leave focus on a presentational wrapper; a Space
        that follows must not reach the browser's own handling.
        """

        source = page()[self.menu_start() :]

        assert source.count("focus_element(event.sender)") == 6

    def test_they_still_listen_for_a_keyboard_activation_too(self):
        source = page()[self.menu_start() :]

        assert source.count('"update:model-value"') >= 6


class TestTheGroups:
    """
    Two groups: how the editor follows the recording and the strip that shows
    where its speech is, with no title (it is what is left when what has a name
    of its own is taken away, and a title over a lone Autoscroll in a
    transcription would be thin), and the review tools under their own, which
    is what the manual calls them (Granskningsstöd in Swedish).
    """

    def after_menu(self) -> str:
        source = page()

        return source[source.index("with settings_menu, ui.column().classes(") :]

    def test_there_are_two_groups_and_only_the_second_has_a_title(self):
        text = self.after_menu()

        assert "with settings_group():" in text
        assert 'review_group = settings_group("Review tools")' in text
        assert text.index("with settings_group():") < text.index(
            'settings_group("Review tools")'
        )
        assert '"Recording"' not in text

    def test_a_group_is_a_group_for_a_screen_reader_named_by_its_title(self):
        source = page()
        group = source[source.index("def settings_group") :]
        group = group[: group.index("return group")]

        assert "role=group aria-labelledby={title_label.html_id}" in group
        assert "editor-settings-title" in group
        # Only a group that has a title is a named group.
        assert "if title:" in group

    def test_following_the_recording_and_the_timeline_are_together(self):
        text = self.after_menu()
        recording = text.index("with settings_group():")
        review = text.index('settings_group("Review tools")')

        for label in ('"Follow audio" if following_words else "Autoscroll"', '"Timeline"'):
            assert recording < text.index(label) < review

    def test_what_is_marked_in_the_text_is_under_review_tools(self):
        text = self.after_menu()
        review = text.index('settings_group("Review tools")')

        for label in ('"My edits"', '"Highlights"', '"Comments"', '"Uncertain words:"'):
            assert text.index(label) > review

    def test_uncertain_words_is_last_and_no_rule_is_drawn_above_it(self):
        text = self.after_menu()
        uncertain = text.index('"Uncertain words:"')

        for label in ('"My edits"', '"Highlights"', '"Comments"'):
            assert text.index(label) < uncertain
        assert 'ui.separator().classes("my-1")' not in text[: text.index("review_group.set_visibility")]

    def test_a_title_with_nothing_under_it_is_not_shown(self):
        text = self.after_menu()

        assert "review_group.set_visibility(" in text
        assert "len(review_group.default_slot.children) > 1" in text


class TestHowItBehavesWithTheKeyboardAndPointer:
    """
    What a try in a real browser showed (Chrome, the tooltip over the first
    row, focus on the button's own presentational span after Esc, focus lost
    to the page behind with the menu still open after Tab past the last row).
    """

    def test_the_tooltip_is_above_the_button_and_off_while_the_menu_is_open(self):
        source = page()
        text = gear()

        assert "anchor=\"top middle\" self=\"bottom middle\"" in text
        toggled = source[source.index("def settings_menu_toggled") :]
        toggled = toggled[: toggled.index("settings_menu.on_value_change")]

        assert 'settings_tip.props("disable")' in toggled
        assert 'settings_tip.props(remove="disable")' in toggled

    def test_after_esc_focus_goes_to_the_button_and_not_its_span(self):
        source = page()
        toggled = source[source.index("def settings_menu_toggled") :]
        toggled = toggled[: toggled.index("settings_menu.on_value_change")]

        assert "ui.run_javascript(" in toggled
        # Only from the button's own helper span: a click that closed the menu
        # on something else is left where it landed.
        assert "gear && here !== gear && gear.contains(here)" in toggled
        assert "gear.focus()" in toggled
        assert "html_id" in toggled

    def test_focus_goes_to_the_first_switch_when_it_opens(self):
        source = page()
        follow = source[source.index("follow = ui.switch(") :]
        follow = follow[: follow.index(".classes(")]

        assert "data-autofocus" in follow

    def test_tab_past_either_end_closes_the_menu_and_goes_to_the_button(self):
        source = page()
        handler = source[source.index("settings_content.on(") :]
        handler = handler[: handler.index("# A title with nothing under it")]

        assert '"keydown"' in handler
        assert "settings_menu.close" in handler
        assert "event.key !== 'Tab'" in handler
        assert "event.shiftKey" in handler
        assert "here === stops[0]" in handler
        assert "here === stops[stops.length - 1]" in handler
        assert "event.preventDefault();" in handler
        assert "settings_button.html_id" in handler
        assert "emit();" in handler

    def test_the_content_column_is_what_the_handler_hangs_on(self):
        source = page()

        assert ") as settings_content:" in source


class TestTheLook:
    def test_the_menu_content_has_room_around_it(self):
        css = stylesheet()
        rule = css[css.index("\n    .editor-settings {") :]
        rule = rule[: rule.index("}")]

        assert "padding: 0.75rem 1rem;" in rule
        assert "flex-direction: column" in rule

    def test_a_group_title_is_small_and_quiet(self):
        css = stylesheet()
        rule = css[css.index("\n    .editor-settings-title {") :]
        rule = rule[: rule.index("}")]

        assert "font-size: 0.75rem;" in rule
        assert "color: var(--color-text-secondary);" in rule

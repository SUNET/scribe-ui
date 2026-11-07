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

"""
The editor's toolbar as one Tab stop with the arrows between its buttons
(utils/toolbar.py), and the editor's structure around the text (F-65).
"""

import pathlib

from utils import toolbar

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "srt.py").read_text()


def test_the_two_groups_are_two_named_toolbars():
    """What works on the text on the left, the document on the right."""

    assert 'with roving_toolbar(ui.row().classes("editor-toolbar-group"), "Text tools"):' in PAGE
    assert 'with roving_toolbar(ui.row().classes("editor-toolbar-group"), "File and settings"):' in PAGE
    assert PAGE.count("roving_toolbar(") == 2


def test_the_name_is_set_as_a_value():
    source = (ROOT / "utils" / "toolbar.py").read_text()

    assert 'element.props("role=toolbar data-roving")' in source
    assert 'element._props["aria-label"] = name' in source


def test_the_keys_are_the_toolbar_pattern():
    keys = toolbar.KEYS

    for key in ("'ArrowRight'", "'ArrowLeft'", "'Home'", "'End'", "'Tab'"):
        assert f"event.key === {key}" in keys
    # Wrapping round at either end.
    assert "items[(at + 1) % items.length]" in keys
    assert "items[(at - 1 + items.length) % items.length]" in keys
    # Into the bar with Tab: to the button last used there.
    assert "kept.get(bar)" in keys
    # The keys of other shortcuts are left to them.
    assert "event.ctrlKey || event.metaKey || event.altKey" in keys


def test_the_buttons_own_tabindex_is_left_to_quasar():
    """A roving tabindex would be undone whenever a button changes."""

    assert "tabIndex =" not in toolbar.KEYS
    assert "setAttribute('tabindex'" not in toolbar.KEYS


def test_the_keys_are_put_on_the_page_once():
    assert "if (window.scribeToolbarKeys) return;" in toolbar.KEYS


def test_the_text_and_the_cards_are_headings():
    assert '"Captions" if data_format == "srt" else "Transcript"' in PAGE
    assert '.classes("sr-only").props("role=heading aria-level=2")' in PAGE

    for path, heading in (
        ("utils/validation_panel.py", "id=validation-panel-heading tabindex=-1 role=heading aria-level=2"),
        ("utils/find_panel.py", "id=find-panel-heading tabindex=-1 role=heading aria-level=2"),
        ("utils/comments_panel.py", "id=comments-panel-heading tabindex=-1 role=heading aria-level=2"),
    ):
        assert heading in (ROOT / path).read_text(), path

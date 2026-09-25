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
The phone layout.

What a phone is for here is recording something and starting a
transcription of it. Editing is not: it wants a video, a caption list and
a timeline side by side, and the editor says so for itself rather than
being shrunk into something that technically fits.

Most of it is CSS, which a test cannot see the effect of -- that was
checked in a browser at 400px. What is worth pinning here is the one place
the layout is decided in *two* languages at once: the table asks to be
drawn as cards below a width, and the stylesheet that dresses those cards
comes in at a width of its own, and nothing but this test says the two
numbers are the same one.
"""

import pathlib
import re

from utils.styles import default_styles

HOME = pathlib.Path("pages/home.py").read_text()
SRT = pathlib.Path("pages/srt.py").read_text()

# The width the page decides to draw cards at.
GRID_AT = re.search(r"window\.innerWidth < (\d+)", HOME)

# The width the stylesheet starts dressing them at.
PHONE_AT = re.findall(r"@media \(max-width: (\d+)px\)", default_styles)


def test_the_page_and_the_stylesheet_agree_on_what_a_phone_is():
    # The cards and the rules that style them have to appear together: a
    # table in grid mode below one width, styled for a hand below another,
    # is cards nobody laid out for a stretch of widths in between.
    assert GRID_AT, "the jobs table no longer asks for grid mode by width"
    assert GRID_AT.group(1) in PHONE_AT


def test_the_rows_become_cards_rather_than_seven_columns():
    assert 'table.add_slot(\n            "item"' in HOME
    assert "jobs-card-name" in HOME
    assert "jobs-card-action" in HOME

    # The card is worth nothing without the row's own action on it: that
    # is the whole of what a phone came to the list for.
    item = HOME[HOME.index('"item"') : HOME.index('with table.add_slot("top-left")')]
    assert "table_handle_row_click" in item
    assert "props.row.status === 'Completed' ? 'View' : 'Transcribe'" in item


def test_a_finished_job_is_viewed_rather_than_edited_on_a_phone():
    # The editor wants a desk, so the card offers the one thing a phone
    # can actually do with a finished job: read it back. The desktop row
    # is untouched and still opens the editor.
    item = HOME[HOME.index('"item"') : HOME.index('with table.add_slot("top-left")')]
    cell = HOME[HOME.index('"body-cell-status"') :]

    assert "table_handle_row_view" in item
    assert "table_handle_row_view" in HOME[HOME.index("def table_handle_row_view") :]
    assert "props.row.status === 'Completed' ? 'Edit' : 'Transcribe'" in cell


def test_the_view_page_shows_a_transcription_without_offering_to_change_it():
    view = pathlib.Path("pages/view.py").read_text()

    # It is the same fetch and the same parsing the editor does -- what a
    # caption is must not be decided twice.
    assert "SRTEditor" in view
    assert "parse_srt" in view and "parse_txt" in view

    # And nothing that writes: no save, no export, no editor on the
    # server behind it.
    assert "save_srt_changes" not in view
    assert "contenteditable" not in view
    assert "TranscriptEditor" not in view

    # Somebody's speech is drawn as a label, never as markup.
    assert "ui.html(" not in view

    # The notice in the editor offers the same page rather than only
    # turning a phone away.
    assert "/view?uuid=" in SRT


def test_the_menu_rail_gives_its_width_back_on_a_phone():
    # 56px of a 390px screen, given over to icons nobody is looking at.
    # Quasar writes the page container's padding inline from the drawer's
    # own width, which is why the stylesheet has to insist.
    assert ".q-drawer--mini" in default_styles
    assert "padding-left: 0 !important;" in default_styles


def test_nothing_is_wider_than_the_phone_it_is_on():
    common = pathlib.Path("utils/common.py").read_text()

    # The upload and record dialog carried a hard 400px minimum, which is
    # wider than the screen it now has to open on. It asks for the width
    # it wants where there is room and gives way where there is not.
    assert "min-width: min(400px, 100%)" in common

    # Every other card that names a width -- the export progress dialog,
    # the shortcuts dialog, the user settings card -- is answered by the
    # stylesheet rather than edited one by one: a minimum wider than the
    # screen takes the whole page sideways, and there are too many of them
    # to keep finding by hand.
    phone = default_styles[
        default_styles.index("@media (max-width: 700px)") :
    ]

    assert phone.count("min-width: 0 !important;") >= 2
    assert ".nicegui-content .q-card" in phone
    assert ".q-dialog__inner > .q-card" in phone


def test_the_editor_says_it_needs_a_computer():
    assert "editor-too-small" in SRT
    assert "editor-too-small" in default_styles

    # Both halves of it: the notice is drawn only on a phone, and the
    # editor itself only where it fits.
    phone = default_styles[default_styles.index(".editor-too-small") :]

    assert "display: none" in phone
    assert ".editor-panes {\n            display: none !important;\n        }" in phone


def test_the_header_stays_on_one_row():
    # The theme and help buttons wrapped onto a line of their own under the
    # logo on a phone: the header is a wrapping row and the logo group did
    # not shrink.
    phone = default_styles[default_styles.index("@media (max-width: 700px)") :]
    assert "flex-wrap: nowrap !important;" in phone
    assert ".header-brand" in phone and ".header-actions" in phone

    common = pathlib.Path("utils/common.py").read_text()
    assert '.classes("header-brand")' in common
    assert '"header-actions"' in common

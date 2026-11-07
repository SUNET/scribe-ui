# Copyright (c) 2025-2026 Sunet.
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
Text that looks like a heading is one (WCAG 1.3.1, F-10).

A ui.label styled as a heading (text-h1..h6, text-lg..text-4xl, bold) is a
heading to the eye; without role=heading and aria-level a screen reader
cannot list it, nor jump to it. Every such label in the pages and utils is
either given the role, or is named below with why it is not a heading.
"""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

LOOKS_LIKE_A_HEADING = re.compile(
    r"\b(text-h[1-6]|text-(?:lg|xl|2xl|3xl|4xl)|font-bold|font-semibold|font-medium)\b"
)

# Styled large or bold, but not headings: what they say is not the title
# of what follows them. Keyed on the file and the label's first argument.
NOT_HEADINGS = {
    # Empty states and errors: a message in place of the content.
    ("pages/admin/announcements.py", "'No announcements yet.'"),
    ("pages/admin/customers.py", "'No customers found. Create a new customer to get started.'"),
    ("pages/admin/customers.py", "'Failed to load customer. Please try again later.'"),
    ("pages/admin/groups.py", "'Error fetching statistics.'"),
    ("pages/admin/groups.py", "'Failed to load group. Please try again later.'"),
    ("pages/admin/groups.py", "'No groups found. Create a new group to get started.'"),
    ("pages/admin/health.py", "'Backend is not reachable'"),
    ("pages/admin/health.py", "'No workers online.'"),
    ("pages/admin/rules.py", "'No provisioning rules defined yet.'"),
    ("pages/admin/rules.py", "'No attributes defined.'"),
    ("pages/admin/users.py", "'Failed to load users. Please try again later.'"),
    ("pages/srt.py", "'Invalid job identifier.'"),
    ("pages/view.py", "'Invalid job identifier.'"),
    ("utils/srt_render.py", "'All captions are valid!'"),
    # The transcription dialogs' error line, empty until there is an error.
    ("utils/common.py", "''"),
    # A live status line, read out as it changes (role=status).
    ("utils/drive_dialogs.py", "''"),
    # Results and values: bold for emphasis, inside a part with a heading.
    ("pages/admin/rules.py", "'Match!'"),
    ("pages/admin/rules.py", "f\"{rule.get('name', '')}\""),
    ("pages/admin/rules.py", "f'• {action}'"),
    # The names of a cookie's fields, each beside its value.
    ("pages/cookies.py", "'Purpose'"),
    ("pages/cookies.py", "'Duration'"),
    ("pages/cookies.py", "'Type'"),
    ("pages/cookies.py", "'Security attributes'"),
    ("pages/cookies.py", "'Source'"),
    # The service's name in the top bar, on every page: the page's own
    # title is its h1.
    ("utils/common.py", "settings.TOPBAR_TEXT + header_text"),
    # The old health page's worker names; the rebuilt page has its own h2s.
    ("pages/admin/health.py", "host"),
}


def chain_root(node: ast.Call):
    """The ui.label(...) call at the root of label(...).classes(...)..., if any."""

    links = []
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "ui":
            return (node, links) if node.func.attr == "label" else (None, links)
        links.append(node)
        node = node.func.value

    return None, links


def headings_without_a_role():
    found = []

    for path in sorted([ROOT / "main.py", *ROOT.glob("pages/**/*.py"), *ROOT.glob("utils/**/*.py")]):
        tree = ast.parse(path.read_text())
        seen = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            label, links = chain_root(node)
            if label is None or id(label) in seen:
                continue
            seen.add(id(label))

            classes = " ".join(ast.unparse(link) for link in links if link.func.attr == "classes")
            props = " ".join(ast.unparse(link) for link in links if link.func.attr == "props")
            if not LOOKS_LIKE_A_HEADING.search(classes) or "role=heading" in props:
                continue

            first = ast.unparse(label.args[0]) if label.args else ""
            found.append((str(path.relative_to(ROOT)), first, label.lineno))

    return found


def test_every_label_that_looks_like_a_heading_is_one():
    unexplained = [
        f"{path}:{line} {first}"
        for path, first, line in headings_without_a_role()
        if (path, first) not in NOT_HEADINGS
    ]

    assert not unexplained, (
        "Styled as a heading but without role=heading aria-level=N; give it the "
        "role, or add it to NOT_HEADINGS with why it is not one:\n" + "\n".join(unexplained)
    )


def test_a_dialog_title_is_a_second_level_heading():
    # The page has the h1; a dialog's title is an h2, its parts h3.
    source = (ROOT / "pages/admin/rules.py").read_text()

    assert 'ui.label("Create provisioning rule").classes("text-2xl font-bold").props("role=heading aria-level=2")' in source
    assert 'ui.label("Scope").classes("text-lg font-semibold mt-2").props("role=heading aria-level=3")' in source


def test_the_two_dialogs_that_had_no_name_have_one():
    assert "ui.dialog().props('aria-label=\"Information\"') as info_dialog" in (ROOT / "pages/srt.py").read_text()
    # Set as a value: a speaker's name in the title may hold quotes.
    assert 'dialog._props["aria-label"] = title' in (ROOT / "utils/transcript_editor.py").read_text()


def test_the_check_finds_a_heading_without_a_role(tmp_path, monkeypatch):
    # The check itself: a made-up page with one such label is caught.
    (tmp_path / "pages").mkdir()
    (tmp_path / "utils").mkdir()
    (tmp_path / "main.py").write_text("")
    (tmp_path / "pages" / "x.py").write_text(
        'from nicegui import ui\n'
        'ui.label("Settings").classes("text-2xl font-bold")\n'
        'ui.label("Named").classes("text-2xl").props("role=heading aria-level=2")\n'
    )
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert headings_without_a_role() == [("pages/x.py", "'Settings'", 2)]

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
Error messages on the administrator pages (WCAG 4.1.3).

When a page fails to load its data it replaces the whole body with one
line of text. Nothing else on the screen changes, so a screen reader says
nothing unless that line is announced (role=alert). The text must also not
be the raw exception: "[Errno 111] Connection refused" tells the reader
nothing and leaks internals. The checks read the source with ast, since the
pages need a running backend to render.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# (file, the start of the label text that must be an alert)
ALERTS = [
    ("pages/admin/users.py", "Failed to load users"),
    ("pages/admin/groups.py", "Failed to load group"),
    ("pages/admin/groups.py", "Error fetching statistics"),
    ("pages/admin/customers.py", "Failed to load customer"),
    ("pages/admin/health.py", "Backend is not reachable"),
]

FILES = sorted({path for path, _ in ALERTS})


def tree(path):
    return ast.parse((ROOT / path).read_text())


def chain(node):
    """Every call in a method chain such as ui.label(..).classes(..).props(..)."""
    calls = []
    while isinstance(node, ast.Call):
        calls.append(node)
        node = node.func.value if isinstance(node.func, ast.Attribute) else None
    return calls


def labels(path):
    """Yield (first argument node, list of props strings) per ui.label chain."""
    for stmt in ast.walk(tree(path)):
        if not isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign)):
            continue
        calls = chain(stmt.value)
        base = [
            c
            for c in calls
            if isinstance(c.func, ast.Attribute)
            and c.func.attr == "label"
            and getattr(c.func.value, "id", None) == "ui"
        ]
        if not base or not base[0].args:
            continue
        props = [
            a.value
            for c in calls
            if isinstance(c.func, ast.Attribute) and c.func.attr == "props"
            for a in c.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        yield base[0].args[0], props


@pytest.mark.parametrize("path,text", ALERTS)
def test_error_label_is_an_alert(path, text):
    found = [
        props
        for arg, props in labels(path)
        if isinstance(arg, ast.Constant)
        and isinstance(arg.value, str)
        and arg.value.startswith(text)
    ]
    assert found, f"no label starting with {text!r} in {path}"
    for props in found:
        assert any("role=alert" in p for p in props), f"{text!r} in {path} is not role=alert"


def test_health_alert_is_persistent_and_only_changes_with_reachability():
    source = (ROOT / "pages/admin/health.py").read_text()
    assert source.index("reachability_alert = ui.label") < source.index("@ui.refreshable")
    assert "if backend_reachable != last_backend_reachable:" in source
    assert '"" if backend_reachable else "Backend is not reachable"' in source
    assert "reachability_alert.set_visibility(not backend_reachable)" in source


@pytest.mark.parametrize("path", FILES)
def test_labels_never_show_the_raw_exception(path):
    """No f-string label inside an except handler may interpolate the exception."""
    offenders = []
    for handler in ast.walk(tree(path)):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        for stmt in handler.body:
            for sub in ast.walk(stmt):
                if not isinstance(sub, ast.Expr):
                    continue
                for call in chain(sub.value):
                    func = call.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr == "label"
                        and getattr(func.value, "id", None) == "ui"
                        and call.args
                        and isinstance(call.args[0], ast.JoinedStr)
                        and any(
                            isinstance(n, ast.Name) and n.id == handler.name
                            for n in ast.walk(call.args[0])
                        )
                    ):
                        offenders.append(ast.unparse(call.args[0]))
    assert not offenders, f"{path} shows the raw exception: {offenders}"


def test_the_detail_is_still_printed():
    """Hiding the exception from the page must not hide it from the log."""
    for path, needle in [
        ("pages/admin/users.py", 'print(f"Error fetching users: {e}")'),
        ("pages/admin/groups.py", 'print(f"Error fetching group: {e}")'),
        ("pages/admin/customers.py", 'print(f"Error fetching customer: {e}")'),
    ]:
        assert needle in (ROOT / path).read_text(), f"{path} no longer prints the error"

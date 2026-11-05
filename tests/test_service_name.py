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
The service's name comes from the settings (SERVICE_NAME), never from the
code: another installation calls it something else ("NORDUnet S2T"). These
look through every string the interface or an export could show.
"""

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAME = re.compile(r"\bScribe\b")


def python_strings(path: pathlib.Path):
    """Every string in a file but its docstrings: what it can show."""

    tree = ast.parse(path.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.lineno, node.value


def js_strings(path: pathlib.Path):
    """Every quoted string in a script, with its comments taken out first."""

    text = path.read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    text = re.sub(r"\s//[^\"'`\n]*$", "", text, flags=re.M)

    for match in re.finditer(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`', text):
        # A template's own comments are not shown either.
        yield re.sub(r"<!--.*?-->", "", match.group(0)[1:-1], flags=re.S)


def test_no_python_string_names_the_service():
    found = []

    for path in [ROOT / "main.py"] + sorted((ROOT / "pages").rglob("*.py")) + sorted((ROOT / "utils").rglob("*.py")):
        if path.name == "settings.py":
            continue  # the defaults themselves

        for line, value in python_strings(path):
            if NAME.search(value):
                found.append(f"{path.relative_to(ROOT)}:{line}: {value.strip()[:80]!r}")

    assert found == [], "\n".join(found)


def test_no_script_names_the_service():
    # The one default, where the page has not said: in the engine and in
    # the recorder that reads it from there. And a header's name, which no
    # one reads.
    allowed = {"Sunet Scribe", "X-Scribe-Recording"}
    found = []

    for path in sorted((ROOT / "static").glob("*.js")) + sorted((ROOT / "utils").glob("*.js")):
        for value in js_strings(path):
            if NAME.search(value) and value not in allowed:
                found.append(f"{path.relative_to(ROOT)}: {value[:80]!r}")

    assert found == [], "\n".join(found)


def test_the_name_defaults_to_sunet_scribe():
    from utils.settings import Settings

    assert Settings.model_fields["SERVICE_NAME"].default == "Sunet Scribe"


def test_the_page_tells_the_recorder_the_name():
    recorder = (ROOT / "utils" / "recorder.py").read_text()

    assert "window.SCRIBE_SERVICE_NAME = {name};" in recorder
    assert 'json.dumps(get_settings().SERVICE_NAME).replace("<", "\\\\u003c")' in recorder
    engine = (ROOT / "static" / "recorder_engine.js").read_text()
    assert 'const SERVICE_NAME = (root && root.SCRIBE_SERVICE_NAME) || "Sunet Scribe";' in engine
    assert "SERVICE_NAME: SERVICE_NAME," in engine
    assert "window.ScribeRecorder.SERVICE_NAME" in (ROOT / "utils" / "recorder.js").read_text()


def test_the_exports_comments_are_from_the_service():
    from utils import srt_export

    assert srt_export.RTF_COMMENT_AUTHOR == "Sunet Scribe"
    assert srt_export.RTF_COMMENT_INITIALS == "SS"


def test_the_job_tables_badge_escapes_the_name():
    home = (ROOT / "pages" / "home.py").read_text()

    assert 'SERVICE_NAME_ATTRIBUTE = html.escape(get_settings().SERVICE_NAME, quote=True)' in home
    assert home.count('aria-label="Recorded in __SERVICE_NAME__"') == 2
    assert home.count('.replace("__SERVICE_NAME__", SERVICE_NAME_ATTRIBUTE)') == 2

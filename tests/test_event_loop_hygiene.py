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
NiceGUI calls event handlers and page builders inline on the event loop, so a
blocking call in one of them stalls every client this server is serving. These
are static guards over the places where that has already been put right.
"""

import ast
import pathlib

BLOCKING_VERBS = {"get", "put", "post", "delete", "patch", "request", "stream"}

ROOT = pathlib.Path(__file__).resolve().parent.parent


def parse(relative_path: str) -> ast.Module:
    return ast.parse((ROOT / relative_path).read_text())


def sync_httpx_calls(tree: ast.Module) -> list:
    """
    Find calls straight to the httpx module, which are the blocking ones.
    Calls on an AsyncClient go through a client instance instead.
    """

    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "httpx"
        and node.func.attr in BLOCKING_VERBS
    ]


def function_named(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node

    raise AssertionError(f"no function named {name}")


class TestHealthPagePoll:
    """
    The health page re-reads the backend every ten seconds on a timer, so it is
    the one place where a blocking call would stall the server unprompted.
    """

    def test_render_health_is_async(self):
        tree = parse("pages/admin/health.py")

        assert isinstance(function_named(tree, "render_health"), ast.AsyncFunctionDef)

    def test_no_blocking_http_on_the_health_page(self):
        lines = sync_httpx_calls(parse("pages/admin/health.py"))

        assert lines == [], f"blocking httpx call at pages/admin/health.py:{lines}"

    def test_the_first_render_is_awaited(self):
        tree = parse("pages/admin/health.py")
        page = function_named(tree, "health")

        awaited = {
            node.value.func.id
            for node in ast.walk(page)
            if isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        }

        assert "render_health" in awaited


class TestBackgroundTasks:
    """
    asyncio.create_task leaves the loop holding only a weak reference, so the
    task can be collected before it finishes and anything it raises is lost.
    NiceGUI's background_tasks.create keeps it alive and reports failures.
    """

    def test_no_bare_create_task_in_application_code(self):
        offenders = []

        for path in ROOT.rglob("*.py"):
            relative = path.relative_to(ROOT)

            if "venv" in str(relative) or relative.parts[0] == "tests":
                continue

            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "create_task"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "asyncio"
                ):
                    offenders.append(f"{relative}:{node.lineno}")

        assert offenders == [], (
            "use background_tasks.create so the task is not collected mid-flight: "
            + ", ".join(offenders)
        )

    def test_uploads_are_started_as_a_tracked_task(self):
        tree = parse("utils/common.py")
        upload = function_named(tree, "handle_upload_with_feedback")

        tracked = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "background_tasks"
            for node in ast.walk(upload)
        )

        assert tracked

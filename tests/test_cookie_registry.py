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
Guards utils/cookies.py against drifting away from what the codebase
actually does -- see issue #140. The registry is meant to be the single
source of truth for the cookie information page, so a cookie or a
browser-storage key that shows up in the source without a matching entry
here would otherwise go undocumented silently.
"""

import re
from pathlib import Path

import pytest

from utils.cookies import COOKIES, DOCUMENTED_BROWSER_STORAGE_KEYS, CookieInfo

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source directories that make up the running application. Deliberately
# excludes tests/, this engagement's own "Claude outputs" folder, and
# anything under a virtual environment or node_modules.
APP_SOURCE_DIRS = ["utils", "pages", "main.py"]

BROWSER_STORAGE_WRITE = re.compile(r'app\.storage\.browser\[([^\]]+)\]\s*=')
SET_COOKIE_CALL = re.compile(r'\.set_cookie\(')


def _resolve_browser_storage_key(raw: str) -> str:
    """
    BROWSER_STORAGE_WRITE captures whatever sits inside the brackets,
    which is either a quoted literal ("_scribe_bk") or a module-level
    constant name (COOKIE_NOTICE_ACKNOWLEDGED_KEY) used instead of a
    bare string to avoid a typo'd key living in two places. Resolve the
    latter against utils.cookies itself, since that is the only module
    this codebase's app.storage.browser writes use a named constant
    from today.
    """

    raw = raw.strip()
    if raw[:1] in "\"'":
        return raw.strip("\"'")

    import utils.cookies as cookies_module

    value = getattr(cookies_module, raw, None)
    if isinstance(value, str):
        return value

    # An identifier that is neither a known constant nor resolvable is
    # returned as-is, so it shows up as "undocumented" in the assertion
    # below rather than silently passing.
    return raw


def _app_source_files():
    for entry in APP_SOURCE_DIRS:
        path = REPO_ROOT / entry
        if path.is_file():
            yield path
        else:
            yield from path.rglob("*.py")


class TestRegistryIsWellFormed:
    def test_every_cookie_has_all_fields_filled_in(self):
        for cookie in COOKIES:
            assert isinstance(cookie, CookieInfo)
            for field in ("name", "purpose", "duration", "cookie_type", "security", "source"):
                value = getattr(cookie, field)
                assert isinstance(value, str) and value.strip(), (
                    f"{cookie.name!r} has an empty {field!r}"
                )

    def test_names_are_unique(self):
        names = [cookie.name for cookie in COOKIES]
        assert len(names) == len(set(names))


class TestRegistryMatchesTheActualCode:
    def test_no_cookie_is_set_outside_session_middleware(self):
        """
        response.set_cookie (or request/response .set_cookie(...)) would
        mean a second, separate HTTP cookie exists that this registry does
        not know about. The only cookie this service sets today is the one
        Starlette's SessionMiddleware manages on its own (see main.py's
        ui.run(storage_secret=...)), which never calls .set_cookie directly
        -- so finding a call here means either a new cookie was added
        without updating utils/cookies.py, or this test needs a documented
        exception.
        """

        offenders = []
        for path in _app_source_files():
            text = path.read_text(encoding="utf-8")
            if SET_COOKIE_CALL.search(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))

        assert offenders == [], (
            f"found .set_cookie(...) in {offenders}, but utils/cookies.py "
            "documents a single cookie set only via SessionMiddleware -- "
            "update the registry (and its docstring) if this is a real "
            "new cookie"
        )

    def test_every_browser_storage_key_written_in_the_app_is_documented(self):
        found_keys = set()
        for path in _app_source_files():
            text = path.read_text(encoding="utf-8")
            found_keys.update(
                _resolve_browser_storage_key(m)
                for m in BROWSER_STORAGE_WRITE.findall(text)
            )

        # A key found in the running code but missing from the registry's
        # documented set would be an undocumented addition to what the
        # "session" cookie's payload actually carries.
        undocumented = found_keys - DOCUMENTED_BROWSER_STORAGE_KEYS
        assert undocumented == set(), (
            f"app.storage.browser keys {undocumented} are written in the "
            "app but not listed in utils.cookies.DOCUMENTED_BROWSER_STORAGE_KEYS "
            "-- document what they are for in utils/cookies.py's module "
            "docstring and add them to that set"
        )

        # And the reverse: a key documented here that no longer appears
        # anywhere in the app would be describing a cookie that does not
        # exist any more.
        stale = DOCUMENTED_BROWSER_STORAGE_KEYS - found_keys
        assert stale == set(), (
            f"{stale} are documented as browser-storage keys but are never "
            "written anywhere in the app -- remove them from utils/cookies.py "
            "or check that the write just looks different from the pattern "
            "this test scans for"
        )


class TestCookieNoticeAcknowledgement:
    def test_is_acknowledged_reflects_storage(self):
        from unittest.mock import MagicMock, patch

        import utils.cookies as cookies_module

        mock_app = MagicMock()
        mock_app.storage.browser = {}

        with patch("utils.cookies.app", mock_app):
            assert cookies_module.is_cookie_notice_acknowledged() is False

            cookies_module.acknowledge_cookie_notice()

            assert cookies_module.is_cookie_notice_acknowledged() is True
            assert (
                mock_app.storage.browser[cookies_module.COOKIE_NOTICE_ACKNOWLEDGED_KEY]
                is True
            )

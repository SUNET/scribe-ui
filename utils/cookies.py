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
Single source of truth for the cookies Sunet Scribe sets.

The cookie notice (utils/common.py, render_cookie_notice_row) and the
public cookie information page (pages/cookies.py) both read COOKIES below
rather than keeping their own copy, so the notice, the information page and
this file cannot drift apart from each other -- see issue #140.

Measured, not assumed: this service sets exactly one HTTP cookie, "session",
from Starlette's SessionMiddleware (utils/storage via ui.run(storage_secret=
...) in main.py), with no session_middleware_kwargs overrides -- so it is
Starlette's own defaults: HttpOnly, SameSite=Lax, Max-Age 14 days, renewed
on every response that still carries session data. Nothing else in this
codebase calls response.set_cookie or otherwise sets a cookie of its own
(checked by test_cookie_registry.py, which scans the source for cookie-
setting calls and session-storage keys and fails if either drifts out of
sync with this file).

That one cookie carries two distinct things, both strictly necessary:

- A session identifier. Nothing interesting sits in the cookie's own bytes
  for this part -- the identifier just points at server-side storage
  (app.storage.user) holding the sign-in tokens, and preferences such as
  dark mode, whether the menu is expanded, and which announcements have
  been dismissed.
- app.storage.browser["_scribe_bk"] (utils/helpers.py, main.py): a random
  key generated once per browser, written directly into the cookie's own
  payload (unlike app.storage.user, app.storage.browser is NOT a pointer --
  its contents sit in the cookie itself). Combined with a server-side
  secret, it derives the encryption key for a user's uploaded recordings,
  so Sunet's own infrastructure cannot read them without that browser
  having taken part in deriving the key.

app.storage.browser["cookie_notice_acknowledged"] (this file) rides in the
same cookie, for the same reason _scribe_bk does: it needs to survive
before sign-in, and adding a second cookie just to remember that the first
one was explained felt like the wrong kind of cookie to add.
"""

from dataclasses import dataclass

from nicegui import app


@dataclass(frozen=True)
class CookieInfo:
    """One row of the public cookie information page."""

    name: str
    purpose: str
    duration: str
    cookie_type: str
    security: str
    source: str


COOKIES = [
    CookieInfo(
        name="session",
        purpose=(
            "Keeps you signed in as you move between pages, remembers a "
            "few preferences such as dark/light mode and whether the menu "
            "is expanded, and carries a random key unique to this browser "
            "that is combined with a server-side secret to derive the "
            "encryption key for your uploaded recordings -- so Sunet's own "
            "infrastructure cannot read your files without your browser "
            "having taken part in deriving that key. It also remembers "
            "whether you have seen this cookie notice."
        ),
        duration="14 days, renewed on every visit",
        cookie_type="Strictly necessary",
        security="HttpOnly, SameSite=Lax",
        source="Sunet Scribe (first-party)",
    ),
]

# app.storage.browser keys that ride inside the "session" cookie's own
# payload, documented individually so test_cookie_registry.py can confirm
# every key actually written anywhere in this codebase is accounted for in
# the paragraph above -- a key added without updating that text would be a
# silent, undocumented change to what the cookie carries.
DOCUMENTED_BROWSER_STORAGE_KEYS = {
    "_scribe_bk",
    "cookie_notice_acknowledged",
}

COOKIE_NOTICE_ACKNOWLEDGED_KEY = "cookie_notice_acknowledged"


def is_cookie_notice_acknowledged() -> bool:
    """Whether this browser has already dismissed the cookie notice."""

    return bool(app.storage.browser.get(COOKIE_NOTICE_ACKNOWLEDGED_KEY, False))


def acknowledge_cookie_notice() -> None:
    """
    Record that this browser has seen the cookie notice.

    This is acknowledgement that the notice was shown, not consent --
    there is nothing to consent to here, since the service uses no
    cookies that would require it. See the module docstring and issue
    #140.
    """

    app.storage.browser[COOKIE_NOTICE_ACKNOWLEDGED_KEY] = True

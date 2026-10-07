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
...) in main.py), whose only override is https_only (the HTTPS_ONLY_COOKIES setting, on by
default, which adds Secure) -- so apart from that it is Starlette's own
defaults: HttpOnly, SameSite=Lax, Max-Age 14 days, renewed
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

Whether this browser has acknowledged the cookie notice
(app.storage.user[COOKIE_NOTICE_ACKNOWLEDGED_KEY], this file) is read from
and written to the server-side storage above, not from the cookie's own
payload the way _scribe_bk is. That is not a style choice: NiceGUI's own
app.storage.browser can only be written while a page's first response is
still being built, and raises if written to afterwards (confirmed by
clicking the notice's own "OK" button, which calls this from a button's
click handler -- necessarily after that response has already gone out).
app.storage.user has no such restriction, and is keyed by the same
session id that already rides inside the "session" cookie before any
sign-in, so this still adds no second cookie and still survives a browser
that never signs in -- the value just lives server-side against that id
instead of inside the cookie's own bytes.
"""

from dataclasses import dataclass

from nicegui import app

from utils.settings import get_settings


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
            "whether you have closed the cookie banner."
        ),
        duration="14 days, renewed on every visit",
        cookie_type="Strictly necessary",
        # Mirrors main.py's session_middleware_kwargs.
        security=(
            "HttpOnly, Secure, SameSite=Lax"
            if get_settings().HTTPS_ONLY_COOKIES
            else "HttpOnly, SameSite=Lax"
        ),
        source="Sunet Scribe (first-party)",
    ),
]

# app.storage.browser keys that ride inside the "session" cookie's own
# payload, documented individually so test_cookie_registry.py can confirm
# every key actually written anywhere in this codebase is accounted for in
# the paragraph above -- a key added without updating that text would be a
# silent, undocumented change to what the cookie carries. Does NOT include
# COOKIE_NOTICE_ACKNOWLEDGED_KEY below: that one lives in app.storage.user,
# not app.storage.browser -- see the module docstring for why.
DOCUMENTED_BROWSER_STORAGE_KEYS = {
    "_scribe_bk",
}

COOKIE_NOTICE_ACKNOWLEDGED_KEY = "cookie_notice_acknowledged"


def is_cookie_notice_acknowledged() -> bool:
    """Whether this browser has already closed the cookie banner."""

    return bool(app.storage.user.get(COOKIE_NOTICE_ACKNOWLEDGED_KEY, False))


def acknowledge_cookie_notice() -> None:
    """
    Record that this browser has closed the cookie banner.

    "Closed", not "clicked" or "activated" on some labelled control:
    the banner's own control is an icon-only close/X (see
    render_cookie_notice_row), not a button with a word like "OK" to
    describe activating -- and "closed" reads naturally for a keyboard
    user pressing Enter or Space on it just as much as for a mouse
    click (WCAG 2.1.1 Keyboard), without needing a caveat to say so.

    Not that the notice was merely shown or seen -- a browser that saw
    the notice and left without closing it gets shown it again next
    time, which is correct: there is no consent to record either way,
    since the service uses no cookies that would require it, so
    nothing is lost by asking again. See the module docstring and
    issue #140.

    app.storage.user, not app.storage.browser: this runs from the
    banner's own close button, i.e. always after the page's own first
    response has already been sent, and app.storage.browser raises a
    TypeError if written to at that point ("the response to the browser
    has already been built..."). Reproduced directly by clicking the
    real button before this fix existed.
    """

    app.storage.user[COOKIE_NOTICE_ACKNOWLEDGED_KEY] = True

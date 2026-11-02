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
How strong a passphrase is, shown as it is typed (SUNET/scribe-ui#80).

The judgement is made in the browser, by passphrase_strength.js, and nowhere
else: this file only draws the meter that script fills in, and puts the script
and its styles in the page. Nothing typed is sent for evaluation, so the
server never sees a passphrase for any reason but setting it.

The level is advice -- except where the script finds the passphrase too easy
to guess: under the minimum length (MIN_LENGTH, kept in step with the script
by a test), a common one or a pattern, the name of a university, a place or
the term, or the reader's own name or user name. Those the page will not set.
To know, it asks the browser for its verdict (verdict()), which is the reason
alone, never the passphrase. No character classes are asked for: a longer
phrase is what is encouraged.
"""

import html
import pathlib
import re
import unicodedata
from typing import Optional

import jwt
from nicegui import app, ui

# The shortest passphrase that is accepted. Under it the meter says "Too
# short" and the page does not set it.
MIN_LENGTH = 8

# What the meter says before anything is typed. The method, not an example:
# an example phrase in the page is the one that gets used.
EMPTY_HINT = (
    "Let your password manager suggest one, or choose four or more words "
    "you don't normally use together. Not a quote or a song line."
)

# What the page says when it will not set a passphrase, by the reason the
# script gave. A reason that is not here is not a refusal.
REFUSALS = {
    "short": f"The passphrase is too short. Use at least {MIN_LENGTH} characters.",
    "guessable": (
        "This passphrase is too easy to guess and can't be used. "
        "Avoid common words and patterns."
    ),
    "personal": (
        "This passphrase is too easy to guess and can't be used. "
        "Don't use your own name or user name."
    ),
    "place": (
        "This passphrase is too easy to guess and can't be used. "
        "Avoid names of universities, places and terms."
    ),
}

# Asked of the browser before a passphrase is set. An expression, so
# NiceGUI's run_javascript gives back its value: the reason, or null.
VERDICT_JS = "window.PassphraseStrength ? window.PassphraseStrength.verdict() : null"

SCRIPT_PATH = pathlib.Path(__file__).with_suffix(".js")
SCRIPT = SCRIPT_PATH.read_text(encoding="utf-8")

# The three levels as colours, light and dark. Each clears 3:1 against the
# dialog's surface in both (1.4.11). They only repeat what the words say,
# which is why the text itself is not coloured.
STYLES = """
<style>
    .passphrase-strength {
        --strength-weak: #c62828;
        --strength-good: #b45309;
        --strength-strong: #2e7d32;
        --strength-colour: transparent;
        margin: 2px 0 10px;
    }
    .body--dark .passphrase-strength {
        --strength-weak: #ef5350;
        --strength-good: #ffc107;
        --strength-strong: #66bb6a;
    }
    .passphrase-strength[data-level="weak"] { --strength-colour: var(--strength-weak); }
    .passphrase-strength[data-level="good"] { --strength-colour: var(--strength-good); }
    .passphrase-strength[data-level="strong"] { --strength-colour: var(--strength-strong); }

    .passphrase-strength-bar {
        display: flex;
        gap: 4px;
        margin-bottom: 6px;
    }
    /* Outlined when empty, so the bar is there to be read as a bar before
       and after it is filled. */
    .passphrase-strength-bar span {
        flex: 1;
        height: 6px;
        box-sizing: border-box;
        border: 1px solid var(--color-border);
        border-radius: 3px;
        background: transparent;
    }
    .passphrase-strength[data-level="weak"] .passphrase-strength-bar span:nth-child(-n+1),
    .passphrase-strength[data-level="good"] .passphrase-strength-bar span:nth-child(-n+2),
    .passphrase-strength[data-level="strong"] .passphrase-strength-bar span:nth-child(-n+3) {
        background: var(--strength-colour);
        border-color: var(--strength-colour);
    }
    /* Windows high contrast takes backgrounds away; the filled part is then
       drawn in the system's own highlight colour. */
    @media (forced-colors: active) {
        .passphrase-strength[data-level="weak"] .passphrase-strength-bar span:nth-child(-n+1),
        .passphrase-strength[data-level="good"] .passphrase-strength-bar span:nth-child(-n+2),
        .passphrase-strength[data-level="strong"] .passphrase-strength-bar span:nth-child(-n+3) {
            forced-color-adjust: none;
            background: Highlight;
            border-color: Highlight;
        }
    }
    .passphrase-strength-label {
        margin: 0;
        font-weight: 600;
    }
    .passphrase-strength-label:empty {
        display: none;
    }
    .passphrase-strength-text {
        margin: 0;
        font-size: 0.875rem;
        color: var(--color-text-secondary);
    }
</style>
"""


def head_html() -> str:
    """
    The styles and the script, for the head of a page that asks for a
    passphrase. Inline: the script is small, and a page behind a proxy that
    does not pass a static path along would otherwise be without it.
    """

    return STYLES + "<script>" + SCRIPT + "</script>"


def refusal(reason: Optional[str]) -> Optional[str]:
    """
    What to tell the reader when the passphrase is not to be set, or None
    when it may be.
    """

    return REFUSALS.get(reason) if isinstance(reason, str) else None


async def verdict(timeout: float = 3.0) -> Optional[str]:
    """
    The reason the script gives for the passphrase in the field, asked of the
    browser. None when it cannot say -- the script is not there, or the page
    did not answer -- and then nothing is refused that the page did not refuse
    before: no one is to be locked out by a meter that did not load.
    """

    try:
        reason = await ui.run_javascript(VERDICT_JS, timeout=timeout)
    except Exception:
        return None

    return reason if isinstance(reason, str) else None


def personal_words(*values) -> list:
    """
    The reader's own words, from their name, user name and e-mail address:
    every part of three letters or more, lower case and without accents, as
    the script compares them. "anna.andersson@lu.se" gives anna and andersson
    (lu is too short; the university is on the script's own list anyway).
    """

    words = set()

    for value in values:
        if not isinstance(value, str):
            continue

        plain = unicodedata.normalize("NFD", value)
        plain = "".join(ch for ch in plain if not unicodedata.combining(ch)).lower()

        for part in re.split(r"[\W\d_]+", plain):
            if len(part) >= 3:
                words.add(part)

    return sorted(words)


def reader_words(user_data: Optional[dict] = None) -> list:
    """
    personal_words() for whoever is signed in: what the backend knows of them
    and what their sign-in token says. Their own words, put in their own page.
    """

    values = []

    if isinstance(user_data, dict):
        values += [user_data.get(key) for key in ("username", "email")]

    token = app.storage.user.get("token") if app.storage.user is not None else None

    if token:
        try:
            claims = jwt.JWT().decode(token, do_verify=False)
        except Exception:
            claims = {}

        values += [
            claims.get(key)
            for key in (
                "name",
                "given_name",
                "family_name",
                "email",
                "eduPersonPrincipalName",
                "preferred_username",
                "username",
            )
        ]

    return personal_words(*values)


def meter(personal: Optional[list] = None) -> None:
    """
    The meter, to be put right under the passphrase field (which has to carry
    class "passphrase-field", see the page). The script fills in what it says.
    `personal` is the reader's own words (reader_words()), which the script
    will not accept a passphrase made of.

    The strength is said in words as well as drawn (a bar and a colour alone
    would not do): the label and the advice are text, joined to the field with
    aria-describedby, and the one live region says a level only when it
    changes.
    """

    ui.html(
        '<div id="passphrase-strength" class="passphrase-strength"'
        f' data-level="empty" data-empty-hint="{html.escape(EMPTY_HINT, quote=True)}"'
        f' data-personal="{html.escape(" ".join(personal or []), quote=True)}">'
        '<div class="passphrase-strength-bar" aria-hidden="true">'
        "<span></span><span></span><span></span></div>"
        '<p id="passphrase-strength-label" class="passphrase-strength-label"></p>'
        f'<p id="passphrase-strength-text" class="passphrase-strength-text">'
        f"{html.escape(EMPTY_HINT)}</p>"
        '<p id="passphrase-strength-status" class="sr-only"'
        ' role="status" aria-live="polite" aria-atomic="true"></p>'
        "</div>",
        sanitize=False,
    )

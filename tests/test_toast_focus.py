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
Focus after a toast goes (WCAG 2.4.3).

A toast with a Close button takes focus when it is pressed, and takes it away
when it goes -- by Close, or by its own timeout -- so focus falls to the
document body and the next Tab starts at the top of the page. The script in the
shared stylesheet puts it back where it was before it went to the toast. The
behaviour was also run in a simulated browser (jsdom) against this very text;
these tests hold the parts of it that a change could take out without anything
noticing.
"""

from utils.styles import default_styles


def script() -> str:
    start = default_styles.index("if (!window._scribeToastFocus) {")

    return default_styles[start: default_styles.index("</script>", start)]


class TestFocusAfterAToast:
    def test_it_is_installed_once(self):
        """
        The page's styles are added by several pages, and one reader can pass
        through more than one of them without a reload.
        """

        text = script()

        assert text.startswith("if (!window._scribeToastFocus) {")
        assert "window._scribeToastFocus = true;" in text

    def test_it_keeps_to_itself(self):
        """
        An inline script's variables are the page's globals.
        """

        text = script()

        assert "(function () {" in text
        assert "    })();\n}" in text

    def test_it_remembers_the_last_place_that_was_not_a_toast(self):
        text = script()

        assert "document.addEventListener('focusin'" in text
        assert "target.closest(toastSelector)" in text
        assert "lastOutsideToast = target;" in text
        assert "target !== document.body" in text

    def test_it_watches_only_the_toasts(self):
        """
        Not the whole page: the editor changes its DOM all the time.
        """

        text = script()

        assert "document.querySelector('.q-notifications')" in text
        assert "observe(host, {" in text
        assert "subtree: true" in text
        # The body is watched for the container being added, and for that only.
        body_watch = text[text.index("observe(document.body, {"):]
        body_watch = body_watch[: body_watch.index("});")]

        assert "childList: true" in body_watch
        assert "subtree" not in body_watch

    def test_it_leaves_alone_what_the_reader_did_themselves(self):
        text = script()

        # Nothing to do unless focus was in the toast...
        assert "if (!focusIsInToast) return;" in text
        # ...and nothing if it is on something real now.
        assert "active !== document.body && active.isConnected" in text

    def test_it_only_returns_to_a_place_that_can_be_used(self):
        text = script()

        assert "target.isConnected && target.getClientRects().length" in text
        assert "target.focus({ preventScroll: true });" in text

    def test_it_waits_for_the_body(self):
        """
        The script is in the head, where there is no body yet.
        """

        text = script()

        assert "if (document.body) startWatchingToasts();" in text
        assert "document.addEventListener('DOMContentLoaded', startWatchingToasts);" in text

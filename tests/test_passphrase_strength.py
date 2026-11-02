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
The passphrase strength meter (SUNET/scribe-ui#80).

The judgement is made in the browser and is tested without one, in
tests/js/passphrase_strength.test.js, which this runs when node is there. What
is tested here is the rest: that the page asks for nothing more than it did,
that nothing typed can leave the browser from this script, that the meter says
its levels in words as well as colour, and that its colours hold.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

import utils.passphrase_strength as module

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = (ROOT / "utils" / "passphrase_strength.js").read_text()
MAIN = (ROOT / "main.py").read_text()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_passphrase_strength_in_node():
    done = subprocess.run(
        ["node", "--test", str(ROOT / "tests" / "js" / "passphrase_strength.test.js")],
        capture_output=True,
        text=True,
    )

    assert done.returncode == 0, done.stdout[-3000:]


def code(text: str) -> str:
    """The script without its comments, which talk about what it does not do."""

    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def setting_dialog() -> str:
    start = MAIN.index('aria-label="Set your encryption passphrase"')

    return MAIN[start : MAIN.index("else:\n        has_token", start)]


class TestNothingTypedLeaves:
    """
    The passphrase is judged where it is typed. A script that could send it
    anywhere, store it or write it to a log would make that a promise on trust.
    """

    @pytest.mark.parametrize(
        "needle",
        [
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "sendBeacon",
            "socket",
            "emit(",
            "console.",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "document.cookie",
            "import(",
            "eval(",
            "new Function",
            "postMessage",
            "location",
        ],
    )
    def test_the_script_has_no_way_out(self, needle):
        assert needle not in code(SCRIPT), needle

    def test_it_only_listens_to_typing_and_arriving(self):
        events = set(re.findall(r'addEventListener\(\s*"([a-z]+)"', code(SCRIPT)))

        assert events == {"focusin", "input"}

    def test_the_page_does_not_listen_to_the_value_either(self):
        """
        NiceGUI sends a field's value to the server as it changes whether or
        not anything listens, and has always done so. Nothing here adds to it:
        no handler on the field, and no judgement made in Python.
        """

        dialog = setting_dialog()

        assert "on_value_change" not in dialog
        assert '.on("update:model-value"' not in dialog
        assert ".bind_value" not in dialog
        assert "evaluate" not in dialog


class TestOnThePage:
    def test_the_minimum_is_the_one_the_script_knows(self):
        found = re.search(r"const MIN_LENGTH = (\d+);", SCRIPT)

        assert found and int(found.group(1)) == module.MIN_LENGTH == 8

    def test_the_page_uses_the_constant_and_not_a_number_of_its_own(self):
        dialog = setting_dialog()

        assert "{MIN_LENGTH}" in dialog
        assert ">= MIN_LENGTH" in dialog
        assert ">= 8" not in dialog
        assert "at least 8" not in dialog
        assert "less than 8" not in dialog

    def test_the_first_field_is_marked_for_the_script_and_the_meter_follows_it(self):
        dialog = setting_dialog()
        field = dialog.index('"Encryption Passphrase", password=True')
        meter = dialog.index("meter()")
        confirm = dialog.index('"Confirm Encryption Passphrase"')

        assert "input-class=passphrase-field" in dialog[field:meter]
        assert field < meter < confirm
        # Only the one field: the confirmation is not rated.
        assert dialog.count("passphrase-field") == 1
        # And it still lets a password manager offer a new one.
        assert "autocomplete=new-password" in dialog[field:meter]

    def test_the_script_and_styles_are_in_the_page_before_it_connects(self):
        """
        A head added after the client has connected goes over the socket, and a
        script that arrives that way is never run.
        """

        index = MAIN.index("async def index")
        connected = MAIN.index("await ui.context.client.connected()", index)
        added = MAIN.index("ui.add_head_html(passphrase_head())", index)

        assert added < connected

    def test_nothing_stops_a_paste_or_caps_the_length(self):
        text = setting_dialog() + code(SCRIPT)

        for needle in ("maxlength", "max-length", "onpaste", '"paste"', "preventDefault"):
            assert needle not in text, needle

    def test_the_head_carries_the_script_and_the_styles(self):
        head = module.head_html()

        assert head.lstrip().startswith("<style>")
        assert "<script>" in head and head.rstrip().endswith("</script>")
        assert "window._scribePassphraseStrength" in head
        assert ".passphrase-strength" in head


class TestTheMeter:
    def markup(self, monkeypatch):
        seen = {}

        def html(content, **kwargs):
            seen["content"] = content
            seen["kwargs"] = kwargs

        monkeypatch.setattr(module.ui, "html", html)

        module.meter()

        return seen["content"], seen["kwargs"]

    def test_it_has_what_the_script_looks_for(self, monkeypatch):
        content, _ = self.markup(monkeypatch)

        for needed in (
            "passphrase-strength",
            "passphrase-strength-label",
            "passphrase-strength-text",
            "passphrase-strength-status",
        ):
            assert f'id="{needed}"' in content, needed
            assert needed in SCRIPT, needed

        assert 'data-level="empty"' in content
        assert "data-empty-hint=" in content

    def test_the_hint_is_the_one_in_this_file_in_both_places(self, monkeypatch):
        content, _ = self.markup(monkeypatch)

        escaped = module.html.escape(module.EMPTY_HINT, quote=True)

        # Once as what the script restores, once as what is shown first.
        assert f'data-empty-hint="{escaped}"' in content
        assert f">{escaped}</p>" in content
        assert content.count(escaped) == 2

    def test_the_bar_is_decoration_and_the_words_carry_it(self, monkeypatch):
        content, _ = self.markup(monkeypatch)

        assert 'class="passphrase-strength-bar" aria-hidden="true"' in content
        assert "progressbar" not in content and "role=\"meter\"" not in content
        # A label and a line of advice, as text.
        assert 'id="passphrase-strength-label"' in content
        assert 'id="passphrase-strength-text"' in content

    def test_one_polite_live_region_that_is_read_whole_and_not_seen(self, monkeypatch):
        content, _ = self.markup(monkeypatch)
        status = re.search(r'<p id="passphrase-strength-status"[^>]*>', content).group(0)

        assert 'role="status"' in status
        assert 'aria-live="polite"' in status
        assert 'aria-atomic="true"' in status
        assert 'class="sr-only"' in status
        assert content.count("aria-live") == 1

    def test_it_is_plain_markup_from_this_file(self, monkeypatch):
        _, kwargs = self.markup(monkeypatch)

        # Nothing typed is in it, so it needs no sanitising -- and a sanitiser
        # would take the ids and attributes the script reads away.
        assert kwargs == {"sanitize": False}

    def test_the_hint_says_how_and_gives_no_phrase_to_copy(self):
        hint = module.EMPTY_HINT.lower()

        assert "password manager" in hint
        assert "four or more words" in hint
        assert "quote or a song line" in hint
        # An example in the page is the one that gets used.
        assert "for example" not in hint
        assert "e.g." not in hint
        assert "“" not in module.EMPTY_HINT and '"' not in module.EMPTY_HINT
        for word in ("sommar", "summer", "bicycle", "library", "cykel"):
            assert word not in hint


def declared_colour(name: str, scope: str) -> str:
    """The value of a custom property in the rule that sets it for `scope`."""

    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", module.STYLES):
        if selector.split(">")[-1].strip() == scope:
            found = re.search(rf"{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})", body)

            if found:
                return found.group(1)

    raise AssertionError(f"{name} not set for {scope}")


def luminance(colour: str) -> float:
    def linear(value: int) -> float:
        value /= 255

        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(int(colour[i : i + 2], 16)) for i in (1, 3, 5))

    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)

    return (lighter + 0.05) / (darker + 0.05)


# The surfaces the dialog's card is drawn on: --color-bg-surface and
# --color-bg-surface-alt in each theme (utils/styles.py).
LIGHT_SURFACES = ["#ffffff", "#f3f4f6"]
DARK_SURFACES = ["#16181d", "#1e2128"]


class TestTheLevelColours:
    @pytest.mark.parametrize("level", ["weak", "good", "strong"])
    def test_each_clears_3_to_1_in_light(self, level):
        colour = declared_colour(f"--strength-{level}", ".passphrase-strength")

        for surface in LIGHT_SURFACES:
            assert contrast(colour, surface) >= 3, (level, surface)

    @pytest.mark.parametrize("level", ["weak", "good", "strong"])
    def test_each_clears_3_to_1_in_dark(self, level):
        colour = declared_colour(f"--strength-{level}", ".body--dark .passphrase-strength")

        for surface in DARK_SURFACES:
            assert contrast(colour, surface) >= 3, (level, surface)

    def test_the_surfaces_are_still_those(self):
        styles = (ROOT / "utils" / "styles.py").read_text()

        for colour in LIGHT_SURFACES + DARK_SURFACES:
            assert colour in styles, colour

    def test_the_empty_bar_has_an_outline_that_clears_3_to_1(self):
        """
        An unfilled bar is its border. --color-border is what the page uses for
        a component boundary.
        """

        assert "border: 1px solid var(--color-border);" in module.STYLES

        styles = (ROOT / "utils" / "styles.py").read_text()
        light = re.search(r"--color-border: (#[0-9a-f]{6});", styles).group(1)

        for surface in LIGHT_SURFACES:
            assert contrast(light, surface) >= 3

    def test_one_two_three_segments_for_weak_good_strong(self):
        for level, count in (("weak", 1), ("good", 2), ("strong", 3)):
            assert f'[data-level="{level}"] .passphrase-strength-bar span:nth-child(-n+{count})' in module.STYLES

    def test_high_contrast_draws_the_filled_part_in_the_system_colour(self):
        start = module.STYLES.index("@media (forced-colors: active)")
        block = module.STYLES[start:]

        assert "forced-color-adjust: none;" in block
        assert "background: Highlight;" in block

    def test_the_text_is_not_coloured(self):
        """
        The dialog sets its own text colour in dark mode and would override it;
        the words carry the level, so they do not need one.
        """

        for rule in re.findall(r"\.passphrase-strength-(?:label|text)[^{]*\{([^}]*)\}", module.STYLES):
            assert "var(--strength" not in rule

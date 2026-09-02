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
The microphone recorder in the upload dialog.

The whole gesture is wired in the page -- getUserMedia wants the click that
asked for it -- so what a behavioural test could reach is one script string.
It is read directly instead: a broken string literal, a lost `addFiles` or a
waveform that decodes the recording are all failures a browser shows and
nothing else does.
"""

import ast
import inspect
import re

import pytest

import utils.common
from utils.recorder import PEAK_MS, SCRIPT, record_panel
from utils.styles import default_styles


@pytest.fixture(scope="module")
def recorder():
    return SCRIPT


@pytest.fixture(scope="module")
def code():
    """
    The script with its comments taken out.

    Comments explain what the code deliberately does *not* do, so a naive
    search finds the very name it was written to say is absent -- and their
    prose carries apostrophes, which is half of what quote balance counts.
    """

    return re.sub(r"//[^\n]*", "", SCRIPT)


def dialog_scripts():
    """
    Every script the upload dialog itself runs in the page.

    Element ids are interpolated at call time and stood in for here; nothing
    asserted below depends on their value.
    """

    def render(node):
        match node:
            case ast.Constant(value=str() as text):
                return text
            case ast.BinOp(op=ast.Add()):
                return render(node.left) + render(node.right)
            case ast.JoinedStr():
                return "".join(render(value) for value in node.values)
            case ast.Call() | ast.FormattedValue():
                return "1"

        raise TypeError(f"not part of a script: {ast.dump(node)[:60]}")

    source = inspect.getsource(utils.common.table_upload)
    source += inspect.getsource(utils.common._dropzone)

    return [
        render(node.args[0])
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run_javascript"
        and node.args
    ]


class TestQuoting:
    """
    A Python string that reaches a browser as source: a stray quote goes
    unnoticed until it gets there.
    """

    def test_the_recorder_has_balanced_quotes(self, code):
        for quote in ("'", '"'):
            assert code.count(quote) % 2 == 0

    def test_every_placeholder_is_one_the_panel_fills_in(self, recorder):
        filled = set(re.findall(r"__[A-Z_]+__", inspect.getsource(record_panel)))

        for token in set(re.findall(r"__[A-Z_]+__", recorder)):
            assert token in filled, f"{token} would reach the browser unfilled"


class TestSecureContext:
    """
    A microphone is offered only in a secure context.  In production TLS ends
    at the proxy and this app is plain http behind it, but the browser is on
    https -- which is what decides this -- so recording is available there.
    """

    def test_https_is_judged_by_the_browser_not_by_the_missing_api(self, recorder):
        assert "window.isSecureContext === false" in recorder

        secure = recorder.index("window.isSecureContext === false")
        support = recorder.index("typeof MediaRecorder === 'undefined'")

        assert secure < support, "the https check has to come first to own that message"

    def test_only_the_insecure_branch_blames_https(self, recorder):
        for message in re.findall(r"say\('([^']*)'\)", recorder):
            if "https" in message:
                assert message == "Recording needs an https connection."

    def test_a_browser_that_cannot_record_says_so_in_its_own_terms(self, recorder):
        assert "'This browser cannot record audio.'" in recorder

    def test_a_refusal_over_https_names_the_permissions_policy(self, recorder):
        # The two ways a refusal happens in production are fixed in different
        # places by different people, so the message has to distinguish them.
        assert "NotAllowedError:" in recorder
        assert "Permissions-Policy" in recorder


class TestWaveform:
    """
    Drawn from the live stream, never by decoding the finished recording --
    the same reason the caption timeline draws speech runs instead of a
    waveform.
    """

    def test_the_recording_is_never_decoded(self, code):
        assert "decodeAudioData" not in code
        assert "createAnalyser" in code

    def test_the_analyser_is_not_wired_to_the_speakers(self, code):
        # A microphone played back through the speakers it can hear.
        assert "connect(audio.destination)" not in code
        assert "connect(analyser)" in code

    def test_a_column_takes_the_loudest_peak_it_covers(self, recorder):
        # Drawing one sampled peak per column lets a quiet sample stand for a
        # loud moment beside it.
        assert "if (peaks[p] > peak) peak = peaks[p];" in recorder

    def test_the_peaks_are_bounded_by_a_bucket_not_by_the_sample_rate(self):
        assert PEAK_MS >= 20, "a bucket this small is a picket fence, not a waveform"

    def test_the_colours_come_from_the_page_not_from_the_canvas(self, recorder):
        # A canvas cannot read a stylesheet, so the theme has to be asked for.
        assert "getPropertyValue" in recorder
        assert "--color-brand-primary" in recorder


class TestDevicePicker:
    """
    Which microphone, when there is a choice worth offering.
    """

    def test_a_device_with_no_name_is_never_offered(self, code):
        # A browser withholds labels until the microphone has been granted,
        # and "Microphone 1 / Microphone 2" is not a choice anyone can make.
        assert "d.kind === 'audioinput' && d.label" in code

    def test_a_single_microphone_is_not_a_choice(self, code):
        assert "show(devices, mics.length > 1)" in code

    def test_the_names_are_asked_for_again_once_permission_is_granted(self, code):
        # The first grant is what makes the labels readable, so the picker can
        # only fill itself in after it.
        grant = code[code.index("if (failure) {"):code.index("chunks = [];")]

        assert "listDevices()" in grant

    def test_a_device_name_is_never_treated_as_markup(self, code):
        # An operating system's own name for a device, rendered into the page.
        assert "innerHTML" not in code
        assert "option.textContent = d.label" in code

    def test_a_chosen_device_is_asked_for_exactly(self, code):
        # Not a hint: a browser silently substitutes another microphone for a
        # deviceId it cannot honour, which is the one outcome a picker must
        # not have.
        assert "{deviceId: {exact: deviceId}}" in code

    def test_a_device_that_went_away_falls_back_and_says_so(self, code):
        assert "OverconstrainedError" in code
        assert "the default was used" in code

    def test_the_picker_is_locked_while_recording(self, code):
        assert "devices.disabled = true" in code
        assert code.count("devices.disabled = false") == 2

    def test_the_devicechange_listener_is_taken_off_again(self, code):
        # It is registered on navigator.mediaDevices, which outlives the
        # dialog by a very long way.
        assert "addEventListener('devicechange', onDeviceChange)" in code
        assert "removeEventListener('devicechange', onDeviceChange)" in code


class TestPreview:
    """
    Nothing is uploaded until the reader has heard it back.
    """

    def test_stopping_does_not_upload(self, recorder):
        # The handoff belongs to the "Use recording" button alone; onstop only
        # draws the take.
        onstop = recorder[recorder.index("recorder.onstop"):recorder.index("// A live")]

        assert "addFiles" not in onstop

    def test_the_recording_is_handed_over_by_the_use_button(self, recorder):
        use = recorder[recorder.index("useBtn.addEventListener"):]

        assert "$refs.qRef.addFiles([file])" in use

    def test_the_playhead_is_scaled_by_the_measured_length(self, code):
        # A webm from MediaRecorder carries no duration, so the recorder's own
        # clock is what the waveform is scaled by -- the player's idea of the
        # length is never what the playhead is worked out from.
        follow = code[code.index("const follow"):code.index("rec.addEventListener")]

        assert "player.duration" not in follow
        assert "player.currentTime / seconds" in follow

    def test_the_player_is_made_seekable(self, code):
        # Chrome answers Infinity until the blob has been seeked once, and an
        # unseekable player can neither be scrubbed nor played to the end.
        assert "player.duration !== Infinity" in code
        assert "player.currentTime = 1e101" in code

    def test_nothing_is_offered_when_nothing_was_recorded(self, recorder):
        assert "if (!blob.size)" in recorder


class TestRelease:
    """
    Closing the dialog mid-recording has to give the microphone back; left
    open, the browser goes on showing the tab as recording.
    """

    def test_the_dialog_cleanup_stops_the_recorder(self):
        cleanup = [script for script in dialog_scripts() if "_cleanup()" in script]

        assert cleanup, "expected the dialog's own cleanup script"
        assert any("_recordCleanup()" in script for script in cleanup)

    def test_the_tracks_are_stopped_not_only_the_recorder(self, recorder):
        assert "getTracks().forEach(t => t.stop())" in recorder

    def test_the_audio_context_is_closed_too(self, recorder):
        # A context left open keeps the tab marked as using the microphone
        # even after the tracks stop.
        assert "audio.close()" in recorder

    def test_the_preview_url_is_revoked(self, recorder):
        assert "URL.revokeObjectURL(url)" in recorder

    def test_a_long_recording_is_not_held_as_one_blob(self, recorder):
        assert re.search(r"recorder\.start\(\d+\)", recorder)


class TestModes:
    """
    The dialog is one thing or the other, chosen before it opens.
    """

    def test_the_dropzone_is_not_drawn_in_record_mode(self):
        source = inspect.getsource(utils.common.table_upload)

        assert 'if mode == "record":' in source
        assert "record_panel(upload)" in source
        assert "_dropzone(upload)" in source

    def test_a_recording_lands_on_the_same_uploader_a_file_does(self):
        source = inspect.getsource(utils.common.table_upload)
        accepted = re.search(r"accept=([^\"]+)", source).group(1).split(",")

        for extension in re.findall(r"'(\.[a-z0-9]+)'", SCRIPT):
            assert extension in accepted, f"{extension} would be rejected on add"


class TestButtons:
    """
    The recorder's buttons are built from two existing styles, one of which
    carries a width and one of which does not.
    """

    def test_every_button_carries_the_shared_width(self):
        source = inspect.getsource(record_panel)
        styled = re.findall(r'\.classes\("([^"]*style[^"]*)"\)', source)

        assert len(styled) == 4, "expected the record, stop, use and again buttons"

        for classes in styled:
            assert "recorder-action" in classes

    def test_the_shared_width_beats_the_style_it_is_paired_with(self):
        # Same specificity, so the stylesheet's own order is what decides:
        # .recorder-action has to come after .cancel-style to take the width
        # away from it.
        assert default_styles.index(".cancel-style") < default_styles.index(
            ".recorder-action"
        )

    def test_a_button_cannot_restack_its_own_label(self):
        # Quasar wraps a q-btn's content when the label does not fit, which
        # puts the icon above the text and makes that button a different
        # height as well as a different shape.
        assert ".recorder-action .q-btn__content" in default_styles
        assert "flex-wrap: nowrap" in default_styles

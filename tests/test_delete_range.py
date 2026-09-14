"""
Deleting a selection that reaches across captions.

Selecting from the middle of one caption into another and pressing Backspace
used to be left to the browser, which deleted the gutters between the blocks
along with the text -- the timings, the numbers and the block elements
themselves -- and the editor came apart on the page. The gesture is one
server-side edit instead: see SRTEditor.delete_range.
"""

import pathlib
import pytest

from utils.caption import SRTCaption
from utils.srt import SRTEditor


def editor(*captions) -> SRTEditor:
    held = SRTEditor("job-uuid", "srt", "file.srt")

    for name in ("refresh_display", "update_words_per_minute",
                 "mark_as_changed", "update_beforeunload_state",
                 "update_flagged_count"):
        setattr(held, name, lambda *a, **k: None)

    held.data_format = "srt"
    held.captions = list(captions)

    return held


def three() -> SRTEditor:
    return editor(
        SRTCaption(1, "00:00:00,370", "00:00:04,980", "Redan innan man vaknar"),
        SRTCaption(2, "00:00:09,390", "00:00:11,740", "fylld av motgangar. Jag vet"),
        SRTCaption(3, "00:00:11,900", "00:00:17,260", "Sa dar kanner alla av"),
    )


class TestDeleteRange:
    def test_the_two_ends_become_one_caption(self):
        held = three()

        seam = held.delete_range(held.captions[0], held.captions[1], 12, 20)

        assert [caption.text for caption in held.captions] == [
            "Redan innan Jag vet",
            "Sa dar kanner alla av",
        ]
        assert seam == len("Redan innan ")

    def test_the_survivor_spans_both_timings(self):
        held = three()

        held.delete_range(held.captions[0], held.captions[1], 12, 20)

        assert held.captions[0].start_time == "00:00:00,370"
        assert held.captions[0].end_time == "00:00:11,740"

    def test_captions_in_between_go(self):
        held = three()

        held.delete_range(held.captions[0], held.captions[2], 5, 6)

        assert len(held.captions) == 1
        assert held.captions[0].text == "Redan kanner alla av"
        assert held.captions[0].end_time == "00:00:17,260"

    def test_the_survivors_are_renumbered(self):
        held = three()

        held.delete_range(held.captions[0], held.captions[1], 12, 20)

        assert [caption.index for caption in held.captions] == [1, 2]

    def test_typed_text_lands_at_the_seam(self):
        """
        A printable key pressed over the selection replaces it, the same as
        it would inside one caption.
        """

        held = three()

        seam = held.delete_range(
            held.captions[0], held.captions[1], 12, 20, text="X"
        )

        assert held.captions[0].text == "Redan innan XJag vet"
        assert seam == len("Redan innan X")

    def test_it_is_one_undo_step(self):
        held = three()
        held.delete_range(held.captions[0], held.captions[1], 12, 20)

        state = held.undo_redo_manager.undo(held.captions, held.speakers)

        assert [caption.text for caption in state.captions] == [
            "Redan innan man vaknar",
            "fylld av motgangar. Jag vet",
            "Sa dar kanner alla av",
        ]

    def test_offsets_from_the_browser_are_clamped(self):
        held = three()

        seam = held.delete_range(held.captions[0], held.captions[1], 9999, -5)

        assert held.captions[0].text == "Redan innan man vaknarfylld av motgangar. Jag vet"
        assert seam == len("Redan innan man vaknar")

    def test_a_range_inside_one_caption_is_refused(self):
        """
        The browser handles that itself; nothing is reported here.
        """

        held = three()

        assert held.delete_range(
            held.captions[0], held.captions[0], 1, 3
        ) is None
        assert len(held.captions) == 3

    def test_a_backwards_range_is_refused(self):
        held = three()

        assert held.delete_range(
            held.captions[2], held.captions[0], 1, 3
        ) is None
        assert len(held.captions) == 3

    def test_surviving_marks_travel_with_their_words(self):
        """
        The reader's own edit marks are word positions, so the words kept
        from the last caption arrive at new positions and their marks with
        them -- and what the deletion itself brought together earns none it
        did not have.
        """

        held = three()
        held.captions[1].edited_words = {3}  # "Jag"

        held.delete_range(held.captions[0], held.captions[1], 12, 20)

        assert held.captions[0].text == "Redan innan Jag vet"
        # "Jag" is the third word of the caption that survives.
        assert 2 in held.captions[0].edited_words


class TestBrowserSide:
    """
    The component has to refuse the browser's own handling of these keys --
    that refusal is the fix; the server method above is only where the work
    then happens.
    """

    @pytest.fixture
    def source(self) -> str:
        return pathlib.Path("utils/transcript_editor.js").read_text()

    def test_a_cross_block_selection_is_reported(self, source):
        assert "selectionSpan()" in source
        assert 'this.$emit("deleterange"' in source

    def test_the_keys_are_caught_before_the_caret_is_read(self, source):
        """
        In onKeydown, not onInput: by the time an input event arrives the
        browser has already done the damage.
        """

        body = source[source.index("onKeydown(event) {"):]

        assert "const span = this.selectionSpan();" in body
        assert '"Backspace", "Delete", "Enter"' in body

    def test_cut_is_intercepted_too(self, source):
        assert '@cut="onCut"' in source

    def test_the_clipboard_is_filled_by_hand(self, source):
        """
        preventDefault on a cut prevents the copy half of it as well, and
        selection.toString() would sweep the gutters in with the text.
        """

        assert 'clipboardData?.setData("text/plain", this.spanText(span))' in source

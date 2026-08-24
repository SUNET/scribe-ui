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
The speech strip under the video: where someone is talking, worked out from
the word timings rather than from the audio.
"""

import pathlib

import pytest

from utils.caption import SRTCaption
from utils.srt import SRTEditor


def editor(*words, captions=()) -> SRTEditor:
    editor = SRTEditor("job-uuid", "srt", "file.srt")
    editor.data_format = "srt"
    editor.captions = list(captions)
    editor.load_words({"version": 1, "words": list(words)})

    return editor


def word(text, start, end):
    return {"t": text, "s": start, "e": end}


class TestSpeechRuns:
    """
    One run per stretch of speech, not one per word: the space between two
    words in a sentence is not a silence anyone means, and drawing every one
    of them turns a paragraph into a picket fence.
    """

    def test_words_close_together_are_one_run(self):
        runs = editor(
            word("Hej", 0.0, 0.4),
            word("på", 0.5, 0.8),
            word("dig", 0.9, 1.4),
        ).speech_runs()

        assert runs == [[0.0, 1.4]]

    def test_a_real_pause_breaks_the_run(self):
        runs = editor(
            word("Hej", 0.0, 0.4),
            word("igen", 3.0, 3.6),
        ).speech_runs()

        assert runs == [[0.0, 0.4], [3.0, 3.6]]

    def test_the_gap_is_the_caller_s_to_choose(self):
        words = (word("Hej", 0.0, 0.4), word("igen", 1.0, 1.6))

        assert len(editor(*words).speech_runs(gap=0.3) ) == 2
        assert len(editor(*words).speech_runs(gap=1.0)) == 1

    def test_a_word_with_no_timing_is_skipped(self):
        """
        Transcribed but not placed: there is nothing to say about when it
        was said, and inventing a position would put speech where there is
        none.
        """

        runs = editor(
            word("Hej", 0.0, 0.4),
            {"t": "tyst"},
            word("igen", 3.0, 3.6),
        ).speech_runs()

        assert runs == [[0.0, 0.4], [3.0, 3.6]]

    def test_no_words_means_no_runs(self):
        assert editor().speech_runs() == []


class TestSpeechDuration:
    """
    How far the strip runs. The captions can be stretched past the last
    thing said, and their own ends have to stay on it.
    """

    def test_the_last_word_when_it_is_last(self):
        assert editor(word("Hej", 0.0, 4.5)).speech_duration() == 4.5

    def test_the_last_caption_when_it_runs_on(self):
        subtitles = editor(
            word("Hej", 0.0, 4.5),
            captions=[SRTCaption(1, "00:00:00,000", "00:00:09,000", "Hej")],
        )

        assert subtitles.speech_duration() == 9.0

    def test_nothing_at_all_is_zero(self):
        assert editor().speech_duration() == 0.0


class TestTheComponent:
    """
    What the browser is told, and what it works out for itself.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_the_playhead_is_not_pushed_from_the_server(self):
        """
        timeupdate fires several times a second; a round trip per tick to
        move a line two pixels is not worth taking, so the component reads
        the player itself.
        """

        source = self.source()
        props = source[source.index("props: {"):]
        props = props[: props.index("},\n  emits:")]

        assert "document.querySelector(\"video\")" in source
        assert "position" not in props, "the playhead is read, not received"

    def test_it_follows_every_frame_while_playing(self):
        """
        timeupdate alone is visibly steppy for a line travelling across a
        strip this wide.
        """

        source = self.source()

        assert "requestAnimationFrame" in source
        assert "cancelAnimationFrame" in source

    def test_clicking_it_seeks(self):
        source = self.source()

        assert "this.video.currentTime =" in source

    def test_it_redraws_when_the_strip_is_resized(self):
        """
        The splitter can change its width at any time, and a canvas drawn at
        the wrong size is stretched rather than re-laid-out.
        """

        assert "ResizeObserver" in self.source()

    def test_it_draws_at_the_display_s_pixel_density(self):
        assert "devicePixelRatio" in self.source()

    def test_the_colours_come_from_the_stylesheet(self):
        """
        A canvas cannot read a stylesheet, so the component asks for the
        custom properties by name -- which is also what lets dark mode
        change them without the component knowing.
        """

        source = self.source()

        for name in (
            "--timeline-ground",
            "--timeline-speech",
            "--timeline-caption",
            "--timeline-playhead",
        ):
            assert name in source

    def test_the_stylesheet_states_them(self):
        from utils.styles import theme_styles

        for name in (
            "--timeline-ground",
            "--timeline-speech",
            "--timeline-caption",
            "--timeline-playhead",
        ):
            assert f"{name}:" in theme_styles


class TestItExplainsItself:
    """
    The strip draws four things and names none of them: bars, gaps, ticks
    and a playhead. A canvas has no elements to hang a tooltip on, so the
    component says what they mean itself.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_there_is_a_key_for_every_thing_it_draws(self):
        source = self.source()

        for label in ("Speech", "Silence", "Caption", "Playhead"):
            assert label in source

    def test_the_swatches_are_stated_in_the_stylesheet(self):
        from utils.styles import theme_styles

        for swatch in (
            "speech-timeline-swatch-speech",
            "speech-timeline-swatch-silence",
            "speech-timeline-swatch-caption",
            "speech-timeline-swatch-playhead",
        ):
            assert f".{swatch}" in theme_styles

    def test_pointing_at_it_says_what_is_there(self):
        """
        The time, whether anyone is talking there, and which caption covers
        it -- worked out from the same runs and boundaries it draws.
        """

        source = self.source()
        body = source[source.index("onMove(event) {"):]
        body = body[: body.index("\n    onLeave()")]

        assert "speech" in body and "silence" in body
        assert "caption #" in body
        # To a tenth: at twenty seconds across the strip a whole second
        # covers around fifty pixels, and the readout said the same thing
        # across all of them.
        assert "this.moment(seconds)" in body

    def test_the_moment_is_reported_to_a_tenth(self):
        source = self.source()
        body = source[source.index("moment(seconds) {"):]
        body = body[: body.index("\n    },")]

        assert "toFixed(1)" in body

    def test_the_readout_never_takes_a_click(self):
        """
        It sits over the strip the reader is trying to click.
        """

        from utils.styles import theme_styles

        rule = theme_styles[theme_styles.index(".speech-timeline-readout {"):]
        rule = rule[: rule.index("}")]

        assert "pointer-events: none" in rule

    def test_leaving_it_clears_the_readout(self):
        source = self.source()

        assert '@mouseleave="onLeave"' in source


class TestZoom:
    """
    Twenty seconds across the strip, always. An hour across a pane this wide is
    roughly a minute per pixel, where no caption edge can be seen let alone
    aimed at -- and a scale that changes underfoot makes the strip harder to
    read, not easier, so it is not offered as a choice.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_the_window_is_twenty_seconds(self):
        """
        Within the 10-30s SUNET/scribe-ui#126 asks for.
        """

        assert "const WINDOW = 20;" in self.source()

    def test_docked_it_holds_a_minute(self):
        """
        Three times as wide along the foot of the page, so three times the
        window at much the same seconds per pixel -- which is what actually
        decides whether an edge can be seen and aimed at.
        """

        assert "const DOCKED_WINDOW = 60;" in self.source()

    def test_it_is_not_a_control(self):
        source = self.source()

        assert "speech-timeline-zoom" not in source
        assert "setWindow" not in source

    def test_a_short_recording_shows_all_of_itself(self):
        source = self.source()
        body = source[source.index("visible() {"):]
        body = body[: body.index("\n    },")]

        assert "Math.min(window, this.span())" in body
        assert "this.docked ? DOCKED_WINDOW : WINDOW" in body

    def test_the_playhead_stays_in_the_centre(self):
        """
        The recording scrolls behind a fixed playhead, deliberately without
        clamping at the ends -- clamping slides the playhead off centre
        exactly where the reader works most, on the first and last captions.
        What lies outside the recording is shaded instead.
        """

        source = self.source()
        body = source[source.index("viewStart() {"):]
        body = body[: body.index("\n    },")]

        assert body.count("return") == 1
        assert "this.position - this.visible() / 2" in body
        assert "Math.max(0" not in body, "not clamped"
        assert "--timeline-void" in source

    def test_it_says_which_part_it_is_showing(self):
        """
        A minute of speech looks much like an hour of it when nothing says
        which one is on screen.
        """

        source = self.source()
        body = source[source.index("range() {"):]
        body = body[: body.index("\n    },")]

        assert "whole recording" in body
        assert "this.clock(from)" in body
        assert "of ${this.clock(span)}" in body


class TestDraggingACaption:
    """
    A caption can be dragged on the strip: by an edge to move that edge, by
    the middle to move the whole cue.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_an_edge_is_taken_before_the_body(self):
        source = self.source()
        body = source[source.index("captionAt(seconds) {"):]
        body = body[: body.index("\n    },")]

        assert body.index("if (closest) return closest;") < body.index('edge: "body"')

    def test_the_nearest_edge_wins_not_the_first_caption(self):
        """
        Two cues close together both answer to a point between them. Taking
        whichever came first in the list meant reaching for one caption's
        end and getting the next one's start -- and a caption shorter than
        the grip could only ever be taken by its start.
        """

        source = self.source()
        body = source[source.index("captionAt(seconds) {"):]
        body = body[: body.index("\n    },")]

        assert "let distance = grip;" in body
        assert "if (away > distance) continue;" in body

    def test_a_tie_is_broken_by_which_side_the_pointer_is_on(self):
        """
        Where one cue ends at exactly the instant the next begins, the two
        edges are the same instant: approaching from the left takes the
        first cue's end, from the right the second cue's start. Any fixed
        preference makes one of the two unreachable.
        """

        source = self.source()
        body = source[source.index("captionAt(seconds) {"):]
        body = body[: body.index("\n    },")]

        assert (
            'edge === "end" ? seconds <= caption.end : seconds >= caption.start'
            in body
        )
        assert "away < distance || (towards && !facing)" in body

    def test_the_readout_says_which_edge(self):
        """
        So the reader can see what a drag would take hold of before taking
        it.
        """

        source = self.source()

        assert "`caption #${found.caption.id} ${found.edge}`" in source

    def test_an_edge_never_crosses_its_own_other_end(self):
        """
        A caption that ends before it starts is refused by the server, so it
        is not offered here either.
        """

        source = self.source()
        body = source[source.index("onDragMove(event) {"):]
        body = body[: body.index("\n    },")]

        assert "end - 0.05" in body
        assert "start + 0.05" in body

    def test_it_snaps_to_the_neighbouring_captions_first(self):
        """
        Two cues meeting exactly is something a reader means. A cue landing
        a hundredth of a second from its neighbour -- a gap no viewer can
        perceive, but a gap in the file -- never is. So caption edges are
        tried first, and from further away than anything else.
        """

        source = self.source()
        body = source[source.index("snap(seconds, movingId) {"):]
        body = body[: body.index("\n    },")]

        assert body.index("CAPTION_SNAP") < body.index("SNAP / perSecond")
        assert "caption.id !== movingId" in body, "never to its own edges"

    def test_a_caption_reaches_further_than_speech(self):
        source = self.source()
        caption_reach = int(
            source[source.index("const CAPTION_SNAP = "):].split("=")[1].split(";")[0]
        )
        speech_reach = int(
            source[source.index("const SNAP = "):].split("=")[1].split(";")[0]
        )

        assert caption_reach > speech_reach

    def test_it_still_snaps_to_speech_when_no_caption_is_near(self):
        """
        Where a cut belongs when it is not against another cue.
        """

        source = self.source()
        body = source[source.index("snap(seconds, movingId) {"):]
        body = body[: body.index("\n    },")]

        assert "this.runs.flat()" in body

    def test_it_lands_where_the_pointer_is_when_nothing_is_near(self):
        source = self.source()
        body = source[source.index("snap(seconds, movingId) {"):]
        body = body[: body.index("\n    },")]

        assert "speechEdge === null ? seconds : speechEdge" in body

    def test_every_drag_says_which_caption_is_moving(self):
        """
        Or a caption would snap to the edge it is being dragged away from.
        """

        source = self.source()
        moves = source[source.index("onDragMove(event) {"):]
        moves = moves[: moves.index("\n    },")]

        assert moves.count("this.snap(") == 3
        assert moves.count("this.drag.id)") == 3

    def test_both_ends_travel_in_one_event(self):
        """
        One retime, so one undo step: dragging a caption across is a single
        gesture and putting it back must be a single press.
        """

        source = self.source()

        assert 'this.$emit("retimespan", {' in source
        assert "start: preview.start" in source
        assert "end: preview.end" in source

    def test_a_drag_does_not_seek(self):
        """
        A click event follows the mouseup that ended a drag, and seeking to
        wherever the drag finished is never what was meant.
        """

        source = self.source()
        body = source[source.index("onClick(event) {"):]
        body = body[: body.index("\n    },")]

        assert "if (this.dragged)" in body
        assert body.index("this.dragged") < body.index("currentTime")

    def test_the_drag_continues_off_the_strip(self):
        source = self.source()

        assert 'window.addEventListener("mousemove", this.onDragMove)' in source
        assert 'window.addEventListener("mouseup", this.onUp)' in source
        assert 'window.removeEventListener("mouseup", this.onUp)' in source

    def test_the_caption_is_drawn_where_it_would_land(self):
        source = self.source()

        assert "dragging && dragging.id === caption.id ? dragging : caption" in source


class TestThreeStates:
    """
    The caption being edited, the caption under the pointer and the caption
    being played are three different things. They are often the same
    caption, and must not be treated as one: hovering a caption on the strip
    cannot take the text editor's focus off another.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_the_current_caption_comes_from_the_server(self):
        """
        Which caption is being edited is known where the editing happens.
        The strip is a second view of the captions, not the owner of them.
        """

        source = self.source()

        assert "currentId: { type: Number, default: -1 }" in source
        assert "set_current" in pathlib.Path("utils/speech_timeline.py").read_text()

    def test_the_playing_caption_is_worked_out_locally(self):
        """
        It follows from the playhead, which the component already has --
        pushing it from the server would be a round trip several times a
        second.
        """

        source = self.source()

        assert "playingId() {" in source
        assert "this.position >= caption.start" in source

    def test_hovering_is_its_own_state(self):
        source = self.source()

        assert "hovered: -1," in source
        assert "this.hovered = found ? found.caption.id : -1;" in source

    def test_leaving_the_strip_clears_only_the_hover(self):
        source = self.source()
        body = source[source.index("onLeave() {"):]
        body = body[: body.index("\n    },")]

        assert "this.hovered = -1;" in body
        assert "currentId" not in body

    def test_the_three_are_drawn_differently(self):
        from utils.styles import theme_styles

        for token in (
            "--timeline-caption:",
            "--timeline-caption-playing:",
            "--timeline-caption-current:",
        ):
            assert token in theme_styles


class TestCaptionsAreBrackets:
    """
    A caption is drawn as a bracket pair -- "[" for its start, "]" for its
    end. A plain block cannot say which of two touching edges belongs to
    which caption when one ends exactly where the next begins, which is the
    common case in a subtitle file.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_each_end_has_a_stem_and_two_arms(self):
        source = self.source()
        body = source[source.index("      for (const caption of this.captions) {"):]

        assert body.count("context.fillRect(left") >= 3
        assert "right - arm" in body

    def test_the_brackets_thicken_when_the_caption_is_hovered(self):
        """
        Which is also when they can be taken hold of.
        """

        source = self.source()

        assert "const stem = hovered || held ? 3 : 2;" in source

    def test_the_whole_caption_is_a_hover_target(self):
        """
        Nobody should have to aim at a thin line to pick a caption up.
        """

        source = self.source()

        assert 'edge: "body"' in source

    def test_it_carries_its_own_number(self):
        """
        The same number identifies the same caption in the text editor.
        """

        source = self.source()

        assert "const label = `#${caption.id}`;" in source
        assert "context.measureText(label).width < room" in source, (
            "and only when there is room for it between the brackets"
        )

    def test_the_number_is_readable_against_the_strip(self):
        """
        Drawn in the bracket's own grey it was there without being legible.
        """

        source = self.source()

        assert '--timeline-label' in source
        assert "700 12px" in source


class TestClickingACaption:
    """
    Clicking a caption asks for that caption: the text editor moves to it
    and the recording follows. Clicking the strip itself asks for that
    moment, and nothing else changes.
    """

    def test_the_strip_tells_the_server_which_one(self):
        source = pathlib.Path("utils/speech_timeline.js").read_text()

        assert 'this.$emit("selectcaption", { id: found.caption.id })' in source

    def test_the_server_focuses_it_and_seeks(self):
        source = pathlib.Path("utils/transcript_editor.py").read_text()
        body = source[source.index("def select_from_timeline(self, args)"):]
        body = body[: body.index("\n    def ", 10)]

        assert "self.editor.seek_video(" in body
        assert "self.focus(caption.index)" in body
        assert "self.mark_current(caption.index)" in body

    def test_clicking_the_strip_only_seeks(self):
        source = pathlib.Path("utils/speech_timeline.js").read_text()
        body = source[source.index("onClick(event) {"):]
        body = body[: body.index("\n    },")]

        assert body.index("selectcaption") < body.index("currentTime")

    def test_moving_to_a_caption_any_other_way_marks_it_too(self):
        """
        Search, autoscroll and a click in the text all move the reader to a
        caption, which is what the strip means by "current".
        """

        source = pathlib.Path("utils/transcript_editor.py").read_text()

        assert source.count("self.mark_current(") >= 3


class TestRetimeSpan:
    """
    The server side of a drag: both ends applied together, as one undo step.
    """

    def source(self) -> str:
        return pathlib.Path("utils/transcript_editor.py").read_text()

    def test_it_applies_both_ends_at_once(self):
        source = self.source()
        body = source[source.index("def retime_span(self, args)"):]
        body = body[: body.index("\n    def ", 10)]

        assert "self.apply_time(caption, start, end)" in body

    def test_a_refused_drag_puts_the_caption_back(self):
        """
        The strip is already drawing it where it was dropped, so nothing
        else would.
        """

        source = self.source()
        body = source[source.index("def retime_span(self, args)"):]
        body = body[: body.index("\n    def ", 10)]

        assert "self.refresh()" in body

    def test_a_value_that_is_not_a_number_is_refused(self):
        source = self.source()
        body = source[source.index("def retime_span(self, args)"):]
        body = body[: body.index("\n    def ", 10)]

        assert "except (TypeError, ValueError):" in body

    def test_the_strip_is_wired_to_it(self):
        source = self.source()

        assert 'timeline.on("retimespan"' in source


class TestTheOverlayFollowsTheControlBar:
    """
    A browser offers no signal for whether the player's own control bar is
    up, so the page follows the same rules the browser draws it by: up while
    the recording is paused, and while the pointer has moved over the frame
    within the last few seconds.
    """

    def page(self) -> str:
        return pathlib.Path("pages/srt.py").read_text()

    def test_pausing_puts_the_bar_up(self):
        page = self.page()

        assert 'video.addEventListener("pause", show)' in page

    def test_the_pointer_keeps_it_up_for_a_while(self):
        page = self.page()

        assert 'frame.addEventListener("mousemove", stir)' in page
        assert "idle = setTimeout(hide, HIDE_AFTER)" in page

    def test_it_never_hides_the_bar_while_paused(self):
        """
        The browser does not either, however long the pointer sits still.
        """

        page = self.page()
        hide = page[page.index("const hide = () => {"):]
        hide = hide[: hide.index("};")]

        assert "if (video.paused) return;" in hide

    def test_it_waits_for_the_player_to_exist(self):
        """
        The script arrives before NiceGUI has drawn the video element.
        """

        page = self.page()

        assert "setInterval" in page
        assert "clearInterval(waiting)" in page


class TestDockingTheStrip:
    """
    The strip can be dragged to the foot of the page, where it spans the
    whole width and holds a minute instead of twenty seconds.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_it_is_moved_by_a_grip_not_by_the_strip(self):
        """
        Dragging the strip already means taking hold of a caption, and one
        gesture cannot mean two things.
        """

        source = self.source()

        assert 'class="speech-timeline-grip"' in source
        assert '@mousedown="startDockDrag"' in source

    def test_letting_go_low_enough_docks_it(self):
        source = self.source()
        body = source[source.index("onDockDragMove(event) {"):]
        body = body[: body.index("\n    },")]

        assert "event.clientY > window.innerHeight * DOCK_AT" in body

    def test_it_says_what_letting_go_would_do(self):
        source = self.source()

        assert "Release to dock along the bottom" in source
        assert "Release to put it back under the video" in source

    def test_moving_it_nowhere_changes_nothing(self):
        """
        A grip picked up and put back where it was is not a move, and must
        not be saved as one.
        """

        source = self.source()
        body = source[source.index("onDockDrop() {"):]
        body = body[: body.index("\n    },")]

        assert "if (willDock === this.docked) return;" in body
        assert body.index("if (willDock === this.docked)") < body.index('$emit("dock"')

    def test_it_redraws_once_the_page_has_settled(self):
        """
        Moving the strip teleports it, changes the padding the page keeps
        for it and moves the splitter under it. The box it ends up with is
        not known until the browser has laid all of that out, and drawn too
        early the canvas keeps its old backing size -- which is what left it
        stretched on the way back from the bottom of the page.
        """

        source = self.source()
        body = source[source.index("settle() {"):]
        body = body[: body.index("\n    },")]

        assert "this.shrinkCanvas();" in body, "before anything is measured"
        assert "this.$nextTick(" in body
        assert "requestAnimationFrame(" in body
        assert "setTimeout(" in body, "and once more after any transition"
        assert body.count("this.draw();") == 3

    def test_the_canvas_lets_go_of_its_old_size_first(self):
        """
        A canvas is as wide as its own backing store unless something stops
        it, and min-content sizing honours that -- coming back from the foot
        of the page the strip measured itself against a box its own canvas
        was holding open, and came back docked-width with nothing on it.
        """

        source = self.source()
        body = source[source.index("shrinkCanvas() {"):]
        body = body[: body.index("\n    },")]

        assert "canvas.width = 0;" in body
        assert 'canvas.style.width = "100%";' in body

    def test_the_stylesheet_holds_it_to_its_box_too(self):
        from utils.styles import theme_styles

        rule = theme_styles[theme_styles.index(".speech-timeline canvas {"):]
        rule = rule[: rule.index("}")]

        assert "max-width: 100%" in rule
        assert "min-width: 0" in rule

    def test_the_page_is_told_to_leave_room(self):
        """
        A fixed strip takes no space of its own, so the foot of the editor
        would sit underneath it.
        """

        from utils.styles import theme_styles

        source = self.source()

        assert (
            'classList.toggle("timeline-docked", this.docked && this.shown)'
            in source
        )
        assert "body.timeline-docked .nicegui-content" in theme_styles

    def test_coming_back_reallocates_the_canvas(self):
        """
        shrinkCanvas() throws the pixels away, and draw() only allocates new
        ones when the size it measures differs from the size it remembers --
        so the remembered size has to go with them. Hiding the strip and
        showing it again gives back exactly the box it had, which matched,
        and the strip came back blank: drawn into a 0x0 backing store.
        """

        source = self.source()
        shrink = source[source.index("shrinkCanvas() {"):]
        shrink = shrink[: shrink.index("\n    },")]

        assert "canvas.width = 0;" in shrink
        assert "this.backing = null;" in shrink

    def test_a_hidden_strip_gives_the_room_back(self):
        """
        The padding is put on the body by hand, so a strip turned off while
        docked would otherwise leave a gap at the foot of the page.
        """

        source = self.source()
        watcher = source[source.index("shown(on) {"):]
        watcher = watcher[: watcher.index("\n    },")]

        assert "this.markDocked();" in watcher
        assert "if (on) this.settle();" in watcher

    def test_it_is_fixed_to_the_foot_of_the_page(self):
        from utils.styles import theme_styles

        rule = theme_styles[theme_styles.index(".speech-timeline-docked {"):]
        rule = rule[: rule.index("}")]

        assert "position: fixed" in rule
        assert "bottom: 0" in rule

    def test_docked_it_is_teleported_out_of_the_splitter(self):
        """
        Fixed positioning alone was not enough: the strip lives inside the
        splitter, whose separator is a positioned element of its own, and
        that separator drew a line straight down through it. Out at the body
        nothing can clip it, give it a containing block, or paint over it.

        Teleport keeps the component itself where it is -- same instance,
        same listeners, same state -- and only moves where it renders.
        """

        source = self.source()

        assert '<Teleport to="body" :disabled="!docked">' in source

    def test_it_starts_where_the_editor_does(self):
        """
        The menu rail down the left is fixed as well, so a strip at left: 0
        runs underneath it -- and the rail is not a fixed width: it opens
        and closes, and Quasar animates it while it does.
        """

        source = self.source()
        body = source[source.index("followTheRail() {"):]
        body = body[: body.index("\n    },")]

        assert 'document.querySelector(".q-drawer--left")' in body
        assert "Math.max(0, box.right)" in body

    def test_it_follows_the_rail_as_it_moves(self):
        source = self.source()

        assert "this.railObserver = new ResizeObserver" in source
        assert 'rail.addEventListener("transitionend", this.followTheRail)' in source
        assert 'window.addEventListener("resize", this.followTheRail)' in source

    def test_the_stylesheet_leaves_the_left_edge_alone(self):
        from utils.styles import theme_styles

        rule = theme_styles[theme_styles.index(".speech-timeline-docked {"):]
        rule = rule[: rule.index("}")]

        assert "left:" not in rule, "the component sets it"
        assert "right: 0" in rule

    def test_where_it_starts_is_remembered(self):
        page = pathlib.Path("pages/srt.py").read_text()

        assert "timeline.set_docked(" in page
        assert "TIMELINE_DOCK_KEY" in page
        assert 'timeline.on("dock", save_dock)' in page

    def test_the_server_only_says_where_it_starts(self):
        """
        The reader moves it after that, and the component owns the position
        from then on -- a prop pushed back mid-session would yank the strip
        out from under them.
        """

        source = pathlib.Path("utils/speech_timeline.py").read_text()

        assert '_props["startDocked"]' in source


class TestTheDrawLoopIsCheap:
    """
    While the recording plays the strip redraws every animation frame, so
    everything draw() does happens sixty times a second.
    """

    def source(self) -> str:
        return pathlib.Path("utils/speech_timeline.js").read_text()

    def test_the_canvas_is_resized_only_when_it_changed(self):
        """
        Assigning canvas.width throws the backing store away and allocates a
        new one. The size changes when the splitter moves, when the strip
        docks and when the window is resized -- not sixty times a second.
        """

        source = self.source()
        body = source[source.index("    draw() {"):]
        body = body[: body.index("\n    },")]

        assert "if (backing !== this.backing) {" in body
        assert body.count("canvas.width =") == 1

    def test_the_colours_are_read_once(self):
        """
        getComputedStyle can force a style recalculation, and draw() asks for
        half a dozen custom properties.
        """

        source = self.source()
        body = source[source.index("colour(name, fallback) {"):]
        body = body[: body.index("\n    },")]

        assert "getComputedStyle" not in body
        assert "this.palette[name]" in body

    def test_the_palette_is_dropped_when_it_could_have_changed(self):
        """
        Dark mode is a class on the body, and the strip moving puts it
        somewhere with a different background behind it.
        """

        source = self.source()

        assert "this.themeObserver = new MutationObserver(this.forgetPalette)" in source
        assert 'attributeFilter: ["class"]' in source
        assert "this.palette = null;" in source[source.index("onDockDrop() {"):]

    def test_only_what_is_on_screen_is_drawn(self):
        """
        An hour of speech is thousands of runs and a subtitle file thousands
        of captions; both lists are time-ordered, so the first one that
        could be visible is found by bisection rather than by walking past
        every earlier one.
        """

        source = self.source()
        body = source[source.index("    draw() {"):]
        body = body[: body.index("\n    },")]

        assert "this.within(this.runs, from, from + visible)" in body
        assert "this.visibleCaptions(from, from + visible)" in body
        assert "for (const caption of this.captions)" not in body

    def test_the_search_steps_back_over_a_long_entry(self):
        """
        The first entry reaching into the window is not necessarily the
        first that starts inside it: a long one can begin well before and
        run past.
        """

        source = self.source()
        body = source[source.index("within(entries, from, to,"):]
        body = body[: body.index("\n    },")]

        assert "while (index > 0 && read(entries[index - 1])[1] >= from)" in body

    def test_the_dragged_caption_is_drawn_wherever_it_is_going(self):
        """
        It is drawn where it would land, which can be outside the window its
        own timings still put it in.
        """

        source = self.source()
        body = source[source.index("visibleCaptions(from, to) {"):]
        body = body[: body.index("\n    },")]

        assert "this.preview" in body
        assert "shown.push(held)" in body


class TestWiring:
    """
    The strip is only offered where there is word data to draw it from, and
    its caption boundaries follow every structural edit.
    """

    def page(self) -> str:
        return pathlib.Path("pages/srt.py").read_text()

    def test_it_is_gated_on_word_timings_and_subtitles(self):
        """
        Nothing to draw without timings -- and nothing to time in a
        transcription, whose blocks are a speaker's whole turn rather than a
        short cue. The subtitle overlay is gated the same way.
        """

        page = pathlib.Path("pages/srt.py").read_text()
        gate = page[page.index('if data_format == "srt" and editor.words:'):]

        assert "SpeechTimeline()" in gate[:200]

    def test_a_structural_edit_redraws_the_captions(self):
        editor_source = pathlib.Path("utils/transcript_editor.py").read_text()
        refresh = editor_source[editor_source.index("    def refresh(self) -> None:"):]
        refresh = refresh[: refresh.index("\n    # ")]

        assert "self.refresh_timeline()" in refresh


class TestTheTimelineSwitch:
    """
    "Timeline" under the video turns the strip off.

    It went through NiceGUI's own set_visibility, which hides an element by
    putting a "hidden" class on it -- and this component's template is
    rooted in a <Teleport>, which is not a DOM node and has nothing for a
    fallthrough class to land on. The switch did nothing at all; the strip
    owns the answer itself now, through a prop.
    """

    def source(self) -> str:
        import pathlib

        return pathlib.Path("utils/speech_timeline.js").read_text()

    def page(self) -> str:
        import pathlib

        return pathlib.Path("pages/srt.py").read_text()

    def test_the_strip_takes_it_as_a_prop(self):
        source = self.source()

        assert "shown: { type: Boolean, default: true }" in source
        assert 'v-show="shown"' in source

    def test_the_switch_sets_it_rather_than_the_element_visibility(self):
        page = self.page()

        assert "timeline.set_shown(value)" in page
        assert "timeline.set_shown(editor.show_timeline)" in page
        assert "timeline.set_visibility" not in page

    def test_it_survives_a_reload(self):
        page = self.page()

        assert "app.storage.user[TIMELINE_SHOW_KEY] = value" in page
        assert "editor.show_timeline = value" in page

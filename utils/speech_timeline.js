// Copyright (c) 2025-2026 Sunet.
// Contributor: Kristofer Hallin
//
// This file is part of Sunet Scribe.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// A strip of where speech is, under the video, with the captions laid over it.
//
// Not a waveform: the runs come from the word timings the transcription
// already carries, so nothing is decoded and the recording is not fetched a
// second time. What it shows is where someone is talking, where the silences
// are, and where each caption sits against them -- which is what the reader
// is looking for when timing subtitles. What it cannot show is loudness.
//
// Two things it does beyond drawing. It shows twenty seconds at a time
// (WINDOW),
// because an hour across a pane this wide is roughly a minute per pixel and
// no caption edge can be seen there, let alone aimed at; the view follows
// the playhead through the recording. And a caption can be dragged -- by an
// edge to move that edge, by the middle to move the whole cue -- which is
// reported to the server as one retime and so one undo step. Dragging where
// there is no caption makes one covering exactly that stretch, which is the
// same gesture meaning the same thing on empty ground: the strip is where a
// reader can see that nothing covers a passage of speech, so it is where
// they should be able to say that something now does.
//
// Docked, the strip is teleported to the body rather than left where it sits
// in the page. Fixed positioning alone was not enough: it lives inside the
// splitter, whose separator is a positioned element of its own, and that
// separator drew a line straight down through the strip. Out at the body it
// answers to nothing but its own z-index, and no ancestor can clip it, give
// it a containing block, or paint over it.
//
// The playhead follows the video element directly rather than being pushed a
// position from the server: timeupdate fires several times a second, and a
// round trip per tick to move a line two pixels is not worth taking. Seeking
// sets the same element's currentTime for the same reason.

// How close to an edge the pointer has to be, in pixels, to take hold of it
// rather than the caption as a whole.
const EDGE_GRIP = 6;

// How close a dragged edge has to come to the start or end of a run of speech
// to snap to it, in pixels. Subtitles are cut against speech, not against
// arbitrary tenths of a second, and hitting a word boundary by hand at this
// scale is luck.
const SNAP = 8;

// The same, for the edge of another caption -- with a wider reach, and taken
// first when both are in range. Two cues meeting exactly is a thing a reader
// means; a cue landing a hundredth of a second short of its neighbour, so
// that a gap no viewer can perceive sits between them, never is.
const CAPTION_SNAP = 14;

// Seconds across the strip at the default zoom. This is the scale at which a
// caption edge can be seen and aimed at, and it is where the strip starts and
// where "Reset zoom" brings it back: zooming is offered (SUNET/scribe-ui#134)
// for the work that wants more precision or more context, as a step the reader
// takes, never something that changes underfoot. Within the 10-30s the issue
// asks for (SUNET/scribe-ui#126).
const WINDOW = 20;

// The same, docked along the foot of the page. It is three or four times as
// wide there, so it can hold three times as long without the scale changing
// at all -- the same seconds per pixel, more of them.
const DOCKED_WINDOW = 60;

// How far down the window the grip has to be let go for the strip to dock.
const DOCK_AT = 0.7;

// How far the strip can be zoomed, as a factor of the window above: 2 shows
// half as many seconds across the same width. Each step doubles or halves, so
// there are five levels -- a quarter to four times -- and the default is one
// of them rather than somewhere between two. Not remembered between visits:
// it is a way of looking at one recording, not a preference.
const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 2;

// The keyboard moves the playhead by a share of what is on the strip, so the
// step follows the zoom: a fine step when zoomed in to aim at an edge, a wide
// one when zoomed out to find one. An arrow key is a fortieth of the strip
// (half a second at the default), Page Up and Page Down a whole strip.
const STEP_SMALL = 1 / 40;
const STEP_PAGE = 1;

// The ruler along the top edge: a band this tall (px), above everything else
// on the strip. Fixed rather than a share of the height, since the numbers in
// it are drawn at a fixed size; the strip is this much taller than the rest of
// it needs (see .speech-timeline in styles.py).
const RULER = 16;

// What the ruler can count in, as [a labelled tick every, a small tick every]
// seconds. The coarsest of these that still leaves LABEL_GAP pixels between
// two labels is used, so zooming in and out changes the unit by itself, and
// a small tick is left out when it would be closer than MINOR_GAP pixels.
const RULER_STEPS = [
  [0.1, 0.05],
  [0.2, 0.05],
  [0.5, 0.1],
  [1, 0.5],
  [2, 0.5],
  [5, 1],
  [10, 2],
  [15, 5],
  [30, 5],
  [60, 10],
  [120, 30],
  [300, 60],
  [600, 120],
  [1800, 300],
  [3600, 600],
  [7200, 1800],
];
const LABEL_GAP = 64;
const MINOR_GAP = 7;

// How long after a sideways wheel event the next ones still count as
// sideways, in milliseconds. See onWheel.
const SWIPE_LATCH = 200;

// Pinching over the strip zooms it. How much one unit of the gesture is
// worth: the zoom is multiplied by exp(-deltaY * PINCH_SPEED), so spreading
// the fingers (a negative deltaY) zooms in and pinching them together zooms
// out, smoothly and by the same share every time.
const PINCH_SPEED = 0.01;

// A mouse wheel with Ctrl held reports a hundred or so at a notch, where a
// pinch reports a few at a time. Capped so a notch is a firm step (about
// one and a half times) and not a leap.
const PINCH_MAX = 40;

// How long the zoom has to stand still before the status region says what
// the strip now shows, in milliseconds. A pinch changes it many times a
// second, and a screen reader that said every value would say nothing else.
const PINCH_SETTLE = 500;

// The id a caption being dragged out of empty strip is drawn under. It has
// no number of its own until the server has made it one -- a caption's
// number is its position among the others -- and no real caption is ever 0,
// since renumber_captions counts from 1.
const NEW_CAPTION = 0;

// The shortest new caption a drag can make. Below this the gesture was a
// click that happened to travel a pixel or two, not an attempt to cover
// anything, and a caption too short to see is worse than none.
const MIN_NEW_SECONDS = 0.05;

export default {
  template: `
    <Teleport to="body" :disabled="!docked">
    <div
      class="speech-timeline-wrap"
      ref="wrap"
      v-show="shown"
      :class="{
        'speech-timeline-docked': docked,
        'speech-timeline-lifting': dockDrag !== null,
      }"
      :style="docked ? { left: dockLeft + 'px' } : null"
    >
      <div
        class="speech-timeline"
        ref="root"
        role="slider"
        tabindex="0"
        aria-label="Playhead position"
        aria-orientation="horizontal"
        aria-valuemin="0"
        aria-describedby="speech-timeline-keys"
        :aria-valuemax="ariaMax()"
        :aria-valuenow="ariaNow()"
        :aria-valuetext="ariaText"
        :class="{ 'speech-timeline-dragging': drag !== null }"
        @mouseenter="holdSwipe"
        @mousemove="onMove"
        @mouseleave="onLeave"
        @mousedown="onDown"
        @focus="syncAria(true)"
        @keydown="onKey"
        @wheel="onWheel"
        @gesturestart="onGesture"
        @gesturechange="onGesture"
        @gestureend="onGesture"
      >
        <canvas ref="canvas" @click="onClick"></canvas>
        <div
          v-if="readout"
          class="speech-timeline-readout"
          :style="{ left: readoutLeft }"
        >{{ readout }}</div>
      </div>
      <div class="speech-timeline-legend">
        <div class="speech-timeline-keyrow">
          <span
            class="speech-timeline-grip"
            :title="docked
              ? 'Drag up to put the timeline back under the video'
              : 'Drag to the bottom of the page to widen the timeline'"
            @mousedown="startDockDrag"
          >⠿</span>
          <span class="speech-timeline-key">
            <span class="speech-timeline-swatch speech-timeline-swatch-speech"></span>
            Speech
          </span>
          <span class="speech-timeline-key">
            <span class="speech-timeline-swatch speech-timeline-swatch-silence"></span>
            Silence
          </span>
          <span class="speech-timeline-key">
            <span class="speech-timeline-swatch speech-timeline-swatch-caption"></span>
            Caption
          </span>
          <span class="speech-timeline-key">
            <span class="speech-timeline-swatch speech-timeline-swatch-playhead"></span>
            Playhead
          </span>
        </div>
        <div
          class="speech-timeline-actions"
          ref="actions"
          role="toolbar"
          aria-label="Timeline controls"
        >
          <template v-for="(action, index) in actions()" :key="action.key">
            <span
              v-if="action.gap"
              class="speech-timeline-actions-gap"
              aria-hidden="true"
            ></span>
            <button
              type="button"
              class="speech-timeline-action"
              :class="{
                'speech-timeline-action-off': action.off,
                'speech-timeline-action-on': action.pressed,
              }"
              :data-key="action.key"
              :aria-label="action.label"
              :aria-disabled="action.off ? 'true' : null"
              :aria-pressed="action.pressed === undefined ? null : String(action.pressed)"
              :tabindex="index === pillStop ? 0 : -1"
              @focus="pillStop = index"
              @keydown="onActionKey($event, index)"
              @click="action.run()"
            ><q-icon :name="action.icon" size="16px" /><q-tooltip>{{ action.tip }}</q-tooltip></button>
          </template>
        </div>
        <span class="speech-timeline-hint">
          Click a caption to go to it · drag it, or one of its brackets, to
          retime · drag across empty space to add a caption
        </span>
      </div>
      <span id="speech-timeline-keys" class="sr-only">
        Left and right arrow keys move the playhead a little, Page Up and Page
        Down a whole strip, Home and End to the start and the end of the
        recording. Shift with the up and down arrow keys, or plus and minus,
        zoom, and 0 resets the zoom. Pinching on a trackpad over the strip
        zooms it too.
      </span>
      <span class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ note }}</span>
    </div>
    </Teleport>
    <div
      v-if="ghost === 'rest'"
      class="speech-timeline-ghost speech-timeline-ghost-rest"
      aria-hidden="true"
      :style="{ height: restHeight + 'px' }"
    >Release to dock Timeline here</div>
    <Teleport to="body">
      <div
        v-if="ghost === 'foot'"
        class="speech-timeline-ghost speech-timeline-ghost-foot"
        aria-hidden="true"
        :style="{ left: dockLeft + 'px' }"
      >Release to dock Timeline here</div>
    </Teleport>
  `,
  props: {
    // [[start, end], ...] in seconds -- where someone is talking.
    runs: { type: Array, default: () => [] },
    // [{ id, start, end }, ...] -- the captions themselves, drawn as a band
    // under the speech and draggable.
    captions: { type: Array, default: () => [] },
    duration: { type: Number, default: 0 },
    // The caption the text editor is on. Sent from the server, because that
    // is where "which caption is being edited" is known -- this is a second
    // view of the captions, not the owner of them.
    currentId: { type: Number, default: -1 },
    // Whether the strip starts along the foot of the page rather than under
    // the video. A saved preference, so it is the server that knows it.
    startDocked: { type: Boolean, default: false },
    // Whether the strip is on at all -- the "Timeline" switch under the
    // video. A prop rather than NiceGUI's own set_visibility: that hides an
    // element by putting a "hidden" class on it, and this component's
    // template is rooted in a <Teleport>, which is not a DOM node and so has
    // nothing for a fallthrough class to land on. The switch did nothing at
    // all until this existed.
    //
    // v-show, not v-if: the canvas and the listeners mounted() set up stay
    // where they are, so coming back is a redraw rather than a rebuild.
    shown: { type: Boolean, default: true },
  },
  emits: ["retimespan", "createcaption", "createatplayhead", "selectcaption", "dock"],
  data() {
    return {
      position: 0,
      // Along the foot of the page, the full width of the editor, rather
      // than under the video.
      docked: false,
      // Where the editor starts, horizontally: the menu rail down the left
      // is fixed too, and a strip starting at 0 runs underneath it.
      dockLeft: 0,
      // Where the grip is while it is being dragged, and whether letting go
      // there would dock -- so the reader can see the answer before
      // committing to it.
      dockDrag: null,
      // How tall the strip and its legend are where it sits under the video,
      // for the placeholder that shows where it will land when it is on its
      // way back there from the foot of the page -- see ghost. Measured as
      // it leaves; this is what stands in for a page that opened docked, and
      // is what they measured at the default text size, 180 px.
      restHeight: 180,
      // The caption under the pointer. Distinct from the caption being
      // played and from the one being edited: hovering one here must not
      // take the text editor's focus off another.
      hovered: -1,
      // { id, edge, grabbed, start, end } while a caption is being dragged.
      drag: null,
      // { anchor, gap, start, end } while a new caption is being dragged out
      // of a stretch the captions do not cover. Separate from `drag`, which
      // is a caption that already exists being moved: this one has no id to
      // move, cannot leave the gap it was started in, and is reported as a
      // different thing entirely.
      creating: null,
      // Set by a drag, cleared on the next click: a click event follows a
      // mouseup even when the pointer travelled, and seeking to wherever a
      // drag ended is never what was meant.
      dragged: false,
      readout: "",
      readoutLeft: "0px",
      // How far the strip is zoomed: 1 is the default window, 2 half as many
      // seconds across, 0.5 twice as many. See ZOOM_MIN and ZOOM_MAX.
      zoom: 1,
      // The playhead position the slider reports to assistive technology.
      // Kept apart from `position`, which moves every frame while the
      // recording plays: a screen reader told about every frame says nothing
      // else. It follows the playhead when the reader moves it, when the
      // recording stops or lands somewhere, and when the strip takes focus.
      ariaPosition: 0,
      // What the status region says: the new zoom, the new place.
      note: "",
      // Where a requested move is waiting for the next frame, so that a
      // wheel turned fast makes one seek per frame and not one per event.
      seekPending: null,
      seekFrame: null,
      // Until when wheel events count as sideways whatever they say.
      swipeUntil: 0,
      // The zoom a Safari pinch started from (see onGesture), and the wait
      // before the new zoom is said (see sayZoomSoon).
      gestureFrom: 1,
      zoomNoteTimer: null,
      // Which of the controls beside the strip is in the tab order. One of
      // them at a time, with the arrow keys moving between them, as in the
      // caption actions.
      pillStop: 0,
      video: null,
      observer: null,
      railObserver: null,
      themeObserver: null,
      frame: null,
      // The canvas's backing size, as "widthxheightxratio" -- see draw().
      backing: null,
      // The custom properties draw() paints with, read once -- see colour().
      palette: null,
    };
  },
  watch: {
    runs() {
      this.draw();
    },
    captions() {
      this.draw();
    },
    currentId() {
      this.draw();
    },
    shown(on) {
      // A strip that is hidden gets no mouseleave.
      if (!on) this.releaseSwipe();

      // A hidden strip must not keep the page padded out of its way, and a
      // strip coming back has been display: none -- so it has no size to
      // have measured itself against, and settle() is what waits for the
      // browser to give it one.
      this.markDocked();

      if (on) this.settle();
    },
    duration() {
      this.draw();
    },
  },
  mounted() {
    // The player is a sibling somewhere on the page, not a child of this
    // component, so it is found rather than passed in.
    this.video = document.querySelector("video");

    if (this.video) {
      this.video.addEventListener("timeupdate", this.follow);
      this.video.addEventListener("seeked", this.follow);
      this.video.addEventListener("play", this.animate);
      this.video.addEventListener("pause", this.stop);
      this.video.addEventListener("pause", this.rest);
      this.video.addEventListener("seeked", this.rest);
    }

    // A drag continues wherever the pointer goes, including off the strip
    // and out of the window, and ends wherever it is let go.
    window.addEventListener("mousemove", this.onDragMove);
    window.addEventListener("mouseup", this.onUp);
    window.addEventListener("mousemove", this.onDockDragMove);
    window.addEventListener("mouseup", this.onDockDrop);

    this.docked = this.startDocked;
    this.markDocked();

    // The strip is drawn at the size it actually has, which the splitter can
    // change at any time.
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe(this.$refs.root);
    // The wrapper too: it is what moves when the strip docks, and it can
    // change size in ways the strip inside it does not report on its own.
    if (this.$refs.root.parentElement) {
      this.observer.observe(this.$refs.root.parentElement);
    }

    // The menu rail opens and closes, and a docked strip has to start where
    // it ends. Watched rather than measured once, and read again after the
    // animation Quasar runs while it moves.
    const rail = document.querySelector(".q-drawer--left");

    if (rail) {
      this.railObserver = new ResizeObserver(() => this.followTheRail());
      this.railObserver.observe(rail);
      rail.addEventListener("transitionend", this.followTheRail);
    }

    window.addEventListener("resize", this.followTheRail);

    // Light and dark are a class on the body, and every colour the strip
    // paints with changes with it.
    this.themeObserver = new MutationObserver(this.forgetPalette);
    this.themeObserver.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
    });

    this.draw();
  },
  beforeUnmount() {
    this.stop();

    if (this.video) {
      this.video.removeEventListener("timeupdate", this.follow);
      this.video.removeEventListener("seeked", this.follow);
      this.video.removeEventListener("play", this.animate);
      this.video.removeEventListener("pause", this.stop);
      this.video.removeEventListener("pause", this.rest);
      this.video.removeEventListener("seeked", this.rest);
    }

    if (this.seekFrame) cancelAnimationFrame(this.seekFrame);

    clearTimeout(this.zoomNoteTimer);

    this.releaseSwipe();

    window.removeEventListener("mousemove", this.onDragMove);
    window.removeEventListener("mouseup", this.onUp);
    window.removeEventListener("mousemove", this.onDockDragMove);
    window.removeEventListener("mouseup", this.onDockDrop);

    document.body.classList.remove("timeline-docked");

    if (this.observer) this.observer.disconnect();
    if (this.railObserver) this.railObserver.disconnect();
    if (this.themeObserver) this.themeObserver.disconnect();

    const rail = document.querySelector(".q-drawer--left");
    if (rail) rail.removeEventListener("transitionend", this.followTheRail);

    window.removeEventListener("resize", this.followTheRail);
  },
  computed: {
    // Where the strip would land if it were let go now, when that is not
    // where it is: "foot" along the bottom of the window, "rest" back under
    // the video, null when there is nothing to show (not being moved, or the
    // pointer is over the place it is already in).
    ghost() {
      if (!this.dockDrag || this.dockDrag.willDock === this.docked) return null;

      return this.dockDrag.willDock ? "foot" : "rest";
    },

    // The caption being played. Worked out here rather than sent: it follows
    // from the position, which this component already has, and pushing it
    // from the server would be a round trip several times a second.
    playingId() {
      const found = this.captions.find(
        (caption) =>
          this.position >= caption.start && this.position < caption.end
      );

      return found ? found.id : -1;
    },
    // What the slider says its value is, in words rather than a number of
    // seconds: where in the recording, and which caption that is in.
    ariaText() {
      const span = this.span();
      if (!span) return "";

      const at = this.ariaPosition;
      const caption = this.captions.find(
        (entry) => at >= entry.start && at < entry.end
      );

      return (
        `${this.moment(at)} of ${this.clock(span)}, ` +
        (caption ? `in caption ${caption.id}` : "no caption here")
      );
    },
  },
  methods: {
    // ── the recording, and the part of it on screen ────────────────────────

    span() {
      // The video's own duration once it is known -- the word timings stop
      // at the last thing said, and a recording usually runs on past that.
      const known =
        this.video && isFinite(this.video.duration) ? this.video.duration : 0;

      return Math.max(known, this.duration, 0);
    },

    // Seconds across the strip: twenty under the video, a minute docked
    // along the foot of the page, divided by the zoom. The docked strip is
    // several times as wide, so it holds the longer window at much the same
    // seconds per pixel, which is the thing that actually decides whether an
    // edge can be seen and aimed at -- and the zoom is a factor of whichever
    // of the two applies, so "Reset zoom" is always that. A recording shorter
    // than the window simply shows all of itself.
    visible() {
      const window = (this.docked ? DOCKED_WINDOW : WINDOW) / this.zoom;

      return Math.min(window, this.span()) || this.span();
    },

    // Left edge of the view. The playhead is fixed in the centre and the
    // recording scrolls behind it -- deliberately not clamped at the ends,
    // which would slide the playhead off centre exactly where the reader
    // works most (the first and last captions). Before the recording starts
    // and after it ends there is nothing to draw, which draw() shades.
    viewStart() {
      return this.position - this.visible() / 2;
    },

    // ── reading the strip ──────────────────────────────────────────────────

    secondsAt(clientX) {
      const box = this.$refs.root.getBoundingClientRect();
      const offset = Math.max(0, Math.min(box.width, clientX - box.left));

      return this.viewStart() + (offset / box.width) * this.visible();
    },

    pixelsPerSecond() {
      const box = this.$refs.root.getBoundingClientRect();
      const visible = this.visible();

      return visible ? box.width / visible : 0;
    },

    // The caption under a point, and which part of it: the nearest edge
    // within EDGE_GRIP, otherwise the body of a caption the point is inside.
    //
    // The nearest edge of any caption, deliberately -- not the first caption
    // in the list that happens to be in range, which is what this used to
    // ask. Two cues close together both answer to a point between them, and
    // taking whichever came first meant reaching for one caption's end and
    // getting the next one's start. It also meant a caption shorter than the
    // grip could only ever be taken by its start, since that check came
    // first and both edges were in range.
    //
    // A tie is broken by which side of the edge the pointer is on, and so
    // by which caption it is nearer the middle of. Where one cue ends at
    // exactly the instant the next begins the two edges are the same
    // instant: approaching from the left takes the first cue's end, from
    // the right the second cue's start. Any fixed preference makes one of
    // the two unreachable, which is what a reader hit when trying to move
    // the start of a caption butted against its neighbour.
    captionAt(seconds) {
      const grip = EDGE_GRIP / (this.pixelsPerSecond() || 1);

      let closest = null;
      let distance = grip;
      // Whether the caption itself lies on the pointer's side of the edge:
      // a caption's body is to the left of its end and to the right of its
      // start.
      let facing = false;

      for (const caption of this.captions) {
        for (const edge of ["end", "start"]) {
          const away = Math.abs(seconds - caption[edge]);

          if (away > distance) continue;

          const towards =
            edge === "end" ? seconds <= caption.end : seconds >= caption.start;

          // Nearer wins outright; equally near, the caption the pointer is
          // approaching from wins, and only then does the order of this
          // loop decide anything.
          if (away < distance || (towards && !facing)) {
            closest = { caption, edge };
            distance = away;
            facing = towards;
          }
        }
      }

      if (closest) return closest;

      for (const caption of this.captions) {
        if (seconds >= caption.start && seconds <= caption.end) {
          return { caption, edge: "body" };
        }
      }

      return null;
    },

    // The stretch around a moment that no caption covers -- what a new one
    // dragged out from there is allowed to fill.
    //
    // A new caption is kept inside it rather than left to overlap: two cues
    // covering the same instant is one of the things "Validate" reports as
    // an error, and a gesture on the strip should not be able to make one
    // by accident. Null when the moment is inside a caption after all, or
    // when there is no room at all around it.
    gapAt(seconds) {
      const span = this.span();

      let from = 0;
      let to = span;

      for (const caption of this.captions) {
        if (seconds > caption.start && seconds < caption.end) return null;

        if (caption.end <= seconds) from = Math.max(from, caption.end);
        if (caption.start >= seconds) to = Math.min(to, caption.start);
      }

      return to > from ? { from, to } : null;
    },

    // ── moving the strip itself ───────────────────────────────────────────

    // A grip of its own, not the strip: dragging the strip already means
    // taking hold of a caption, and one gesture cannot mean two things.
    startDockDrag(event) {
      event.preventDefault();
      this.followTheRail();
      this.dockDrag = { willDock: this.docked };
      this.onDockDragMove(event);
    },

    onDockDragMove(event) {
      if (!this.dockDrag) return;

      // Far enough down the window to be asking for the foot of it.
      this.dockDrag = {
        willDock: event.clientY > window.innerHeight * DOCK_AT,
      };
    },

    onDockDrop() {
      if (!this.dockDrag) return;

      const willDock = this.dockDrag.willDock;
      this.dockDrag = null;

      this.setDocked(willDock);
    },

    setDocked(willDock) {
      if (willDock === this.docked) return;

      this.noteRestHeight();
      this.docked = willDock;
      this.palette = null;
      this.markDocked();
      this.$emit("dock", { docked: willDock });

      // A different width, and a different window across it.
      this.settle();
    },

    // How much room the strip and its legend take where they sit under the
    // video, for the placeholder that shows it where it is on its way back
    // to. Only while they are there -- docked, they are somewhere else and a
    // different width -- so it is noted as it leaves, by the drop and by the
    // button alike.
    noteRestHeight() {
      const wrap = this.$refs.wrap;

      if (this.docked || !wrap || !wrap.offsetHeight) return;

      this.restHeight = wrap.offsetHeight;
    },

    // The same move as the grip, for whoever cannot drag. Docking teleports
    // the strip to the body, which moves the nodes in it, and a node that is
    // moved loses focus -- so focus is put back on the button once the move
    // has happened, or a keyboard user would find themselves at the top of
    // the page every time they pressed it.
    toggleDock() {
      this.setDocked(!this.docked);
      this.note = this.docked
        ? "Timeline docked along the bottom of the page"
        : "Timeline back under the video";

      this.$nextTick(() => this.focusAction("dock"));
    },

    // Redraw once the page has settled into its new shape.
    //
    // One redraw on the next tick is not enough: moving the strip teleports
    // it, changes the padding the page keeps for it and moves the splitter
    // under it, and the box it ends up with is not known until the browser
    // has laid all of that out. Drawn too early the canvas keeps its old
    // backing size and the strip comes back stretched -- the frames below
    // are cheap, and the last one covers a transition finishing after them.
    settle() {
      // Let go of the old backing store first. A canvas is as wide as its
      // own pixels unless something stops it, so on the way back from the
      // foot of the page the strip measured itself against a box its own
      // canvas was holding open -- and came back the width it had been
      // docked at, with nothing drawn on it.
      this.shrinkCanvas();

      this.$nextTick(() => {
        this.followTheRail();
        this.draw();

        requestAnimationFrame(() => {
          this.followTheRail();
          this.draw();
        });

        setTimeout(() => {
          this.followTheRail();
          this.draw();
        }, 250);
      });
    },

    // Back to nothing, so the element around it can be measured for what it
    // is rather than for what the canvas used to be. draw() sizes it again
    // from the box it finds.
    shrinkCanvas() {
      const canvas = this.$refs.canvas;

      if (!canvas) return;

      canvas.width = 0;
      canvas.height = 0;
      canvas.style.width = "100%";
      canvas.style.height = "100%";

      // draw() only reallocates the backing store when the size string it
      // works out differs from this one -- so the remembered size has to go
      // with the pixels. Hiding the strip and showing it again gives back
      // exactly the box it had, which matched, so draw() kept the 0x0
      // backing store this just left and painted the strip into nothing.
      this.backing = null;
    },

    // The page has to leave room for a strip fixed along its foot, and the
    // page is not this component's to style -- so it is told, and takes the
    // room in its own stylesheet.
    markDocked() {
      // Only while it is actually on screen: a fixed strip takes no space of
      // its own, so the page is padded out of its way by hand, and a hidden
      // one would leave that padding as a gap at the foot of the page.
      document.body.classList.toggle("timeline-docked", this.docked && this.shown);
      this.followTheRail();
    },

    // Start where the editor starts, not where the window does. The menu
    // rail down the left is fixed as well, so a strip at left: 0 runs
    // underneath it -- and the rail is not a fixed width: it opens and
    // closes, and Quasar animates it while it does.
    followTheRail() {
      const rail = document.querySelector(".q-drawer--left");
      const box = rail ? rail.getBoundingClientRect() : null;

      this.dockLeft = box ? Math.max(0, box.right) : 0;
    },

    // ── pointer ───────────────────────────────────────────────────────────

    onMove(event) {
      // A gesture in flight owns the readout and the cursor; the strip's own
      // mousemove still fires alongside the window one that is driving it.
      if (this.drag || this.creating) return;

      const span = this.span();

      if (!span) {
        this.readout = "";
        return;
      }

      const seconds = this.secondsAt(event.clientX);
      const found = this.captionAt(seconds);
      const speaking = this.runs.some(
        ([start, end]) => seconds >= start && seconds <= end
      );

      // Hovering a caption here says nothing about which caption is being
      // edited -- the text editor keeps its own focus, and this state only
      // decides what the strip draws and what a click would take hold of.
      this.hovered = found ? found.caption.id : -1;

      const part = found
        ? found.edge === "body"
          ? `caption #${found.caption.id}`
          : `caption #${found.caption.id} ${found.edge}`
        : null;

      this.readout =
        `${this.moment(seconds)} · ${speaking ? "speech" : "silence"}` +
        (part ? ` · ${part}` : "");

      const box = this.$refs.root.getBoundingClientRect();
      this.readoutLeft = `${event.clientX - box.left}px`;

      // The pointer says what letting go here would do.
      this.$refs.root.style.cursor = found
        ? found.edge === "body"
          ? "grab"
          : "ew-resize"
        : this.gapAt(seconds)
        ? "crosshair"
        : "pointer";
    },

    onLeave() {
      this.releaseSwipe();

      if (this.drag || this.creating) return;

      this.readout = "";
      this.hovered = -1;
      this.draw();
    },

    onDown(event) {
      const seconds = this.secondsAt(event.clientX);
      const found = this.captionAt(seconds);

      // Nothing there to take hold of: the same gesture starts a caption
      // covering whatever is dragged over instead.
      if (!found) {
        this.startCreate(event, seconds);
        return;
      }

      // Or the browser starts a text selection across the page instead.
      event.preventDefault();

      this.drag = {
        id: found.caption.id,
        edge: found.edge,
        grabbed: this.secondsAt(event.clientX),
        start: found.caption.start,
        end: found.caption.end,
      };
      this.dragged = false;
    },

    onDragMove(event) {
      if (this.creating) {
        this.onCreateMove(event);
        return;
      }

      if (!this.drag) return;

      const moved = this.secondsAt(event.clientX) - this.drag.grabbed;

      if (Math.abs(moved) * this.pixelsPerSecond() > 2) this.dragged = true;

      const span = this.span();
      let { start, end } = this.drag;

      if (this.drag.edge === "start") {
        // Never past its own end: a caption that ends before it starts is
        // refused by the server anyway, so it is not offered here.
        start = Math.min(this.snap(start + moved, this.drag.id), end - 0.05);
      } else if (this.drag.edge === "end") {
        end = Math.max(this.snap(end + moved, this.drag.id), start + 0.05);
      } else {
        const length = end - start;
        start = Math.max(
          0,
          Math.min(span - length, this.snap(start + moved, this.drag.id))
        );
        end = start + length;
      }

      this.preview = { id: this.drag.id, start, end };
      this.readout =
        `#${this.drag.id} · ${this.timecode(start)} → ${this.timecode(end)}`;

      const box = this.$refs.root.getBoundingClientRect();
      this.readoutLeft = `${event.clientX - box.left}px`;

      this.draw();
    },

    onUp() {
      if (this.creating) {
        this.finishCreate();
        return;
      }

      if (!this.drag) return;

      const preview = this.preview;
      const moved = this.dragged;

      this.drag = null;
      this.preview = null;
      this.readout = "";
      this.$refs.root.style.cursor = "";

      if (!moved || !preview) {
        this.draw();
        return;
      }

      // One event carrying both ends, so the server applies them together
      // and the whole drag is one undo step.
      this.$emit("retimespan", {
        id: preview.id,
        start: preview.start,
        end: preview.end,
      });
    },

    // ── making a caption ──────────────────────────────────────────────────

    // Pressing down where no caption is: the start of a new one.
    //
    // Both ends are snapped exactly as a dragged edge is, so a caption
    // pulled out beside an existing one meets it flush, and one pulled over
    // a phrase lands on the ends of the speech rather than a hair inside
    // them.
    startCreate(event, seconds) {
      const gap = this.gapAt(seconds);

      if (!this.span() || !gap) return;

      // Or the browser starts a text selection across the page instead.
      event.preventDefault();

      const anchor = this.withinGap(this.snap(seconds, null), gap);

      this.creating = { anchor, gap, start: anchor, end: anchor };
      this.dragged = false;
    },

    onCreateMove(event) {
      const { anchor, gap } = this.creating;
      const to = this.withinGap(
        this.snap(this.secondsAt(event.clientX), null),
        gap
      );

      const start = Math.min(anchor, to);
      const end = Math.max(anchor, to);

      if ((end - start) * this.pixelsPerSecond() > 2) this.dragged = true;

      this.creating = { ...this.creating, start, end };
      this.readout =
        `New caption · ${this.timecode(start)} → ${this.timecode(end)}`;

      const box = this.$refs.root.getBoundingClientRect();
      this.readoutLeft = `${event.clientX - box.left}px`;

      this.draw();
    },

    finishCreate() {
      const made = this.creating;

      this.creating = null;
      this.readout = "";
      this.$refs.root.style.cursor = "";

      // Barely moved: that was a click on empty strip, which means the
      // moment rather than a caption, and onClick is left to seek to it.
      if (!this.dragged || made.end - made.start < MIN_NEW_SECONDS) {
        this.draw();
        return;
      }

      this.$emit("createcaption", { start: made.start, end: made.end });
    },

    // The button under the strip: a caption where the playhead is, for a
    // reader who cannot, or would rather not, drag one out. The same thing
    // the drag makes, with the same answer to "how long" -- except that this
    // gesture names a moment rather than a stretch, so the server works out
    // the stretch (see create_at_playhead). The moment is read from the
    // player, not from `position`, which lags it by a frame or two.
    addAtPlayhead() {
      const at = this.video ? this.video.currentTime : this.position;

      // The recording's own length, when the player knows it: not the
      // `duration` prop, which is how far the speech goes. Nothing is made
      // past the end of the recording.
      const limit =
        this.video && isFinite(this.video.duration) ? this.video.duration : 0;

      this.$emit("createatplayhead", { at, limit });
    },

    // Kept inside the stretch the captions leave free -- see gapAt.
    withinGap(seconds, gap) {
      return Math.max(gap.from, Math.min(gap.to, seconds));
    },

    onClick(event) {
      // A click follows the mouseup that ended a drag; seeking to wherever
      // the drag finished is never what was meant.
      if (this.dragged) {
        this.dragged = false;
        return;
      }

      if (!this.span()) return;

      const seconds = this.secondsAt(event.clientX);
      const found = this.captionAt(seconds);

      // Clicking a caption is asking for that caption -- the text editor
      // moves to it and the recording follows. Clicking the strip itself is
      // asking for that moment, and nothing else changes.
      if (found) {
        this.$emit("selectcaption", { id: found.caption.id });
        return;
      }

      if (!this.video) return;

      this.video.currentTime = Math.max(0, Math.min(this.span(), seconds));
    },

    // Where a dragged edge actually lands.
    //
    // The edges of the other captions first, and from further away than
    // anything else: two cues meeting exactly is something a reader means,
    // and a cue landing a hundredth of a second from its neighbour -- a gap
    // no viewer can perceive, but a gap in the file -- never is. Only if no
    // caption is in reach does it fall back to the edges of a run of
    // speech, which is where a cut belongs when it is not against another
    // cue. Failing both, the position the pointer is actually at.
    snap(seconds, movingId) {
      const perSecond = this.pixelsPerSecond() || 1;

      const captionEdge = this.nearest(
        seconds,
        this.captions
          .filter((caption) => caption.id !== movingId)
          .flatMap((caption) => [caption.start, caption.end]),
        CAPTION_SNAP / perSecond
      );

      if (captionEdge !== null) return Math.max(0, captionEdge);

      const speechEdge = this.nearest(
        seconds,
        this.runs.flat(),
        SNAP / perSecond
      );

      return Math.max(0, speechEdge === null ? seconds : speechEdge);
    },

    // The slice of a time-ordered list that overlaps a window.
    //
    // Bisection for the first candidate, then a walk until they stop
    // overlapping: the lists are ordered by start, so once one begins after
    // the window ends, so does everything after it. Entries are [start,
    // end] pairs (the speech runs) or objects (the captions); `read` says
    // which. The first entry that reaches into the window is not
    // necessarily the first that starts inside it -- a long one can begin
    // well before and run past -- so the search steps back over anything
    // still overlapping.
    within(entries, from, to, read = (entry) => entry) {
      const found = [];

      if (!entries.length) return found;

      let low = 0;
      let high = entries.length;

      while (low < high) {
        const middle = (low + high) >> 1;

        if (read(entries[middle])[0] < from) low = middle + 1;
        else high = middle;
      }

      let index = low;

      while (index > 0 && read(entries[index - 1])[1] >= from) index -= 1;

      for (; index < entries.length; index += 1) {
        const [start, end] = read(entries[index]);

        if (start > to) break;
        if (end >= from) found.push(entries[index]);
      }

      return found;
    },

    visibleCaptions(from, to) {
      const shown = this.within(
        this.captions,
        from,
        to,
        (caption) => [caption.start, caption.end]
      );

      // The one being dragged is drawn where it would land, which can be
      // outside the window its own timings still put it in.
      const dragging = this.preview;

      if (dragging && !shown.some((caption) => caption.id === dragging.id)) {
        const held = this.captions.find((caption) => caption.id === dragging.id);

        if (held) shown.push(held);
      }

      // A caption being dragged out of empty strip is not in the list at
      // all -- it exists only as the gesture until the server has made it
      // one -- so it is added here to be drawn like any other.
      if (this.creating && this.dragged) {
        shown.push({
          id: NEW_CAPTION,
          start: this.creating.start,
          end: this.creating.end,
        });
      }

      return shown;
    },

    // The closest of a set of times, if any of them is within reach.
    nearest(seconds, candidates, reach) {
      let best = null;
      let distance = reach;

      for (const candidate of candidates) {
        const away = Math.abs(candidate - seconds);

        if (away < distance) {
          best = candidate;
          distance = away;
        }
      }

      return best;
    },

    // The same shape the timecode fields in the text editor use, so a drag
    // and a typed value are read the same way.
    timecode(seconds) {
      const whole = Math.max(0, seconds);
      const minutes = Math.floor(whole / 60);
      const rest = whole - minutes * 60;

      return `${String(minutes).padStart(2, "0")}:${rest.toFixed(3).padStart(6, "0")}`;
    },

    // A moment being pointed at, to a tenth. Twenty seconds across the
    // strip is around a fiftieth of a second per pixel, so a whole second
    // covers fifty of them: the readout said the same thing for a stretch
    // wide enough to hold a short word.
    moment(seconds) {
      const whole = Math.max(0, seconds);
      const minutes = Math.floor(whole / 60);
      const rest = whole - minutes * 60;

      return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
    },

    // Whole seconds, for the stretch of recording on screen -- a tenth of a
    // second says nothing about a twenty-second window.
    clock(seconds) {
      const whole = Math.max(0, Math.floor(seconds));
      const minutes = Math.floor(whole / 60);
      const rest = whole % 60;

      return `${minutes}:${String(rest).padStart(2, "0")}`;
    },

    // ── the ruler ──────────────────────────────────────────────────────────

    // The ticks to draw between two moments, for a strip `pixels` wide showing
    // `visible` seconds: { step, major: [seconds], minor: [seconds] }, all
    // inside the recording. Counted in whole multiples of the step rather
    // than by adding it up, so a tenth of a second does not drift.
    rulerTicks(from, to, visible, pixels) {
      if (!(visible > 0) || !(pixels > 0)) return { step: 0, major: [], minor: [] };

      const perSecond = pixels / visible;
      const row =
        RULER_STEPS.find(([major]) => major * perSecond >= LABEL_GAP) ||
        RULER_STEPS[RULER_STEPS.length - 1];
      const [step, small] = row;

      const first = Math.max(0, from);
      const last = Math.min(this.span(), to);
      const major = [];
      const minor = [];

      // Whole thousandths: 0.1 * 3 is 0.30000000000000004.
      const at = (index, size) => Math.round(index * size * 1000) / 1000;

      for (let n = Math.ceil(first / step - 1e-9); at(n, step) <= last; n++) {
        major.push(at(n, step));
      }

      if (small * perSecond >= MINOR_GAP) {
        for (let n = Math.ceil(first / small - 1e-9); at(n, small) <= last; n++) {
          const seconds = at(n, small);

          // The labelled ticks have a longer one of their own.
          if (Math.abs(seconds / step - Math.round(seconds / step)) > 1e-6) {
            minor.push(seconds);
          }
        }
      }

      return { step, major, minor };
    },

    // What a labelled tick says: minutes and seconds, with a tenth only when
    // the step is finer than a second, and hours only when there are some.
    tickLabel(seconds, step) {
      const whole = Math.floor(seconds + 1e-6);
      const hours = Math.floor(whole / 3600);
      const minutes = Math.floor((whole % 3600) / 60);
      const rest = whole % 60;
      const pad = (value) => String(value).padStart(2, "0");

      let text = hours
        ? `${hours}:${pad(minutes)}:${pad(rest)}`
        : `${minutes}:${pad(rest)}`;

      if (step < 1) {
        text += `.${Math.round((seconds - whole) * 10) % 10}`;
      }

      return text;
    },

    // ── zoom ───────────────────────────────────────────────────────────────

    canZoomIn() {
      return this.zoom < ZOOM_MAX;
    },

    // Not when the whole recording is on the strip already: there is nothing
    // more to show, and a button that only changes a number does nothing.
    canZoomOut() {
      return this.zoom > ZOOM_MIN && this.visible() < this.span();
    },

    zoomIn() {
      if (!this.canZoomIn()) {
        this.note = "Already zoomed in as far as it goes";
        return;
      }

      this.zoomTo(this.zoom * ZOOM_STEP);
    },

    zoomOut() {
      if (!this.canZoomOut()) {
        this.note =
          this.zoom > ZOOM_MIN
            ? "The whole recording is already on the strip"
            : "Already zoomed out as far as it goes";
        return;
      }

      this.zoomTo(this.zoom / ZOOM_STEP);
    },

    zoomReset() {
      if (this.zoom === 1) {
        this.note = "The zoom is already the default";
        return;
      }

      this.zoomTo(1);
    },

    // Zooming changes how the strip is drawn and nothing else: not a
    // caption, not the playhead, not what the player is doing.
    zoomTo(zoom) {
      this.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom));
      this.note = `The strip shows ${this.seconds(this.visible())}`;
      this.draw();
    },

    // Said in words, for the status region.
    seconds(value) {
      const whole = Math.round(value);

      if (whole < 60) return `${whole} ${whole === 1 ? "second" : "seconds"}`;

      const minutes = Math.floor(whole / 60);
      const rest = whole % 60;
      const head = `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;

      return rest ? `${head} ${rest} seconds` : head;
    },

    // ── moving the playhead ────────────────────────────────────────────────

    // The one place the playhead is moved from, for the keyboard and the
    // wheel alike. The strip moves at once, since it is only a drawing; the
    // player is told on the next frame, once, whatever has been asked for in
    // between -- a wheel turned fast makes dozens of events a frame, and
    // every one of them a seek the player would start and abandon. Never
    // past either end of the recording.
    seekTo(seconds) {
      const span = this.span();
      if (!span) return;

      const to = Math.max(0, Math.min(span, seconds));

      this.position = to;
      this.draw();

      this.seekPending = to;

      if (this.seekFrame === null) {
        this.seekFrame = requestAnimationFrame(() => {
          this.seekFrame = null;

          const target = this.seekPending;
          this.seekPending = null;

          if (this.video && target !== null) this.video.currentTime = target;
        });
      }
    },

    onKey(event) {
      // Only the strip itself: the controls beside it have keys of their own.
      if (event.target !== this.$refs.root) return;

      // Ctrl and Cmd with plus, minus and 0 are the browser's own zoom, and
      // the reader who uses it for the page is not to lose it here.
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (this.drag || this.creating || this.dockDrag) return;

      // Shift with up and down: zoom, where plus and minus need a modifier of
      // their own on some keyboards. Up and down on their own are the page's.
      if (event.shiftKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
        event.preventDefault();

        if (event.key === "ArrowUp") this.zoomIn();
        else this.zoomOut();

        this.syncAria(true);
        return;
      }

      const visible = this.visible();
      const keys = {
        ArrowRight: () => this.seekTo(this.position + visible * STEP_SMALL),
        ArrowLeft: () => this.seekTo(this.position - visible * STEP_SMALL),
        PageUp: () => this.seekTo(this.position + visible * STEP_PAGE),
        PageDown: () => this.seekTo(this.position - visible * STEP_PAGE),
        Home: () => this.seekTo(0),
        End: () => this.seekTo(this.span()),
        "+": () => this.zoomIn(),
        "=": () => this.zoomIn(),
        "-": () => this.zoomOut(),
        _: () => this.zoomOut(),
        0: () => this.zoomReset(),
      };

      const move = keys[event.key];
      if (!move) return;

      event.preventDefault();
      move();
      this.syncAria(true);
    },

    // Sideways scrolling moves the recording under the playhead, which stays
    // where it is in the middle (SUNET/scribe-ui#128). Only sideways: up and
    // down is the page's, and a strip that took it would trap the reader in
    // the middle of a long page. Shift with the wheel is sideways on a mouse
    // that has no other way to say so. Ctrl with the wheel is a pinch, and
    // zooms the strip (see pinch).
    //
    // Once a gesture has been sideways, the next few hundred milliseconds of
    // it are too. A swipe often starts more vertical than sideways, and the
    // first event that is let through is the one the browser decides the
    // whole gesture on -- which is how a swipe over the strip ended up going
    // back to the previous page. See holdSwipe for the other half of that.
    onWheel(event) {
      // A pinch on a trackpad arrives as a wheel with Ctrl held (Chrome,
      // Edge and Firefox, on a Mac too), and so does Ctrl with a mouse
      // wheel. Over the strip it zooms the strip; everywhere else it is
      // still the browser's zoom, and so are Ctrl and Cmd with plus, minus
      // and 0 (see onKey), so the page can always be enlarged.
      if (event.ctrlKey) {
        event.preventDefault();
        this.pinch(event);
        return;
      }

      if (event.metaKey) return;
      if (this.drag || this.creating || this.dockDrag) return;

      const now = performance.now();
      const sideways =
        Math.abs(event.deltaX) > Math.abs(event.deltaY) ||
        event.shiftKey ||
        now < this.swipeUntil;
      if (!sideways) return;

      this.swipeUntil = now + SWIPE_LATCH;
      event.preventDefault();

      // Shift with a plain wheel arrives as vertical movement on some
      // systems; a latched event is sideways whatever its vertical part.
      const delta = event.deltaX || (event.shiftKey ? event.deltaY : 0);
      if (!delta) return;

      const pixelsPerSecond = this.pixelsPerSecond();
      if (!pixelsPerSecond) return;

      // Pixels, lines or pages, depending on the device.
      const box = this.$refs.root.getBoundingClientRect();
      const pixels =
        event.deltaMode === 1
          ? delta * 16
          : event.deltaMode === 2
          ? delta * box.width
          : delta;

      // From where the playhead is going, not where the player has got to.
      const from = this.seekPending !== null ? this.seekPending : this.position;

      this.seekTo(from + pixels / pixelsPerSecond);
      this.syncAria(false);
    },

    // One step of a pinch, or of Ctrl with the wheel: zoom by an amount
    // that follows the gesture. The strip is drawn around the playhead, so
    // there is nowhere to zoom towards. Not while a caption is being dragged,
    // when what the pixels mean would change under the pointer -- though the
    // browser's own zoom is still kept off, or the page would grow instead.
    pinch(event) {
      const box = this.$refs.root.getBoundingClientRect();
      const pixels =
        event.deltaMode === 1
          ? event.deltaY * 16
          : event.deltaMode === 2
          ? event.deltaY * box.height
          : event.deltaY;

      const capped = Math.max(-PINCH_MAX, Math.min(PINCH_MAX, pixels));

      this.zoomBy(Math.exp(-capped * PINCH_SPEED));
    },

    // Safari does not send a pinch as a wheel but as its own gesture, with
    // the whole scale since it began. Cancelled, or the page zooms.
    onGesture(event) {
      event.preventDefault();

      if (event.type === "gesturestart") {
        this.gestureFrom = this.zoom;
        return;
      }

      if (event.type === "gesturechange" && event.scale > 0) {
        this.zoomBy((this.gestureFrom * event.scale) / this.zoom);
      }
    },

    // Multiply the zoom, within the same limits as the buttons: nothing
    // further in than the strip goes, and not further out than the whole
    // recording on it.
    zoomBy(factor) {
      if (this.drag || this.creating || this.dockDrag) return;

      const zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, this.zoom * factor));

      if (zoom === this.zoom) return;
      if (zoom < this.zoom && !this.canZoomOut()) return;

      this.zoom = zoom;
      this.draw();
      this.sayZoomSoon();
    },

    // Once the zoom has stood still for a moment, not at every step of it.
    sayZoomSoon() {
      clearTimeout(this.zoomNoteTimer);

      this.zoomNoteTimer = setTimeout(() => {
        this.zoomNoteTimer = null;
        this.note = `The strip shows ${this.seconds(this.visible())}`;
      }, PINCH_SETTLE);
    },

    // The browser goes back to the previous page on a sideways swipe that
    // nothing has taken, and cancelling the wheel events is not enough to stop
    // that: overscroll-behavior on the page's own root is what says the swipe
    // is not for navigating. (It has no effect on the strip itself, which is
    // not a scroll container.) Held only while the pointer is over the strip,
    // so Back works as before everywhere else on the page.
    holdSwipe() {
      document.documentElement.style.overscrollBehaviorX = "none";
      document.body.style.overscrollBehaviorX = "none";
    },

    releaseSwipe() {
      document.documentElement.style.overscrollBehaviorX = "";
      document.body.style.overscrollBehaviorX = "";
    },

    // ── what assistive technology is told ──────────────────────────────────

    ariaMax() {
      return Math.round(this.span() * 10) / 10;
    },

    ariaNow() {
      return Math.round(this.ariaPosition * 10) / 10;
    },

    // Brings the slider's value up to the playhead -- except while the
    // recording plays with the strip in focus, when it would change many
    // times a second and the screen reader would say nothing else. `force`
    // is for a move the reader has just made themselves.
    syncAria(force) {
      const playing = this.video && !this.video.paused && !this.video.ended;
      const focused =
        this.$refs.root && document.activeElement === this.$refs.root;

      if (!force && playing && focused) return;

      this.ariaPosition = this.position;
    },

    // The recording has stopped, or landed somewhere new.
    rest() {
      this.syncAria(false);
    },

    // ── the controls beside the strip ──────────────────────────────────────

    // Dock, zoom and add a caption. Icons only, so every one carries its
    // name; the state of the dock button is aria-pressed rather than a label
    // that changes, and a control that cannot be used says so with
    // aria-disabled and stays focusable, so that pressing it at the end of
    // its range does not drop focus on the page.
    actions() {
      return [
        {
          key: "dock",
          icon: "vertical_align_bottom",
          label: "Dock timeline",
          tip: this.docked
            ? "Put the timeline back under the video"
            : "Dock the timeline along the bottom of the page",
          pressed: this.docked,
          run: this.toggleDock,
        },
        {
          key: "zoomOut",
          icon: "zoom_out",
          label: "Zoom out",
          tip: "Zoom out (or pinch on the strip)",
          off: !this.canZoomOut(),
          gap: true,
          run: this.zoomOut,
        },
        {
          key: "zoomIn",
          icon: "zoom_in",
          label: "Zoom in",
          tip: "Zoom in (or pinch on the strip)",
          off: !this.canZoomIn(),
          run: this.zoomIn,
        },
        {
          key: "zoomReset",
          icon: "zoom_out_map",
          label: "Reset zoom",
          tip: "Reset zoom",
          off: this.zoom === 1,
          run: this.zoomReset,
        },
        {
          key: "add",
          icon: "playlist_add",
          label: "Add caption at playhead",
          tip: "Add caption at playhead",
          gap: true,
          run: this.addAtPlayhead,
        },
      ];
    },

    focusAction(key) {
      const root = this.$refs.actions;
      const button = root && root.querySelector(`[data-key="${key}"]`);

      if (button) button.focus();
    },

    onActionKey(event, index) {
      const buttons = this.$refs.actions.querySelectorAll(
        ".speech-timeline-action"
      );
      const last = buttons.length - 1;

      const to =
        event.key === "ArrowRight"
          ? index === last ? 0 : index + 1
          : event.key === "ArrowLeft"
          ? index === 0 ? last : index - 1
          : event.key === "Home"
          ? 0
          : event.key === "End"
          ? last
          : null;

      if (to === null) return;

      event.preventDefault();
      buttons[to].focus();
    },

    // ── the player ────────────────────────────────────────────────────────

    follow() {
      // A move that has not been handed to the player yet is the truth, and
      // the player's own position is the one it replaces.
      if (this.seekPending !== null) return;

      this.position = this.video ? this.video.currentTime : 0;
      this.draw();
    },

    // timeupdate fires a few times a second, which is visibly steppy for a
    // line travelling across a strip this wide. While the video is playing
    // the playhead is moved every frame instead; when it stops, timeupdate
    // and seeked are enough on their own.
    animate() {
      this.stop();

      const step = () => {
        this.follow();
        this.frame = requestAnimationFrame(step);
      };

      this.frame = requestAnimationFrame(step);
    },
    stop() {
      if (this.frame) cancelAnimationFrame(this.frame);
      this.frame = null;
    },

    // ── drawing ───────────────────────────────────────────────────────────

    // getComputedStyle can force a style recalculation, and draw() asks for
    // half a dozen colours -- sixty times a second while the recording
    // plays. They are read once and kept until something that could change
    // them happens: the theme, or the strip moving to a place with a
    // different background behind it.
    colour(name, fallback) {
      if (this.palette === null) this.readPalette();

      return this.palette[name] || fallback;
    },

    readPalette() {
      const style = getComputedStyle(this.$refs.root);
      const palette = {};

      for (const name of [
        "--timeline-ground",
        "--timeline-speech",
        "--timeline-caption",
        "--timeline-caption-playing",
        "--timeline-caption-current",
        "--timeline-void",
        "--timeline-playhead",
        "--timeline-label",
        "--timeline-ruler",
      ]) {
        palette[name] = style.getPropertyValue(name).trim();
      }

      this.palette = palette;
    },

    // Dark mode is a class on the body, and every colour above is a custom
    // property that changes with it.
    forgetPalette() {
      this.palette = null;
      this.draw();
    },

    draw() {
      const canvas = this.$refs.canvas;
      const root = this.$refs.root;
      if (!canvas || !root) return;

      const span = this.span();
      const width = root.clientWidth;
      const height = root.clientHeight;
      if (!width || !height) return;

      // Drawn at the display's own pixel density, or the strip is soft and
      // the playhead lands between pixels.
      //
      // Only when it has actually changed, though: assigning canvas.width
      // throws the backing store away and allocates a new one, and this
      // runs every animation frame while the recording plays. The size
      // changes when the splitter moves, when the strip docks and when the
      // window is resized -- not sixty times a second.
      const ratio = window.devicePixelRatio || 1;
      const backing = `${width}x${height}x${ratio}`;

      if (backing !== this.backing) {
        canvas.width = width * ratio;
        canvas.height = height * ratio;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        this.backing = backing;
      }

      const context = canvas.getContext("2d");
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);

      const from = this.viewStart();
      const visible = this.visible();
      const at = (seconds) =>
        visible ? ((seconds - from) / visible) * width : 0;

      // Speech is the reference, the captions are the subject: speech is
      // drawn quietly along the top, the captions below it at full weight.
      // The issue this follows is explicit about the order of those two.
      // Everything below the ruler keeps the proportions it always had, in
      // the height that is left.
      const body = height - RULER;
      const speechTop = RULER + body * 0.1;
      const speechHeight = body * 0.2;
      const bandTop = RULER + body * 0.42;
      const bandHeight = body * 0.42;

      // Before the recording starts and after it ends there is nothing --
      // said outright rather than left as blank strip, since the playhead
      // stays centred and those stretches are on screen at both ends.
      context.fillStyle = this.colour("--timeline-void", "#f3f4f6");

      if (from < 0) context.fillRect(0, 0, at(0), height);
      if (from + visible > span) {
        context.fillRect(at(span), 0, width - at(span), height);
      }

      // Silence: the ground speech sits on.
      context.fillStyle = this.colour("--timeline-ground", "#e5e7eb");
      context.fillRect(0, speechTop + speechHeight / 2 - 1, width, 2);

      context.fillStyle = this.colour("--timeline-speech", "#9aa1ab");

      // Only what is on screen. Both lists are time-ordered, so the first
      // one that could be visible is found by bisection rather than by
      // walking past every earlier one -- an hour of speech is thousands of
      // runs and a subtitle file thousands of captions, and this ran for
      // every one of them on every animation frame.
      for (const [start, end] of this.within(this.runs, from, from + visible)) {
        const left = at(start);
        // Never narrower than a pixel: a single short word still happened.
        const run = Math.max(1, at(end) - left);

        context.fillRect(left, speechTop, run, speechHeight);
      }

      // The captions, each drawn as a bracket pair -- "[" for a start and
      // "]" for an end. A plain block cannot say which of two touching
      // edges belongs to which caption when one ends exactly where the next
      // begins, which is the common case in a subtitle file.
      const dragging = this.preview;

      for (const caption of this.visibleCaptions(from, from + visible)) {
        const shown =
          dragging && dragging.id === caption.id ? dragging : caption;

        // The one being made right now is held by definition, and drawn as
        // the caption the reader is on: it is about to become exactly that.
        const making = caption.id === NEW_CAPTION;
        const held = making || (dragging && dragging.id === caption.id);
        const hovered = this.hovered === caption.id;
        const current = this.currentId === caption.id;
        const playing = this.playingId === caption.id;

        const colour =
          making || current
            ? this.colour("--timeline-caption-current", "#082954")
            : playing
            ? this.colour("--timeline-caption-playing", "#3f5f8a")
            : this.colour("--timeline-caption", "#9aa1ab");

        const left = at(shown.start);
        const right = Math.max(left + 2, at(shown.end));

        // The body: a hover target the whole width of the caption, so
        // nobody has to aim at a thin line to pick one up.
        context.fillStyle = colour;
        context.globalAlpha = hovered || held ? 0.22 : 0.1;
        context.fillRect(left, bandTop, right - left, bandHeight);
        context.globalAlpha = 1;

        // The brackets themselves. Thicker while hovered or held, which is
        // also when they can be taken hold of.
        const stem = hovered || held ? 3 : 2;
        const arm = Math.min(6, (right - left) / 2);

        context.fillStyle = colour;
        context.fillRect(left, bandTop, stem, bandHeight);
        context.fillRect(left, bandTop, arm, stem);
        context.fillRect(left, bandTop + bandHeight - stem, arm, stem);

        context.fillRect(right - stem, bandTop, stem, bandHeight);
        context.fillRect(right - arm, bandTop, arm, stem);
        context.fillRect(right - arm, bandTop + bandHeight - stem, arm, stem);

        // Its number, so the same caption can be found in the text editor.
        // Inside the brackets rather than above them, and in the text
        // colour rather than the bracket's own -- drawn in a bracket grey
        // over a strip this busy it was there without being readable.
        //
        // Only when there is room between the two brackets: a very short
        // caption at this scale has none, and a number spilling over its
        // neighbour is worse than no number.
        const label = `#${caption.id}`;
        context.font = "700 12px system-ui, sans-serif";
        context.textBaseline = "middle";

        const room = right - left - arm * 2 - 4;

        if (!making && context.measureText(label).width < room) {
          context.fillStyle = this.colour("--timeline-label", "#111827");
          context.fillText(label, left + arm + 2, bandTop + bandHeight / 2);
        }
      }

      // The ruler: ticks hanging from the top edge, a time at each long one.
      // Only inside the recording -- the void before and after it has no time.
      if (span) {
        const ticks = this.rulerTicks(from, from + visible, visible, width);
        const ink = this.colour("--timeline-ruler", "#4b5563");

        context.fillStyle = ink;
        context.font = "500 10px system-ui, sans-serif";
        context.textBaseline = "middle";

        for (const seconds of ticks.minor) {
          context.fillRect(Math.round(at(seconds)), 0, 1, 3);
        }

        for (const seconds of ticks.major) {
          const x = Math.round(at(seconds));
          const label = this.tickLabel(seconds, ticks.step);

          context.fillRect(x, 0, 1, 7);

          // Not past the edge, where it would be cut in half.
          if (x + 3 + context.measureText(label).width <= width) {
            context.fillText(label, x + 3, RULER / 2 + 0.5);
          }
        }
      }

      if (span) {
        const x = Math.round(at(this.position)) + 0.5;

        context.strokeStyle = this.colour("--timeline-playhead", "#d32f2f");
        context.lineWidth = 2;
        context.beginPath();
        context.moveTo(x, 0);
        context.lineTo(x, height);
        context.stroke();
      }
    },
  },
};

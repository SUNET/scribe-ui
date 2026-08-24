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
// reported to the server as one retime and so one undo step.
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

// Seconds across the strip. Fixed rather than offered as a choice: this is
// the scale at which a caption edge can be seen and aimed at, and a strip
// whose scale changes underfoot is harder to read, not easier. Within the
// 10-30s the issue asks for (SUNET/scribe-ui#126).
const WINDOW = 20;

// The same, docked along the foot of the page. It is three or four times as
// wide there, so it can hold three times as long without the scale changing
// at all -- the same seconds per pixel, more of them.
const DOCKED_WINDOW = 60;

// How far down the window the grip has to be let go for the strip to dock.
const DOCK_AT = 0.7;

export default {
  template: `
    <Teleport to="body" :disabled="!docked">
    <div
      class="speech-timeline-wrap"
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
        :class="{ 'speech-timeline-dragging': drag !== null }"
        @mousemove="onMove"
        @mouseleave="onLeave"
        @mousedown="onDown"
      >
        <canvas ref="canvas" @click="onClick"></canvas>
        <div
          v-if="readout"
          class="speech-timeline-readout"
          :style="{ left: readoutLeft }"
        >{{ readout }}</div>
      </div>
      <div class="speech-timeline-legend">
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
        <span class="speech-timeline-hint">
          Click a caption to go to it · drag it, or one of its brackets, to retime
        </span>
        <span class="speech-timeline-range" :title="rangeTitle">{{ range }}</span>
        <span v-if="dockDrag" class="speech-timeline-dock-hint">
          {{ dockDrag.willDock
            ? "Release to dock along the bottom"
            : "Release to put it back under the video" }}
        </span>
      </div>
    </div>
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
  emits: ["retimespan", "selectcaption", "dock"],
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
      // The caption under the pointer. Distinct from the caption being
      // played and from the one being edited: hovering one here must not
      // take the text editor's focus off another.
      hovered: -1,
      // { id, edge, grabbed, start, end } while a caption is being dragged.
      drag: null,
      // Set by a drag, cleared on the next click: a click event follows a
      // mouseup even when the pointer travelled, and seeking to wherever a
      // drag ended is never what was meant.
      dragged: false,
      readout: "",
      readoutLeft: "0px",
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
    }

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
    // Which part of the recording is on the strip: one stretch of speech
    // looks much like another, and the strip says nothing about where in
    // the recording it is otherwise.
    range() {
      const span = this.span();

      if (!span) return "";
      if (this.visible() >= span) {
        return `whole recording · ${this.clock(span)}`;
      }

      const from = Math.max(0, this.viewStart());
      const to = Math.min(span, this.viewStart() + this.visible());

      return `${this.clock(from)}–${this.clock(to)} of ${this.clock(span)}`;
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
    rangeTitle() {
      return "The part of the recording on the strip. It follows the playhead.";
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
    // along the foot of the page. Not a choice offered for its own sake --
    // the docked strip is several times as wide, so it holds the longer
    // window at much the same seconds per pixel, which is the thing that
    // actually decides whether an edge can be seen and aimed at. A
    // recording shorter than the window simply shows all of itself.
    visible() {
      const window = this.docked ? DOCKED_WINDOW : WINDOW;

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

    // ── moving the strip itself ───────────────────────────────────────────

    // A grip of its own, not the strip: dragging the strip already means
    // taking hold of a caption, and one gesture cannot mean two things.
    startDockDrag(event) {
      event.preventDefault();
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

      if (willDock === this.docked) return;

      this.docked = willDock;
      this.palette = null;
      this.markDocked();
      this.$emit("dock", { docked: willDock });

      // A different width, and a different window across it.
      this.settle();
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
      if (this.drag) return;

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
        : "pointer";
    },

    onLeave() {
      if (this.drag) return;

      this.readout = "";
      this.hovered = -1;
      this.draw();
    },

    onDown(event) {
      const found = this.captionAt(this.secondsAt(event.clientX));

      if (!found) return;

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

    // ── the player ────────────────────────────────────────────────────────

    follow() {
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
      const speechTop = height * 0.1;
      const speechHeight = height * 0.2;
      const bandTop = height * 0.42;
      const bandHeight = height * 0.42;

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

        const held = dragging && dragging.id === caption.id;
        const hovered = this.hovered === caption.id;
        const current = this.currentId === caption.id;
        const playing = this.playingId === caption.id;

        const colour = current
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

        if (context.measureText(label).width < room) {
          context.fillStyle = this.colour("--timeline-label", "#111827");
          context.fillText(label, left + arm + 2, bandTop + bandHeight / 2);
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

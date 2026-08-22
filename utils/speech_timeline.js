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

// Seconds across the strip. Fixed rather than offered as a choice: this is
// the scale at which a caption edge can be seen and aimed at, and a strip
// whose scale changes underfoot is harder to read, not easier. Within the
// 10-30s the issue asks for (SUNET/scribe-ui#126).
const WINDOW = 20;

export default {
  template: `
    <div class="speech-timeline-wrap">
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
      </div>
    </div>
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
  },
  emits: ["retimespan", "selectcaption"],
  data() {
    return {
      position: 0,
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
      frame: null,
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

    // The strip is drawn at the size it actually has, which the splitter can
    // change at any time.
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe(this.$refs.root);

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

    if (this.observer) this.observer.disconnect();
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

    // Seconds across the strip. Twenty, always: an hour across a pane this
    // wide is roughly a minute per pixel, where no caption edge can be seen
    // let alone aimed at, and a scale that changes underfoot makes the strip
    // harder to read rather than easier. A recording shorter than the window
    // simply shows all of itself.
    visible() {
      return Math.min(WINDOW, this.span()) || this.span();
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

    // The caption under a point, and which part of it: an edge if the
    // pointer is within EDGE_GRIP of one, otherwise the body.
    captionAt(seconds) {
      const grip = EDGE_GRIP / (this.pixelsPerSecond() || 1);

      for (const caption of this.captions) {
        if (seconds < caption.start - grip || seconds > caption.end + grip) {
          continue;
        }

        if (Math.abs(seconds - caption.start) <= grip) {
          return { caption, edge: "start" };
        }
        if (Math.abs(seconds - caption.end) <= grip) {
          return { caption, edge: "end" };
        }

        return { caption, edge: "body" };
      }

      return null;
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

      this.readout =
        `${this.moment(seconds)} · ${speaking ? "speech" : "silence"}` +
        (found ? ` · caption #${found.caption.id}` : "");

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
        start = Math.min(this.snap(start + moved), end - 0.05);
      } else if (this.drag.edge === "end") {
        end = Math.max(this.snap(end + moved), start + 0.05);
      } else {
        const length = end - start;
        start = Math.max(0, Math.min(span - length, this.snap(start + moved)));
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

    // The nearest edge of a run of speech, when one is close enough to be
    // what was meant. Subtitles are cut against speech, not against
    // arbitrary tenths of a second.
    snap(seconds) {
      const reach = SNAP / (this.pixelsPerSecond() || 1);
      let best = seconds;
      let distance = reach;

      for (const [start, end] of this.runs) {
        for (const edge of [start, end]) {
          const away = Math.abs(edge - seconds);

          if (away < distance) {
            best = edge;
            distance = away;
          }
        }
      }

      return Math.max(0, best);
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

    colour(name, fallback) {
      const value = getComputedStyle(this.$refs.root)
        .getPropertyValue(name)
        .trim();

      return value || fallback;
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
      const ratio = window.devicePixelRatio || 1;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

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

      for (const [start, end] of this.runs) {
        if (end < from || start > from + visible) continue;

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

      for (const caption of this.captions) {
        const shown =
          dragging && dragging.id === caption.id ? dragging : caption;

        if (shown.end < from || shown.start > from + visible) continue;

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

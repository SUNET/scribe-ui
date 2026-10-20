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

// The player's own controls, over the foot of the picture.
//
// Why they exist: the browser's native bar handles keys inside itself, in
// ways that differ from one browser to the next and that the page cannot
// reliably intercept, so Space sometimes played and paused the recording and
// sometimes did not, depending on what happened to have focus. With no
// native bar the rule is simple and the same everywhere: the recording has no
// tab stop of its own, Space does what it does on whatever has focus (it
// presses a button, it types a space), and Ctrl+Space -- the page's own
// handler -- always plays and pauses.
//
// What it offers is what a transcriber uses: play and pause, the stretch
// around the caption the caret is in (the button for Ctrl+Shift+Space), a
// speed, a bar to move about the recording with the time beside it, and the
// volume. No fullscreen, no picture-in-picture, no download: none of them is
// work on a transcript, and the page has captions to show alongside.
//
// Like the strip under it, it follows the video element directly rather than
// being told anything: the position changes many times a second, and the
// round trip to the server for each would be both late and wasteful. Only
// "play with context" needs the server, which knows which caption the caret
// was last in, so that one is emitted.

// What "play with context" is drawn with: a speech bubble with a play
// triangle, "play what this caption says". Material Symbols (the sym_o_ prefix),
// whose font NiceGUI already ships, so no font of our own. Kept in one place so
// that is the only line to change.
const CONTEXT_ICON = "sym_o_auto_read_play";

// The speeds on offer, as playbackRate values. Quarter steps either side of
// normal and the usual halves and doubles: for checking a boundary by ear,
// slower is the one that matters, and faster for skimming a long recording.
const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];

// How far the arrow keys move the recording on the bar, and Page Up / Page
// Down. The same ordinary media-player steps the native bar used.
const STEP = 5;
const STEP_PAGE = 30;

export default {
  template: `
    <div
      class="player-controls"
      :class="{ 'player-controls-audio': audioOnly, 'player-controls-asleep': asleep }"
    >
      <div v-if="audioOnly && label" class="player-name">
        <q-icon name="sym_o_audio_file" size="18px" />
        <span>{{ label }}</span>
      </div>
      <div
        class="player-bar"
        role="group"
        aria-label="Player controls"
        @keydown="keepModifiedSpace"
        @keyup="keepModifiedSpace"
      >
        <div class="player-seekrow">
          <span class="player-time" aria-hidden="true">{{ clock(current) }}</span>
          <input
            type="range"
            class="player-range player-seek"
            aria-label="Position in the recording"
            min="0"
            :max="duration"
            step="any"
            :value="current"
            :disabled="!duration"
            :aria-valuetext="positionText"
            :style="{ '--fill': fill + '%' }"
            @input="onSeekInput"
            @change="scrubbing = false"
            @pointerdown="scrubbing = true"
            @keydown="onSeekKey"
          />
          <span class="player-time" aria-hidden="true">{{ duration ? clock(duration) : '--:--' }}</span>
        </div>
        <div class="player-buttons">
          <button
            type="button"
            class="player-btn player-btn-main"
            :aria-label="playing ? 'Pause' : 'Play'"
            @mousedown.prevent
            @click="toggle"
          ><q-icon :name="playing ? 'pause' : 'play_arrow'" size="28px" /><q-tooltip>{{ playing ? 'Pause' : 'Play' }} (Ctrl + Space)</q-tooltip></button>
          <button
            type="button"
            class="player-btn player-btn-context"
            aria-label="Play with context"
            aria-keyshortcuts="Control+Shift+Space"
            @mousedown.prevent
            @click="$emit('playcontext')"
          ><q-icon :name="contextIcon" size="22px" /><q-tooltip>Play with context</q-tooltip></button>
          <div class="player-speed" ref="speed">
            <button
              type="button"
              class="player-speed-btn"
              :class="{ 'player-speed-btn-open': menuOpen }"
              :aria-label="'Playback speed ' + rateLabel(rate)"
              aria-haspopup="menu"
              :aria-expanded="String(menuOpen)"
              @mousedown.prevent
              @click="toggleMenu"
              @keydown.down.prevent="openMenu"
              @keydown.up.prevent="openMenu"
            >{{ rateLabel(rate) }}<q-tooltip v-if="!menuOpen">Playback speed</q-tooltip></button>
            <div
              v-if="menuOpen"
              class="player-menu"
              role="menu"
              aria-label="Playback speed"
              :style="menuMax ? { maxHeight: menuMax + 'px' } : null"
              @keydown="onMenuKey"
            >
              <button
                v-for="option in rates"
                :key="option"
                type="button"
                class="player-menu-item"
                :class="{ 'player-menu-item-on': option === rate }"
                role="menuitemradio"
                :aria-checked="String(option === rate)"
                :data-rate="option"
                tabindex="-1"
                @click="setRate(option)"
              >
                <q-icon name="check" size="16px" class="player-menu-check" />
                {{ rateLabel(option) }}
              </button>
            </div>
          </div>
          <span class="player-spacer"></span>
          <div class="player-volume">
            <button
              type="button"
              class="player-btn"
              :aria-label="muted || !volume ? 'Unmute' : 'Mute'"
              @mousedown.prevent
              @click="toggleMute"
            ><q-icon :name="volumeIcon" size="22px" /><q-tooltip>{{ muted || !volume ? 'Unmute' : 'Mute' }}</q-tooltip></button>
            <input
              type="range"
              class="player-range player-volume-range"
              aria-label="Volume"
              min="0"
              max="1"
              step="0.05"
              :value="muted ? 0 : volume"
              :aria-valuetext="Math.round((muted ? 0 : volume) * 100) + ' percent'"
              :style="{ '--fill': (muted ? 0 : volume) * 100 + '%' }"
              @input="onVolumeInput"
            />
          </div>
        </div>
      </div>
    </div>
  `,
  props: {
    // The recording's file name, shown under the bar when there is no picture
    // -- the frame that would have carried it is gone then.
    label: { type: String, default: "" },
  },
  emits: ["playcontext"],
  data() {
    return {
      playing: false,
      current: 0,
      duration: 0,
      volume: 1,
      muted: false,
      rate: 1,
      // No picture: a recording that is sound alone. Known once the player has
      // read the file's header, which is when the frame gives way.
      audioOnly: false,
      menuOpen: false,
      // How tall the speed menu may be: over a picture it has to fit in the
      // frame, which a narrow splitter leaves short. 0 is no limit.
      menuMax: 0,
      // Something has just been done to the controls (the pointer moved over
      // the picture); see `asleep`.
      awake: true,
      // The bar is being dragged, and so is not to be moved by the recording
      // underneath it.
      scrubbing: false,
      rates: RATES,
      contextIcon: CONTEXT_ICON,
    };
  },
  computed: {
    fill() {
      return this.duration ? Math.min(100, (this.current / this.duration) * 100) : 0;
    },
    volumeIcon() {
      if (this.muted || !this.volume) return "volume_off";
      return this.volume < 0.5 ? "volume_down" : "volume_up";
    },
    // Over the picture the controls get out of the way while it plays and
    // nothing is being done to them, as the browser's own bar does. Never
    // while they have the keyboard (CSS keeps them up for :focus-within), and
    // never on a recording without a picture: there is nothing to see past.
    asleep() {
      return this.playing && !this.awake && !this.menuOpen && !this.audioOnly;
    },
    // What a screen reader says for the bar, which is more than a bare number
    // of seconds.
    positionText() {
      if (!this.duration) return "";
      return this.spoken(this.current) + " of " + this.spoken(this.duration);
    },
  },
  watch: {
    audioOnly(value) {
      // The frame is the page's, not this component's; it is told rather than
      // changed from here. Without a picture it becomes the player's own
      // surface and the controls stop being laid over anything.
      this.frameElement()?.classList.toggle("video-frame-audio", value);
    },
    playing(value) {
      // Playback has just started: the controls stay for a moment, then go.
      if (value) this.wake();
      else this.awake = true;
    },
  },
  mounted() {
    this.events = [
      "play",
      "pause",
      "ended",
      "timeupdate",
      "seeked",
      "durationchange",
      "loadedmetadata",
      "volumechange",
      "ratechange",
    ];
    this.onOutside = (event) => {
      if (this.menuOpen && !this.$refs.speed?.contains(event.target)) this.menuOpen = false;
    };
    document.addEventListener("pointerdown", this.onOutside, true);

    // The controls are over the picture, so the pointer over the picture is
    // what keeps them up; a moment after it stops, or leaves, they go (while
    // playing).
    this.onWake = () => this.wake();
    this.onLeave = () => this.wake(1000);
    const frame = this.frameElement();
    if (frame) {
      frame.addEventListener("pointermove", this.onWake);
      frame.addEventListener("pointerdown", this.onWake);
      frame.addEventListener("pointerleave", this.onLeave);
    }
    this.attach();

    // The player is drawn by the page, a sibling and not a child of this
    // component, and may not be there yet.
    if (!this.video) {
      this.waiting = setInterval(() => {
        this.attach();
        if (this.video) clearInterval(this.waiting);
      }, 200);
      setTimeout(() => clearInterval(this.waiting), 10000);
    }
  },
  beforeUnmount() {
    clearInterval(this.waiting);
    cancelAnimationFrame(this.frame);
    clearTimeout(this.sleepTimer);
    document.removeEventListener("pointerdown", this.onOutside, true);
    const frame = this.frameElement();
    if (frame) {
      frame.removeEventListener("pointermove", this.onWake);
      frame.removeEventListener("pointerdown", this.onWake);
      frame.removeEventListener("pointerleave", this.onLeave);
    }
    if (this.video) {
      for (const name of this.events) this.video.removeEventListener(name, this.sync);
    }
    frame?.classList.remove("video-frame-audio");
  },
  methods: {
    // The page's frame around the picture, which this component sits in.
    frameElement() {
      return this.$el?.closest?.(".video-frame") || null;
    },

    // Awake now, and asleep again after `delay` ms if nothing else is done.
    wake(delay = 3000) {
      this.awake = true;
      clearTimeout(this.sleepTimer);
      this.sleepTimer = setTimeout(() => {
        this.awake = false;
      }, delay);
    },

    attach() {
      if (this.video) return;
      this.video = document.querySelector("video");
      if (!this.video) return;
      for (const name of this.events) this.video.addEventListener(name, this.sync);
      this.sync();
    },

    // Everything the bar shows is read back off the element, whichever of the
    // events fired: it is cheap, and it means nothing here can drift from what
    // the player is doing, whoever started it -- this bar, Ctrl+Space, the
    // strip, or a caption played with its context.
    sync() {
      const video = this.video;
      if (!video) return;
      this.playing = !video.paused && !video.ended;
      if (!this.scrubbing) this.current = video.currentTime || 0;
      this.duration = Number.isFinite(video.duration) ? video.duration : 0;
      this.volume = video.volume;
      this.muted = video.muted;
      this.rate = video.playbackRate;
      this.audioOnly = video.readyState >= 1 && video.videoWidth === 0;
      if (this.playing && !this.frame) this.follow();
    },

    // While playing, the position is read every frame rather than at the
    // few times a second timeupdate comes, so the thumb glides.
    follow() {
      const step = () => {
        const video = this.video;
        if (!video || video.paused || video.ended) {
          this.frame = null;
          return;
        }
        if (!this.scrubbing) this.current = video.currentTime;
        this.frame = requestAnimationFrame(step);
      };
      this.frame = requestAnimationFrame(step);
    },

    toggle() {
      const video = this.video;
      if (!video) return;
      if (video.paused || video.ended) video.play();
      else video.pause();
    },

    // Ctrl+Space plays and pauses, and is the page's own handler's. With a
    // button focused the browser would also press it -- the key's release
    // counts as a click -- and the two would cancel out. Only the browser's
    // own action is stopped here; the event itself carries on to the page.
    keepModifiedSpace(event) {
      if (event.ctrlKey && (event.code === "Space" || event.key === " ")) {
        event.preventDefault();
      }
    },

    // The bar.
    onSeekInput(event) {
      this.scrubbing = true;
      this.moveTo(Number(event.target.value));
    },
    onSeekKey(event) {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const keys = {
        ArrowLeft: -STEP,
        ArrowDown: -STEP,
        ArrowRight: STEP,
        ArrowUp: STEP,
        PageDown: -STEP_PAGE,
        PageUp: STEP_PAGE,
      };
      let target = null;
      if (event.key in keys) target = this.current + keys[event.key];
      else if (event.key === "Home") target = 0;
      else if (event.key === "End") target = this.duration;
      if (target === null) return;
      event.preventDefault();
      this.moveTo(target);
    },
    moveTo(seconds) {
      const video = this.video;
      if (!video || !this.duration) return;
      const target = Math.max(0, Math.min(this.duration, seconds));
      video.currentTime = target;
      this.current = target;
    },

    // The speed.
    rateLabel(rate) {
      return String(rate) + "×";
    },
    setRate(rate) {
      if (this.video) this.video.playbackRate = rate;
      this.rate = rate;
      this.closeMenu(true);
    },
    toggleMenu() {
      if (this.menuOpen) this.closeMenu(true);
      else this.openMenu();
    },
    openMenu() {
      // Over a picture the menu has to fit in the frame, which a narrow
      // splitter leaves short; it scrolls rather than being cut off. A frame
      // that has become the player's own surface (no picture) does not clip.
      const frame = this.frameElement();
      this.menuMax = frame && !this.audioOnly
        ? Math.max(96, frame.clientHeight - this.$el.offsetHeight - 16)
        : 0;
      this.menuOpen = true;
      // On the one in force, so Enter alone changes nothing and an arrow key
      // moves from where the reader is.
      this.$nextTick(() => {
        const on = this.$el.querySelector(".player-menu-item-on")
          || this.$el.querySelector(".player-menu-item");
        on?.focus();
      });
    },
    closeMenu(refocus) {
      this.menuOpen = false;
      if (refocus) this.$nextTick(() => this.$el.querySelector(".player-speed-btn")?.focus());
    },
    onMenuKey(event) {
      const items = [...this.$el.querySelectorAll(".player-menu-item")];
      const at = items.indexOf(document.activeElement);
      let next = null;
      if (event.key === "ArrowDown") next = (at + 1) % items.length;
      else if (event.key === "ArrowUp") next = (at - 1 + items.length) % items.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = items.length - 1;
      else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        return this.closeMenu(true);
      } else if (event.key === "Tab") {
        // Left to carry on to the next control, with the menu out of the way.
        return this.closeMenu(false);
      }
      if (next === null) return;
      event.preventDefault();
      items[next].focus();
    },

    // The volume.
    toggleMute() {
      const video = this.video;
      if (!video) return;
      // What the button says is what it does: while the sound is off, by the
      // mute or by the slider at zero, it turns it on -- and at zero that
      // means something audible, or it would change nothing.
      if (video.muted || video.volume === 0) {
        video.muted = false;
        if (video.volume === 0) video.volume = 0.5;
      } else {
        video.muted = true;
      }
    },
    onVolumeInput(event) {
      const video = this.video;
      if (!video) return;
      const value = Number(event.target.value);
      video.volume = value;
      video.muted = value === 0;
    },

    // Time as it is read off a clock: 12:34, or 1:23:45 once past the hour.
    clock(seconds) {
      const whole = Math.max(0, Math.floor(seconds || 0));
      const h = Math.floor(whole / 3600);
      const m = Math.floor((whole % 3600) / 60);
      const s = whole % 60;
      const pad = (n) => String(n).padStart(2, "0");
      return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
    },
    // The same, as it is said.
    spoken(seconds) {
      const whole = Math.max(0, Math.floor(seconds || 0));
      const h = Math.floor(whole / 3600);
      const m = Math.floor((whole % 3600) / 60);
      const s = whole % 60;
      const parts = [];
      if (h) parts.push(h + (h === 1 ? " hour" : " hours"));
      if (m) parts.push(m + (m === 1 ? " minute" : " minutes"));
      if (s || !parts.length) parts.push(s + (s === 1 ? " second" : " seconds"));
      return parts.join(" ");
    },
  },
};

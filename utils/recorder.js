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

// The recorder page: what the reader sees and presses.  Everything that
// keeps a recording safe lives in static/recorder_engine.js; this only draws
// it and hands the engine what the reader asked for.
//
// Built for a phone lying on a lectern for an hour and a half, which decides
// most of what is here:
//
//   - **One filled action at a time** (Start, then Stop, then Upload), large
//     enough for a thumb, so what the page is for is never in question.
//   - **Stop asks twice.**  A phone in a hand or a pocket gets tapped, and a
//     stopped lecture cannot be un-stopped -- only continued in a new part.
//   - **It says where the recording is**: seconds kept on this device, and
//     how much of it Scribe already has.  "Saved" is the reassurance a
//     professor needs before walking away from the phone.
//   - **It says when something is wrong, in words**: the microphone paused
//     by the phone, storage full, the screen allowed to lock, signed out.
//     None of these stop the page; each changes what the reader should do.
//
// The level meter is drawn from a live analyser on the stream already open
// -- never by decoding the recording, which for an hour is over a gigabyte of
// PCM.  The preview after stopping is the browser's own <audio> player:
// accessible from the keyboard and a screen reader as it is, which a canvas
// scrubber is not.

const METER_MS = 100;
// Which microphone was chosen last, remembered per browser.
const DEVICE_KEY = "scribe-recorder-device";
const METER_SAMPLES = 300; // thirty seconds of level history

const pad = (n) => String(n).padStart(2, "0");

function clock(ms) {
  const total = Math.max(0, Math.floor((ms || 0) / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
}

function size(bytes) {
  if (!bytes) return "0 KB";
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

const FAILURES = {
  NotAllowedError:
    "Microphone access was refused. Allow it for this site in the browser settings and try again.",
  SecurityError: "Microphone access is blocked by this site's security policy.",
  NotFoundError: "No microphone was found.",
  DevicesNotFoundError: "No microphone was found.",
  NotReadableError: "The microphone is being used by another app.",
  TrackStartError: "The microphone is being used by another app.",
  InsecureContext: "Recording needs an https connection.",
  NotSupported: "This browser cannot record audio. Try an up-to-date Chrome, Edge, Firefox or Safari.",
};

// NiceGUI's own client reloads the page by itself in three places: a
// reconnect attempt that times out (nicegui.js, "reloading because
// connection timed out" -- which is exactly what a computer waking from
// sleep, or a laptop between two wifi networks, runs into), a handshake the
// server refuses, and a reconnect the server asks for.  A reload stops the
// MediaRecorder.  What was recorded is safe either way, but a lecture must
// not be cut in two because the lid was closed for a minute.
//
// So while a recording runs, those three are answered here instead: the
// socket goes on reconnecting by itself, a handshake is made without the
// reload behind it, and anything that really needs a fresh page is put off
// until the recording has stopped -- and then only offered, not done,
// since nothing on this page needs the socket to go on working: recording
// and uploading are both the browser's own.  Every other moment the
// original handlers run untouched.  Pinned against the NiceGUI release in
// tests/test_recording.py, since it reaches into nicegui.js.
const RELOAD_EVENTS = ["connect", "connect_error", "try_reconnect"];

function guardReloads(busy, onStale) {
  const socket = window.socket;
  if (!socket || socket.__scribeGuarded) return !!socket;
  socket.__scribeGuarded = true;

  const original = {};
  RELOAD_EVENTS.forEach((event) => {
    original[event] = socket.listeners(event).slice();
    socket.off(event);
  });
  const passOn = (event, args) => original[event].forEach((handler) => handler(...args));

  socket.on("connect_error", (...args) => {
    const error = args[0] || {};
    if (busy() && (error.message === "timeout" || error.message === "Implicit handshake failed")) {
      // socket.io keeps trying on its own; only the reload is skipped.
      onStale();
      return;
    }
    passOn("connect_error", args);
  });

  socket.on("try_reconnect", (...args) => {
    if (busy()) {
      onStale();
      return;
    }
    passOn("try_reconnect", args);
  });

  socket.on("connect", (...args) => {
    const query = (socket.io && socket.io.opts && socket.io.opts.query) || {};
    if (!busy() || query.implicit_handshake) {
      passOn("connect", args);
      return;
    }
    // The handshake nicegui.js would make, without its reload on refusal.
    socket.emit("handshake", query, (ok) => {
      if (!ok) {
        onStale();
        return;
      }
      window.did_handshake = true;
      const popup = document.getElementById("popup");
      if (popup) popup.ariaHidden = true;
    });
  });

  return true;
}

export default {
  template: `
    <div class="recorder">
      <div v-if="unsupported" class="recorder-banner recorder-banner-danger" role="alert">
        {{ unsupported }}
      </div>

      <div v-if="sessionEnded" class="recorder-banner recorder-banner-warn" role="alert">
        You have been signed out. The recording goes on and is saved in this browser; when you
        stop it you are taken to sign in again, and it is here to upload afterwards.
      </div>

      <div v-if="!persistent" class="recorder-banner recorder-banner-danger" role="alert">
        This browser does not let Scribe save recordings while they are made (a private
        window?). If this page closes before the recording is uploaded or downloaded, it is lost.
      </div>

      <div v-if="stale && !live" class="recorder-banner recorder-banner-warn" role="status">
        The connection to Scribe was interrupted while recording. Your recordings are safe and
        uploads carry on; reload the page to reconnect the rest of Scribe.
        <q-btn flat no-caps dense class="recorder-quiet" icon="refresh" label="Reload" @click="reloadPage" />
      </div>

      <template v-if="!unsupported">
        <!-- The record button is the card: one round button in the middle,
             the clock under it, the level drawn beneath while recording --
             the shape everyone knows from a voice-memo app. -->
        <div class="recorder-hero" :class="{ 'is-live': live, 'is-paused': live && paused }">
          <div v-if="live" class="recorder-live-name">{{ liveMeta.name }}</div>
          <button
            type="button"
            class="recorder-record"
            :class="{ 'is-live': live, 'is-armed': stopArmed }"
            :disabled="starting || (!live && !!sessionElsewhere)"
            :aria-label="!live ? 'Start recording' : (stopArmed ? 'Press again to stop the recording' : 'Stop recording')"
            @click="live ? stop() : start()"
          >
            <span class="recorder-record-icon" aria-hidden="true">
              <q-spinner v-if="starting" size="36px" />
              <q-icon v-else :name="live ? 'stop' : 'mic'" size="40px" />
            </span>
          </button>
          <div class="recorder-record-caption" aria-hidden="true">
            {{ !live ? "Start recording" : (stopArmed ? "Press again to stop" : (paused ? "Paused" : "Recording")) }}
          </div>
          <div class="recorder-clock" role="timer" aria-label="Recording time">{{ clock(elapsed) }}</div>
          <canvas ref="meter" class="recorder-meter" aria-hidden="true"></canvas>
          <q-btn
            v-if="live"
            outline
            no-caps
            class="recorder-secondary recorder-small"
            :icon="paused ? 'play_arrow' : 'pause'"
            :label="paused ? 'Resume' : 'Pause'"
            @click="togglePause"
          />
        </div>

        <div v-if="live" class="recorder-safety" role="status" aria-live="polite">
          <span class="recorder-safety-item">
            <q-icon name="save" size="16px" aria-hidden="true" />
            Saved in this browser: {{ clock(savedMs) }}
          </span>
        </div>

        <div v-for="warning in warnings" :key="warning" class="recorder-banner recorder-banner-warn" role="alert">
          {{ warning }}
        </div>

        <!-- Name and microphone as a pair of settings.  Both native
             controls with one class, so they are the same height and, in
             their two equal columns, the same width -- a QInput beside a
             <select> never quite matched. -->
        <div v-if="!live" class="recorder-settings">
          <div class="recorder-setting">
            <label :for="nameInputId" class="recorder-setting-label">Name</label>
            <input
              :id="nameInputId"
              v-model="name"
              type="text"
              class="recorder-field"
              maxlength="120"
              :placeholder="defaultName"
            />
          </div>
          <div class="recorder-setting">
            <label :for="deviceSelectId" class="recorder-setting-label">Microphone</label>
            <select
              :id="deviceSelectId"
              v-model="deviceId"
              class="recorder-field"
              :disabled="!devices.length"
              @change="rememberDevice"
            >
              <option v-if="!devices.length" value="">{{ micRefused ? "Not available" : "Asking for permission…" }}</option>
              <option v-for="d in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label }}</option>
            </select>
          </div>
        </div>
        <div v-if="!live && micRefused" class="recorder-banner recorder-banner-warn" role="alert">
          {{ micRefused }}
          <q-btn flat no-caps dense class="recorder-quiet" icon="mic" label="Ask again" @click="askForMicrophone" />
        </div>

        <div class="recorder-status" role="status" aria-live="polite">{{ status }}</div>

        <div v-if="!live && freeHours !== null && freeHours < 4" class="recorder-banner recorder-banner-warn" role="status">
          This browser has room for about {{ freeHours < 1 ? Math.max(1, Math.round(freeHours * 60)) + " minutes" : freeHours.toFixed(1) + " hours" }} of recording.
        </div>

        <div v-if="!live" class="recorder-help-row">
          <q-btn
            flat
            no-caps
            dense
            class="recorder-quiet"
            icon="help_outline"
            label="How recording works"
            @click="helpOpen = true"
          />
        </div>

        <q-dialog v-model="helpOpen" aria-labelledby="recorder-help-title">
          <q-card class="recorder-help-card">
            <q-card-section>
              <h2 id="recorder-help-title" class="recorder-help-title">How recording works</h2>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Before you start</h3>
                <p>Any up-to-date browser on a computer, phone or tablet works.</p>
                <p>The browser asks for permission to use the microphone. Choose which microphone under "Microphone", and place it close to whoever is speaking.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">While recording</h3>
                <p>Keep this page open. On a computer, keep it from going to sleep; on a phone or tablet, keep the screen on{{ wakeLockSupported ? " – Scribe asks the device to stay awake for you" : "" }}.</p>
                <p>For a long recording, connect the charger.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">If something goes wrong</h3>
                <p>The recording is saved in this browser second by second. If the browser or the device crashes, it is here when you open this page again.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Keeping the original</h3>
                <p>Before transcribing, you can listen to the recording and download the original file. It stays here, ready to download, for {{ keepDays }} days after uploading.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Privacy and security</h3>
                <p>While it is being recorded, and until it is removed, the recording is stored unencrypted in this browser on this device. Anyone who can use this browser on this device could get to it, so on a shared computer, remove recordings from this browser once they are uploaded.</p>
                <p>Nothing leaves this device until you press Upload. Then it is sent to Scribe over an encrypted connection and stored encrypted there, under your account only. It passes through Scribe's web server on the way without being stored there.</p>
                <p>A downloaded original is an ordinary file on your device. Keep it the way your organisation asks you to keep recordings of people.</p>
              </div>
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat no-caps label="Close" color="black" v-close-popup />
            </q-card-actions>
          </q-card>
        </q-dialog>
      </template>

      <section v-if="others.length" class="recorder-list" aria-labelledby="recorder-list-heading">
        <h2 id="recorder-list-heading" class="recorder-list-heading">Recordings in this browser</h2>

        <article
          v-for="item in others"
          :key="item.id"
          class="recorder-item"
          :class="{ 'is-open': openId === item.id }"
        >
          <div class="recorder-item-head">
            <div class="recorder-item-text">
              <div class="recorder-item-name">{{ item.name }}</div>
              <div class="recorder-item-meta">
                {{ when(item.createdAt) }} · {{ clock(item.durationMs || item.chunks * 1000) }} · {{ size(item.bytes) }}
              </div>
              <div class="recorder-item-state" :class="'is-' + tone(item)">
                <q-icon :name="icon(item)" size="16px" aria-hidden="true" />
                {{ describe(item) }}
              </div>
            </div>
            <!-- In the header, not the action row: a destructive action is
                 not one of the things to do next, and in the row it was the
                 button that wrapped onto a line of its own.  Armed, it says
                 in words what the second press does. -->
            <q-btn
              v-if="!item.elsewhere && !(item.submit && item.state !== 'uploaded' && !item.error)"
              flat
              no-caps
              dense
              :round="discardArmed !== item.id"
              class="recorder-quiet recorder-discard"
              :class="{ 'is-armed': discardArmed === item.id }"
              icon="delete"
              :label="discardArmed === item.id ? (item.state === 'uploaded' ? 'Press again to remove' : 'Press again to delete') : undefined"
              :aria-label="discardArmed === item.id ? 'Confirm: ' + (item.state === 'uploaded' ? 'remove ' + item.name + ' from this browser; the uploaded copy is kept' : 'delete ' + item.name) : (item.state === 'uploaded' ? 'Remove ' + item.name + ' from this browser; the uploaded copy is kept' : 'Delete ' + item.name)"
              @click="discard(item)"
            >
              <q-tooltip v-if="discardArmed !== item.id">{{ item.state === 'uploaded' ? 'Remove from this browser' : 'Delete' }}</q-tooltip>
            </q-btn>
          </div>

          <div v-if="item.state === 'stopped' && !item.submit && !item.error" class="recorder-item-edit">
            <q-input
              :model-value="item.name"
              @update:model-value="(v) => rename(item, v)"
              outlined
              dense
              label="Name"
              maxlength="120"
              :aria-label="'Name of ' + item.name"
            />
          </div>

          <audio
            v-if="openId === item.id && playUrl"
            ref="player"
            class="recorder-player"
            controls
            playsinline
            :src="playUrl"
            @loadedmetadata="fixDuration"
          ></audio>

          <div class="recorder-item-actions">
            <q-btn
              v-if="item.state === 'stopped' && !item.submit"
              unelevated
              no-caps
              class="recorder-primary recorder-small"
              icon="cloud_upload"
              :label="item.error ? 'Try again' : 'Upload'"
              :aria-label="(item.error ? 'Try uploading again: ' : 'Upload ') + item.name"
              @click="upload(item)"
            />
            <q-btn
              v-if="item.submit && item.state !== 'uploaded' && item.sync.phase !== 'uploading'"
              outline
              no-caps
              class="recorder-secondary recorder-small"
              icon="refresh"
              label="Retry now"
              :aria-label="'Retry uploading ' + item.name + ' now'"
              @click="retryNow(item)"
            />
            <q-btn
              v-if="item.interrupted && item.state === 'stopped' && item.id === latestInterruptedId && !live"
              outline
              no-caps
              class="recorder-secondary recorder-small"
              icon="mic"
              label="Continue recording"
              :aria-label="'Continue recording ' + item.name + ' in a new part'"
              @click="continueFrom(item)"
            />
            <q-btn
              v-if="!item.elsewhere"
              flat
              no-caps
              class="recorder-quiet recorder-small"
              :icon="openId === item.id ? 'close' : 'play_arrow'"
              :label="openId === item.id ? 'Close' : 'Listen'"
              :aria-label="(openId === item.id ? 'Close player for ' : 'Listen to ') + item.name"
              @click="togglePlay(item)"
            />
            <q-btn
              v-if="!item.elsewhere"
              flat
              no-caps
              class="recorder-quiet recorder-small"
              icon="download"
              label="Download original"
              :aria-label="'Download the original recording of ' + item.name"
              @click="save(item)"
            />
            <q-btn
              v-if="item.state === 'uploaded'"
              flat
              no-caps
              class="recorder-quiet recorder-small"
              icon="folder_open"
              label="My files"
              @click="goToFiles"
            />
          </div>
        </article>
      </section>
    </div>
  `,

  props: {
    owner: { type: String, required: true },
    filesUrl: { type: String, default: "/home" },
    sessionEnded: { type: Boolean, default: false },
    logoutUrl: { type: String, default: "" },
  },

  data() {
    return {
      engine: null,
      items: [],
      name: "",
      defaultName: "",
      starting: false,
      live: false,
      liveMeta: {},
      paused: false,
      elapsed: 0,
      savedMs: 0,
      warnings: [],
      status: "",
      unsupported: "",
      persistent: true,
      devices: [],
      deviceId: "",
      deviceSelectId: "recorder-device-" + Math.random().toString(36).slice(2),
      nameInputId: "recorder-name-" + Math.random().toString(36).slice(2),
      openId: null,
      playUrl: null,
      stopArmed: false,
      discardArmed: null,
      freeHours: null,
      wakeLockSupported: !!(navigator.wakeLock && navigator.wakeLock.request),
      helpOpen: false,
      stale: false,
      micRefused: "",
      keepDays: Math.round(window.ScribeRecorder ? window.ScribeRecorder.KEEP_UPLOADED_MS / 86400000 : 7),
      hiddenSince: null,
      awayMs: 0,
      levels: [],
    };
  },

  computed: {
    others() {
      return this.items.filter((item) => !item.live);
    },
    sessionElsewhere() {
      return this.items.find((item) => item.elsewhere) || null;
    },
    latestInterruptedId() {
      const found = this.items.find((item) => item.interrupted && item.state === "stopped");
      return found ? found.id : null;
    },
  },

  watch: {
    // Signed out: leave now, unless a recording is running -- then leave
    // the moment it stops (see follow()), with everything it recorded
    // saved in the browser.
    sessionEnded(ended) {
      if (ended) this.leaveIfSignedOut();
    },
  },

  mounted() {
    if (!window.ScribeRecorder) {
      this.unsupported = "The recorder did not load. Reload the page.";
      return;
    }

    this.defaultName = window.ScribeRecorder.defaultName(new Date());

    this.engine = window.ScribeRecorder.engine(this.owner);

    const problem = this.engine.supported();
    if (problem) {
      this.unsupported = FAILURES[problem === "insecure" ? "InsecureContext" : "NotSupported"];
    }

    this.unwatch = this.engine.onChange(() => this.redraw());
    this.engine.init().then(() => {
      this.persistent = this.engine.persistent();
      this.redraw();
    });

    try {
      this.deviceId = window.localStorage.getItem(DEVICE_KEY) || "";
    } catch (e) {
      this.deviceId = "";
    }

    // Asked for as soon as the page opens, not at the first press of Start:
    // a browser names its microphones only once it has been granted one,
    // and choosing the right microphone is something to do before the
    // lecture starts, not after the first take was made on the wrong one.
    if (!problem) this.askForMicrophone();
    if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
      this.onDeviceChange = () => this.listDevices();
      navigator.mediaDevices.addEventListener("devicechange", this.onDeviceChange);
    }

    this.estimate();

    this.onVisibility = () => this.visibilityChanged();
    document.addEventListener("visibilitychange", this.onVisibility);

    // The list's own countdowns ("trying again in 20 s") and the default
    // name's minute move on even when nothing else happens.
    this.slow = setInterval(() => {
      if (!this.live) this.defaultName = window.ScribeRecorder.defaultName(new Date());
      this.redraw();
    }, 1000);

    const guard = () =>
      guardReloads(
        () => !!(this.engine && this.engine.session()),
        () => {
          this.stale = true;
        }
      );
    // window.socket is made when NiceGUI's root app mounts, which is after
    // this component mounts; wait for it.
    if (!guard()) {
      this.guardTimer = setInterval(() => {
        if (guard()) clearInterval(this.guardTimer);
      }, 100);
    }

    this.onResize = () => this.drawMeter();
    window.addEventListener("resize", this.onResize);
    this.$nextTick(() => this.drawMeter());

    // A recording going on in this page when the component is made again
    // (NiceGUI rebuilding it after a reconnect) is picked back up.
    const running = this.engine.session();
    if (running) this.follow(running);
  },

  beforeUnmount() {
    if (this.unwatch) this.unwatch();
    if (this.ticker) clearInterval(this.ticker);
    if (this.slow) clearInterval(this.slow);
    if (this.guardTimer) clearInterval(this.guardTimer);
    if (this.onDeviceChange) navigator.mediaDevices.removeEventListener("devicechange", this.onDeviceChange);
    document.removeEventListener("visibilitychange", this.onVisibility);
    window.removeEventListener("resize", this.onResize);
    if (this.playUrl) URL.revokeObjectURL(this.playUrl);
  },

  methods: {
    clock: clock,
    size: size,

    when(ms) {
      const d = new Date(ms);
      return d.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    },

    redraw() {
      if (!this.engine) return;
      this.items = this.engine.list();
      const running = this.engine.session();
      this.live = !!running;

      if (running) {
        this.liveMeta = Object.assign({}, running.meta);
        this.paused = running.paused;
        this.savedMs = running.savedMs();
      }

      this.warnings = this.currentWarnings(running);
    },

    currentWarnings(running) {
      const out = [];
      if (!running) return out;
      if (running.muted) {
        out.push(
          "The microphone has been paused by the device – a locked screen or another app using it. Keep this page open, and on a phone or tablet keep the screen on."
        );
      }
      if (running.writeProblem) {
        out.push(
          "The storage for this browser is full. Recording goes on, but the newest audio is only in memory until space is freed."
        );
      }
      if (this.awayMs > 2000) {
        out.push(
          "This page was in the background for " + clock(this.awayMs) + ". Some devices stop the microphone meanwhile; the level meter shows whether it is still hearing you."
        );
      }
      if (running.fellBack) {
        out.push("The chosen microphone is no longer available; the default one is being used.");
      }
      return out;
    },

    async askForMicrophone() {
      this.micRefused = "";
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Only for the permission and the names: let go at once, so the
        // browser does not show the microphone as in use while idle.
        stream.getTracks().forEach((track) => track.stop());
      } catch (e) {
        this.micRefused = FAILURES[e && e.name] || "The microphone could not be opened.";
      }
      await this.listDevices();
    },

    rememberDevice() {
      try {
        window.localStorage.setItem(DEVICE_KEY, this.deviceId);
      } catch (e) {
        /* only a convenience */
      }
    },

    async listDevices() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
      try {
        const found = await navigator.mediaDevices.enumerateDevices();
        // Names are withheld until the microphone has been granted once, and
        // a list of "Microphone 1, Microphone 2" is not a choice anyone can
        // make -- so the picker only appears when there are names.
        this.devices = found.filter((d) => d.kind === "audioinput" && d.label);
        if (!this.devices.some((d) => d.deviceId === this.deviceId)) {
          this.deviceId = this.devices.length ? this.devices[0].deviceId : "";
        }
      } catch (e) {
        this.devices = [];
      }
    },

    async estimate() {
      const room = await this.engine.storageEstimate();
      if (!room) return;
      const bytesPerHour = (window.ScribeRecorder.BITRATE / 8) * 3600;
      this.freeHours = room.free / bytesPerHour;
    },

    async start(opts) {
      if (this.live || this.starting) return;
      this.starting = true;
      this.status = "";
      this.awayMs = 0;

      try {
        const running = await this.engine.startRecording(
          Object.assign({ name: this.name || this.defaultName, deviceId: this.deviceId }, opts || {})
        );
        this.name = "";
        this.follow(running);
        this.listDevices();
        this.status = "Recording. It is saved in this browser as it is recorded.";
      } catch (e) {
        this.status = FAILURES[e && e.name] || "Could not start recording: " + ((e && (e.name || e.message)) || e);
      } finally {
        this.starting = false;
      }
    },

    follow(running) {
      this.levels = [];
      this.live = true;
      this.redraw();

      if (this.ticker) clearInterval(this.ticker);
      this.ticker = setInterval(() => {
        this.elapsed = running.elapsedMs();
        this.savedMs = running.savedMs();
        this.levels.push(running.paused ? 0 : running.level());
        if (this.levels.length > METER_SAMPLES) this.levels.shift();
        this.drawMeter();
      }, METER_MS);

      running.done.then((result) => {
        clearInterval(this.ticker);
        this.ticker = null;
        this.live = false;
        this.stopArmed = false;
        this.paused = false;
        this.levels = [];
        this.drawMeter();

        if (result && result.empty) {
          this.status = "Nothing was recorded.";
        } else if (result && result.interrupted) {
          this.status =
            "The recording stopped unexpectedly – the microphone was taken by another app or a call. Everything up to " +
            clock(result.meta.durationMs) +
            " is saved below.";
        } else if (result) {
          this.status = "Stopped. Listen to it, download the original, or upload it for transcription below.";
          this.openId = null;
        }
        this.elapsed = 0;
        this.redraw();
        this.leaveIfSignedOut();
      });
    },

    togglePause() {
      const running = this.engine.session();
      if (!running) return;
      if (running.paused) running.resume();
      else running.pause();
      this.redraw();
    },

    stop() {
      const running = this.engine.session();
      if (!running) return;
      if (!this.stopArmed) {
        this.stopArmed = true;
        clearTimeout(this.stopTimer);
        this.stopTimer = setTimeout(() => (this.stopArmed = false), 4000);
        return;
      }
      clearTimeout(this.stopTimer);
      this.stopArmed = false;
      running.stop();
    },

    continueFrom(item) {
      const base = item.name.replace(/ \(part \d+\)$/, "");
      const part = (item.name.match(/ \(part (\d+)\)$/) || [0, "1"])[1];
      this.start({ name: base + " (part " + (Number(part) + 1) + ")", follows: item.id });
    },

    rename(item, value) {
      clearTimeout(this.renameTimer);
      this.renameTimer = setTimeout(() => this.engine.rename(item.id, value), 300);
    },

    upload(item) {
      this.engine.submit(item.id);
    },

    retryNow(item) {
      this.engine.kick(item.id);
    },

    async togglePlay(item) {
      if (this.playUrl) {
        URL.revokeObjectURL(this.playUrl);
        this.playUrl = null;
      }
      if (this.openId === item.id) {
        this.openId = null;
        return;
      }
      const blob = await this.engine.blob(item.id);
      if (!blob) return;
      this.openId = item.id;
      this.playUrl = URL.createObjectURL(blob);
    },

    // A webm straight out of MediaRecorder carries no duration, and Chrome
    // answers Infinity until the player has been seeked once -- which leaves
    // the player unable to scrub.  Seeking far past the end makes it work
    // the duration out; the position is put back before anyone sees it.
    fixDuration(event) {
      const player = event.target;
      if (player.duration !== Infinity) return;
      player.currentTime = 1e101;
      player.ontimeupdate = () => {
        player.ontimeupdate = null;
        player.currentTime = 0;
      };
    },

    async save(item) {
      const blob = await this.engine.blob(item.id);
      if (!blob) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = this.engine.fileName(item);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    },

    discard(item) {
      if (this.discardArmed !== item.id) {
        this.discardArmed = item.id;
        clearTimeout(this.discardTimer);
        this.discardTimer = setTimeout(() => (this.discardArmed = null), 4000);
        return;
      }
      clearTimeout(this.discardTimer);
      this.discardArmed = null;
      if (this.openId === item.id) this.togglePlay(item);
      this.engine.discard(item.id);
    },

    leaveIfSignedOut() {
      if (!this.sessionEnded || !this.logoutUrl) return;
      if (this.engine && this.engine.session()) return;
      window.location.href = this.logoutUrl;
    },

    reloadPage() {
      window.location.reload();
    },

    goToFiles() {
      window.location.href = this.filesUrl;
    },

    visibilityChanged() {
      if (!this.engine || !this.engine.session()) {
        this.hiddenSince = null;
        return;
      }
      if (document.visibilityState === "hidden") {
        this.hiddenSince = Date.now();
      } else if (this.hiddenSince) {
        this.awayMs = Date.now() - this.hiddenSince;
        this.hiddenSince = null;
        this.redraw();
      }
    },

    tone(item) {
      if (item.elsewhere) return "live";
      if (item.state === "uploaded") return "ok";
      if (item.error) return "danger";
      const phase = item.sync.phase;
      if (phase === "auth" || phase === "offline" || phase === "unavailable") return "warn";
      if (item.interrupted && !item.submit) return "warn";
      return "muted";
    },

    icon(item) {
      if (item.elsewhere) return "fiber_manual_record";
      if (item.state === "uploaded") return "check_circle";
      if (item.error) return "error";
      switch (item.sync.phase) {
        case "uploading":
        case "queued":
          return "cloud_upload";
        case "offline":
          return "cloud_off";
        case "auth":
          return "lock";
        case "unavailable":
          return "schedule";
      }
      return item.interrupted ? "warning" : "save";
    },

    describe(item) {
      if (item.elsewhere) return "Being recorded in another tab";
      if (item.state === "uploaded") {
        return "Uploaded, can be downloaded until " + this.when(item.uploadedAt + window.ScribeRecorder.KEEP_UPLOADED_MS);
      }
      if (item.error) return item.error + " It is still saved in this browser.";

      const sync = item.sync || {};
      const retry = sync.retryAt ? " Trying again in " + Math.max(1, Math.round((sync.retryAt - Date.now()) / 1000)) + " s." : "";

      if (item.submit) {
        switch (sync.phase) {
          case "uploading":
            return sync.total ? "Uploading " + Math.round((100 * (sync.sent || 0)) / sync.total) + "%" : "Uploading";
          case "offline":
            return "Waiting for a connection. Saved in this browser." + retry;
          case "auth":
            return "Signed out. Sign in again to finish the upload – it is saved in this browser.";
          case "unavailable":
            return (sync.message || "Scribe is not answering right now.") + " Saved in this browser." + retry;
          case "elsewhere":
            return "Being uploaded from another tab";
          default:
            return "Waiting to upload";
        }
      }

      if (item.interrupted) {
        return "Stopped unexpectedly – everything up to here is saved. Not uploaded yet.";
      }
      return "Not uploaded yet";
    },

    // Thirty seconds of level, newest on the right.  A canvas cannot read a
    // stylesheet, so the colours come from the theme's custom properties.
    drawMeter() {
      const canvas = this.$refs.meter;
      if (!canvas) return;
      const ratio = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
      const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      const c = canvas.getContext("2d");
      c.clearRect(0, 0, width, height);

      const style = getComputedStyle(canvas);
      // At rest a row of short, quiet bars: says where the level will be
      // drawn without pretending to be one.
      const levels = this.levels.length ? this.levels : null;
      c.fillStyle = !levels || this.paused
        ? style.getPropertyValue("--recorder-meter-paused").trim() || "#9ca3af"
        : style.getPropertyValue("--recorder-meter").trim() || "#d32f2f";

      const bar = Math.max(2, Math.round(2 * ratio));
      const step = bar * 2;
      const columns = Math.floor(width / step);
      const shown = levels ? levels.slice(-columns) : new Array(Math.min(columns, 40)).fill(0.004);
      const offset = levels ? columns - shown.length : Math.floor((columns - shown.length) / 2);
      const middle = height / 2;

      shown.forEach((level, i) => {
        // A square root, so quiet speech across a room still shows as
        // something rather than a flat line.
        const tall = Math.max(ratio, Math.sqrt(level) * (height - 8 * ratio));
        const x = (offset + i) * step;
        if (c.roundRect) {
          c.beginPath();
          c.roundRect(x, middle - tall / 2, bar, tall, bar / 2);
          c.fill();
        } else {
          c.fillRect(x, middle - tall / 2, bar, tall);
        }
      });
    },
  },
};

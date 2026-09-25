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
//   - **One filled action at a time** (Start, then Stop), large enough for a
//     thumb, so what the page is for is never in question.  Stopping is
//     finishing: the recording goes to Scribe by itself.
//   - **Stop asks twice.**  A phone in a hand or a pocket gets tapped, and a
//     stopped lecture cannot be un-stopped -- only continued in a new part.
//   - **It says where the recording is**: seconds kept on this device, and
//     how much of it Scribe already has.  "Sent to Scribe" is the
//     reassurance a professor needs before walking away from the phone.
//   - **It says when something is wrong, in words**: the microphone paused
//     by the phone, storage full, the screen allowed to lock, signed out.
//     None of these stop the page; each changes what the reader should do.
//
// The level meter is drawn from a live analyser on the stream already open
// -- never by decoding the recording, which for an hour is over a gigabyte of
// PCM.  Nothing is played back here: the recording leaves this browser when
// it stops, and its original is downloaded from My files.

const METER_MS = 100;
// Which microphone was chosen last, remembered per browser.
const DEVICE_KEY = "scribe-recorder-device";
// Set once the reader has closed the "Before you record" note.
const NOTICE_KEY = "scribe-recorder-notice-dismissed";
const METER_SAMPLES = 300; // thirty seconds of level history
// The sample the audio test records to play back: long enough for a
// sentence, short enough to be kept in memory without a thought.
const TEST_SAMPLE_MS = 5000;
// The verdict on the level reads back over a window of meter samples rather
// than the instant, since speech has gaps: a second and a half while
// testing, three seconds while recording, where a speaker pausing for
// breath must not be told the microphone has gone.
const TEST_WINDOW = 15;
const LIVE_WINDOW = 30;
// How fast the bar falls back, in dB per meter tick, so it does not flicker
// to nothing between words.  The peak marker lingers longer.
const LEVEL_FALL = 3.6;
const PEAK_FALL = 1.8;
// The same capture the recorder asks for (static/recorder_engine.js), so
// what the test hears is what a recording would.
const CAPTURE = { echoCancellation: false, noiseSuppression: false, autoGainControl: true };

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
  NoKey: "Scribe could not be reached to start recording. Check the connection and try again.",
};

// NiceGUI reloads the page by itself in four places: a reconnect attempt
// that times out (nicegui.js, "reloading because connection timed out" --
// which is exactly what a computer waking from sleep, or a laptop between
// two wifi networks, runs into), a handshake the server refuses, a
// reconnect the server asks for, and -- from the server, as a plain
// run_javascript -- a reconnect whose missed messages it can no longer
// replay (outbox.py, try_rewind).  A reload stops the MediaRecorder.  What
// was recorded is safe either way, but a lecture must not be cut in two
// because the wifi went for a minute.
//
// So while a recording runs, those four are answered here instead: the
// socket goes on reconnecting by itself, a handshake is made without the
// reload behind it, and anything that really needs a fresh page is put off
// until the recording has stopped -- and then only offered, not done,
// since nothing on this page needs the socket to go on working: recording
// and uploading are both the browser's own.  Every other moment the
// original handlers run untouched.  Pinned against the NiceGUI release in
// tests/test_recording.py, since it reaches into nicegui.js.
const RELOAD_EVENTS = ["connect", "connect_error", "try_reconnect", "run_javascript"];
// What the server sends when it cannot replay a reconnect's missed messages.
const SERVER_RELOAD = "window.location.reload()";

function guardReloads(busy, onStale, onConnected) {
  const socket = window.socket;
  if (!socket || socket.__scribeGuarded) return !!socket;
  socket.__scribeGuarded = true;

  const original = {};
  RELOAD_EVENTS.forEach((event) => {
    original[event] = socket.listeners(event).slice();
    socket.off(event);
  });
  const passOn = (event, args) => original[event].forEach((handler) => handler(...args));
  // A page that is stale -- above all one whose client the server no longer
  // has, after a restart -- never reconnects: socket.io does not retry a
  // refused connection.  NiceGUI's "Connection lost" popup would stay up for
  // good, over a recording that is going on fine; the page says so itself.
  const stale = () => {
    const popup = document.getElementById("popup");
    if (popup) popup.ariaHidden = true;
    onStale();
  };

  // Whether the page is connected right now, for the banner shown while
  // recording: stale is for good, a lost connection is not.  Plain
  // listeners, next to the replaced ones rather than instead of them.
  onConnected(socket.connected);
  socket.on("connect", () => onConnected(true));
  socket.on("disconnect", () => onConnected(false));

  // nicegui.js puts next_message_id in the socket's query once, at page
  // load, and never moves it on -- so every reconnect asks the server to
  // replay from the very first message, long since pruned by the acks, and
  // the server answers with a reload.  That is what showed the stale banner
  // after every wifi drop that recovered fine.  Telling it where the page
  // really is lets it replay only what was missed; a reload then means the
  // messages really are gone.
  if (socket.io) {
    socket.io.on("reconnect_attempt", () => {
      const query = socket.io.opts && socket.io.opts.query;
      if (query && window.nextMessageId !== undefined) query.next_message_id = window.nextMessageId;
    });
  }

  socket.on("connect_error", (...args) => {
    const error = args[0] || {};
    if (busy() && error.message === "timeout") {
      // socket.io keeps trying on its own; only the reload is skipped.  Not
      // stale: the reconnect that follows either succeeds -- the page is
      // whole again -- or is refused, and that refusal says so itself.
      return;
    }
    if (busy() && error.message === "Implicit handshake failed") {
      stale();
      return;
    }
    passOn("connect_error", args);
  });

  socket.on("run_javascript", (...args) => {
    const message = args[0] || {};
    if (busy() && typeof message.code === "string" && message.code.trim() === SERVER_RELOAD) {
      // Passed on emptied rather than dropped: nicegui.js's own handler is
      // what keeps count of the messages it has had.
      stale();
      args[0] = Object.assign({}, message, { code: "undefined" });
    }
    passOn("run_javascript", args);
  });

  socket.on("try_reconnect", (...args) => {
    if (busy()) {
      stale();
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
        stale();
        return;
      }
      window.did_handshake = true;
      const popup = document.getElementById("popup");
      if (popup) popup.ariaHidden = true;
    });
  });

  return true;
}

const toDb = (value) => (value > 0 ? Math.max(-60, 20 * Math.log10(value)) : -60);
const fallTo = (shown, now, fall) => (now > shown ? now : Math.max(-60, shown - fall));

// What the reader should do about the level, in words, from recent peaks.
function levelVerdict(levels, window, paused) {
  if (paused) return { tone: "muted", icon: "pause", text: "Paused." };
  const recent = levels.slice(-window);
  if (recent.length < window) {
    return { tone: "muted", icon: "hearing", text: "Listening… say something." };
  }
  const loudest = Math.max(...recent);
  if (loudest >= 0.98) {
    return { tone: "danger", icon: "volume_up", text: "Too loud – the sound is clipping. Move the microphone further away." };
  }
  const db = loudest > 0 ? 20 * Math.log10(loudest) : -100;
  if (db < -50) {
    return { tone: "warn", icon: "volume_off", text: "Almost nothing is heard. Check that this is the right audio source, and that it is not muted." };
  }
  if (db < -30) {
    return { tone: "warn", icon: "volume_down", text: "Quiet. Speak up, or move the microphone closer to whoever is speaking." };
  }
  return { tone: "ok", icon: "check_circle", text: "Good level." };
}

// The level in dB with a peak marker, and the verdict under it.  One piece,
// used by the recording itself and by Test audio, so the two always read
// the same way.
const LevelMeter = {
  props: {
    db: { type: Number, default: -60 },
    peakDb: { type: Number, default: -60 },
    verdict: { type: Object, required: true },
    // In words too: Test audio only.  While recording the bar is enough,
    // and a sentence changing under the button every few seconds is not
    // something anyone should be reading in the middle of a lecture.
    words: { type: Boolean, default: true },
  },
  computed: {
    percent() {
      return Math.max(0, Math.min(100, ((this.db + 60) / 60) * 100));
    },
    peakPercent() {
      return Math.max(0, Math.min(100, ((this.peakDb + 60) / 60) * 100));
    },
  },
  template: `
    <div class="recorder-level">
      <div
        class="recorder-test-bar"
        role="meter"
        aria-label="Sound level"
        aria-valuemin="-60"
        aria-valuemax="0"
        :aria-valuenow="Math.round(db)"
        :aria-valuetext="Math.round(db) + ' dB'"
      >
        <div class="recorder-test-bar-fill" :class="'is-' + verdict.tone" :style="{ width: percent + '%' }"></div>
        <div class="recorder-test-bar-peak" :style="{ left: peakPercent + '%' }"></div>
      </div>
      <div class="recorder-test-scale" aria-hidden="true">
        <span>−60 dB</span><span>−30</span><span>0 dB</span>
      </div>
      <div v-if="words" class="recorder-test-verdict" :class="'is-' + verdict.tone" role="status" aria-live="polite">
        <q-icon :name="verdict.icon" size="18px" aria-hidden="true" />
        {{ verdict.text }}
      </div>
    </div>
  `,
};

export default {
  components: { LevelMeter },

  template: `
    <div class="recorder">
      <div v-if="unsupported" class="recorder-banner recorder-banner-danger" role="alert">
        {{ unsupported }}
      </div>

      <div v-if="sessionEnded" class="recorder-banner recorder-banner-warn" role="alert">
        You have been signed out. The recording goes on and is saved in this browser; when you
        stop it you are taken to sign in again, and it is sent to Scribe once you have.
      </div>

      <div v-if="!persistent" class="recorder-banner recorder-banner-danger" role="alert">
        This browser does not let Scribe save recordings while they are made (a private
        window?). If this page closes, whatever has not yet reached Scribe is lost.
      </div>

      <!-- Stands in for NiceGUI's own "Connection lost" popup, which
           guardReloads() hides once the page is stale: that popup never
           goes away by itself then, and the recording is not affected.
           Gone again once the socket is back. -->
      <div v-if="stale && live && !connected" class="recorder-banner recorder-banner-warn" role="status">
        The connection to Scribe was interrupted. Recording and uploading carry on; reload the
        page after you stop to reconnect the rest of Scribe.
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
          <level-meter v-if="live" :db="liveDb" :peak-db="livePeakDb" :verdict="liveVerdict" :words="false" />
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
            <q-icon :name="sentMs ? 'cloud_done' : 'cloud_queue'" size="16px" aria-hidden="true" />
            Sent to Scribe: {{ sentMs ? clock(sentMs) : "not yet" }}
          </span>
          <span v-if="liveMeta.spilled" class="recorder-safety-item">
            <q-icon name="save" size="16px" aria-hidden="true" />
            Kept in this browser until it can be sent: {{ clock(Math.max(0, savedMs - sentMs)) }}
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
            <label :for="deviceSelectId" class="recorder-setting-label">Audio source</label>
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

        <!-- Said on the page, not only in the help: it is the one thing
             to settle before pressing Start, and nobody opens the help
             first.  Informational, so not a warning banner.  Closed, it
             stays closed in this browser; the same words remain in the
             help under Privacy and security. -->
        <aside v-if="!live && !noticeDismissed" class="recorder-notice" aria-labelledby="recorder-notice-title">
          <q-icon name="record_voice_over" size="22px" class="recorder-notice-icon" aria-hidden="true" />
          <div>
            <h2 id="recorder-notice-title" class="recorder-notice-title">Before you press Start recording</h2>
            <p class="recorder-notice-text">
              Make sure everyone knows they are being recorded.
              Follow your organisation's requirements for permission, information and handling of recordings.
            </p>
          </div>
          <q-btn
            flat
            round
            dense
            size="sm"
            icon="close"
            class="recorder-quiet recorder-notice-close"
            aria-label="Dismiss this note"
            @click="dismissNotice"
          />
        </aside>

        <div v-if="!live" class="recorder-help-row">
          <q-btn
            flat
            no-caps
            dense
            class="recorder-quiet"
            icon="graphic_eq"
            label="Test audio"
            :disable="!!micRefused && !devices.length"
            @click="openTest"
          />
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

        <!-- Hearing the microphone before the lecture starts, rather than
             finding out afterwards that it recorded the ventilation.  What
             is recorded here is kept in memory for playing back and is
             gone when the dialog closes: never stored, never sent. -->
        <q-dialog v-model="testOpen" aria-labelledby="recorder-test-title" @hide="closeTest">
          <q-card class="recorder-test-card">
            <q-card-section>
              <h2 id="recorder-test-title" class="recorder-help-title">Test audio</h2>
              <p class="recorder-test-intro">Speak as you will while recording, from where you will be. The meter shows what the microphone hears.</p>

              <div class="recorder-setting">
                <label :for="testSelectId" class="recorder-setting-label">Audio source</label>
                <select
                  :id="testSelectId"
                  v-model="deviceId"
                  class="recorder-field"
                  :disabled="!devices.length || testState === 'recording'"
                  @change="testDeviceChanged"
                >
                  <option v-if="!devices.length" value="">Not available</option>
                  <option v-for="d in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label }}</option>
                </select>
              </div>

              <div v-if="testError" class="recorder-banner recorder-banner-warn q-mt-md" role="alert">{{ testError }}</div>

              <template v-else>
                <canvas ref="testMeter" class="recorder-meter recorder-test-history" aria-hidden="true"></canvas>
                <level-meter :db="testDb" :peak-db="testPeakDb" :verdict="testVerdict" />

                <div class="recorder-test-sample">
                  <q-btn
                    outline
                    no-caps
                    class="recorder-secondary recorder-small"
                    :icon="testState === 'recording' ? 'stop' : 'fiber_manual_record'"
                    :label="testState === 'recording' ? 'Recording… ' + Math.ceil(testLeftMs / 1000) + ' s' : 'Record 5 seconds and listen'"
                    :disable="!testStream"
                    @click="testState === 'recording' ? stopSample() : recordSample()"
                  />
                  <audio
                    v-if="testUrl"
                    class="recorder-test-player"
                    controls
                    playsinline
                    :src="testUrl"
                    aria-label="Test recording"
                  ></audio>
                </div>
              </template>
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat no-caps label="Done" color="black" v-close-popup />
            </q-card-actions>
          </q-card>
        </q-dialog>

        <q-dialog v-model="helpOpen" aria-labelledby="recorder-help-title">
          <q-card class="recorder-help-card">
            <q-card-section>
              <h2 id="recorder-help-title" class="recorder-help-title">How recording works</h2>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Before you start</h3>
                <p>Choose the microphone you want to use under Audio source.</p>
                <p>Check the audio level while you speak. If you want to make sure the recording sounds good, use Test audio to record and play back a short test.</p>
                <p>Place the microphone close to whoever is speaking. For a long recording, connect your device to a charger.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Start recording</h3>
                <p>Select Start recording to begin.</p>
                <p>Keep this page open while recording. On a computer, prevent it from going to sleep. On a phone or tablet, keep the screen on. Scribe asks the device to stay awake for you, but some devices may still turn the screen off.</p>
                <p>You can see how long you have been recording on the timer.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Stop recording</h3>
                <p>Select Stop recording when you are finished.</p>
                <p>Sunet Scribe completes the upload and the recording appears in My files. You can then transcribe it in the same way as any other audio file.</p>
                <p>Do not close the page until Sunet Scribe confirms that the recording has been saved.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">If something goes wrong</h3>
                <p>Sunet Scribe saves the recording continuously while you record. When you are online, recorded audio is sent to Sunet Scribe every few seconds.</p>
                <p>If the connection is lost, recording continues in this browser and uploading resumes when the connection returns.</p>
                <p>If the browser or device crashes, open this page again. Sunet Scribe will recover anything that had already reached the service or was saved in this browser. While connected, only the last few seconds may be lost.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Your original recording</h3>
                <p>Once a recording is in My files it is no longer listed here. Sunet Scribe keeps the original recording in My files for 7 days, just like other uploaded files, marked as a recording. Download it or delete it from My files.</p>
              </div>
              <div class="recorder-help-section">
                <h3 class="recorder-help-heading">Privacy and security</h3>
                <p>Make sure everyone knows they are being recorded. Follow your organisation's requirements for permission, information and handling of recordings.</p>
                <p>While you are online, recorded audio is sent to Sunet Scribe over an encrypted connection and stored encrypted under your account.</p>
                <p>If audio cannot be sent immediately, it is temporarily stored in this browser. It is encrypted using a key provided by Sunet Scribe while you are signed in and is removed from the browser after it has been successfully sent.</p>
                <p>Locally stored audio can only be recovered in this browser, and only for a limited time. If you clear this browser's cookies or site data, or do not open Sunet Scribe in this browser for 14 days, the audio can no longer be recovered and is lost. Open this page again as soon as you are back online so the recording can be sent.</p>
                <p>Anyone who can use this browser may be able to access locally stored recordings while you are signed in. Avoid leaving unfinished recordings on a shared device.</p>
                <p>A downloaded recording is an ordinary file on your device. Store and handle it according to your organisation's requirements.</p>
              </div>
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat no-caps label="Close" color="black" v-close-popup />
            </q-card-actions>
          </q-card>
        </q-dialog>
      </template>

      <section v-if="others.length" class="recorder-list" aria-labelledby="recorder-list-heading">
        <h2 id="recorder-list-heading" class="recorder-list-heading">Recordings</h2>

        <article
          v-for="item in others"
          :key="item.id"
          class="recorder-item"
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
              v-if="!item.elsewhere && item.state !== 'uploaded' && !(item.submit && !item.error)"
              flat
              no-caps
              dense
              :round="discardArmed !== item.id"
              class="recorder-quiet recorder-discard"
              :class="{ 'is-armed': discardArmed === item.id }"
              icon="delete"
              :label="discardArmed === item.id ? 'Press again to delete' : undefined"
              :aria-label="discardArmed === item.id ? 'Confirm: delete ' + item.name : 'Delete ' + item.name"
              @click="discard(item)"
            >
              <q-tooltip v-if="discardArmed !== item.id">Delete</q-tooltip>
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
          </div>
        </article>

      </section>
    </div>
  `,

  props: {
    owner: { type: String, required: true },
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
      sentMs: 0,
      warnings: [],
      status: "",
      unsupported: "",
      persistent: true,
      devices: [],
      deviceId: "",
      deviceSelectId: "recorder-device-" + Math.random().toString(36).slice(2),
      nameInputId: "recorder-name-" + Math.random().toString(36).slice(2),
      stopArmed: false,
      discardArmed: null,
      freeHours: null,
      helpOpen: false,
      noticeDismissed: false,
      stale: false,
      connected: true,
      micRefused: "",
      hiddenSince: null,
      awayMs: 0,
      levels: [],
      announced: new Set(),
      liveDb: -60,
      livePeakDb: -60,
      testOpen: false,
      testSelectId: "recorder-test-device-" + Math.random().toString(36).slice(2),
      testStream: null,
      testLevels: [],
      testDb: -60,
      testPeakDb: -60,
      testError: "",
      testState: "idle",
      testLeftMs: 0,
      testUrl: null,
    };
  },

  computed: {
    testVerdict() {
      return levelVerdict(this.testLevels, TEST_WINDOW, false);
    },
    liveVerdict() {
      return levelVerdict(this.levels, LIVE_WINDOW, this.paused);
    },
    // Only what has not reached My files yet.  A recording that has is
    // downloaded and deleted there, like any other file.
    others() {
      return this.items.filter((item) => !item.live && item.state !== "uploaded");
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
      this.noticeDismissed = window.localStorage.getItem(NOTICE_KEY) === "1";
    } catch (e) {
      this.noticeDismissed = false;
    }

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
        },
        (connected) => {
          this.connected = connected;
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
    this.closeTest();
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
        const sent = (running.meta.sent || []).length;
        this.sentMs = Math.min(this.savedMs, sent * window.ScribeRecorder.PART_CHUNKS * window.ScribeRecorder.CHUNK_MS);
      }

      this.warnings = this.currentWarnings(running);

      // A recording has just become a job and leaves this list: said once,
      // in words, so it does not simply vanish.
      for (const item of this.items) {
        if (item.state !== "uploaded" || this.announced.has(item.id)) continue;
        this.announced.add(item.id);
        this.status = "“" + item.name + "” is in My files, ready to transcribe.";
      }
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
      const mine = this.items.find((item) => item.id === running.meta.id);
      const sync = (mine && mine.sync) || {};
      if (["offline", "auth", "unavailable", "error"].includes(sync.phase)) {
        out.push(
          "Not reaching Scribe right now: " +
            (sync.message || "no answer") +
            " The recording is still being saved in this browser and is sent as soon as Scribe can be reached."
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

    dismissNotice() {
      this.noticeDismissed = true;
      try {
        window.localStorage.setItem(NOTICE_KEY, "1");
      } catch (e) {
        /* only a convenience: it comes back on the next visit */
      }
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

    // -- Test audio --

    async openTest() {
      this.testOpen = true;
      this.testError = "";
      await this.startTest();
    },

    async startTest() {
      this.stopTestStream();
      this.testLevels = [];
      this.testDb = -60;
      this.testPeakDb = -60;
      try {
        this.testStream = await navigator.mediaDevices.getUserMedia({
          audio: this.deviceId ? Object.assign({ deviceId: { exact: this.deviceId } }, CAPTURE) : CAPTURE,
        });
      } catch (e) {
        this.testError = FAILURES[e && e.name] || "The microphone could not be opened.";
        return;
      }
      await this.listDevices();

      const AudioContextImpl = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextImpl) {
        this.testError = "This browser cannot show a sound level.";
        return;
      }
      this.testAudio = new AudioContextImpl();
      const analyser = this.testAudio.createAnalyser();
      analyser.fftSize = 2048;
      this.testAudio.createMediaStreamSource(this.testStream).connect(analyser);
      const samples = new Float32Array(analyser.fftSize);

      // Drawn every frame; the history the verdict reads moves on at the
      // main meter's own rate, so the two look the same.
      let lastSample = 0;
      const frame = (time) => {
        if (!this.testStream) return;
        analyser.getFloatTimeDomainData(samples);
        let peak = 0;
        let sum = 0;
        for (let i = 0; i < samples.length; i++) {
          const value = Math.abs(samples[i]);
          if (value > peak) peak = value;
          sum += samples[i] * samples[i];
        }
        // Every frame here, so the fall is a sixth of a meter tick's.
        this.testDb = fallTo(this.testDb, toDb(Math.sqrt(sum / samples.length)), LEVEL_FALL / 6);
        this.testPeakDb = fallTo(this.testPeakDb, toDb(peak), PEAK_FALL / 6);
        if (time - lastSample >= METER_MS) {
          lastSample = time;
          this.testLevels.push(peak);
          if (this.testLevels.length > METER_SAMPLES) this.testLevels.shift();
        }
        this.drawLevels(this.$refs.testMeter, this.testLevels, false);
        this.testFrame = requestAnimationFrame(frame);
      };
      this.testFrame = requestAnimationFrame(frame);
    },

    testDeviceChanged() {
      this.rememberDevice();
      this.discardSample();
      this.startTest();
    },

    recordSample() {
      if (!this.testStream || !window.MediaRecorder) return;
      this.discardSample();
      const pieces = [];
      const recorder = new MediaRecorder(this.testStream);
      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size) pieces.push(event.data);
      };
      recorder.onstop = () => {
        clearInterval(this.testCountdown);
        this.testState = "idle";
        if (pieces.length && this.testOpen) {
          this.testUrl = URL.createObjectURL(new Blob(pieces, { type: recorder.mimeType || "audio/webm" }));
        }
      };
      this.testRecorder = recorder;
      this.testState = "recording";
      this.testLeftMs = TEST_SAMPLE_MS;
      recorder.start();
      const began = Date.now();
      this.testCountdown = setInterval(() => {
        this.testLeftMs = Math.max(0, TEST_SAMPLE_MS - (Date.now() - began));
        if (this.testLeftMs === 0) this.stopSample();
      }, 200);
    },

    stopSample() {
      clearInterval(this.testCountdown);
      if (this.testRecorder && this.testRecorder.state !== "inactive") this.testRecorder.stop();
      this.testRecorder = null;
    },

    discardSample() {
      if (this.testUrl) URL.revokeObjectURL(this.testUrl);
      this.testUrl = null;
    },

    stopTestStream() {
      if (this.testFrame) cancelAnimationFrame(this.testFrame);
      this.testFrame = null;
      if (this.testStream) this.testStream.getTracks().forEach((track) => track.stop());
      this.testStream = null;
      if (this.testAudio) {
        try {
          this.testAudio.close();
        } catch (e) {
          /* already closed */
        }
      }
      this.testAudio = null;
    },

    // The microphone is let go the moment the dialog closes, and the
    // sample goes with it: nothing from the test outlives it.
    closeTest() {
      this.stopSample();
      this.stopTestStream();
      this.discardSample();
      this.testState = "idle";
      this.testLevels = [];
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
        this.status = "Recording. It is sent to Scribe as it is recorded.";
      } catch (e) {
        this.status = FAILURES[e && e.name] || "Could not start recording: " + ((e && (e.name || e.message)) || e);
      } finally {
        this.starting = false;
      }
    },

    follow(running) {
      this.levels = [];
      this.liveDb = -60;
      this.livePeakDb = -60;
      this.live = true;
      this.redraw();

      if (this.ticker) clearInterval(this.ticker);
      this.ticker = setInterval(() => {
        this.elapsed = running.elapsedMs();
        this.savedMs = running.savedMs();
        const loud = running.paused ? { peak: 0, rms: 0 } : running.loudness();
        this.levels.push(loud.peak);
        this.liveDb = fallTo(this.liveDb, toDb(loud.rms), LEVEL_FALL);
        this.livePeakDb = fallTo(this.livePeakDb, toDb(loud.peak), PEAK_FALL);
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
          this.status = "Stopped. It is going to My files in Scribe, ready to transcribe.";
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

    discard(item) {
      if (this.discardArmed !== item.id) {
        this.discardArmed = item.id;
        clearTimeout(this.discardTimer);
        this.discardTimer = setTimeout(() => (this.discardArmed = null), 4000);
        return;
      }
      clearTimeout(this.discardTimer);
      this.discardArmed = null;
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
        case "finishing":
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
      if (item.state === "uploaded") return "In My files, ready to transcribe";
      if (item.error) return item.error;

      const sync = item.sync || {};
      const retry = sync.retryAt ? " Trying again in " + Math.max(1, Math.round((sync.retryAt - Date.now()) / 1000)) + " s." : "";

      if (item.submit) {
        switch (sync.phase) {
          case "uploading":
            return sync.total ? "Sending to Scribe " + Math.round((100 * (sync.sent || 0)) / sync.total) + "%" : "Sending to Scribe";
          case "finishing":
            return "Handing over to Scribe";
          case "offline":
            return "Waiting for a connection. Saved in this browser." + retry;
          case "auth":
            return "Signed out. Sign in again to send the rest – it is saved in this browser.";
          case "unavailable":
            return (sync.message || "Scribe is not answering right now.") + " Saved in this browser." + retry;
          case "elsewhere":
            return "Being sent from another tab";
          default:
            return "Waiting to be sent";
        }
      }

      if (item.interrupted) {
        return "Stopped unexpectedly – everything up to here is saved. Upload it, or continue recording in a new part.";
      }
      return "Not sent yet";
    },

    // Thirty seconds of level, newest on the right.  A canvas cannot read a
    // stylesheet, so the colours come from the theme's custom properties.
    drawMeter() {
      this.drawLevels(this.$refs.meter, this.levels, this.paused);
    },

    drawLevels(canvas, history, paused) {
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
      const levels = history.length ? history : null;
      c.fillStyle = !levels || paused
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

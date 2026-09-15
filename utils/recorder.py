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
Recording straight into the upload dialog.

The whole gesture is wired in the page rather than through Python handlers:
getUserMedia wants the click that asked for it, and a round trip to the server
and back is not that click any more.  A recording is finished by being handed
to the same `ui.upload` a dropped file goes to, so progress, naming, the
temporary table row and the upload itself all stay one code path.

**The waveform is the card.**  It is tall enough to actually read, and the
clock and the recording marker sit *inside* it rather than in a caption
underneath, so there is one thing to look at rather than four.  The card shows
**exactly one filled action at a time** -- Start recording, then Stop, then Use
recording -- and everything else is a quiet control, so what the card is for is
never in question.  There is no `<audio controls>`: the browser's own player
was the loudest thing in the card and the least like the rest of the app, so
play is a button of ours and the waveform is the scrubber.

**The waveform is drawn from the live stream, never by decoding the
recording.**  An AnalyserNode on the stream that is already open costs
nothing, works for a recording of any length, and is the only thing on screen
saying the microphone is actually picking anything up while it runs -- and
`decodeAudioData` over an hour of audio costs more than a gigabyte of PCM,
which is the same reason the caption timeline draws speech runs rather than a
waveform (see `utils/speech_timeline.py`).  The peaks it collects are kept
after the recording stops and are what the preview draws, so nothing is
decoded there either.

**Nothing is uploaded until the reader says so.**  A recording is listened
back to first -- that is the whole point of the preview -- so "Use recording"
is what reaches the uploader, and "Record again" throws the take away.
"""

from nicegui import ui

# One peak per bucket, and the bucket decides how much of a recording the
# waveform can show: 100ms is fine enough that a spoken word is visible and
# coarse enough that an hour is 36000 floats rather than a gigabyte of PCM.
PEAK_MS = 100

SCRIPT = """
const startBtn = getHtmlElement(__START__);
const stopBtn = getHtmlElement(__STOP__);
const playBtn = getHtmlElement(__PLAY__);
const playIcon = getHtmlElement(__PLAY_ICON__);
const playText = getHtmlElement(__PLAY_TEXT__);
const useBtn = getHtmlElement(__USE__);
const againBtn = getHtmlElement(__AGAIN__);
const devices = getHtmlElement(__DEVICES__);
const canvas = getHtmlElement(__CANVAS__);
const hint = getHtmlElement(__HINT__);
const clock = getHtmlElement(__CLOCK__);
const live = getHtmlElement(__LIVE__);
const player = getHtmlElement(__PLAYER__);
const status = getHtmlElement(__STATUS__);
const upl = getElement(__UPLOAD__);
if (!startBtn || !stopBtn || !playBtn || !playIcon || !playText) return;
if (!useBtn || !againBtn || !devices || !canvas) return;
if (!hint || !clock || !live || !player || !status || !upl) return;

const show = (el, on) => { el.style.display = on ? '' : 'none'; };
const say = t => { status.textContent = t; };

// A microphone is only offered in a secure context -- https, or localhost in
// development.  In production TLS ends at the proxy and this app is plain
// http behind it, but the *browser* is on https, which is what decides this,
// so recording is available there.  The two ways it can be missing are told
// apart on purpose: over https the answer is never "use https", and a message
// that says so sends whoever reads it looking in the wrong place.
if (window.isSecureContext === false) {
  startBtn.disabled = true;
  say('Recording needs an https connection.');
  return;
}
if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia
    || typeof MediaRecorder === 'undefined') {
  startBtn.disabled = true;
  say('This browser cannot record audio.');
  return;
}

const kinds = [
  ['audio/webm;codecs=opus', '.webm'],
  ['audio/webm', '.webm'],
  ['audio/ogg;codecs=opus', '.ogg'],
  ['audio/mp4', '.mp4'],
];
const kind = kinds.find(k => MediaRecorder.isTypeSupported(k[0]));

let recorder = null, stream = null, audio = null, analyser = null;
let chunks = [], peaks = [], sampler = null, frame = null;
let started = 0, seconds = 0, take = null, url = null;
let deviceId = '';

const time = s => Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0');

const colour = (name, fallback) => {
  const value = getComputedStyle(document.body).getPropertyValue(name).trim();
  return value || fallback;
};

// Read per draw rather than cached: the palette follows the page's own theme
// custom properties, and a canvas cannot read a stylesheet.
const draw = progress => {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(canvas.clientWidth * ratio));
  const height = Math.max(1, Math.round(canvas.clientHeight * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const c = canvas.getContext('2d');
  c.clearRect(0, 0, width, height);

  const bar = Math.max(2, Math.round(2 * ratio));
  const step = Math.round(bar * 2);
  const columns = Math.max(1, Math.floor(width / step));
  const middle = height / 2;
  // While it runs the bars carry the same red as the REC marker beside them:
  // the two are saying one thing, and this is the one place in the app where
  // red means "in progress" rather than "wrong" -- which is why the word REC
  // is there to say it in words as well.
  const recording = progress === null;
  const played = recording
    ? colour('--color-text-danger', '#d32f2f')
    : colour('--color-brand-primary', '#082954');
  const rest = colour('--color-text-muted', '#6b7280');

  for (let i = 0; i < columns; i++) {
    // Every peak the column covers, so a loud moment cannot be drawn away by
    // a quiet neighbour that happened to be sampled.
    const from = Math.floor((i / columns) * peaks.length);
    const to = Math.max(from + 1, Math.floor(((i + 1) / columns) * peaks.length));
    if (from >= peaks.length) break;
    let peak = 0;
    for (let p = from; p < to && p < peaks.length; p++) {
      if (peaks[p] > peak) peak = peaks[p];
    }

    const tall = Math.max(ratio, peak * (height - 4 * ratio));
    c.fillStyle = (recording || (i / columns) <= progress) ? played : rest;
    c.beginPath();
    c.roundRect(i * step, middle - tall / 2, bar, tall, bar / 2);
    c.fill();
  }

  if (!recording && peaks.length) {
    c.fillStyle = played;
    c.fillRect(Math.min(width - 2 * ratio, progress * width), 0, Math.max(1, 2 * ratio), height);
  }
};

// One filled action at a time, and one place that says which.  Everything the
// card can show is named here rather than being hidden and shown from a dozen
// places, so a state that forgets an element is a change to one function.
const setState = state => {
  show(hint, state === 'idle');
  show(canvas, state !== 'idle');
  show(clock, state !== 'idle');
  show(live, state === 'recording');
  show(startBtn, state === 'idle');
  show(stopBtn, state === 'recording');
  show(playBtn, state === 'review');
  show(useBtn, state === 'review');
  show(againBtn, state === 'review');
  devices.disabled = state === 'recording';
  if (state !== 'review') {
    playIcon.textContent = 'play_arrow';
    playText.textContent = 'Play';
  }
};

// Which microphone, when there is a choice to be had.
//
// Two things decide whether this can be offered at all, and neither is ours:
// a browser reports **no device labels** until the microphone has been
// granted once for the origin -- a list reading "Microphone 1 / Microphone 2"
// is not a choice anyone can make -- and it reports one entry per input,
// which on most machines is a single built-in microphone.  So the picker is
// drawn only when the names are known *and* there is more than one of them;
// the rest of the time the browser's own default is used, silently.  It fills
// in by itself the moment the first recording is granted, and again whenever
// a device is plugged in or taken away.
const listDevices = async () => {
  if (!navigator.mediaDevices.enumerateDevices) return;
  let found = [];
  try {
    found = await navigator.mediaDevices.enumerateDevices();
  } catch (e) {
    return;
  }
  const mics = found.filter(d => d.kind === 'audioinput' && d.label);
  if (!mics.length) {
    show(devices, false);
    return;
  }
  const chosen = deviceId || devices.value;
  devices.textContent = '';
  mics.forEach(d => {
    const option = document.createElement('option');
    option.value = d.deviceId;
    // textContent, never innerHTML: a device name is whatever the operating
    // system says it is, and some of them carry punctuation.
    option.textContent = d.label;
    devices.appendChild(option);
  });
  if (chosen && mics.some(d => d.deviceId === chosen)) devices.value = chosen;
  deviceId = devices.value;
  show(devices, mics.length > 1);
};

devices.addEventListener('change', () => { deviceId = devices.value; });

const onDeviceChange = () => { listDevices(); };
if (navigator.mediaDevices.addEventListener) {
  navigator.mediaDevices.addEventListener('devicechange', onDeviceChange);
}

const release = () => {
  if (sampler) { clearInterval(sampler); sampler = null; }
  if (frame) { cancelAnimationFrame(frame); frame = null; }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  // An AudioContext is a hardware resource of its own: left open, the browser
  // goes on showing the tab as using the microphone after the tracks stop.
  if (audio) { try { audio.close(); } catch (e) {} audio = null; }
  analyser = null;
  recorder = null;
};

const discard = () => {
  if (url) { URL.revokeObjectURL(url); url = null; }
  player.removeAttribute('src');
  player.load();
  take = null;
  peaks = [];
  seconds = 0;
};

// timeupdate fires about four times a second, which is visibly steppy under a
// playhead this wide, so the frame loop draws while it is actually playing.
const follow = () => {
  const at = seconds > 0 ? Math.min(player.currentTime / seconds, 1) : 0;
  draw(at);
  clock.textContent = time(player.currentTime) + ' / ' + time(seconds);
  frame = player.paused ? null : requestAnimationFrame(follow);
};

startBtn.addEventListener('click', async () => {
  if (recorder) return;
  discard();
  say('');

  const ask = want => navigator.mediaDevices.getUserMedia({audio: want});
  let failure = null;
  try {
    stream = await ask(deviceId ? {deviceId: {exact: deviceId}} : true);
  } catch (e) {
    failure = e;
    // exact, so a device unplugged since it was chosen fails loudly rather
    // than quietly recording from something else -- and only then is the
    // default used, with the reader told that is what happened.
    if (e.name === 'OverconstrainedError' && deviceId) {
      deviceId = '';
      try {
        stream = await ask(true);
        failure = null;
        say('That microphone is no longer available; the default was used.');
      } catch (again) {
        failure = again;
      }
    }
  }

  if (failure) {
    // Named, not "something went wrong": over https the refusal is nearly
    // always the browser's own permission, or a Permissions-Policy header
    // from the proxy in front of this app -- and those are fixed in two
    // different places by two different people.
    const named = {
      NotAllowedError: 'Microphone access was refused. Allow it for this site in the browser; if it was never asked for, a Permissions-Policy header is blocking it.',
      SecurityError: 'Microphone access was blocked by the security policy of this site.',
      NotFoundError: 'No microphone was found.',
      DevicesNotFoundError: 'No microphone was found.',
      NotReadableError: 'The microphone is being used by another program.',
      TrackStartError: 'The microphone is being used by another program.',
    };
    say(named[failure.name] || ('No microphone available: ' + (failure.name || failure)));
    return;
  }

  // The names are readable only now: a browser withholds them until the
  // microphone has been granted, so this first grant is what fills the picker
  // in for the next take.
  listDevices();

  chunks = [];
  peaks = [];
  recorder = new MediaRecorder(stream, kind ? {mimeType: kind[0]} : undefined);
  recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
  recorder.onstop = () => {
    const type = (kind && kind[0]) || 'audio/webm';
    const blob = new Blob(chunks, {type: type});
    chunks = [];
    release();
    if (!blob.size) {
      setState('idle');
      say('Nothing was recorded.');
      return;
    }
    const d = new Date(), p = n => String(n).padStart(2, '0');
    const name = 'recording-' + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate())
      + '-' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds())
      + ((kind && kind[1]) || '.webm');
    take = new File([blob], name, {type: type});
    url = URL.createObjectURL(blob);
    player.src = url;
    setState('review');
    clock.textContent = '0:00 / ' + time(seconds);
    say(name);
    draw(0);
  };

  // A live analyser rather than decoding the finished recording: the stream
  // is already open, and decodeAudioData over a long take is hundreds of
  // megabytes of PCM for a picture a few hundred pixels wide.
  try {
    audio = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audio.createAnalyser();
    analyser.fftSize = 2048;
    // Deliberately not connected to the destination: that is a microphone
    // played back through the speakers the microphone can hear.
    audio.createMediaStreamSource(stream).connect(analyser);
  } catch (e) {
    analyser = null;
  }

  const samples = analyser ? new Uint8Array(analyser.fftSize) : null;
  sampler = setInterval(() => {
    if (analyser) {
      analyser.getByteTimeDomainData(samples);
      let peak = 0;
      for (let i = 0; i < samples.length; i++) {
        const level = Math.abs(samples[i] - 128) / 128;
        if (level > peak) peak = level;
      }
      peaks.push(peak);
    }
    seconds = (Date.now() - started) / 1000;
    clock.textContent = time(seconds);
    draw(null);
  }, __PEAK_MS__);

  // A timeslice rather than one blob at the end: a long recording held whole
  // in memory is a tab that dies before it can be uploaded.
  recorder.start(1000);
  started = Date.now();
  setState('recording');
  clock.textContent = '0:00';
  draw(null);
});

stopBtn.addEventListener('click', () => {
  seconds = (Date.now() - started) / 1000;
  if (recorder && recorder.state !== 'inactive') recorder.stop();
});

const drawTransport = () => {
  playIcon.textContent = player.paused ? 'play_arrow' : 'pause';
  playText.textContent = player.paused ? 'Play' : 'Pause';
};

playBtn.addEventListener('click', () => {
  if (!take) return;
  if (player.paused) { player.play(); } else { player.pause(); }
});

player.addEventListener('play', () => { drawTransport(); if (!frame) follow(); });
player.addEventListener('pause', () => { drawTransport(); follow(); });
player.addEventListener('ended', () => { drawTransport(); });

// The waveform is the only place the recording is laid out in time, so it is
// also the scrubber -- there is no other one, the browser's own player having
// been the thing that made this card read as a form.
canvas.addEventListener('click', e => {
  if (!take || !seconds) return;
  const box = canvas.getBoundingClientRect();
  player.currentTime = Math.min(seconds, Math.max(0, (e.clientX - box.left) / box.width * seconds));
  follow();
});

// A webm straight out of MediaRecorder carries no duration, and Chrome
// answers Infinity until the player has been seeked once -- which leaves the
// preview unable to scrub or to play to the end.  Seeking far past any real
// recording forces the duration to be worked out, and the position is put
// back before anyone sees it.  The recorder's own clock is what the waveform
// is scaled by either way; this is only about the player being seekable.
player.addEventListener('loadedmetadata', () => {
  if (player.duration !== Infinity) return;
  player.currentTime = 1e101;
  player.ontimeupdate = () => {
    player.ontimeupdate = null;
    player.currentTime = 0;
  };
});

useBtn.addEventListener('click', () => {
  if (!take) return;
  player.pause();
  const file = take;
  // Handed over before the preview is torn down: discard() revokes the URL
  // the player is still holding.
  take = null;
  discard();
  upl.$refs.qRef.addFiles([file]);
});

againBtn.addEventListener('click', () => {
  player.pause();
  discard();
  setState('idle');
  say('');
  startBtn.click();
});

upl._recordCleanup = () => {
  if (recorder && recorder.state !== 'inactive') {
    recorder.onstop = null;
    try { recorder.stop(); } catch (e) {}
  }
  release();
  try { player.pause(); } catch (e) {}
  discard();
  if (navigator.mediaDevices.removeEventListener) {
    navigator.mediaDevices.removeEventListener('devicechange', onDeviceChange);
  }
};

setState('idle');
listDevices();
// The card is in a dialog and the dialog is in a window that can be resized
// under it; the peaks are kept, so the picture can simply be drawn again.
window.addEventListener('resize', () => { if (peaks.length) draw(take ? 0 : null); });
"""


def _action(label: str, icon: str, tone: str):
    """
    One button of the card's action row.

    The icon and the label are children rather than a `q-btn`'s own `icon`
    prop, for two reasons: the page rewrites both of them when Play becomes
    Pause, which a prop would need a round trip for, and a prop-set icon
    carries its own margin while a child does not -- so mixing the two spaced
    one button's icon differently from the rest.
    """

    # color=black flat, as every other button in the app is built: it is what
    # keeps Quasar from painting the label in its own primary blue, and the
    # stylesheet's .body--dark .q-btn--flat rule takes it from there.
    with ui.button().props("color=black flat").classes(
        f"recorder-action {tone}"
    ) as button:
        button.icon_element = ui.icon(icon)
        button.text_element = ui.label(label)

    return button


def record_panel(upload) -> None:
    """
    Draw the recorder and wire it to `upload`.

    Parameters:
        upload: The dialog's `ui.upload`, hidden, which a finished recording is
            handed to exactly as a dropped file is.
    """

    with ui.column().classes("w-full items-center"):
        # The waveform is the card: the clock and the recording marker sit in
        # it rather than in a caption underneath, so there is one thing to
        # look at instead of four.
        with ui.element("div").classes("recorder-hero"):
            canvas = ui.element("canvas").classes("recorder-wave")
            hint = ui.label("The waveform appears as you speak").classes(
                "recorder-hint"
            )
            clock = ui.label("0:00").classes("recorder-clock")
            with ui.element("div").classes("recorder-live") as live:
                ui.element("span").classes("recorder-dot")
                ui.label("REC")

        # Exactly one filled action is ever visible: Start recording, then
        # Stop, then Use recording.  Play is the only outlined button, and it
        # only ever stands beside Use.
        with ui.row().classes("items-center q-mt-md").style("gap: 10px;"):
            start_button = _action("Start recording", "mic", "recorder-filled")
            stop_button = _action("Stop", "stop", "recorder-filled")
            play_button = _action("Play", "play_arrow", "recorder-outline")
            use_button = _action("Use recording", "check", "recorder-filled")

        # Everything that is not the action of the moment.
        with ui.row().classes("items-center q-mt-sm").style("gap: 14px;"):
            again_button = _action("Record again", "refresh", "recorder-muted")
            # Drawn hidden and filled in from the page: a browser withholds
            # device names until the microphone has been granted once, so
            # there is nothing worth showing until then -- and on a machine
            # with a single built-in microphone there never is.
            devices = ui.element("select").classes("recorder-device")
            devices.style("display: none;")

        # Hidden, and driven by the button above: the browser's own controls
        # were the loudest thing in the card and the least like the rest of
        # the app.
        player = ui.element("audio").classes("recorder-player")

        status = ui.label("").classes("recorder-status")

    script = SCRIPT
    for token, value in (
        ("__START__", start_button.id),
        ("__STOP__", stop_button.id),
        ("__PLAY_ICON__", play_button.icon_element.id),
        ("__PLAY_TEXT__", play_button.text_element.id),
        ("__PLAY__", play_button.id),
        ("__USE__", use_button.id),
        ("__AGAIN__", again_button.id),
        ("__DEVICES__", devices.id),
        ("__CANVAS__", canvas.id),
        ("__HINT__", hint.id),
        ("__CLOCK__", clock.id),
        ("__LIVE__", live.id),
        ("__PLAYER__", player.id),
        ("__STATUS__", status.id),
        ("__UPLOAD__", upload.id),
        ("__PEAK_MS__", PEAK_MS),
    ):
        script = script.replace(token, str(value))

    # The dialog is drawn from the server, so its elements are not in the page
    # yet when this is queued; the timer runs the script once they are.
    ui.timer(0.1, lambda: ui.run_javascript(script), once=True)

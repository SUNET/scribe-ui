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

// The recorder engine without a browser: storage in memory, the server a
// fake that behaves like utils/recording_api.py, the microphone a fake that
// produces a chunk whenever the test says so.  Run by
// tests/test_recorder_engine.py (skipped where there is no node), or
// directly: node --test tests/js/

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const Recorder = require(path.join(__dirname, "..", "..", "static", "recorder_engine.js"));

const OWNER = "a".repeat(32);
// Long enough that a recording spans many seconds of chunks.
const N = 30;

// -- Fakes -----------------------------------------------------------------

// Behaves like utils/recording_api.py: one POST with the whole recording,
// streamed on to the backend, and the backend's answer remembered by
// recording id so a repeated upload gets the same job.
function fakeServer() {
  const server = {
    done: new Map(),
    finishes: 0,
    down: false,
    status401: false,
    backendDown: false,
    requests: [],
  };

  server.fetch = async (url, init) => {
    server.requests.push(init.method + " " + url);

    if (server.down) throw new TypeError("Failed to fetch");
    if (init.headers["X-Scribe-Recording"] !== "1") return reply(400, {});
    if (server.status401) return reply(401, {});

    const match = url.match(/^\/record\/api\/([0-9a-f]{32})\/upload$/);
    if (!match || init.method !== "POST") return reply(404, {});
    const rid = match[1];

    if (server.done.has(rid)) return reply(200, { done: server.done.get(rid) });
    if (server.backendDown) return reply(503, { detail: "backend unavailable" });

    const file = Buffer.from(await init.body.arrayBuffer());
    server.finishes += 1;
    const done = {
      uuid: "job-" + server.finishes,
      filename: decodeURIComponent(init.headers["X-Recording-Name"]),
      bytes: file.length,
      type: init.headers["Content-Type"],
    };
    server.done.set(rid, done);
    server.file = file;
    return reply(200, { done: done });
  };

  return server;
}

function reply(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status: status,
    json: async () => body,
  };
}

function fakeTimers() {
  const queue = [];
  return {
    queue: queue,
    set: (fn, ms) => {
      const handle = { fn: fn, ms: ms, cleared: false };
      queue.push(handle);
      return handle;
    },
    clear: (handle) => {
      if (handle) handle.cleared = true;
    },
    // Fire everything due, once -- enough to drive one retry.
    fire: async () => {
      const due = queue.splice(0).filter((h) => !h.cleared);
      due.forEach((h) => h.fn());
      await settle();
    },
  };
}

class FakeTrack {
  stop() {
    this.stopped = true;
  }
}

class FakeMediaRecorder {
  static isTypeSupported(type) {
    return type === "audio/webm;codecs=opus";
  }

  constructor(stream, options) {
    this.stream = stream;
    this.options = options;
    this.mimeType = options && options.mimeType;
    this.state = "inactive";
    FakeMediaRecorder.last = this;
  }

  start(timeslice) {
    this.timeslice = timeslice;
    this.state = "recording";
  }

  // The test's stand-in for a second of audio arriving.
  emit(text) {
    this.ondataavailable({ data: new Blob([text]) });
  }

  requestData() {}

  pause() {
    this.state = "paused";
  }

  resume() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    this.onstop();
  }
}

function fakeNavigator() {
  const track = new FakeTrack();
  return {
    track: track,
    mediaDevices: {
      getUserMedia: async () => ({ getTracks: () => [track] }),
    },
  };
}

const settle = () => new Promise((resolve) => setImmediate(resolve)).then(
  () => new Promise((resolve) => setImmediate(resolve))
);

async function settled(times) {
  for (let i = 0; i < (times || 10); i++) await settle();
}

function makeEngine(overrides) {
  const server = (overrides && overrides.server) || fakeServer();
  const timers = (overrides && overrides.timers) || fakeTimers();
  const store = (overrides && overrides.store) || Recorder.memoryStore();
  let clock = (overrides && overrides.clock) || 1_700_000_000_000;
  const nav = (overrides && overrides.navigator) || fakeNavigator();

  const engine = Recorder.createEngine({
    owner: (overrides && overrides.owner) || OWNER,
    store: store,
    fetch: server.fetch,
    timers: timers,
    now: () => clock,
    navigator: nav,
    MediaRecorder: FakeMediaRecorder,
    AudioContext: null,
    crypto: require("node:crypto").webcrypto,
    watch: false,
  });

  return {
    engine: engine,
    server: server,
    timers: timers,
    store: store,
    nav: nav,
    tick: (ms) => {
      clock += ms;
    },
  };
}

async function record(ctx, seconds, opts) {
  const session = await ctx.engine.startRecording(opts || {});
  for (let i = 0; i < seconds; i++) {
    FakeMediaRecorder.last.emit("c" + i + ";");
    ctx.tick(1000);
    await settle();
  }
  await settled();
  return session;
}

function storedMeta(ctx, id) {
  return ctx.store.metas.get(id);
}

// -- Tests -----------------------------------------------------------------

test("every chunk is on the device as it arrives, in order", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 5);
  const id = session.meta.id;

  assert.equal(storedMeta(ctx, id).chunks, 5);
  assert.equal(storedMeta(ctx, id).state, "recording");
  const text = (await ctx.store.getChunks(id, 0, 5)).map((c) => Buffer.from(c).toString()).join("");
  assert.equal(text, "c0;c1;c2;c3;c4;");
});

test("the recorder asks for speech-rate audio in a timeslice", async () => {
  const ctx = makeEngine();
  await record(ctx, 1);
  assert.equal(FakeMediaRecorder.last.timeslice, Recorder.CHUNK_MS);
  assert.equal(FakeMediaRecorder.last.options.audioBitsPerSecond, Recorder.BITRATE);
});

test("nothing leaves the device while recording, or after it, until Upload", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N * 3);
  assert.deepEqual(ctx.server.requests, []);

  await session.stop();
  await settled();
  assert.deepEqual(ctx.server.requests, [], "stopping is not uploading");
});

test("Upload sends the whole recording once, named, and keeps the original", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 3);
  const result = await session.stop();
  await settled();

  assert.equal(result.interrupted, false);
  await ctx.engine.submit(session.meta.id, "Lecture 1");
  await settled();

  const meta = storedMeta(ctx, session.meta.id);
  assert.equal(meta.state, "uploaded");
  assert.equal(meta.job.uuid, "job-1");
  assert.equal(ctx.server.finishes, 1);
  assert.equal(ctx.server.file.toString().split(";").length - 1, N + 3, "every chunk made it, once");
  assert.equal(ctx.server.requests.length, 1, "one request");
  assert.equal(meta.job.filename, "Lecture 1");
  assert.equal(ctx.server.done.get(session.meta.id).type, "audio/webm");
  // The original stays downloadable from the device after the upload.
  const kept = await ctx.engine.blob(session.meta.id);
  assert.equal((await kept.text()).split(";").length - 1, N + 3);
});

test("an uploaded recording is removed from the device after the keep period", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  await session.stop();
  await settled();
  await ctx.engine.submit(session.meta.id);
  await settled();

  const later = makeEngine({
    server: ctx.server,
    store: ctx.store,
    clock: 1_700_000_000_000 + Recorder.KEEP_UPLOADED_MS + 60_000,
  });
  await later.engine.init();
  assert.equal(later.engine.list().length, 0);
  assert.equal(ctx.store.chunks.size, 0);
});

test("removing an uploaded recording from the device leaves Scribe's copy alone", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  await session.stop();
  await settled();
  await ctx.engine.submit(session.meta.id);
  await settled();

  await ctx.engine.discard(session.meta.id);
  await settled();
  assert.equal(ctx.engine.list().length, 0);
  assert.ok(!ctx.server.requests.some((r) => r.startsWith("DELETE")));
});

test("a name any language can write survives the trip", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  await session.stop();
  await settled();
  await ctx.engine.submit(session.meta.id, "Föreläsning 3 – Ångström");
  await settled();
  assert.equal(storedMeta(ctx, session.meta.id).job.filename, "Föreläsning 3 – Ångström");
});

test("offline keeps the recording and retries with a growing backoff", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 3);
  await session.stop();
  await settled();

  ctx.server.down = true;
  await ctx.engine.submit(session.meta.id);
  await settled();

  let state = ctx.engine.list()[0];
  assert.equal(state.sync.phase, "offline");
  assert.equal(state.state, "stopped");
  const first = ctx.timers.queue.filter((h) => !h.cleared).pop().ms;

  await ctx.timers.fire();
  await settled();
  const second = ctx.timers.queue.filter((h) => !h.cleared).pop().ms;
  assert.ok(second > first, `backoff grows (${first} -> ${second})`);

  ctx.server.down = false;
  await ctx.timers.fire();
  await settled();

  state = ctx.engine.list()[0];
  assert.equal(state.state, "uploaded");
  assert.equal(ctx.server.finishes, 1);
});

test("a backend that is down is waited out, not given up on", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  await session.stop();
  await settled();

  ctx.server.backendDown = true;
  await ctx.engine.submit(session.meta.id);
  await settled();
  assert.equal(ctx.engine.list()[0].sync.phase, "unavailable");
  assert.equal(storedMeta(ctx, session.meta.id).submit, true);

  ctx.server.backendDown = false;
  await ctx.timers.fire();
  await settled();
  assert.equal(ctx.engine.list()[0].state, "uploaded");
});

test("a signed-out session keeps the recording and waits", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  await session.stop();
  await settled();

  ctx.server.status401 = true;
  await ctx.engine.submit(session.meta.id);
  await settled();
  const state = ctx.engine.list()[0];
  assert.equal(state.sync.phase, "auth");
  assert.equal(state.state, "stopped");
  assert.equal((await ctx.store.getChunks(session.meta.id, 0, 10)).length, 2);
});

test("an answer lost after the backend took the file does not make a second job", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  await session.stop();
  await settled();

  const server = ctx.server;
  const original = server.fetch;
  let lose = true;
  server.fetch = async (url, init) => {
    const response = await original(url, init);
    if (lose && init.method === "POST") {
      lose = false;
      throw new TypeError("connection reset");
    }
    return response;
  };
  const ctx2 = makeEngine({ server: server, store: ctx.store });
  await ctx2.engine.init();
  await ctx2.engine.submit(session.meta.id);
  await settled();
  assert.equal(ctx2.engine.list()[0].state, "stopped");

  await ctx2.timers.fire();
  await settled();
  assert.equal(ctx2.engine.list()[0].state, "uploaded");
  assert.equal(server.finishes, 1);
});

test("a crashed tab's recording is recovered as interrupted, whole", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 4);
  const id = session.meta.id;
  // The tab dies: nothing stops the recorder, nothing more is written.

  const later = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + 10 * 60_000 });
  await later.engine.init();
  await settled();

  const recovered = later.engine.list().find((r) => r.id === id);
  assert.equal(recovered.state, "stopped");
  assert.equal(recovered.interrupted, true);
  assert.equal(recovered.chunks, N + 4);

  await later.engine.submit(id);
  await settled();
  assert.equal(later.engine.list()[0].state, "uploaded");
  assert.equal(ctx.server.file.toString().split(";").length - 1, N + 4);
});

test("a recording another tab is still writing is left alone", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 3);

  const other = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + 3000 });
  await other.engine.init();
  const seen = other.engine.list().find((r) => r.id === session.meta.id);
  assert.equal(seen.state, "recording");
  assert.equal(seen.elsewhere, true);
});

test("another user's recordings on the same device are neither shown nor sent", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 1);
  await session.stop();
  await settled();
  const sent = ctx.server.requests.length;

  const stranger = makeEngine({ server: ctx.server, store: ctx.store, owner: "b".repeat(32) });
  await stranger.engine.init();
  await settled();
  assert.equal(stranger.engine.list().length, 0);
  await stranger.engine.discard(session.meta.id);
  assert.ok(ctx.store.metas.has(session.meta.id), "not the stranger's to discard");
  assert.equal(ctx.server.requests.length, sent);
});

test("a storage failure keeps chunks in order and loses none", async () => {
  const store = Recorder.memoryStore();
  const append = store.appendChunk;
  let fail = false;
  store.appendChunk = async (...args) => {
    if (fail) {
      const error = new Error("full");
      error.name = "QuotaExceededError";
      throw error;
    }
    return append(...args);
  };

  const ctx = makeEngine({ store: store });
  const session = await ctx.engine.startRecording({});
  FakeMediaRecorder.last.emit("a;");
  await settled();
  fail = true;
  FakeMediaRecorder.last.emit("b;");
  FakeMediaRecorder.last.emit("c;");
  await settled();
  assert.equal(session.writeProblem, "QuotaExceededError");
  assert.equal(store.metas.get(session.meta.id).chunks, 1);

  fail = false;
  await ctx.timers.fire();
  await settled();
  assert.equal(session.writeProblem, null);
  const text = (await store.getChunks(session.meta.id, 0, 10)).map((c) => Buffer.from(c).toString()).join("");
  assert.equal(text, "a;b;c;");
});

test("the microphone taken away ends the recording as interrupted, kept", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 4);
  ctx.nav.track.onended();
  const result = await session.done;

  assert.equal(result.interrupted, true);
  assert.equal(storedMeta(ctx, session.meta.id).state, "stopped");
  assert.equal(storedMeta(ctx, session.meta.id).chunks, 4);
  assert.equal(ctx.engine.session(), null);
});

test("a recording with nothing in it is not kept", async () => {
  const ctx = makeEngine();
  const session = await ctx.engine.startRecording({});
  const result = await session.stop();
  assert.equal(result.empty, true);
  assert.equal(ctx.engine.list().length, 0);
});

test("paused time is not counted", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  session.pause();
  ctx.tick(60_000);
  session.resume();
  FakeMediaRecorder.last.emit("x;");
  ctx.tick(1000);
  await settled();
  const result = await session.stop();
  assert.equal(result.meta.durationMs, 3000);
});

test("the file is named after the recording, safely", () => {
  const ctx = makeEngine();
  assert.equal(ctx.engine.fileName({ name: "Lecture: 1/2", mime: "audio/webm" }), "Lecture 12.webm");
  assert.equal(ctx.engine.fileName({ name: "", mime: "audio/mp4" }), "Recording.m4a");
});

test("a default name says when it was recorded", () => {
  assert.equal(Recorder.defaultName(new Date(2026, 8, 24, 9, 5)), "Recording 2026-09-24 09.05");
});

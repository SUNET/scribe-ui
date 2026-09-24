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
const N = Recorder.PART_CHUNKS;

// -- Fakes -----------------------------------------------------------------

function fakeServer() {
  const server = {
    parts: new Map(), // rid -> Map(seq -> bytes)
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

    const match = url.match(/^\/record\/api\/([0-9a-f]{32})(\/part\/(\d+)|\/finish)?$/);
    if (!match) return reply(404, {});
    const rid = match[1];
    const held = server.parts.get(rid) || new Map();
    server.parts.set(rid, held);

    if (init.method === "GET") {
      return reply(200, {
        parts: Array.from(held.keys()).sort((a, b) => a - b),
        done: server.done.get(rid) || null,
      });
    }

    if (init.method === "PUT") {
      const bytes = Buffer.from(await init.body.arrayBuffer());
      held.set(Number(match[3]), bytes);
      return reply(200, { ok: true });
    }

    if (init.method === "POST") {
      const body = JSON.parse(init.body);
      if (server.done.has(rid)) return reply(200, { done: server.done.get(rid) });
      const missing = [];
      for (let i = 0; i < body.parts; i++) if (!held.has(i)) missing.push(i);
      if (missing.length) return reply(409, { missing: missing });
      if (server.backendDown) return reply(503, { detail: "backend unavailable" });
      server.finishes += 1;
      const file = Buffer.concat(Array.from({ length: body.parts }, (_, i) => held.get(i)));
      const done = { uuid: "job-" + server.finishes, filename: body.name, bytes: file.length };
      server.done.set(rid, done);
      server.file = file;
      return reply(200, { done: done });
    }

    if (init.method === "DELETE") {
      server.parts.delete(rid);
      return reply(200, { ok: true });
    }

    return reply(405, {});
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

// Web Locks shared by the tabs of one browser.  Each tab asks through its
// own navigator; closing a tab lets go of everything it held.
function fakeLocks() {
  const held = new Map();
  return {
    held: held,
    tab(name) {
      return {
        request(lock, opts, callback) {
          if (typeof opts === "function") {
            callback = opts;
            opts = {};
          }
          if (held.has(lock)) {
            if (opts.ifAvailable) return Promise.resolve(callback(null));
            return new Promise(() => {});
          }
          held.set(lock, name);
          return Promise.resolve(callback({ name: lock })).finally(() => {
            if (held.get(lock) === name) held.delete(lock);
          });
        },
      };
    },
    close(name) {
      for (const [lock, tab] of held) if (tab === name) held.delete(lock);
    },
  };
}

function navigatorWithLocks(locks, tab) {
  return Object.assign(fakeNavigator(), { locks: locks.tab(tab) });
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
    key: (overrides && overrides.key) || (async () => new Uint8Array(32).fill(7)),
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

// What the device holds for a recording, decrypted the way the engine does.
async function plain(ctx, id, from, to) {
  const chunks = await ctx.engine._readChunks(storedMeta(ctx, id), from, to);
  return chunks.map((c) => Buffer.from(c).toString()).join("");
}

// How many of a recording's chunks are still on the device.
function chunksHeld(ctx, id) {
  return Array.from(ctx.store.chunks.keys()).filter((k) => k.startsWith(id + "/")).length;
}

const seconds = (file) => file.toString().split(";").length - 1;

// -- Tests -----------------------------------------------------------------

test("online, no audio is written to the device at all", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N * 3 + 2);
  const id = session.meta.id;

  assert.equal(ctx.store.chunks.size, 0);
  assert.deepEqual(storedMeta(ctx, id).sent, [0, 1, 2], "the record says what Scribe has");
  assert.equal(await plain(ctx, id, N * 3, N * 3 + 2), "c" + N * 3 + ";c" + (N * 3 + 1) + ";", "the growing part is in memory");
});

test("the recording's name is never written in the clear", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 1, { name: "Seminar with Anna Svensson" });
  const stored = JSON.stringify(storedMeta(ctx, session.meta.id));

  assert.ok(!stored.includes("Anna"), stored);
  assert.equal(ctx.engine.list()[0].name, "Seminar with Anna Svensson");

  const later = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + 10 * 60_000 });
  await later.engine.init();
  assert.equal(later.engine.list()[0].name, "Seminar with Anna Svensson", "read back with the key");
});

test("when sending fails, audio is written to the device, encrypted, and in order", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N - 2);
  ctx.server.down = true;
  for (let i = N - 2; i < N + 3; i++) {
    FakeMediaRecorder.last.emit("c" + i + ";");
    await settle();
  }
  await settled();
  const id = session.meta.id;

  assert.equal(chunksHeld(ctx, id), N + 3, "what was in memory, and everything after it");
  const expected = Array.from({ length: N + 3 }, (_, i) => "c" + i + ";").join("");
  assert.equal(await plain(ctx, id, 0, N + 3), expected);
  const raw = Buffer.concat(Array.from(ctx.store.chunks.values()).map((c) => Buffer.from(c)));
  assert.ok(!raw.includes("c0;"), "no audio is kept in the clear");
});

test("once the backlog is sent, the device is emptied and recording goes back to memory", async () => {
  const ctx = makeEngine();
  ctx.server.down = true;
  const session = await record(ctx, N * 2 + 1);
  const id = session.meta.id;
  assert.equal(chunksHeld(ctx, id), N * 2 + 1);

  ctx.server.down = false;
  await ctx.timers.fire();
  await settled();
  assert.equal(chunksHeld(ctx, id), 1, "only the growing part's chunk is left");

  for (let i = 0; i < N; i++) {
    FakeMediaRecorder.last.emit("n" + i + ";");
    await settle();
  }
  await settled();
  assert.equal(chunksHeld(ctx, id), 0, "and new audio is not written");
  assert.deepEqual(storedMeta(ctx, id).sent, [0, 1, 2]);
});

test("a chunk moved to another place no longer reads", async () => {
  const ctx = makeEngine();
  ctx.server.down = true;
  const session = await record(ctx, N + 1);
  const id = session.meta.id;
  const first = ctx.store.chunks.get(id + "/0");
  ctx.store.chunks.set(id + "/0", ctx.store.chunks.get(id + "/1"));
  ctx.store.chunks.set(id + "/1", first);

  await assert.rejects(ctx.engine._readChunks(storedMeta(ctx, id), 0, 2), /can no longer be read/);
});

test("without a key nothing is recorded", async () => {
  const ctx = makeEngine({
    key: async () => {
      throw new TypeError("Failed to fetch");
    },
  });

  await assert.rejects(ctx.engine.startRecording({}), (e) => e.name === "NoKey");
  assert.equal(ctx.engine.session(), null);
  assert.equal(ctx.store.metas.size, 0);
});

test("the recorder asks for speech-rate audio in a timeslice", async () => {
  const ctx = makeEngine();
  await record(ctx, 1);
  assert.equal(FakeMediaRecorder.last.timeslice, Recorder.CHUNK_MS);
  assert.equal(FakeMediaRecorder.last.options.audioBitsPerSecond, Recorder.BITRATE);
});

test("complete parts are sent while recording, the growing one is not", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N * 2 + 3);
  const held = ctx.server.parts.get(session.meta.id);

  assert.deepEqual(Array.from(held.keys()).sort(), [0, 1]);
  assert.equal(ctx.server.finishes, 0, "nothing is a job while recording");
});

test("a crash while online costs only the part not yet sent", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N * 2 + 3);
  const id = session.meta.id;
  // The tab dies: its memory goes with it.

  const later = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + 10 * 60_000 });
  await later.engine.init();
  const recovered = later.engine.list().find((r) => r.id === id);
  assert.equal(recovered.interrupted, true);
  assert.equal(recovered.chunks, N * 2, "what reached Scribe");

  await later.engine.submit(id);
  await settled();
  assert.equal(later.engine.list()[0].state, "uploaded");
  assert.equal(seconds(ctx.server.file), N * 2);
});

test("a crash before anything reached Scribe leaves nothing behind", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);

  const later = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + 10 * 60_000 });
  await later.engine.init();
  assert.equal(later.engine.list().length, 0);
  assert.equal(ctx.store.metas.size, 0);
  assert.ok(ctx.server.requests.includes("DELETE /record/api/" + session.meta.id));
});

test("stop sends the rest and finishes at once, leaving nothing on the device", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 3);
  const id = session.meta.id;
  const result = await session.stop();
  await settled();

  assert.equal(result.interrupted, false);
  assert.equal(ctx.server.finishes, 1);
  assert.equal(seconds(ctx.server.file), N + 3, "every chunk made it, once");
  assert.equal(ctx.store.metas.size, 0);
  assert.equal(ctx.store.chunks.size, 0);

  const shown = ctx.engine.list().find((r) => r.id === id);
  assert.equal(shown.state, "uploaded");
  assert.equal(shown.job.uuid, "job-1");
});

test("a finished recording is not on the device after a reload", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 2);
  await session.stop();
  await settled();

  const later = makeEngine({ server: ctx.server, store: ctx.store });
  await later.engine.init();
  assert.equal(later.engine.list().length, 0);
});

test("a recording left by an earlier version, uploaded and kept, is removed", async () => {
  const ctx = makeEngine();
  ctx.store.metas.set("f".repeat(32), { id: "f".repeat(32), owner: OWNER, state: "uploaded", chunks: 1 });
  ctx.store.chunks.set("f".repeat(32) + "/0", Buffer.from("old;"));

  await ctx.engine.init();
  assert.equal(ctx.engine.list().length, 0);
  assert.equal(ctx.store.chunks.size, 0);
});

test("a part the backend lost after the device let it go is reported, not looped", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 2);
  const id = session.meta.id;
  // The tab dies after part 0 was confirmed and dropped; the backend's
  // sweep then takes the unfinished recording.
  ctx.server.parts.clear();

  const later = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + 10 * 60_000 });
  await later.engine.init();
  await later.engine.submit(id);
  await settled();

  const shown = later.engine.list().find((r) => r.id === id);
  assert.equal(shown.sync.phase, "error");
  assert.match(shown.error, /lost on Scribe/);
  assert.equal(ctx.server.finishes, 0);
});

test("offline, everything waits on the device and goes when the connection is back", async () => {
  const ctx = makeEngine();
  ctx.server.down = true;
  const session = await record(ctx, N + 3);
  const id = session.meta.id;
  assert.equal(chunksHeld(ctx, id), N + 3, "nothing is dropped that was not confirmed");

  await session.stop();
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
  assert.equal(seconds(ctx.server.file), N + 3);
  assert.equal(ctx.store.chunks.size, 0);
});

test("a backend that is down is waited out, not given up on", async () => {
  const ctx = makeEngine();
  ctx.server.backendDown = true;
  const session = await record(ctx, 2);
  await session.stop();
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
  ctx.server.status401 = true;
  const session = await record(ctx, 2);
  await session.stop();
  await settled();

  const state = ctx.engine.list()[0];
  assert.equal(state.sync.phase, "auth");
  assert.equal(state.state, "stopped");
  assert.equal(await plain(ctx, session.meta.id, 0, 2), "c0;c1;");
});

test("an answer lost after the backend made the job does not make a second job", async () => {
  const server = fakeServer();
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
  const ctx = makeEngine({ server: server });
  const session = await record(ctx, 2);
  await session.stop();
  await settled();
  assert.equal(ctx.engine.list()[0].state, "stopped");

  await ctx.timers.fire();
  await settled();
  assert.equal(ctx.engine.list()[0].state, "uploaded");
  assert.equal(server.finishes, 1);
});

test("a crashed tab's recording is recovered as interrupted, whole, when it was offline", async () => {
  const ctx = makeEngine();
  ctx.server.down = true;
  const session = await record(ctx, N + 4);
  ctx.server.down = false;
  const id = session.meta.id;
  // The tab dies: nothing stops the recorder, nothing more is written.

  const later = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + 10 * 60_000 });
  await later.engine.init();
  await settled();

  const recovered = later.engine.list().find((r) => r.id === id);
  assert.equal(recovered.state, "stopped");
  assert.equal(recovered.interrupted, true);
  assert.equal(recovered.chunks, N + 4);
  assert.equal(ctx.server.finishes, 0, "cut short: the reader decides");

  await later.engine.submit(id);
  await settled();
  assert.equal(later.engine.list()[0].state, "uploaded");
  assert.equal(seconds(ctx.server.file), N + 4);
});

test("a recording another tab is still writing is left alone", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 3);

  const other = makeEngine({ server: ctx.server, store: ctx.store, clock: 1_700_000_000_000 + N * 1000 + 3000 });
  await other.engine.init();
  await settled();
  const seen = other.engine.list().find((r) => r.id === session.meta.id);
  assert.equal(seen.state, "recording");
  assert.equal(seen.elsewhere, true);
  assert.equal(other.engine.list()[0].error, null, "not sent from a tab that does not hold it");
});

test("with locks, a recording another tab holds is shown as elsewhere however quiet it is", async () => {
  const locks = fakeLocks();
  const ctx = makeEngine({ navigator: navigatorWithLocks(locks, "a") });
  const session = await record(ctx, 3);

  // Long past what timing alone would call gone.
  const other = makeEngine({
    server: ctx.server,
    store: ctx.store,
    clock: 1_700_000_000_000 + 10 * 60_000,
    navigator: navigatorWithLocks(locks, "b"),
  });
  await other.engine.init();
  await settled();
  const seen = other.engine.list().find((r) => r.id === session.meta.id);
  assert.equal(seen.state, "recording");
  assert.equal(seen.elsewhere, true);
});

test("a page reloaded mid-recording is not told its recording is in another tab", async () => {
  // The wifi drops, NiceGUI reloads the page: the old document -- and its
  // lock -- are gone at once, but what it wrote a second ago looks fresh.
  const locks = fakeLocks();
  const ctx = makeEngine({ navigator: navigatorWithLocks(locks, "a") });
  const session = await record(ctx, N + 2);
  locks.close("a");

  const reloaded = makeEngine({
    server: ctx.server,
    store: ctx.store,
    clock: 1_700_000_000_000 + (N + 2) * 1000 + 500,
    navigator: navigatorWithLocks(locks, "a2"),
  });
  await reloaded.engine.init();
  await settled();
  const seen = reloaded.engine.list().find((r) => r.id === session.meta.id);
  assert.equal(seen.elsewhere, false);
  assert.equal(seen.state, "stopped");
  assert.equal(seen.interrupted, true, "offered to continue, not left running");
});

test("the live lock is taken before the recording is first written, and let go after its last", async () => {
  const locks = fakeLocks();
  const ctx = makeEngine({ navigator: navigatorWithLocks(locks, "a") });
  const put = ctx.store.putMeta.bind(ctx.store);
  let heldAtFirstWrite = null;
  ctx.store.putMeta = async (meta) => {
    if (heldAtFirstWrite === null) heldAtFirstWrite = locks.held.has("scribe-live-" + meta.id);
    return put(meta);
  };
  const session = await record(ctx, 2);
  assert.equal(heldAtFirstWrite, true);

  await session.stop();
  await settled();
  assert.equal(locks.held.has("scribe-live-" + session.meta.id), false);
});

test("another user's recordings on the same device are neither shown nor sent", async () => {
  const ctx = makeEngine();
  ctx.server.down = true;
  const session = await record(ctx, N + 1);
  ctx.nav.track.onended();
  await session.done;
  await settled();
  ctx.server.down = false;
  const sent = ctx.server.requests.length;

  const stranger = makeEngine({ server: ctx.server, store: ctx.store, owner: "b".repeat(32) });
  await stranger.engine.init();
  await settled();
  assert.equal(stranger.engine.list().length, 0);
  await stranger.engine.discard(session.meta.id);
  assert.ok(ctx.store.metas.has(session.meta.id), "not the stranger's to discard");
  assert.equal(ctx.server.requests.length, sent);
});

test("discarding an unfinished recording tells the backend too", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, N + 1);
  ctx.nav.track.onended();
  await session.done;
  await settled();

  await ctx.engine.discard(session.meta.id);
  await settled();
  assert.equal(ctx.engine.list().length, 0);
  assert.equal(ctx.store.chunks.size, 0);
  assert.ok(ctx.server.requests.includes("DELETE /record/api/" + session.meta.id));
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
  ctx.server.down = true;
  const session = await record(ctx, N); // the part's send fails: from now on it is written
  const id = session.meta.id;
  assert.equal(chunksHeld(ctx, id), N);

  fail = true;
  FakeMediaRecorder.last.emit("b;");
  FakeMediaRecorder.last.emit("c;");
  await settled();
  assert.equal(session.writeProblem, "QuotaExceededError");
  assert.equal(store.metas.get(id).chunks, N);

  fail = false;
  // Only the storage retry, not the send retry: the server is still down.
  const retries = ctx.timers.queue.splice(0).filter((h) => h.ms === 5000);
  retries.forEach((h) => h.fn());
  await settled();
  assert.equal(session.writeProblem, null);
  const expected = Array.from({ length: N }, (_, i) => "c" + i + ";").join("") + "b;c;";
  assert.equal(await plain(ctx, id, 0, N + 2), expected);
});

test("the microphone taken away ends the recording as interrupted, kept for the reader", async () => {
  const ctx = makeEngine();
  const session = await record(ctx, 4);
  ctx.nav.track.onended();
  const result = await session.done;
  await settled();

  assert.equal(result.interrupted, true);
  assert.equal(storedMeta(ctx, session.meta.id).state, "stopped");
  assert.equal(storedMeta(ctx, session.meta.id).chunks, 4);
  assert.equal(storedMeta(ctx, session.meta.id).submit, false);
  assert.equal(ctx.server.finishes, 0);
  assert.equal(ctx.store.chunks.size, 0, "the tail was sent, not written");
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
  ctx.server.down = true;
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

test("a default name says when it was recorded", () => {
  assert.equal(Recorder.defaultName(new Date(2026, 8, 24, 9, 5)), "Recording 2026-09-24 09.05");
});

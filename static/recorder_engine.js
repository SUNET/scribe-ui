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

// The recorder's engine: capture, keeping, and getting a recording to Scribe.
//
// The one rule everything here follows is that **a recording exists on the
// device until the backend has said it holds the file**.  Every second of
// audio is written to IndexedDB as it is recorded, so what a crash, a reload,
// a flat battery or a closed tab costs is the last second -- not the lecture.
//
// **Nothing leaves the device until the reader presses Upload.**  Then the
// whole recording is sent in one request, which the web server streams on
// to the backend without writing it anywhere -- so the only copy that is
// ever stored outside this browser is the backend's, encrypted.  Sending is
// a separate, restartable job that never holds the only copy of anything:
// failures are sorted into "later" (offline, server or backend down), "after
// signing in again" and "never as sent", only the last one stops the
// retrying, and nothing is ever deleted because a send failed.
//
// Uploading goes through plain fetch(), not the page's websocket: the
// websocket is what a phone loses first, and NiceGUI reloads the page when it
// has been gone too long.  So the same engine is loaded on the files page and
// resumes whatever a previous page left unfinished.
//
// Written to run in Node as well (module.exports), with the browser's pieces
// -- IndexedDB, fetch, MediaRecorder, timers -- handed in, so the retry and
// recovery logic is tested without a browser (tests/js/recorder_engine.test.js).

(function (root, factory) {
  const api = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ScribeRecorder = api;
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  // One chunk a second: what a crash can cost at most.
  const CHUNK_MS = 1000;
  // Speech, not music: 64 kbit/s Opus is transparent for a voice, and it is
  // under 30 MB an hour -- which decides how long a phone can record before
  // its storage runs out, and how long the upload takes afterwards.
  const BITRATE = 64000;
  // A recording marked as running whose tab has written nothing for this
  // long is not running: that tab crashed or was closed.
  const LIVE_STALE_MS = 15000;
  const HEARTBEAT_MS = 5000;
  const RETRY_MIN_MS = 2000;
  const RETRY_MAX_MS = 60000;
  // Uploaded recordings, audio and all, stay on the device this long -- so
  // the original can still be downloaded -- and are then removed.  The
  // reader can remove one sooner themselves.
  const KEEP_UPLOADED_MS = 7 * 24 * 3600 * 1000;

  // Kept in step with API_PREFIX in utils/recording_api.py (the test there
  // checks).  Not under /api: behind the proxy that is the backend's.
  const API = "/record/api";
  const DB_NAME = "scribe-recordings";
  const DB_VERSION = 1;

  const KINDS = [
    ["audio/webm;codecs=opus", ".webm"],
    ["audio/webm", ".webm"],
    ["audio/ogg;codecs=opus", ".ogg"],
    ["audio/mp4", ".m4a"],
  ];

  // --- Keeping -------------------------------------------------------------

  // IndexedDB, holding ArrayBuffers rather than Blobs: Safari has a history
  // of Blobs in IndexedDB that read back empty, and an ArrayBuffer is just
  // bytes everywhere.  A chunk and the count saying it exists are written in
  // one transaction, so the two can never disagree after a crash.
  function idbStore(indexedDB, IDBKeyRange) {
    let opening = null;

    const open = () => {
      if (opening) return opening;

      opening = new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = () => {
          const db = request.result;
          if (!db.objectStoreNames.contains("recordings")) {
            db.createObjectStore("recordings", { keyPath: "id" });
          }
          if (!db.objectStoreNames.contains("chunks")) {
            db.createObjectStore("chunks", { keyPath: ["rid", "seq"] });
          }
        };
        request.onsuccess = () => {
          const db = request.result;
          db.onversionchange = () => {
            db.close();
            opening = null;
          };
          db.onclose = () => {
            opening = null;
          };
          resolve(db);
        };
        request.onerror = () => {
          opening = null;
          reject(request.error);
        };
      });

      return opening;
    };

    const run = async (stores, mode, body) => {
      const db = await open();

      return new Promise((resolve, reject) => {
        const tx = db.transaction(stores, mode);
        let result;

        tx.oncomplete = () => resolve(result);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error || new Error("transaction aborted"));
        body(tx, (value) => {
          result = value;
        });
      });
    };

    const chunkRange = (rid, from, to) =>
      IDBKeyRange.bound([rid, from], [rid, to], false, true);

    return {
      putMeta: (meta) =>
        run(["recordings"], "readwrite", (tx) => {
          tx.objectStore("recordings").put(meta);
        }),
      getMeta: (id) =>
        run(["recordings"], "readonly", (tx, set) => {
          const request = tx.objectStore("recordings").get(id);
          request.onsuccess = () => set(request.result || null);
        }),
      listMeta: () =>
        run(["recordings"], "readonly", (tx, set) => {
          const request = tx.objectStore("recordings").getAll();
          request.onsuccess = () => set(request.result || []);
        }),
      appendChunk: (meta, seq, data) =>
        run(["recordings", "chunks"], "readwrite", (tx) => {
          tx.objectStore("chunks").put({ rid: meta.id, seq: seq, data: data });
          tx.objectStore("recordings").put(meta);
        }),
      getChunks: (rid, from, to) =>
        run(["chunks"], "readonly", (tx, set) => {
          const request = tx.objectStore("chunks").getAll(chunkRange(rid, from, to));
          request.onsuccess = () => set((request.result || []).map((c) => c.data));
        }),
      deleteChunks: (rid) =>
        run(["chunks"], "readwrite", (tx) => {
          tx.objectStore("chunks").delete(chunkRange(rid, 0, Infinity));
        }),
      deleteRecording: (rid) =>
        run(["recordings", "chunks"], "readwrite", (tx) => {
          tx.objectStore("chunks").delete(chunkRange(rid, 0, Infinity));
          tx.objectStore("recordings").delete(rid);
        }),
    };
  }

  // The same interface in memory.  Used by the tests, and in a browser that
  // offers no IndexedDB at all -- where the page says plainly that a crash
  // will lose the recording, since it will.
  function memoryStore() {
    const metas = new Map();
    const chunks = new Map();
    const copy = (value) => (value ? JSON.parse(JSON.stringify(value)) : value);

    return {
      persistent: false,
      metas: metas,
      chunks: chunks,
      putMeta: async (meta) => {
        metas.set(meta.id, copy(meta));
      },
      getMeta: async (id) => copy(metas.get(id)) || null,
      listMeta: async () => Array.from(metas.values()).map(copy),
      appendChunk: async (meta, seq, data) => {
        chunks.set(meta.id + "/" + seq, data);
        metas.set(meta.id, copy(meta));
      },
      getChunks: async (rid, from, to) => {
        const out = [];
        for (let seq = from; seq < to; seq++) {
          const data = chunks.get(rid + "/" + seq);
          if (data !== undefined) out.push(data);
        }
        return out;
      },
      deleteChunks: async (rid) => {
        for (const key of Array.from(chunks.keys())) {
          if (key.startsWith(rid + "/")) chunks.delete(key);
        }
      },
      deleteRecording: async (rid) => {
        for (const key of Array.from(chunks.keys())) {
          if (key.startsWith(rid + "/")) chunks.delete(key);
        }
        metas.delete(rid);
      },
    };
  }

  // --- Small helpers -------------------------------------------------------

  const pad = (n) => String(n).padStart(2, "0");

  function defaultName(date) {
    return (
      "Recording " +
      date.getFullYear() +
      "-" +
      pad(date.getMonth() + 1) +
      "-" +
      pad(date.getDate()) +
      " " +
      pad(date.getHours()) +
      "." +
      pad(date.getMinutes())
    );
  }

  function newId(cryptoApi) {
    if (cryptoApi && cryptoApi.randomUUID) {
      return cryptoApi.randomUUID().replace(/-/g, "");
    }
    const bytes = new Uint8Array(16);
    cryptoApi.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  class SyncError extends Error {
    constructor(kind, message) {
      super(message || kind);
      this.kind = kind;
    }
  }

  // --- The engine ----------------------------------------------------------

  function createEngine(options) {
    const env = options || {};
    const g = typeof window !== "undefined" ? window : globalThis;

    const owner = env.owner || "";
    const fetchFn = env.fetch || (g.fetch ? g.fetch.bind(g) : null);
    const now = env.now || (() => Date.now());
    const timers = env.timers || {
      set: (fn, ms) => setTimeout(fn, ms),
      clear: (handle) => clearTimeout(handle),
    };
    const nav = env.navigator || g.navigator || {};
    const doc = env.document || g.document || null;
    const cryptoApi = env.crypto || g.crypto;
    const MediaRecorderImpl = env.MediaRecorder || g.MediaRecorder;
    const AudioContextImpl = env.AudioContext || g.AudioContext || g.webkitAudioContext;

    let store = env.store || null;
    let storeProblem = null;

    if (!store) {
      try {
        if (!g.indexedDB) throw new Error("no IndexedDB");
        store = idbStore(g.indexedDB, g.IDBKeyRange);
        store.persistent = true;
      } catch (e) {
        store = memoryStore();
        storeProblem = "unavailable";
      }
    }

    const listeners = new Set();
    const metas = new Map();
    const sync = new Map();
    const retry = new Map();
    const running = new Set();
    const again = new Set();
    let session = null;
    let initialised = null;

    const emit = () => {
      listeners.forEach((fn) => {
        try {
          fn();
        } catch (e) {
          /* one broken listener must not stop the others */
        }
      });
    };

    const setSync = (id, state) => {
      sync.set(id, Object.assign({}, sync.get(id) || {}, state));
      emit();
    };

    const remember = (meta) => {
      metas.set(meta.id, Object.assign({}, meta));
      emit();
    };

    // -- Talking to the server --

    // fetch() cannot say how far an upload has got, and an hour of audio
    // over a slow connection is minutes of a button saying nothing -- so in
    // a browser the upload goes through XMLHttpRequest, answering in the
    // same shape as fetch so everything after it is one code path.
    function sendWithProgress(url, init, onProgress) {
      const XHR = env.XMLHttpRequest || g.XMLHttpRequest;
      if (!onProgress || !XHR || env.fetch) return fetchFn(url, init);

      return new Promise((resolve, reject) => {
        const xhr = new XHR();
        xhr.open(init.method, url);
        xhr.withCredentials = true;
        Object.entries(init.headers || {}).forEach(([k, v]) => xhr.setRequestHeader(k, v));
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) onProgress(event.loaded, event.total);
        };
        xhr.onload = () =>
          resolve({
            ok: xhr.status >= 200 && xhr.status < 300,
            status: xhr.status,
            json: async () => JSON.parse(xhr.responseText || "{}"),
          });
        xhr.onerror = () => reject(new TypeError("network error"));
        xhr.onabort = () => reject(new TypeError("aborted"));
        xhr.send(init.body);
      });
    }

    async function api(method, path, body, headers, onProgress) {
      if (!fetchFn) throw new SyncError("offline", "no fetch");

      let response;

      try {
        response = await sendWithProgress(
          API + path,
          {
            method: method,
            body: body,
            credentials: "same-origin",
            cache: "no-store",
            headers: Object.assign({ "X-Scribe-Recording": "1" }, headers || {}),
          },
          onProgress
        );
      } catch (e) {
        throw new SyncError("offline", "No connection to Scribe.");
      }

      if (response.ok) {
        try {
          return await response.json();
        } catch (e) {
          return {};
        }
      }

      if (response.status === 401) {
        throw new SyncError("auth", "Signed out of Scribe.");
      }

      if (response.status === 400 || response.status === 413 || response.status === 422) {
        let detail = "";
        try {
          detail = (await response.json()).detail || "";
        } catch (e) {
          /* the status says enough */
        }
        throw new SyncError("refused", detail || "Scribe refused the recording.");
      }

      // The status is in the message on purpose: "not answering" covers a
      // backend that is down (503) and a proxy sending these routes
      // somewhere they do not exist (404), and the two are fixed by
      // different people.
      throw new SyncError("unavailable", "Scribe is not answering right now (" + response.status + ").");
    }

    async function markUploaded(meta, done) {
      meta.state = "uploaded";
      meta.job = done || {};
      meta.uploadedAt = now();
      meta.error = null;
      // The audio stays on the device: the reader may want the original
      // file for themselves, and the recorder page is where they download
      // it -- before transcribing it or after.  It goes when they remove it,
      // or after KEEP_UPLOADED_MS.
      await store.putMeta(meta);
      remember(meta);
    }

    // One attempt at uploading a recording the reader has asked to upload.
    // Throws a SyncError to say why it stopped; returns what it reached.
    async function syncOnce(id) {
      if (session && session.meta.id === id) return "idle";

      const meta = await store.getMeta(id);

      if (!meta || meta.owner !== owner || meta.state !== "stopped" || !meta.submit) {
        return "idle";
      }

      if (meta.chunks === 0) {
        throw new SyncError("refused", "Nothing was recorded.");
      }

      const chunks = await store.getChunks(id, 0, meta.chunks);

      if (chunks.length !== meta.chunks) {
        // Chunks written are always a contiguous run from 0, so this is
        // storage having lost something underneath us.  Sending it anyway
        // would stitch a gap into the file without anyone knowing.
        throw new SyncError("refused", "Part of the recording is missing on this device.");
      }

      const file = new Blob(chunks, { type: meta.mime });
      setSync(id, { phase: "uploading", sent: 0, total: file.size });

      const answer = await api(
        "POST",
        "/" + id + "/upload",
        file,
        {
          "Content-Type": meta.mime,
          // A header carries only Latin-1; a recording's name is whatever
          // the reader typed.
          "X-Recording-Name": encodeURIComponent(meta.name || ""),
        },
        (sent, total) => setSync(id, { phase: "uploading", sent: sent, total: total })
      );

      if (answer && answer.done) {
        await markUploaded(meta, answer.done);
        return "done";
      }

      throw new SyncError("unavailable", "Scribe gave an unexpected answer.");
    }

    // Single flight per recording: a kick while one is running is folded
    // into one more run afterwards rather than a second one alongside it.
    // Across tabs, a Web Lock keeps two tabs from sending the same recording
    // at once -- which would make two jobs of it.
    function kick(id) {
      if (retry.has(id)) {
        timers.clear(retry.get(id).handle);
        retry.delete(id);
      }

      if (running.has(id)) {
        again.add(id);
        return undefined;
      }

      running.add(id);

      const attempt = async () => {
        let outcome;
        let failure = null;

        try {
          outcome = await syncOnce(id);
        } catch (e) {
          failure = e instanceof SyncError ? e : new SyncError("unavailable", String(e && e.message));
        }

        return { outcome: outcome, failure: failure };
      };

      const withLock = () => {
        const locks = nav.locks;
        if (!locks || !locks.request) return attempt();
        return locks.request("scribe-recording-" + id, { ifAvailable: true }, (lock) =>
          lock ? attempt() : { outcome: "elsewhere", failure: null }
        );
      };

      return withLock().then(async ({ outcome, failure }) => {
        running.delete(id);

        if (failure) {
          await fail(id, failure);
        } else if (outcome === "done") {
          setSync(id, { phase: "done", message: null, attempts: 0 });
        } else if (outcome === "elsewhere") {
          schedule(id, RETRY_MAX_MS, { phase: "elsewhere" });
        } else if (outcome === "idle") {
          setSync(id, { phase: "idle", attempts: 0 });
        } else {
          setSync(id, { attempts: 0 });
        }

        if (again.has(id)) {
          again.delete(id);
          return kick(id);
        }

        return outcome;
      });
    }

    function schedule(id, delay, state) {
      const previous = retry.get(id);
      if (previous) timers.clear(previous.handle);

      const handle = timers.set(() => {
        retry.delete(id);
        kick(id);
      }, delay);

      retry.set(id, { handle: handle });
      setSync(id, Object.assign({ retryAt: now() + delay }, state));
    }

    async function fail(id, error) {
      // Counted in the sync state, not the retry timer: kick() clears the
      // timer before every attempt, and a count kept there would be back at
      // zero each time -- a server that is down would be asked every two
      // seconds forever instead of backing off.
      const attempts = (sync.get(id) || {}).attempts || 0;

      if (error.kind === "refused") {
        const meta = await store.getMeta(id);
        if (meta) {
          meta.error = error.message;
          // A refused send is no longer "submitted": pressing the button
          // again is what asks for another try, not the retry timer.
          meta.submit = false;
          await store.putMeta(meta);
          remember(meta);
        }
        setSync(id, { phase: "error", message: error.message });
        return;
      }

      const delay =
        error.kind === "auth"
          ? RETRY_MAX_MS
          : Math.min(RETRY_MAX_MS, RETRY_MIN_MS * Math.pow(2, attempts));
      // Jitter, so a room of phones coming back online at once does not
      // arrive at the server in the same instant.
      const jittered = Math.round(delay * (0.75 + Math.random() * 0.5));

      schedule(id, jittered, { phase: error.kind, message: error.message, attempts: attempts + 1 });
    }

    // Forced, everything waiting goes now -- the connection has just come
    // back, or the reader has just come back to the tab.  Otherwise only
    // what this page has not looked at yet (a recording another tab made),
    // so the periodic refresh does not cut short a backoff in progress.
    function kickAll(force) {
      metas.forEach((meta) => {
        if (meta.owner !== owner || meta.state === "uploaded" || meta.error) return;
        if (force || !sync.has(meta.id)) kick(meta.id);
      });
    }

    // -- Recovering what an earlier page left behind --

    // Whether another tab is recording this right now.  A Web Lock is held
    // for the whole of a recording, so where locks exist the answer is exact
    // -- which matters, because declaring a recording over while it is not
    // offers it for upload, cut short, while it is still growing.  Timing
    // alone is the fallback, with a wider margin: a background tab can go
    // quiet for a while without being gone.
    async function recordingElsewhere(meta) {
      if (session && session.meta.id === meta.id) return false;

      if (nav.locks && nav.locks.request) {
        try {
          return await nav.locks.request("scribe-live-" + meta.id, { ifAvailable: true }, (lock) => !lock);
        } catch (e) {
          /* fall through to timing */
        }
      }

      return now() - meta.updatedAt <= LIVE_STALE_MS * 4;
    }

    // Read what storage holds -- other tabs write to it too -- and settle
    // anything a tab that is gone left marked as running.
    async function refresh() {
      let all = [];

      try {
        all = await store.listMeta();
      } catch (e) {
        storeProblem = storeProblem || "unreadable";
        return;
      }

      const seen = new Set();

      for (const meta of all) {
        if (meta.owner !== owner) continue;
        if (session && session.meta.id === meta.id) {
          seen.add(meta.id);
          continue;
        }

        if (meta.state === "uploaded" && now() - (meta.uploadedAt || 0) > KEEP_UPLOADED_MS) {
          await store.deleteRecording(meta.id);
          continue;
        }

        // Running, as far as storage knows, but the tab that was recording
        // it is gone.  What it wrote is a valid recording up to that point.
        if (
          meta.state === "recording" &&
          now() - meta.updatedAt > LIVE_STALE_MS &&
          !(await recordingElsewhere(meta))
        ) {
          meta.state = "stopped";
          meta.interrupted = true;
          await store.putMeta(meta);
        }

        seen.add(meta.id);
        metas.set(meta.id, meta);
      }

      // Discarded or finished in another tab.
      for (const id of Array.from(metas.keys())) {
        if (!seen.has(id)) metas.delete(id);
      }

      emit();
    }

    async function init() {
      if (initialised) return initialised;

      initialised = (async () => {
        await refresh();
        kickAll(true);

        const again = () => {
          refresh().then(() => kickAll(false), () => {});
          timers.set(again, LIVE_STALE_MS);
        };
        if (env.watch !== false) timers.set(again, LIVE_STALE_MS);
      })();

      return initialised;
    }

    // -- Recording --

    function supported() {
      if (g.isSecureContext === false) return "insecure";
      if (!nav.mediaDevices || !nav.mediaDevices.getUserMedia || !MediaRecorderImpl) {
        return "unsupported";
      }
      return null;
    }

    function pickKind() {
      if (!MediaRecorderImpl || !MediaRecorderImpl.isTypeSupported) return null;
      return KINDS.find((kind) => MediaRecorderImpl.isTypeSupported(kind[0])) || null;
    }

    class Session {
      constructor(meta, stream, recorder, extras) {
        this.meta = meta;
        this.stream = stream;
        this.recorder = recorder;
        this.analyser = extras.analyser;
        this.audio = extras.audio;
        this.samples = this.analyser ? new Uint8Array(this.analyser.fftSize) : null;
        this.pending = [];
        this.flushing = null;
        this.flushAgain = false;
        this.writeProblem = null;
        this.muted = false;
        this.stoppedByUser = false;
        this.activeSince = now();
        this.activeMs = 0;
        this.paused = false;
        this.wakeLock = null;
        this.heartbeat = null;
        this.flushRetry = null;
        this.done = new Promise((resolve) => {
          this.finished = resolve;
        });
      }

      elapsedMs() {
        return this.activeMs + (this.paused || !this.activeSince ? 0 : now() - this.activeSince);
      }

      level() {
        if (!this.analyser) return 0;
        this.analyser.getByteTimeDomainData(this.samples);
        let peak = 0;
        for (let i = 0; i < this.samples.length; i++) {
          const value = Math.abs(this.samples[i] - 128) / 128;
          if (value > peak) peak = value;
        }
        return peak;
      }

      savedMs() {
        return this.meta.chunks * CHUNK_MS;
      }

      // Chunks are written strictly in order and one at a time, and the
      // count only moves when a write lands, so what storage holds is always
      // an unbroken run from the start.  A failed write (storage full) keeps
      // the chunk, and everything after it, in memory and tries again --
      // the recording goes on, and the page says it is no longer protected.
      //
      // Single flight: a flush asked for while one is writing is folded into
      // another pass once it finishes, and everyone waiting gets the same
      // promise.  Two writers at once would each take pending[0] and write
      // the same chunk under two numbers.
      flush() {
        if (this.flushing) {
          this.flushAgain = true;
          return this.flushing;
        }

        this.flushing = this.writeAll().finally(() => {
          this.flushing = null;
          if (this.flushAgain) {
            this.flushAgain = false;
            if (this.pending.length && !this.writeProblem) return this.flush();
          }
          return undefined;
        });

        return this.flushing;
      }

      async writeAll() {
        while (this.pending.length) {
          const blob = this.pending[0];
          const data = blob.arrayBuffer ? await blob.arrayBuffer() : blob;
          const seq = this.meta.chunks;

          this.meta.chunks = seq + 1;
          this.meta.bytes = (this.meta.bytes || 0) + (data.byteLength || 0);
          this.meta.updatedAt = now();
          this.meta.durationMs = this.elapsedMs();

          try {
            await store.appendChunk(this.meta, seq, data);
          } catch (e) {
            this.meta.chunks = seq;
            this.meta.bytes -= data.byteLength || 0;
            this.writeProblem = (e && e.name) || "write failed";
            emit();
            this.retryFlush();
            return false;
          }

          this.pending.shift();

          if (this.writeProblem) {
            this.writeProblem = null;
            emit();
          }

        }

        remember(this.meta);
        return true;
      }

      retryFlush() {
        if (this.flushRetry) return;
        this.flushRetry = timers.set(() => {
          this.flushRetry = null;
          this.writeProblem = null;
          this.flush();
        }, 5000);
      }

      // Between chunks storage already hears every second; this is for the
      // pauses, when nothing arrives and a quiet recording must not look
      // like an abandoned one to another tab.
      async beat() {
        if (this.flushing || this.pending.length || this.finalizing) return;
        this.meta.updatedAt = now();
        this.meta.durationMs = this.elapsedMs();
        try {
          await store.putMeta(this.meta);
        } catch (e) {
          /* the next chunk tries again */
        }
        emit();
      }

      pause() {
        if (this.paused || this.recorder.state !== "recording") return;
        // Everything recorded so far is kept now, not a second from now.
        try {
          this.recorder.requestData();
        } catch (e) {
          /* best effort */
        }
        this.recorder.pause();
        this.activeMs += now() - this.activeSince;
        this.paused = true;
        emit();
      }

      resume() {
        if (!this.paused) return;
        this.recorder.resume();
        this.activeSince = now();
        this.paused = false;
        emit();
      }

      stop() {
        this.stoppedByUser = true;
        if (this.recorder.state !== "inactive") {
          this.recorder.stop();
        } else {
          this.finalize();
        }
        return this.done;
      }

      async acquireWakeLock() {
        if (!nav.wakeLock || !nav.wakeLock.request) return;
        if (doc && doc.visibilityState !== "visible") return;
        if (this.wakeLock && !this.wakeLock.released) return;
        try {
          this.wakeLock = await nav.wakeLock.request("screen");
        } catch (e) {
          this.wakeLock = null;
        }
        emit();
      }

      release() {
        if (this.heartbeat) timers.clear(this.heartbeat);
        this.heartbeat = null;
        if (this.stream) this.stream.getTracks().forEach((track) => track.stop());
        if (this.audio) {
          try {
            this.audio.close();
          } catch (e) {
            /* already closed */
          }
        }
        if (this.wakeLock) {
          try {
            this.wakeLock.release();
          } catch (e) {
            /* already released */
          }
        }
        this.wakeLock = null;
      }

      // Called once, when the recorder has stopped for whatever reason --
      // the Stop button, the microphone being taken by a phone call, the
      // browser giving up.  The last dataavailable arrives before onstop, so
      // everything is in `pending` by now; it is written before the
      // recording is marked stopped, because a stopped recording is one the
      // uploader treats as complete.
      async finalize() {
        if (this.finalizing) return;
        this.finalizing = true;

        if (!this.paused && this.activeSince) this.activeMs += now() - this.activeSince;
        this.paused = false;
        this.activeSince = null;

        this.release();

        await this.flush();

        if (this.pending.length) {
          // Storage refused the last of it.  Keep trying in the background;
          // the recording stays "recording" in storage until then, which on
          // a reload recovers exactly what was written.
          this.retryFlush();
          await new Promise((resolve) => {
            const wait = () => (this.pending.length ? timers.set(wait, 1000) : resolve());
            wait();
          });
        }

        this.meta.durationMs = this.activeMs;
        this.meta.updatedAt = now();

        if (this.meta.chunks === 0) {
          await store.deleteRecording(this.meta.id);
          metas.delete(this.meta.id);
          session = null;
          this.finished({ empty: true });
          emit();
          return;
        }

        this.meta.state = "stopped";
        this.meta.interrupted = !this.stoppedByUser;
        try {
          await store.putMeta(this.meta);
        } catch (e) {
          /* recovered as interrupted on the next load, with every chunk */
        }
        remember(this.meta);
        session = null;
        emit();
        // Only now: the lock is what tells other tabs this recording is
        // live, and it must outlast the last write.
        this.finished({ meta: Object.assign({}, this.meta), interrupted: this.meta.interrupted });
        kick(this.meta.id);
      }
    }

    async function startRecording(opts) {
      const settings = opts || {};

      if (session) throw new Error("already recording");

      const problem = supported();
      if (problem) {
        const error = new Error(problem);
        error.name = problem === "insecure" ? "InsecureContext" : "NotSupported";
        throw error;
      }

      await init();

      // Echo cancellation is for a call, where the speaker plays back into
      // the microphone; here nothing plays back, and it colours a voice
      // across a room.  Noise suppression cuts quiet, distant speech along
      // with the ventilation, and the transcription model copes with the
      // ventilation far better than with speech that has been cut.  Gain
      // control is what makes a lecturer ten metres away audible at all.
      const constraints = {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: true,
      };

      let stream;
      let fellBack = false;

      try {
        stream = await nav.mediaDevices.getUserMedia({
          audio: settings.deviceId
            ? Object.assign({ deviceId: { exact: settings.deviceId } }, constraints)
            : constraints,
        });
      } catch (e) {
        // exact, so an unplugged microphone fails loudly rather than
        // quietly recording from something else -- and only then is the
        // default used, with the reader told so.
        if (e && e.name === "OverconstrainedError" && settings.deviceId) {
          stream = await nav.mediaDevices.getUserMedia({ audio: constraints });
          fellBack = true;
        } else {
          throw e;
        }
      }

      const kind = pickKind();
      const recorderOptions = { audioBitsPerSecond: BITRATE };
      if (kind) recorderOptions.mimeType = kind[0];

      let recorder;
      try {
        recorder = new MediaRecorderImpl(stream, recorderOptions);
      } catch (e) {
        recorder = new MediaRecorderImpl(stream);
      }

      const mime = (recorder.mimeType || (kind && kind[0]) || "audio/webm").split(";")[0];
      const start = new Date(now());
      const meta = {
        id: newId(cryptoApi),
        owner: owner,
        name: (settings.name || "").trim() || defaultName(start),
        mime: mime,
        createdAt: now(),
        updatedAt: now(),
        state: "recording",
        chunks: 0,
        bytes: 0,
        durationMs: 0,
        submit: false,
        interrupted: false,
        error: null,
        follows: settings.follows || null,
      };

      try {
        await store.putMeta(meta);
      } catch (e) {
        storeProblem = "unwritable";
      }

      // A live analyser on the stream already open, for the level meter:
      // it is what tells the reader the microphone is hearing anything.
      // Deliberately not connected to the destination, which would play the
      // microphone back through the speaker it can hear.
      const extras = { analyser: null, audio: null };
      try {
        if (AudioContextImpl) {
          extras.audio = new AudioContextImpl();
          extras.analyser = extras.audio.createAnalyser();
          extras.analyser.fftSize = 2048;
          extras.audio.createMediaStreamSource(stream).connect(extras.analyser);
        }
      } catch (e) {
        extras.analyser = null;
      }

      const live = new Session(meta, stream, recorder, extras);
      live.fellBack = fellBack;
      session = live;

      // Held until the recording is finalised: how another tab knows,
      // exactly, that this one is still recording it.
      if (nav.locks && nav.locks.request) {
        nav.locks.request("scribe-live-" + meta.id, () => live.done).catch(() => {});
      }

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size) {
          live.pending.push(event.data);
          live.flush();
        }
      };
      recorder.onstop = () => live.finalize();
      recorder.onerror = () => {
        // onstop follows an error; finalize() is what keeps what was made.
      };

      stream.getTracks().forEach((track) => {
        // The microphone taken away -- a phone call, another app, a headset
        // unplugged.  The recorder stops itself; the recording so far is
        // kept and the page offers to carry on in a new part.
        track.onended = () => {
          if (recorder.state !== "inactive") {
            try {
              recorder.stop();
            } catch (e) {
              live.finalize();
            }
          }
        };
        // Muted is the phone pausing the microphone -- iOS does it when the
        // screen locks.  Nothing to do but say so; audio resumes with it.
        track.onmute = () => {
          live.muted = true;
          emit();
        };
        track.onunmute = () => {
          live.muted = false;
          emit();
        };
      });

      recorder.start(CHUNK_MS);
      live.activeSince = now();
      const tick = () => {
        if (live.finalizing) return;
        live.beat();
        live.heartbeat = timers.set(tick, HEARTBEAT_MS);
      };
      live.heartbeat = timers.set(tick, HEARTBEAT_MS);

      live.acquireWakeLock();
      remember(meta);

      // Ask for storage that is not cleared under pressure.  Granted or not,
      // it costs nothing to ask, and a phone that is nearly full is exactly
      // where a browser starts evicting.
      if (nav.storage && nav.storage.persist) {
        nav.storage.persist().catch(() => {});
      }

      return live;
    }

    // -- What the page does with recordings --

    async function update(id, change) {
      if (session && session.meta.id === id) {
        Object.assign(session.meta, change);
        await store.putMeta(session.meta);
        remember(session.meta);
        return session.meta;
      }

      const meta = await store.getMeta(id);
      if (!meta || meta.owner !== owner) return null;
      Object.assign(meta, change);
      await store.putMeta(meta);
      remember(meta);
      return meta;
    }

    async function submit(id, name) {
      const change = { submit: true, error: null };
      if (name !== undefined && String(name).trim()) change.name = String(name).trim();
      const meta = await update(id, change);
      if (!meta) return null;
      retry.delete(id);
      setSync(id, { phase: "queued", attempts: 0, message: null });
      return kick(id);
    }

    async function discard(id) {
      if (session && session.meta.id === id) throw new Error("still recording");
      const meta = await store.getMeta(id);
      if (meta && meta.owner !== owner) return;
      // Only this browser's copy: an uploaded recording stays in My files.
      await store.deleteRecording(id);
      metas.delete(id);
      sync.delete(id);
      if (retry.has(id)) {
        timers.clear(retry.get(id).handle);
        retry.delete(id);
      }
      emit();
    }

    async function blob(id) {
      const meta = await store.getMeta(id);
      if (!meta || meta.owner !== owner) return null;
      const chunks = await store.getChunks(id, 0, meta.chunks);
      return new Blob(chunks, { type: meta.mime });
    }

    function fileName(meta) {
      const extension = (KINDS.find((kind) => kind[0].split(";")[0] === meta.mime) || [0, ".webm"])[1];
      const stem = String(meta.name || "Recording").replace(/[\/\\:*?"<>|\x00-\x1f]/g, "").trim();
      return (stem || "Recording") + extension;
    }

    function list() {
      return Array.from(metas.values())
        .filter((meta) => meta.owner === owner)
        .map((meta) => {
          const live = session && session.meta.id === meta.id;
          const current = live ? session.meta : meta;
          const elsewhere =
            !live && current.state === "recording" && now() - current.updatedAt <= LIVE_STALE_MS;
          return Object.assign({}, current, {
            live: !!live,
            elsewhere: elsewhere,
            sync: sync.get(meta.id) || { phase: "idle" },
          });
        })
        .sort((a, b) => b.createdAt - a.createdAt);
    }

    async function storageEstimate() {
      if (!nav.storage || !nav.storage.estimate) return null;
      try {
        const estimate = await nav.storage.estimate();
        return { free: Math.max(0, (estimate.quota || 0) - (estimate.usage || 0)) };
      } catch (e) {
        return null;
      }
    }

    return {
      init: init,
      list: list,
      kick: kick,
      kickAll: kickAll,
      submit: submit,
      rename: (id, name) => update(id, { name: String(name || "").trim() }),
      discard: discard,
      blob: blob,
      fileName: fileName,
      startRecording: startRecording,
      supported: supported,
      storageEstimate: storageEstimate,
      session: () => session,
      storeProblem: () => storeProblem,
      persistent: () => !!store.persistent && !storeProblem,
      onChange: (fn) => {
        listeners.add(fn);
        return () => listeners.delete(fn);
      },
      // For tests.
      _syncOnce: syncOnce,
      _store: store,
    };
  }

  // One engine per page, shared by whatever on it wants one: the recorder
  // and the files page's reminder must not each run their own uploader.
  let shared = null;

  function engine(owner) {
    if (shared && shared.owner === owner) return shared.engine;

    const made = createEngine({ owner: owner });
    shared = { owner: owner, engine: made };

    if (typeof window !== "undefined") {
      // Coming back online, or back to the tab, is the moment a waiting
      // upload is most likely to go through.
      window.addEventListener("online", () => made.kickAll(true));
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState !== "visible") {
          const live = made.session();
          // The last second, kept now: a hidden tab on a phone is the one
          // most likely to be killed without another event.
          if (live && live.recorder.state === "recording") {
            try {
              live.recorder.requestData();
            } catch (e) {
              /* best effort */
            }
          }
          return;
        }
        const live = made.session();
        if (live) live.acquireWakeLock();
        made.kickAll(true);
      });
      // Leaving while recording asks first.  It is the one thing here that
      // can stop a recording in progress, and it is easy to do by accident
      // on a phone -- a swipe, a tap on a notification.
      window.addEventListener("beforeunload", (event) => {
        if (made.session()) {
          event.preventDefault();
          event.returnValue = "";
        }
      });
    }

    return made;
  }

  return {
    CHUNK_MS: CHUNK_MS,
    BITRATE: BITRATE,
    LIVE_STALE_MS: LIVE_STALE_MS,
    KEEP_UPLOADED_MS: KEEP_UPLOADED_MS,
    createEngine: createEngine,
    memoryStore: memoryStore,
    defaultName: defaultName,
    engine: engine,
  };
});

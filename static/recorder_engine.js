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
// The rule everything here follows is that **audio is kept on this device
// only while it cannot be sent to Scribe**:
//
//   - While recording, audio is held in memory, and every complete part
//     (PART_CHUNKS seconds) is sent to the backend, which encrypts it as it
//     arrives.  Once the backend has confirmed a part it is dropped.
//     Online, nothing but a small record of the recording is written to the
//     device, and what a crash costs is the part not yet sent.
//   - The moment a send fails -- offline, Scribe down, signed out -- what is
//     held in memory is written to IndexedDB, and so is everything recorded
//     after it, so a crash, a reload or a flat battery then costs the last
//     second rather than everything since the connection went.  Each part
//     is deleted from IndexedDB as soon as it gets through, and once the
//     backlog is cleared recording goes back to memory.
//   - Whatever is written is encrypted (AES-GCM) first -- the audio and the
//     recording's name alike.  The key comes from the server for this user
//     and this browser and is held in memory only, so what is left in
//     IndexedDB is unreadable without signing in.
//   - Stop sends the rest and asks the backend to make the recording a job
//     at once; the recording then leaves this device altogether.  Its
//     original is downloaded from Scribe, not from here.
//   - Before sending anything the backend is asked what it already holds,
//     so a reload half way through sends only what is missing.  A part is
//     immutable once complete, so sending one twice is harmless and a part
//     that got no answer is simply sent again.
//   - Failures are sorted into "later" (offline, server or backend down),
//     "after signing in again" and "never as sent", and only the last one
//     stops the retrying.  Nothing is ever deleted because a send failed:
//     offline, parts simply wait here until they can go.
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
  // Five chunks to a part: about 40 KB at BITRATE.  A part is only in memory
  // until it is sent, so this is what a crash costs while online -- set
  // against the number of requests, 720 an hour, which is still nothing.
  const PART_CHUNKS = 5;
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
  const IV_BYTES = 12;

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
      getChunkMap: (rid, from, to) =>
        run(["chunks"], "readonly", (tx, set) => {
          const request = tx.objectStore("chunks").getAll(chunkRange(rid, from, to));
          request.onsuccess = () => set(new Map((request.result || []).map((c) => [c.seq, c.data])));
        }),
      deleteChunks: (rid) =>
        run(["chunks"], "readwrite", (tx) => {
          tx.objectStore("chunks").delete(chunkRange(rid, 0, Infinity));
        }),
      // Chunks the backend has confirmed, dropped in the same transaction
      // as the meta saying so: after a crash the two still agree.
      dropChunks: (meta, from, to) =>
        run(["recordings", "chunks"], "readwrite", (tx) => {
          tx.objectStore("chunks").delete(chunkRange(meta.id, from, to));
          tx.objectStore("recordings").put(meta);
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
      getChunkMap: async (rid, from, to) => {
        const out = new Map();
        for (let seq = from; seq < to; seq++) {
          const data = chunks.get(rid + "/" + seq);
          if (data !== undefined) out.set(seq, data);
        }
        return out;
      },
      deleteChunks: async (rid) => {
        for (const key of Array.from(chunks.keys())) {
          if (key.startsWith(rid + "/")) chunks.delete(key);
        }
      },
      dropChunks: async (meta, from, to) => {
        for (let seq = from; seq < to; seq++) chunks.delete(meta.id + "/" + seq);
        metas.set(meta.id, copy(meta));
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

  function partCount(chunks) {
    return Math.ceil(chunks / PART_CHUNKS);
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

    // Recordings that became a job while this page was open.  They are gone
    // from storage by then; this is only so the page can say where they went.
    const finishedHere = new Map();

    // -- The key audio is encrypted with on this device --

    // Asked of the server, for this user in this browser, and held in memory
    // only: a reload asks again.  Not extractable once imported, so nothing
    // on the page can read it back out.
    const subtle = cryptoApi && cryptoApi.subtle;
    const encoder = typeof TextEncoder !== "undefined" ? new TextEncoder() : null;
    let keyPromise = null;

    function getKey() {
      if (!keyPromise) {
        keyPromise = (async () => {
          if (!subtle || !encoder) throw new SyncError("refused", "This browser cannot encrypt the recording.");
          let raw;
          if (env.key) {
            raw = await env.key();
          } else {
            const answer = await api("GET", "/key");
            raw = Uint8Array.from(atob(String(answer.key || "")), (c) => c.charCodeAt(0));
          }
          if (!raw || raw.length !== 32) throw new SyncError("unavailable", "Scribe did not hand over a key.");
          return subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
        })();
        keyPromise.catch(() => {
          keyPromise = null;
        });
      }
      return keyPromise;
    }

    // Each chunk is bound to its recording and position, so a chunk cannot
    // be moved to another place -- or another recording -- and still read.
    const chunkLabel = (rid, seq) => encoder.encode(rid + "/" + seq);

    async function seal(rid, seq, data) {
      const key = await getKey();
      const iv = cryptoApi.getRandomValues(new Uint8Array(IV_BYTES));
      const sealed = await subtle.encrypt({ name: "AES-GCM", iv: iv, additionalData: chunkLabel(rid, seq) }, key, data);
      const out = new Uint8Array(IV_BYTES + sealed.byteLength);
      out.set(iv, 0);
      out.set(new Uint8Array(sealed), IV_BYTES);
      return out.buffer;
    }

    async function unseal(rid, seq, stored) {
      const key = await getKey();
      const bytes = new Uint8Array(stored);
      try {
        return await subtle.decrypt(
          { name: "AES-GCM", iv: bytes.slice(0, IV_BYTES), additionalData: chunkLabel(rid, seq) },
          key,
          bytes.slice(IV_BYTES)
        );
      } catch (e) {
        throw new SyncError("refused", "This recording can no longer be read in this browser.");
      }
    }

    // -- The recording's own record, kept encrypted too --

    // A recording's record (its id, how many chunks, which parts Scribe has)
    // is written from the start, online or not: without it a crash would
    // lose track of the parts already on Scribe, and the backend would sweep
    // them.  It holds no audio, and its name -- whatever the reader typed,
    // often a course and a date, sometimes a person -- is encrypted.
    const decoder = typeof TextDecoder !== "undefined" ? new TextDecoder() : null;
    const toBase64 = (buffer) => btoa(String.fromCharCode(...new Uint8Array(buffer)));
    const fromBase64 = (text) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0)).buffer;

    async function sealName(meta) {
      const out = Object.assign({}, meta);
      delete out.name;
      delete out.nameFor;
      // A name that could not be read (no key right now) is carried over
      // sealed as it was, never overwritten by a stand-in.
      if (meta.name == null) return out;
      if (!(meta.nameSealed && meta.nameFor === meta.name)) {
        meta.nameSealed = toBase64(await seal(meta.id, "name", encoder.encode(meta.name)));
        meta.nameFor = meta.name;
      }
      out.nameSealed = meta.nameSealed;
      return out;
    }

    async function openName(stored) {
      if (!stored || !stored.nameSealed) return stored;
      try {
        stored.name = decoder.decode(await unseal(stored.id, "name", fromBase64(stored.nameSealed)));
        stored.nameFor = stored.name;
      } catch (e) {
        stored.name = null;
      }
      return stored;
    }

    const rawStore = store;
    store = {
      persistent: rawStore.persistent,
      putMeta: async (meta) => rawStore.putMeta(await sealName(meta)),
      getMeta: async (id) => openName(await rawStore.getMeta(id)),
      listMeta: async () => Promise.all((await rawStore.listMeta()).map(openName)),
      appendChunk: async (meta, seq, data) => rawStore.appendChunk(await sealName(meta), seq, data),
      dropChunks: async (meta, from, to) => rawStore.dropChunks(await sealName(meta), from, to),
      getChunkMap: (rid, from, to) => rawStore.getChunkMap(rid, from, to),
      deleteChunks: (rid) => rawStore.deleteChunks(rid),
      deleteRecording: (rid) => rawStore.deleteRecording(rid),
    };

    // -- Audio held in memory until it is sent --

    // By recording id, then chunk number: plaintext, never written anywhere
    // unless sending fails (spill()).  Only the tab that recorded it has it.
    const buffers = new Map();

    // Chunks from..to-1, readable, or a SyncError.  From memory where this
    // tab still holds them, from storage otherwise.  Chunks are always a
    // contiguous run, so one missing is storage having lost something
    // underneath us -- and sending round it would stitch a gap into the file.
    async function readChunks(meta, from, to) {
      const held = buffers.get(meta.id);
      const stored = await store.getChunkMap(meta.id, from, to);
      const out = [];
      for (let seq = from; seq < to; seq++) {
        if (held && held.has(seq)) {
          out.push(held.get(seq));
        } else if (stored.has(seq)) {
          out.push(meta.encrypted ? await unseal(meta.id, seq, stored.get(seq)) : stored.get(seq));
        } else {
          throw new SyncError("refused", "Part of the recording is missing on this device.");
        }
      }
      return out;
    }

    // Sending has failed: what is held in memory goes to storage, encrypted,
    // and so does everything recorded from now on (writeAll() reads the
    // flag), until the backlog is sent.  A chunk that cannot be written
    // stays in memory; it is still sent if the tab lives.
    async function spill(meta) {
      meta.spilled = true;
      const held = buffers.get(meta.id);
      if (held) {
        for (const seq of Array.from(held.keys()).sort((a, b) => a - b)) {
          const data = held.get(seq);
          if (data === undefined) continue;
          await store.appendChunk(meta, seq, await seal(meta.id, seq, data));
          held.delete(seq);
        }
      }
      remember(meta);
    }

    // Everything this tab still holds in memory for a recording, sent now.
    // Throws a SyncError if any of it cannot be.
    async function sendHeld(meta) {
      const total = Math.ceil(meta.chunks / PART_CHUNKS);
      for (let part = 0; part < total; part++) {
        if ((meta.sent || []).includes(part)) continue;
        const from = part * PART_CHUNKS;
        const to = Math.min(from + PART_CHUNKS, meta.chunks);
        const data = await readChunks(meta, from, to);
        await api("PUT", "/" + meta.id + "/part/" + part, new Blob(data, { type: meta.mime }), {
          "Content-Type": "application/octet-stream",
        });
        await confirmPart(meta, part);
      }
    }

    // How much of a recording whose tab is gone can still be had: parts on
    // Scribe, then chunks in storage, up to the first gap.  What was only in
    // that tab's memory went with it.
    async function available(meta) {
      const sent = new Set(meta.sent || []);
      const stored = await store.getChunkMap(meta.id, 0, meta.chunks);
      let n = 0;
      while (n < meta.chunks) {
        const part = Math.floor(n / PART_CHUNKS);
        if (sent.has(part)) {
          n = Math.min((part + 1) * PART_CHUNKS, meta.chunks);
        } else if (stored.has(n)) {
          n += 1;
        } else {
          break;
        }
      }
      return n;
    }

    // -- Talking to the server --

    async function api(method, path, body, headers) {
      if (!fetchFn) throw new SyncError("offline", "no fetch");

      let response;

      try {
        response = await fetchFn(API + path, {
          method: method,
          body: body,
          credentials: "same-origin",
          cache: "no-store",
          headers: Object.assign({ "X-Scribe-Recording": "1" }, headers || {}),
        });
      } catch (e) {
        throw new SyncError("offline", "No connection to Scribe.");
      }

      if (response.ok || response.status === 409) {
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

    // The backend holds it now, original and all, so nothing of it stays on
    // this device.  The original is downloaded from Scribe's file list.
    async function markUploaded(meta, done) {
      meta.state = "uploaded";
      meta.job = done || {};
      meta.uploadedAt = now();
      meta.error = null;
      await store.deleteRecording(meta.id);
      buffers.delete(meta.id);
      metas.delete(meta.id);
      finishedHere.set(meta.id, Object.assign({}, meta));
      emit();
    }

    // A part the backend has confirmed: its audio is dropped here.
    async function confirmPart(meta, part) {
      const from = part * PART_CHUNKS;
      const to = Math.min(from + PART_CHUNKS, meta.chunks);
      const held = buffers.get(meta.id);
      if (held) for (let seq = from; seq < to; seq++) held.delete(seq);
      const sent = new Set(meta.sent || []);
      if (sent.has(part)) return;
      sent.add(part);
      meta.sent = Array.from(sent).sort((a, b) => a - b);
      // The record is written with it either way: it is what says, after a
      // crash, that this part is on Scribe.
      await store.dropChunks(meta, from, to);
      remember(meta);
    }

    const lostPart = () =>
      new SyncError("refused", "Part of this recording was lost on Scribe before it was finished.");

    // One attempt at moving a recording on: send what the server lacks and,
    // if the reader has asked for it, finish.  Throws a SyncError to say why
    // it stopped; returns what state it reached.
    async function syncOnce(id) {
      const meta = (session && session.meta.id === id && session.meta) || (await store.getMeta(id));

      if (!meta || meta.owner !== owner || meta.state === "uploaded") return "idle";

      const live = meta.state === "recording";

      // Its audio is in another tab's memory; that tab sends it.
      if (live && !(session && session.meta.id === id)) return "idle";
      const total = partCount(meta.chunks);
      const ready = live ? Math.floor(meta.chunks / PART_CHUNKS) : total;
      const finishing = meta.submit && !live;

      if (ready === 0 && !finishing) return "idle";

      if (finishing && total === 0) {
        throw new SyncError("refused", "Nothing was recorded.");
      }

      const status = await api("GET", "/" + id);

      if (status.done) {
        await markUploaded(meta, status.done);
        return "done";
      }

      const have = new Set(status.parts || []);

      for (const part of meta.sent || []) {
        if (!have.has(part)) throw lostPart();
      }

      // Forty rounds is far more than a correct server ever needs (one to
      // send, one more if it lost parts while we sent), and bounds a server
      // that keeps claiming parts are missing.
      for (let round = 0; round < 40; round++) {
        setSync(id, { phase: "uploading", sent: Math.min(have.size, ready), total: live ? null : total });

        for (let part = 0; part < ready; part++) {
          if (have.has(part)) {
            // Held there already -- its answer was lost on the way back.
            await confirmPart(meta, part);
            continue;
          }

          if ((meta.sent || []).includes(part)) throw lostPart();

          const data = await readChunks(
            meta,
            part * PART_CHUNKS,
            Math.min((part + 1) * PART_CHUNKS, meta.chunks)
          );

          await api("PUT", "/" + id + "/part/" + part, new Blob(data, { type: meta.mime }), {
            "Content-Type": "application/octet-stream",
          });
          have.add(part);
          await confirmPart(meta, part);
          setSync(id, { phase: "uploading", sent: have.size, total: live ? null : total });
        }

        if (!finishing) {
          // Caught up: what is recorded from now on is held in memory again.
          // Chunks already in storage stay there until their part is sent.
          if (live && meta.spilled) {
            meta.spilled = false;
            remember(meta);
          }
          setSync(id, { phase: "backed-up", sent: have.size, total: null });
          return "backed-up";
        }

        setSync(id, { phase: "finishing", sent: total, total: total });

        const answer = await api(
          "POST",
          "/" + id + "/finish",
          JSON.stringify({ parts: total, name: meta.name, mime: meta.mime }),
          { "Content-Type": "application/json" }
        );

        if (answer && answer.done) {
          await markUploaded(meta, answer.done);
          return "done";
        }

        if (answer && Array.isArray(answer.missing)) {
          answer.missing.forEach((part) => have.delete(part));
          continue;
        }

        throw new SyncError("unavailable", "Scribe gave an unexpected answer.");
      }

      throw new SyncError("unavailable", "Scribe keeps losing parts of the recording.");
    }

    // Single flight per recording: a kick while one is running is folded
    // into one more run afterwards rather than a second one alongside it.
    // Across tabs, a Web Lock keeps two tabs from sending the same recording
    // at once; the server is idempotent either way, this only saves bytes.
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

      if (session && session.meta.id === id) {
        try {
          await spill(session.meta);
        } catch (e) {
          session.writeProblem = (e && e.name) || "write failed";
          emit();
        }
      }

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
    // gets its last, still-growing part sent as if it were final.  Timing
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

        // Left by an earlier version, which kept uploaded audio around.
        if (meta.state === "uploaded") {
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
          meta.chunks = await available(meta);
          if (meta.chunks === 0) {
            await store.deleteRecording(meta.id);
            api("DELETE", "/" + meta.id).catch(() => {});
            continue;
          }
          try {
            await store.putMeta(meta);
          } catch (e) {
            /* no key right now: settled again next time */
          }
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
        this.samples = this.analyser ? new Float32Array(this.analyser.fftSize) : null;
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

      // Peak and RMS of the last frame, 0..1.  Float samples, not bytes: a
      // byte has nothing below about -42 dB, which is exactly where "is the
      // microphone hearing anything at all" is decided.
      loudness() {
        if (!this.analyser) return { peak: 0, rms: 0 };
        this.analyser.getFloatTimeDomainData(this.samples);
        let peak = 0;
        let sum = 0;
        for (let i = 0; i < this.samples.length; i++) {
          const value = Math.abs(this.samples[i]);
          if (value > peak) peak = value;
          sum += value * value;
        }
        return { peak: peak, rms: Math.sqrt(sum / this.samples.length) };
      }

      level() {
        return this.loudness().peak;
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

          // Sending is keeping up: memory only.  No await between the check
          // and the set, so spill() cannot miss a chunk put here.
          if (!this.meta.spilled) {
            buffers.get(this.meta.id).set(seq, data);
            this.pending.shift();
            if (this.meta.chunks % PART_CHUNKS === 0) kick(this.meta.id);
            continue;
          }

          try {
            const stored = this.meta.encrypted ? await seal(this.meta.id, seq, data) : data;
            await store.appendChunk(this.meta, seq, stored);
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

          if (this.meta.chunks % PART_CHUNKS === 0) kick(this.meta.id);
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

        // Nothing holds this tab's memory once the session ends, so what is
        // still only there is sent now, while the recording is still marked
        // as live here (no other tab touches it) -- or, if it cannot be,
        // written to storage.  A long backlog is not waited on: it is
        // written, and sent from storage like any other.
        const held = buffers.get(this.meta.id);
        if (held && held.size && this.meta.chunks) {
          try {
            if (held.size > PART_CHUNKS * 2 || this.meta.spilled) throw new SyncError("unavailable", "backlog");
            await sendHeld(this.meta);
          } catch (e) {
            try {
              await spill(this.meta);
            } catch (e2) {
              /* storage refused too: sent from memory while this tab lives */
            }
          }
        }

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
        // Stopped on purpose is finished: it goes to Scribe at once.  One
        // that was cut short (a call took the microphone, the tab died)
        // waits for the reader, who may carry on recording it.
        if (this.stoppedByUser) this.meta.submit = true;
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

      // Without the key nothing can be kept, so nothing is recorded: the
      // page is open, so the server was reachable a moment ago.
      try {
        await getKey();
      } catch (e) {
        const error = new Error(e && e.message ? e.message : "no key");
        error.name = "NoKey";
        throw error;
      }

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
        encrypted: true,
        sent: [],
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

      buffers.set(meta.id, new Map());
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
      finishedHere.delete(id);
      buffers.delete(id);
      await store.deleteRecording(id);
      metas.delete(id);
      sync.delete(id);
      if (retry.has(id)) {
        timers.clear(retry.get(id).handle);
        retry.delete(id);
      }
      emit();
      // Best effort: the backend sweeps what it is not told about anyway.
      if (meta) api("DELETE", "/" + id).catch(() => {});
    }

    function list() {
      return Array.from(metas.values())
        .concat(Array.from(finishedHere.values()).filter((meta) => !metas.has(meta.id)))
        .filter((meta) => meta.owner === owner)
        .map((meta) => {
          const live = session && session.meta.id === meta.id;
          const current = live ? session.meta : meta;
          const elsewhere =
            !live && current.state === "recording" && now() - current.updatedAt <= LIVE_STALE_MS;
          return Object.assign({}, current, {
            name: current.name == null ? "Recording" : current.name,
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
      _readChunks: readChunks,
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
    PART_CHUNKS: PART_CHUNKS,
    BITRATE: BITRATE,
    LIVE_STALE_MS: LIVE_STALE_MS,
    createEngine: createEngine,
    memoryStore: memoryStore,
    defaultName: defaultName,
    engine: engine,
  };
});

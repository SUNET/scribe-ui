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

// A line on the files page about recordings still on this device.
//
// It is also what keeps them moving: the engine it starts resumes every
// upload a previous page left unfinished -- the recorder was closed, the
// phone went offline, the server restarted -- so a professor who never goes
// back to the recorder still gets the lecture into My files.  When one
// arrives it says so to the server, which redraws the table.
//
// Draws nothing at all when there is nothing on the device.

export default {
  template: `
    <div v-if="waiting.length || moving.length" class="recorder-reminder" role="status" aria-live="polite">
      <q-icon :name="moving.length ? 'cloud_upload' : 'save'" size="20px" aria-hidden="true" />
      <span class="recorder-reminder-text">{{ text }}</span>
      <q-btn flat no-caps dense class="recorder-reminder-open" label="Open recorder" @click="open" />
    </div>
  `,

  emits: ["uploaded"],

  props: {
    owner: { type: String, required: true },
    recorderUrl: { type: String, default: "/record" },
  },

  data() {
    return { items: [] };
  },

  computed: {
    pending() {
      return this.items.filter((item) => item.state !== "uploaded" && !item.live);
    },
    moving() {
      return this.pending.filter((item) => item.submit && !item.error);
    },
    waiting() {
      return this.pending.filter((item) => !item.submit || item.error);
    },
    text() {
      const parts = [];
      if (this.moving.length) {
        parts.push(
          this.moving.length === 1
            ? "A recording is being uploaded from this browser."
            : this.moving.length + " recordings are being uploaded from this browser."
        );
      }
      if (this.waiting.length) {
        parts.push(
          this.waiting.length === 1
            ? "A recording in this browser has not been uploaded yet."
            : this.waiting.length + " recordings in this browser have not been uploaded yet."
        );
      }
      return parts.join(" ");
    },
  },

  mounted() {
    if (!window.ScribeRecorder || !this.owner) return;

    this.engine = window.ScribeRecorder.engine(this.owner);
    this.seen = new Set();
    // Only an upload that finishes while this page is open is news.  The
    // engine announces a change while it is still reading storage, so
    // without `ready` every recording uploaded on some earlier visit was
    // announced again on every load of this page.
    this.ready = false;
    this.unwatch = this.engine.onChange(() => this.redraw());
    this.engine.init().then(() => {
      this.engine.list().forEach((item) => {
        if (item.state === "uploaded") this.seen.add(item.id);
      });
      this.ready = true;
      this.redraw();
    });
  },

  beforeUnmount() {
    if (this.unwatch) this.unwatch();
  },

  methods: {
    redraw() {
      this.items = this.engine.list();
      if (!this.ready) return;
      for (const item of this.items) {
        if (item.state === "uploaded" && !this.seen.has(item.id)) {
          this.seen.add(item.id);
          this.$emit("uploaded", { name: item.name });
        }
      }
    },

    open() {
      window.location.href = this.recorderUrl;
    },
  },
};

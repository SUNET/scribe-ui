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

// A transcription editor: one contenteditable holding every speaker turn.
//
// The gutter cells carry the speaker and the timestamps. They are real
// elements so they can be clicked, but contenteditable=false, so the caret
// cannot enter them and typing can never damage them.
//
// Structural keys are intercepted rather than left to the browser. Enter,
// Backspace at the start of a block and Delete at its end would otherwise let
// the browser invent or destroy elements inside the contenteditable, which is
// where this kind of editor usually falls apart. Instead each of them is
// reported to the server, which owns the block structure and sends back a
// fresh set. The contenteditable is then only ever doing what it is reliable
// at: editing text inside one block.

export default {
  template: `
    <div class="transcript-editor">
      <div
        class="transcript-body"
        contenteditable="true"
        spellcheck="false"
        @input="onInput"
        @keydown="onKeydown"
        @click="onClick"
        ref="body"
      ><template v-for="block in blocks" :key="block.id"><div
          class="transcript-gutter"
          contenteditable="false"
          :data-id="block.id"
        ><span
            class="transcript-speaker"
            :data-id="block.id"
          >{{ block.speaker }}</span><span class="transcript-colon">:</span></div><div
          class="transcript-cell"
          :class="{ 'transcript-cell-active': block.id === activeId }"
          :data-id="block.id"
        ><div
            class="transcript-time"
            contenteditable="false"
            :data-id="block.id"
          >{{ block.start_label }}<span class="transcript-dash">-</span>{{ block.end_label }}</div><div
            class="transcript-text"
            :data-id="block.id"
          ><span v-for="(run, i) in block.runs" :key="i" :class="run.flag ? 'review-word' : null" :data-review="run.flag ? reviewLabel : null" :data-s="run.s" :data-e="run.e">{{ run.t }}</span><br v-if="!block.runs || block.runs.length === 0"></div></div></template></div>
    </div>
  `,
  props: {
    blocks: { type: Array, default: () => [] },
    activeId: { type: Number, default: -1 },
    reviewLabel: { type: String, default: "" },
    highlightWord: { type: Boolean, default: false },
    follow: { type: Boolean, default: false },
    revision: { type: Number, default: 0 },
  },
  // One watch block. Two would silently discard the first: duplicate keys in
  // an object literal keep only the last.
  watch: {
    activeId(id) {
      if (!this.follow) return;
      const cell = this.$refs.body?.querySelector(
        `.transcript-cell[data-id="${id}"]`
      );
      if (cell) cell.scrollIntoView({ block: "center", behavior: "smooth" });
    },
    revision() {
      // Bumped by the server only when the blocks actually change. Watching
      // the blocks themselves fires on every update, because an update
      // resends all props and the array arrives as a new reference -- several
      // times a second while the audio plays.
      this.$nextTick(() => this.indexWords());
    },
    highlightWord(on) {
      if (on) this.$nextTick(() => this.indexWords());
      else this.clearCurrentWord();
    },
  },
  data() {
    return { pending: null, timed: [] };
  },
  mounted() {
    // Following the audio has to happen here rather than on the server: a
    // word lasts a few hundred milliseconds, and a round trip per word would
    // be both late and wasteful.
    this.onTime = () => this.markCurrentWord();
    this.attachVideo();
    this.$nextTick(() => this.indexWords());
  },
  beforeUnmount() {
    this.video?.removeEventListener("timeupdate", this.onTime);
    this.video?.removeEventListener("seeking", this.onTime);
  },
  methods: {
    // The block a node sits in, walking up from wherever the caret is.
    blockOf(node) {
      let el = node instanceof Element ? node : node?.parentElement;
      while (el && !el.classList?.contains("transcript-text")) {
        el = el.parentElement;
      }
      return el;
    },

    caret() {
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0) return null;
      const range = selection.getRangeAt(0);
      const block = this.blockOf(range.startContainer);
      if (!block) return null;
      // Offset from the start of the block's text, not of the text node,
      // so a block split across highlight spans still reports one number.
      const measure = range.cloneRange();
      measure.selectNodeContents(block);
      measure.setEnd(range.startContainer, range.startOffset);
      return {
        id: Number(block.dataset.id),
        offset: measure.toString().length,
        length: block.textContent.length,
        collapsed: range.collapsed,
        block,
      };
    },

    // Text edits are reported on a short delay: the server recomputes the
    // review highlighting from them, and doing that per keystroke would fight
    // the caret.
    onInput() {
      const at = this.caret();
      if (!at) return;
      clearTimeout(this.pending);
      const id = at.id;
      const text = at.block.textContent;
      this.pending = setTimeout(() => this.$emit("blocktext", { id, text }), 400);
    },

    flush() {
      clearTimeout(this.pending);
      const at = this.caret();
      if (at) {
        this.$emit("blocktext", { id: at.id, text: at.block.textContent });
      }
    },

    onKeydown(event) {
      const at = this.caret();
      if (!at) return;

      // Let the server split and re-render, rather than letting the browser
      // guess what element a new line should be.
      if (event.key === "Enter") {
        event.preventDefault();
        this.flush();
        this.$emit("splitblock", { id: at.id, offset: at.offset });
        return;
      }

      // Joining blocks is a structural change too, but only when the caret is
      // against the edge and nothing is selected -- otherwise it is an
      // ordinary character delete.
      if (event.key === "Backspace" && at.collapsed && at.offset === 0) {
        event.preventDefault();
        this.flush();
        this.$emit("mergeblock", { id: at.id, direction: "previous" });
        return;
      }

      if (event.key === "Delete" && at.collapsed && at.offset === at.length) {
        event.preventDefault();
        this.flush();
        this.$emit("mergeblock", { id: at.id, direction: "next" });
      }
    },

    onClick(event) {
      const speaker = event.target.closest(".transcript-speaker");
      if (speaker) {
        this.$emit("speakerclick", { id: Number(speaker.dataset.id) });
        return;
      }

      const time = event.target.closest(".transcript-time");
      if (time) {
        this.$emit("timeclick", { id: Number(time.dataset.id) });
        return;
      }

      const block = this.blockOf(event.target);
      if (block) {
        this.$emit("blockclick", { id: Number(block.dataset.id) });
      }
    },

    // Put the caret in a block. Used after a new one is started, so it can be
    // typed into without reaching for the mouse.
    focusBlock(id) {
      this.$nextTick(() => {
        const block = this.$refs.body?.querySelector(
          `.transcript-text[data-id="${id}"]`
        );
        if (!block) return;

        this.$refs.body.focus();

        const range = document.createRange();
        range.selectNodeContents(block);
        range.collapse(true);

        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      });
    },

    attachVideo() {
      this.video = document.querySelector("video");
      if (!this.video) return;
      this.video.addEventListener("timeupdate", this.onTime);
      this.video.addEventListener("seeking", this.onTime);
    },

    // Every word that carries a timing, in playback order, so the word under
    // the playhead can be found by bisection rather than by scanning.
    indexWords() {
      const body = this.$refs.body;
      if (!body) return;
      this.timed = Array.from(body.querySelectorAll("[data-s]"))
        .map((el) => ({ el, s: Number(el.dataset.s), e: Number(el.dataset.e) }))
        .filter((w) => Number.isFinite(w.s) && Number.isFinite(w.e))
        .sort((a, b) => a.s - b.s);
    },

    // Asks the DOM what is marked rather than trusting a remembered element.
    // A re-render can drop that reference while the mark is still on the page,
    // which is how marks were piling up as playback moved on.
    clearCurrentWord() {
      this.$refs.body
        ?.querySelectorAll("[data-current]")
        .forEach((el) => el.removeAttribute("data-current"));
    },

    currentWord() {
      return this.$refs.body?.querySelector("[data-current]") || null;
    },

    markCurrentWord() {
      if (!this.highlightWord || !this.video || this.timed.length === 0) return;

      const t = this.video.currentTime;
      const marked = this.currentWord();

      // Still inside the word already marked: nothing to do, which is the
      // common case between ticks.
      if (marked) {
        const s = Number(marked.dataset.s);
        const e = Number(marked.dataset.e);
        if (t >= s && t < e) return;
      }

      let low = 0;
      let high = this.timed.length - 1;
      let found = null;

      while (low <= high) {
        const mid = (low + high) >> 1;
        const word = this.timed[mid];
        if (t < word.s) high = mid - 1;
        else if (t >= word.e) low = mid + 1;
        else {
          found = word;
          break;
        }
      }

      if (found && found.el === marked) return;

      this.clearCurrentWord();

      // Marked with an attribute, not a class: the spans have a bound :class
      // for the review marking, and Vue rewrites that list whenever it
      // patches them, which would take a class added here with it.
      //
      // Silence between words leaves nothing marked, rather than leaving the
      // previous word lit until the next one starts.
      if (found) found.el.setAttribute("data-current", "");
    },
  },
};

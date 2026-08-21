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
// The gutter cells carry the speaker; the cell itself carries the timing,
// as a pair of plain inputs. Both are real elements so they can be clicked
// or typed into, but contenteditable=false, so the caret cannot enter them
// through the surrounding text and typing there can never damage it.
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
    <div class="transcript-editor" :class="{ 'transcript-show-edits': showEdits, 'transcript-subtitle-mode': subtitleMode }">
      <div
        class="transcript-body"
        contenteditable="true"
        spellcheck="false"
        @input="onInput"
        @keydown="onKeydown"
        @click="onClick"
        @blur="flush"
        ref="body"
      ><template v-for="block in blocks" :key="blockKey(block)"><div
          class="transcript-gutter"
          contenteditable="false"
          :data-id="block.id"
        ><span
            v-if="subtitleMode"
            class="transcript-subtitle-index"
          >#{{ block.id }}</span><div
            v-if="subtitleMode"
            class="transcript-subtitle-counts"
          ><span
              v-for="(count, i) in (liveCounts[block.id] || block.line_counts)"
              :key="i"
              class="transcript-count-row"
            ><span
                class="transcript-count"
                :class="{ 'transcript-count-exceeded': count.exceeded }"
                :title="count.tooltip"
              >{{ count.length }}</span></span></div><span
            v-else
            class="transcript-speaker"
            :data-id="block.id"
          >{{ block.speaker }}</span><span v-if="!subtitleMode" class="transcript-colon">:</span></div><div
          class="transcript-cell"
          :class="{ 'transcript-cell-active': block.id === activeId, 'transcript-cell-invalid': block.invalid, 'transcript-cell-highlighted': block.highlighted }"
          :data-id="block.id"
        ><div
            v-if="!subtitleMode"
            class="transcript-time"
            contenteditable="false"
            :data-id="block.id"
          ><input
              class="transcript-time-input"
              :value="block.start_label"
              @click.stop
              @keydown="onTimeInputKeydown($event)"
              @blur="retimeBlock(block.id, 'start', $event)"
            /><span class="transcript-dash">-</span><input
              class="transcript-time-input"
              :value="block.end_label"
              @click.stop
              @keydown="onTimeInputKeydown($event)"
              @blur="retimeBlock(block.id, 'end', $event)"
            /></div><div
            v-if="subtitleMode"
            class="transcript-subtitle-content"
          ><div
              class="transcript-subtitle-time"
              contenteditable="false"
              :data-id="block.id"
            ><div class="transcript-subtitle-timing"><input
                  class="transcript-time-input"
                  :value="block.start_label"
                  @click.stop
                  @keydown="onTimeInputKeydown($event)"
                  @blur="retimeBlock(block.id, 'start', $event)"
                /><span class="transcript-dash">-</span><input
                  class="transcript-time-input"
                  :value="block.end_label"
                  @click.stop
                  @keydown="onTimeInputKeydown($event)"
                  @blur="retimeBlock(block.id, 'end', $event)"
                /></div><div
                class="transcript-cell-actions"
              ><div
                  class="transcript-action transcript-action-split"
                  @click.stop="splitAt(block.id)"
                ><q-icon name="call_split" size="16px" /><q-tooltip>Split caption at cursor</q-tooltip></div><div
                  class="transcript-action transcript-action-merge"
                  @click.stop="mergeWithNext(block.id)"
                ><q-icon name="merge_type" size="16px" /><q-tooltip>Merge with next caption</q-tooltip></div><div
                  class="transcript-action transcript-action-add"
                  @click.stop="$emit('addblock', { id: block.id })"
                ><q-icon name="add" size="16px" /><q-tooltip>Add caption after</q-tooltip></div><div
                  class="transcript-action transcript-action-delete"
                  @click.stop="$emit('deleteblock', { id: block.id })"
                ><q-icon name="delete_outline" size="16px" /><q-tooltip>Delete caption</q-tooltip></div></div></div><div
              class="transcript-text"
              :data-id="block.id"
            ><span v-for="(run, i) in block.runs" :key="i" :class="run.flag ? 'review-word' : (run.edit ? 'edit-word' : null)" :data-review="run.flag ? reviewLabel : null" :data-edit="editLabel" :data-s="run.s" :data-e="run.e">{{ run.t }}</span><br v-if="!block.runs || block.runs.length === 0"></div></div><div
            v-else
            class="transcript-text"
            :data-id="block.id"
          ><span v-for="(run, i) in block.runs" :key="i" :class="run.flag ? 'review-word' : (run.edit ? 'edit-word' : null)" :data-review="run.flag ? reviewLabel : null" :data-edit="editLabel" :data-s="run.s" :data-e="run.e">{{ run.t }}</span><br v-if="!block.runs || block.runs.length === 0"></div></div></template></div>

      <!-- Outside the contenteditable, or it would become editable content.
           Positioned against this component's own root rather than the
           viewport: the transcription sits in a Quasar scroll area, which sets
           contain: strict, and that quietly makes it the containing block for
           anything position: fixed inside it. Taking the difference between two
           client rects sidesteps the question of which ancestor wins. -->
      <div
        v-if="menu.open"
        class="speaker-menu"
        :style="{ top: menu.y + 'px', left: menu.x + 'px' }"
        @click.stop
      >
        <div class="speaker-menu-add" @click="$emit('addspeaker', {})">
          <span>Add new</span>
          <q-icon name="add" size="20px" />
        </div>
        <div
          v-for="name in speakers"
          :key="name"
          class="speaker-menu-row"
          :class="{ 'speaker-menu-row-current': name === menu.speaker }"
          @click="assign(name)"
        >
          <span class="speaker-menu-name">{{ name }}</span>
          <!-- sym_o_ is Quasar's prefix for Material Symbols Outlined, which
               is where person_edit lives; the plain Material Icons set has no
               such name and would render the ligature text instead. Both fonts
               ship with NiceGUI, so nothing is fetched for this. -->
          <q-icon
            name="sym_o_person_edit"
            size="18px"
            class="speaker-menu-icon"
            @click.stop="$emit('renamespeaker', { speaker: name })"
          ><q-tooltip>Rename speaker</q-tooltip></q-icon>
          <q-icon
            v-if="unused.includes(name)"
            name="delete_outline"
            size="18px"
            class="speaker-menu-icon speaker-menu-remove"
            @click.stop="$emit('removespeaker', { speaker: name })"
          />
        </div>
      </div>
    </div>
  `,
  props: {
    blocks: { type: Array, default: () => [] },
    activeId: { type: Number, default: -1 },
    reviewLabel: { type: String, default: "" },
    editLabel: { type: String, default: "" },
    showEdits: { type: Boolean, default: false },
    highlightWord: { type: Boolean, default: false },
    follow: { type: Boolean, default: false },
    revision: { type: Number, default: 0 },
    speakers: { type: Array, default: () => [] },
    unused: { type: Array, default: () => [] },
    subtitleMode: { type: Boolean, default: false },
    characterLimit: { type: Number, default: 42 },
    maxSubtitleLines: { type: Number, default: 2 },
  },
  // One watch block. Two would silently discard the first: duplicate keys in
  // an object literal keep only the last.
  watch: {
    activeId(id) {
      if (!this.follow) return;
      this.scrollToBlock(id);
    },
    revision() {
      // Bumped by the server only when the blocks actually change. Watching
      // the blocks themselves fires on every update, because an update
      // resends all props and the array arrives as a new reference -- several
      // times a second while the audio plays.
      //
      // A block that was typed into has its text changed directly in the DOM,
      // not through Vue -- the server does not re-render the block the caret
      // is in while it is still being typed into, see set_text. So Vue's own
      // record of that block's text is still whatever it was at the last
      // render, and stays that way through the edit. If a later render (undo,
      // most of all) sends back exactly that same text, Vue's diff finds
      // nothing to do and leaves the browser's own DOM as it is -- which
      // still holds the typed word, unrelated to what was just sent down. The
      // word looked as if undo had not reached it, because for that block it
      // truly had not: nothing told Vue that the DOM no longer matched what
      // it last rendered. Changing the block's key throws the element away
      // instead of patching it, so the next render always builds it fresh
      // from the props actually sent.
      //
      // Thrown away is the operative word for a dirty block's own element --
      // typed into, then undo pressed while it was still dirty, is the usual
      // way there. But even a block that keeps its own key can lose the
      // specific node the caret was anchored to: undoing a merge, for one,
      // patches the survivor's runs back down to fewer spans than it had a
      // moment ago, and if the caret was in one that no longer exists past
      // the patch, the browser does not so much as leave it at the block's
      // edge. A caret whose node was removed collapses to the very start of
      // the contenteditable, or to an unrelated block adjacent to where the
      // node used to be -- either way it reads as the cursor jumping
      // somewhere it was never asked to go. Read before this render can
      // touch anything, restored once Vue has finished patching, for
      // whichever block held it -- a block whose own content did not
      // change under the caret just gets put back where it already was, so
      // there is no reason to restrict this to only the blocks known to be
      // dirty. Superseded a moment later wherever a render is paired with
      // its own explicit focus() call (add_after, delete, merge): that
      // always reaches the client as a second, later message, and wins.
      const restoring = this.caret();

      this.dirty.forEach((id) => {
        this.stamps[id] = (this.stamps[id] || 0) + 1;
      });
      this.dirty.clear();

      // A fresh render's own block.line_counts is the server's authoritative
      // account, worked out from the caption text it actually holds now --
      // whatever was guessed at locally in the meantime is stale.
      this.liveCounts = {};

      // Rebuilt from scratch below, so whatever span it named is about to
      // stop existing -- effectiveSpan would just fail its identity check
      // either way, this only saves it the trouble. editingWord the same:
      // left stale it still compares unequal to whatever wordAt finds next
      // (a detached node matches nothing), so it costs nothing beyond an
      // unnecessary flush() of an edit that was likely already sent -- but
      // nothing needs that flush to keep pointing at an element that no
      // longer exists either.
      this.newWordBoundary = null;
      this.editingWord = null;
      this.syntheticSpace = null;

      this.$nextTick(() => {
        this.indexWords();

        // A fresh render is the server's own account of which words have been
        // changed, worked out by diffing the text properly rather than word by
        // word, so the marks put on here in the meantime are dropped. Left in
        // place they would decorate whatever word now sits where they were put:
        // these spans are keyed by position, so Vue reuses them.
        this.$refs.body
          ?.querySelectorAll("[data-changed]")
          .forEach((el) => el.removeAttribute("data-changed"));

        if (restoring) {
          const block = this.$refs.body?.querySelector(
            `.transcript-text[data-id="${restoring.id}"]`
          );
          if (block) {
            // The caret was always at or after whatever just changed --
            // typing leaves it there, and so does clicking undo or redo
            // right after. Carrying the block's own change in length along
            // with it is what keeps the caret at the same word rather than
            // the naive offset overshooting into the next one once undo
            // shrinks the text out from under it (or redo falling short
            // once it grows again): restoring offset 12 unchanged into a
            // block one character shorter lands one character into
            // whatever now sits where the old offset 12 used to be, not
            // the same place in the word the reader was actually at.
            const newLength = this.plainText(block.textContent).length;
            const offset = Math.max(
              0,
              restoring.offset + (newLength - restoring.length)
            );
            this.placeCaretAt(block, offset);
          }
        }
      });
    },
    highlightWord(on) {
      if (on) this.$nextTick(() => this.indexWords());
      else this.clearCurrentWord();
    },
  },
  data() {
    return {
      pending: null,
      // The edit waiting to be sent, kept separately from the caret because
      // by the time it is sent -- on blur, in particular -- the caret may
      // already have moved or gone.
      edit: null,
      // The word span currently being typed into. A keystroke landing in a
      // different word flushes whatever was pending first, so two words
      // edited one after another become two undo steps rather than one --
      // see onInput.
      editingWord: null,
      // Where, within editingWord's own span, the word itself ends and a
      // new one starts forming -- see pastWordBoundary.
      newWordBoundary: null,
      // A space inserted by hand, not typed, to hold a new word apart from
      // the one right after it until the reader types a separator of
      // their own -- see effectiveSpan's headMatch branch.
      syntheticSpace: null,
      // Blocks typed into since the last real render, and how many times
      // each has had to be rebuilt because of it. See the revision watcher.
      dirty: new Set(),
      stamps: {},
      timed: [],
      menu: { open: false, x: 0, y: 0, id: null, speaker: null },
      // A block's own guess at its character-count guideline, from the text
      // as typed rather than what the server last rendered -- keyed by
      // block id, and only ever set for subtitles. See onInput and the
      // revision watcher.
      liveCounts: {},
    };
  },
  mounted() {
    // Following the audio has to happen here rather than on the server: a
    // word lasts a few hundred milliseconds, and a round trip per word would
    // be both late and wasteful.
    this.onTime = () => this.markCurrentWord();
    this.onOutside = (event) => {
      if (!event.target.closest(".speaker-menu")) this.closeMenu();
    };
    this.onEscape = (event) => {
      if (event.key === "Escape") this.closeMenu();
    };
    document.addEventListener("pointerdown", this.onOutside, true);
    document.addEventListener("keydown", this.onEscape, true);
    this.attachVideo();
    this.$nextTick(() => this.indexWords());
  },
  beforeUnmount() {
    this.video?.removeEventListener("timeupdate", this.onTime);
    this.video?.removeEventListener("seeking", this.onTime);
    document.removeEventListener("pointerdown", this.onOutside, true);
    document.removeEventListener("keydown", this.onEscape, true);
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

    // A block's real text, with the zero-width space insertLineBreak plants
    // at the end of a trailing empty line stripped back out -- that
    // character exists only to give the browser something to hang a caret
    // on there (see insertLineBreak), never part of the caption itself.
    plainText(text) {
      return (text || "").replace(/\u200B/g, "");
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
        offset: this.plainText(measure.toString()).length,
        length: this.plainText(block.textContent).length,
        collapsed: range.collapsed,
        block,
      };
    },

    // The inverse of caret()'s own offset -- used to put the caret back
    // after a block has been rebuilt from scratch (see the revision
    // watcher), where nothing else remembers where it was. A freshly
    // rendered block is the server's own text with none of plainText's
    // placeholder in it, so this walks the DOM's own text nodes directly
    // rather than stripping anything. An offset past the end (the caption
    // shrank out from under it) collapses to the end instead of failing.
    placeCaretAt(block, offset) {
      const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
      let remaining = offset;
      let node = walker.nextNode();
      let target = null;
      let targetOffset = 0;

      while (node) {
        const length = node.textContent.length;
        if (remaining <= length) {
          target = node;
          targetOffset = remaining;
          break;
        }
        remaining -= length;
        node = walker.nextNode();
      }

      const range = document.createRange();
      if (target) {
        // setStart alone leaves the range collapsed already -- a fresh
        // Range starts out collapsed at the document's own start, and
        // setStart pulls the end boundary along with it rather than
        // leaving a start-after-end range behind.
        range.setStart(target, targetOffset);
      } else {
        range.selectNodeContents(block);
        range.collapse(false);
      }

      this.$refs.body?.focus();
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    },

    // The word the caret is inside, which is the one being typed into.
    wordAt(range) {
      let el = range?.startContainer;
      if (el && !(el instanceof Element)) el = el.parentElement;
      const span = el?.closest?.("span");
      // Only the word spans, not the gutter's speaker or timestamp spans.
      return span && this.blockOf(span) ? span : null;
    },

    // How far into a span the caret sits, in characters -- caret()'s own
    // offset, but scoped to one span instead of the whole block.
    offsetWithinSpan(span, range) {
      const measure = range.cloneRange();
      measure.selectNodeContents(span);
      measure.setEnd(range.startContainer, range.startOffset);

      return measure.toString().length;
    },

    // A space typed right after a word starts a new word; it is not an edit
    // to the word before it. The browser disagrees: a caret sitting at the
    // very end of a word's span -- wherever that word is, mid-caption or the
    // last one, verified against both -- keeps extending that span's own text
    // node instead of starting a new one, because there is nowhere else there
    // for the character to go.
    //
    // Caught by asking two things together: does the span the caret is in now
    // end in whitespace, and does the caret sit at the very end of it. Either
    // one alone is not enough. A span ending in whitespace but with the caret
    // still inside its real content is a genuine edit -- most of all a span
    // holding several whitespace-joined words at once, which is what My edits
    // being off renders instead of one span per word, and where the caret is
    // essentially never at the tail while the reader is editing one of the
    // words in the middle. And a caret at the tail of a span that does not
    // end in whitespace is just the ordinary case of typing at the end of a
    // word, real content and no quirk to catch.
    spaceAtTail(span, range) {
      if (!span || !range || !/\s$/.test(span.textContent)) return false;
      if (!span.contains(range.startContainer)) return false;

      return this.offsetWithinSpan(span, range) === span.textContent.length;
    },

    // spaceAtTail alone only catches the instant the space is typed, while
    // the span still ends in whitespace. The very next real character
    // removes that trailing whitespace -- the browser keeps extending the
    // same span for as long as the caret stays at its own tail, same as it
    // did for the space itself -- so on that keystroke spaceAtTail no
    // longer matches, and without remembering where the boundary was, the
    // word before the space reads as edited by a keystroke that was
    // actually starting the next one.
    //
    // Remembered as a span-and-offset pair rather than re-derived, then, and
    // kept only for as long as the caret stays in that same span. wordAt
    // resetting to a genuinely different span, or a real render rebuilding
    // the spans outright, both leave the remembered span no longer
    // matching, which is what retires it without needing to clear it
    // explicitly everywhere.
    //
    // A Backspace that reaches back before the remembered offset -- undoing
    // the space itself, or eating into the new word and then the original
    // one -- means the reader is editing that earlier content now, not
    // extending what came after it, and the boundary stops describing
    // anything real. Forgotten there rather than left standing, or typing
    // forward again later -- appending to the original word for a real
    // reason, nothing to do with the space any more -- would still read as
    // past a boundary that should not apply to it, which is exactly a
    // regression this once caused: a genuine edit stopped marking at all.
    //
    // The other side of that same regression: once real content exists past
    // the boundary, it is a word of its own and has to be markable as one --
    // but marking the span it still physically shares with the original
    // word would mark that word too, right back to the first regression.
    // splitNewWord gives it a span of its own the moment that happens, the
    // one time this needs to reach into the DOM directly rather than only
    // read it -- a plain move of existing nodes into a new wrapper, nothing
    // like the execCommand corruption insertLineBreak hit, and dirty
    // already guarantees whatever shape it leaves behind is thrown away and
    // rebuilt whenever a real render finally reaches this block anyway.
    effectiveSpan(span, range) {
      if (this.newWordBoundary && this.newWordBoundary.span === span) {
        const boundary = this.newWordBoundary.offset;
        const offset = this.offsetWithinSpan(span, range);

        if (offset > boundary) {
          // Still nothing but whitespace past the space -- a second space,
          // typed right after the first -- extends the boundary rather
          // than splitting off a span with nothing in it worth marking.
          if (/^\s*$/.test(span.textContent.slice(boundary, offset))) {
            this.newWordBoundary = { span, offset };
            return null;
          }

          const wrapper = this.splitNewWord(span, boundary);
          this.newWordBoundary = null;
          // Set here rather than left to onInput's own comparison below:
          // the space keystroke that started this already cleared
          // editingWord (spaceAtTail's own null), so onInput would read
          // this new wrapper as a different word and flush whatever was
          // still pending -- the space's own transient snapshot, not a
          // finished edit in its own right, which split the reader's one
          // continuous "type a word after a space" action into two undo
          // steps, the second one landing on that half-finished text.
          // Setting it here first makes onInput's span !== editingWord
          // already false, so nothing flushes and the pending edit simply
          // keeps being overwritten with fuller text until the real,
          // debounced flush finally sends the finished word.
          this.editingWord = wrapper;
          return wrapper;
        }
        if (offset === boundary) return null;

        this.newWordBoundary = null;
        return span;
      }

      if (this.spaceAtTail(span, range)) {
        // A real separator now exists where the synthetic one was standing
        // in -- see the headMatch branch below -- so it is retired here,
        // the same moment spaceAtTail itself starts tracking this space.
        if (this.syntheticSpace && this.syntheticSpace.previousSibling === span) {
          this.syntheticSpace.remove();
          this.syntheticSpace = null;
        }
        this.newWordBoundary = { span, offset: this.offsetWithinSpan(span, range) };
        return null;
      }

      // The mirror image of spaceAtTail: a separator span -- pure
      // whitespace up to here -- has just gained its first real character,
      // typed at its own tail. A caret sitting between a separator and the
      // word right after it resolves into the separator's own tail, not
      // the word's head, so this is what a new word inserted right before
      // an existing one looks like as it starts. Left alone the new word
      // keeps growing inside the separator's own span, flush against the
      // word after it with nothing keeping them apart -- harmless while
      // the reader keeps typing, since nothing has been sent yet, but the
      // debounced flush 400ms out does not know that: a natural pause
      // mid-word sends the two run together as whatever is on screen at
      // that moment, and undo then makes that permanent.
      //
      // splitNewWord isolates the new word into a span of its own, same as
      // the boundary-crossing branch above, and a synthetic space follows
      // it immediately so every flush from here on stays properly spaced
      // even before the reader has typed a separator of their own.
      const headMatch = /^(\s+)(\S+)$/.exec(span.textContent);
      if (headMatch && this.offsetWithinSpan(span, range) === span.textContent.length) {
        const wrapper = this.splitNewWord(span, headMatch[1].length);
        if (wrapper) {
          const next = span.nextSibling;
          if (next && !/^\s/.test(next.textContent || "")) {
            this.syntheticSpace = document.createTextNode(" ");
            span.appendChild(this.syntheticSpace);
          }
          return wrapper;
        }
      }

      return span;
    },

    // The synthetic space above stands in for a separator the reader has not
    // typed yet, and only earns its place while there is a new word in front
    // of it to hold apart from the next one. Backspacing that word away again
    // leaves it separating nothing -- and, left in the DOM, it is read back
    // out as part of the caption and flushed as text the reader never typed
    // (a stray double space, which in subtitleMode also counts against the
    // character guideline). Retired here rather than in spaceAtTail's own
    // branch, which only fires when a real space is typed and so never sees
    // the word being deleted instead.
    //
    // "Separating nothing" is everything before it inside its own parent
    // being whitespace: the word had a span of its own (splitNewWord), and
    // the browser takes that span away with the last character of it.
    retireSyntheticSpace() {
      const space = this.syntheticSpace;
      if (!space) return;

      if (!space.parentNode) {
        // Already gone -- a Backspace reaching it, or a render rebuilding
        // the block around it.
        this.syntheticSpace = null;
        return;
      }

      let before = "";
      for (
        let node = space.parentNode.firstChild;
        node && node !== space;
        node = node.nextSibling
      ) {
        before += node.textContent || "";
      }

      if (!/\S/.test(before)) {
        space.remove();
        this.syntheticSpace = null;
      }
    },

    // Moves everything from characterOffset onward, within span, into a new
    // sibling span of its own -- left holding the caret, since that is
    // always at its end (see effectiveSpan, the only caller: this only ever
    // runs the instant typing forward crosses the boundary, and only once
    // effectiveSpan has already checked there is something other than more
    // whitespace to move). Marking it is onInput's own job, same as any
    // other span -- effectiveSpan hands this one back just like it would
    // any other. Text.splitText divides the one text node characterOffset
    // falls in; any further nodes after it (rare here, but a span can hold
    // more than one) move across whole.
    splitNewWord(span, characterOffset) {
      const walker = document.createTreeWalker(span, NodeFilter.SHOW_TEXT);
      let remaining = characterOffset;
      let node = walker.nextNode();

      while (node && remaining > node.textContent.length) {
        remaining -= node.textContent.length;
        node = walker.nextNode();
      }
      if (!node) return null;

      const tail = remaining < node.textContent.length ? node.splitText(remaining) : node.nextSibling;
      if (!tail) return null;

      const wrapper = document.createElement("span");
      span.insertBefore(wrapper, tail);

      let moving = tail;
      while (moving) {
        const next = moving.nextSibling;
        wrapper.appendChild(moving);
        moving = next;
      }

      const range = document.createRange();
      range.selectNodeContents(wrapper);
      range.collapse(false);

      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);

      return wrapper;
    },

    // Normalised the same way as match_key on the server: neither case nor the
    // punctuation around a word decides whether it is still the word that was
    // transcribed. Both sides have to agree, or a mark would come off as the
    // reader types and be put straight back by the next render.
    //
    // The character class is Python's \w -- letters, numbers, underscore -- so
    // that the two strip the same things. toLowerCase stands in for casefold,
    // which JavaScript has no equivalent of; they differ only on characters
    // that change length when lowercased, such as ß.
    // The word the caret is in has just been typed into, so it is a word the
    // reader has changed. Nothing is compared: an edit is something that
    // happened, not something to be worked out from how the text now differs
    // from what the model transcribed. Working it out that way marked words
    // nobody had touched, wherever a word's timing put it outside the segment
    // it belongs to.
    //
    // Done here rather than waiting for the server, which records the same
    // thing but cannot re-render the block the caret is sitting in without
    // moving it. A render clears these and takes the server's account instead.
    //
    // An attribute rather than a class: Vue owns the class and rewrites it
    // whenever it patches the span.
    //
    // Whitespace has no word in it to have changed, so it never earns the
    // marking even when wordAt does hand back a separator's own span --
    // caret() and effectiveSpan() both work at the DOM's own element
    // boundaries, not word boundaries, so a caret landing in the gap
    // between two words is exactly as valid a position as one inside
    // either of them. Highlighting it would draw a floating green box over
    // a plain space, nothing there for the reader to actually look at.
    markChanged(span) {
      if (span && !/^\s*$/.test(span.textContent)) span.setAttribute("data-changed", "");
    },

    // Text edits are reported on a short delay: the server recomputes the
    // review highlighting from them, and doing that per keystroke would fight
    // the caret.
    onInput() {
      // Before the caret and the text are read below, so a space that has
      // stopped separating anything is gone by the time either is measured
      // and never reaches the flush.
      this.retireSyntheticSpace();

      const at = this.caret();
      if (!at) return;

      const selection = window.getSelection();
      const range = selection?.rangeCount ? selection.getRangeAt(0) : null;
      let span = range ? this.wordAt(range) : null;

      span = this.effectiveSpan(span, range);

      this.markChanged(span);

      // A different word than the one already being typed into: whatever was
      // pending belongs to a finished edit, so it is sent now, as its own
      // undo step, before this one starts accumulating. Comparing elements
      // rather than text or position is what makes this safe -- the server
      // does not re-render the block the caret is in while it is still being
      // typed into, so the same word keeps the same span for as long as the
      // reader stays on it, and a real render (see the revision watcher)
      // resets this along with everything else.
      if (span !== this.editingWord) {
        this.flush();
        this.editingWord = span;
      }

      // This block now disagrees with what Vue thinks it rendered. See the
      // revision watcher for why that matters.
      this.dirty.add(at.id);

      const text = this.plainText(at.block.textContent);

      // The character-count guideline in the margin, redrawn from what was
      // just typed rather than waiting for the debounced report below and
      // the server's own answer to it -- that round trip is exactly what
      // set_text avoids taking for the block's own text, for the same
      // reason: it would fight the caret. Vue-reactive rather than a direct
      // DOM write, unlike markChanged above, because these spans live in
      // the gutter, outside the contenteditable -- patching them here
      // cannot disturb the caret the way patching the text ever could.
      if (this.subtitleMode) {
        this.liveCounts = { ...this.liveCounts, [at.id]: this.computeLineCounts(text) };
      }

      clearTimeout(this.pending);
      this.edit = { id: at.id, text };
      this.pending = setTimeout(() => this.flush(), 400);
    },

    // Mirrors caption_line_counts on the Python side exactly -- same
    // guideline, same tooltip wording -- so what is shown while typing
    // matches what the next real render sends down.
    computeLineCounts(text) {
      const lines = (text || "").split("\n");
      const tooManyLines = lines.length > this.maxSubtitleLines;

      return lines.map((line) => {
        const length = line.length;
        const lineTooLong = length > this.characterLimit;

        let tooltip =
          `Guideline: max ${this.characterLimit} characters per line, ` +
          `${this.maxSubtitleLines} lines.`;
        if (lineTooLong) tooltip += ` This line is ${length} characters.`;
        if (tooManyLines) tooltip += ` ${lines.length} lines in this caption.`;

        return { length, exceeded: lineTooLong || tooManyLines, tooltip };
      });
    },

    // Report a waiting edit now, e.g. before the caret is going to leave the
    // block it is in. Kept rather than read back off the caret when sent: by
    // the time this runs -- on blur, in particular -- the caret may already
    // be gone.
    flush() {
      clearTimeout(this.pending);
      this.editingWord = null;

      const edit = this.edit;
      this.edit = null;

      if (edit) this.$emit("blocktext", edit);
    },

    // The key a block is drawn under -- see the revision watcher.
    blockKey(block) {
      return `${block.id}:${this.stamps[block.id] || 0}`;
    },

    // A literal line break at the caret, replacing any selection the way
    // typing a character would. document.execCommand("insertText", ...)
    // looked like the natural fit but does not behave as a plain insertion
    // for "\n" -- it went as far as deleting surrounding content in testing
    // -- so this builds the same result by hand: a real text node, spliced
    // in with the Range API. white-space: pre-wrap is what turns that
    // character into a visible line break; nothing here draws one.
    //
    // A "\n" with nothing after it does not get a line box at all -- the
    // browser only reserves room for a forced break when there is a real
    // character following it, so a break at the very end of a caption drew
    // no second line and the caret had nowhere on it to go. A zero-width
    // space after the "\n" is exactly that character, invisible but real,
    // and only added when the break lands at the true end -- one already
    // followed by real text needs nothing extra, that text already earns
    // its line box. plainText strips it back out wherever a block's text
    // is read for anything other than drawing it, so it never reaches the
    // caption's saved text, a character count, or an offset.
    //
    // Inserting through the DOM this way fires no input event, so onInput's
    // own bookkeeping (marking the block dirty, scheduling the debounced
    // send) is called directly afterward rather than left to fire on its
    // own the way a real keystroke's insertion does.
    insertLineBreak() {
      const selection = window.getSelection();
      if (!selection.rangeCount) return;

      const range = selection.getRangeAt(0);
      const block = this.blockOf(range.startContainer);

      let atEnd = false;
      if (block) {
        const rest = range.cloneRange();
        rest.selectNodeContents(block);
        rest.setStart(range.endContainer, range.endOffset);
        atEnd = this.plainText(rest.toString()).length === 0;
      }

      range.deleteContents();

      const node = document.createTextNode(atEnd ? "\n\u200B" : "\n");
      range.insertNode(node);
      range.setStart(node, 1);
      range.collapse(true);

      selection.removeAllRanges();
      selection.addRange(range);

      this.onInput();
    },

    // The split icon in a caption's own action row -- the mouse equivalent
    // of Ctrl/Cmd+Enter, for a reader who has not necessarily got the caret
    // in this particular caption's text right now (clicking the icon does
    // not itself move it there). Splits at the caret when it already is;
    // otherwise the middle of the caption's own text is as reasonable a
    // point as any, and split_caption falls back to exactly that when no
    // cursor position reaches it at all -- this just picks it here instead,
    // since a click always carries a block id and this event needs an
    // offset it can act on.
    splitAt(id) {
      const at = this.caret();
      let offset;

      if (at && at.id === id) {
        offset = at.offset;
      } else {
        const text = this.plainText(
          this.$refs.body?.querySelector(`.transcript-text[data-id="${id}"]`)
            ?.textContent
        );
        offset = text ? Math.floor(text.length / 2) : 0;
      }

      this.flush();
      this.$emit("splitblock", { id, offset });
    },

    // The merge icon in a caption's own action row -- the mouse equivalent
    // of Delete at the end of its text. Always the caption after this one:
    // "after" is already the direction Add works in, and a reader wanting
    // the other direction can open that caption's own menu instead, rather
    // than this row carrying two arrows for what Backspace and Delete
    // already do without needing a direction spelled out.
    mergeWithNext(id) {
      this.flush();
      this.$emit("mergeblock", { id, direction: "next" });
    },

    // A start or end time typed directly into its own input -- no dialog,
    // no slider, in either mode. Marked dirty the same way a text edit
    // does: the reply might leave the value exactly as it was (a mistyped
    // time is refused, not guessed at), and an unchanged prop is a patch
    // Vue's own diff skips, which would leave whatever the reader typed
    // showing in an input that never actually saved it.
    retimeBlock(id, edge, event) {
      this.dirty.add(id);
      this.$emit("retime", { id, edge, value: event.target.value });
    },

    // Typing in a time input must not reach the document's own keydown
    // handling below -- Enter there splits a caption, not this. Enter and
    // Escape here just commit or abandon the edit, the same as leaving the
    // field any other way.
    onTimeInputKeydown(event) {
      event.stopPropagation();

      if (event.key === "Enter" || event.key === "Escape") {
        event.target.blur();
      }
    },

    onKeydown(event) {
      // Undo and redo are the server's alone. It holds the real history --
      // every block, speaker and timing, not just the text of the one being
      // typed into -- and this key reaches it too, through the page's own
      // keyboard handler. Left alone, the browser also treats Ctrl/Cmd+Z and
      // +Y as contenteditable's native undo/redo: it replays a DOM edit of
      // its own, invisible to the server, and that replay fires an input
      // event that onInput reports as a fresh edit -- on whatever word the
      // caret ends up in, which is how a redo left an unrelated word marked.
      // Only preventDefault is needed to stop it; the key itself still
      // reaches the document handler that drives the server's undo.
      const key = event.key.toLowerCase();

      if ((event.ctrlKey || event.metaKey) && (key === "z" || key === "y")) {
        event.preventDefault();
        this.flush();
        return;
      }

      const at = this.caret();
      if (!at) return;

      // A bare Enter inserts a line break, in a transcription the same as
      // a subtitle -- starting a whole new block (a new timed cue, or a
      // fresh speaker turn) now needs Ctrl/Cmd held down instead.
      if (event.key === "Enter" && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        this.insertLineBreak();
        return;
      }

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

    assign(name) {
      const id = this.menu.id;
      this.closeMenu();
      if (id !== null) this.$emit("assignspeaker", { id, speaker: name });
    },

    openMenu(label) {
      const box = label.getBoundingClientRect();
      const root = this.$el.getBoundingClientRect();

      // Estimates, only used to keep the menu on screen. Width follows the
      // min-width in the stylesheet; height is the "Add new" row plus one per
      // speaker.
      const width = 176;
      const height = 44 + this.speakers.length * 38;
      const gap = 8;
      const edge = 8;

      // Beside the label, on its right. If the right hand side has no room,
      // it goes to the left instead rather than off the screen.
      const fitsRight = box.right + gap + width <= window.innerWidth - edge;
      const x = fitsRight ? box.right + gap : box.left - gap - width;

      // Top aligned with the label, lifted only by as much as it would
      // otherwise hang below the bottom of the window.
      const overhang = Math.max(0, box.top + height - (window.innerHeight - edge));

      // Offsets within this component, so the menu sits beside the label
      // whatever the page has done to positioning further up the tree, and
      // stays with it while the transcription scrolls.
      this.menu = {
        open: true,
        x: Math.max(edge, x) - root.left,
        y: Math.max(edge, box.top - overhang) - root.top,
        id: Number(label.dataset.id),
        speaker: label.textContent.trim(),
      };
    },

    closeMenu() {
      this.menu = { open: false, x: 0, y: 0, id: null, speaker: null };
    },

    onClick(event) {
      const speaker = event.target.closest(".transcript-speaker");
      if (speaker) {
        this.openMenu(speaker);
        return;
      }

      this.closeMenu();

      const block = this.blockOf(event.target);
      if (!block) return;

      // Where in the block the caret landed, so the recording can be moved to
      // that word rather than to the start of the block. The browser places
      // the caret on mousedown, so it is already correct by the time click
      // runs.
      const id = Number(block.dataset.id);
      const at = this.caret();

      this.$emit("blockclick", {
        id,
        offset: at && at.id === id ? at.offset : 0,
      });
    },

    // Put the caret in a block, at a character offset that defaults to its
    // very start. Used after a new block is started, so it can be typed
    // into without reaching for the mouse, and after a merge, so the caret
    // lands at the seam between the two texts rather than wherever a
    // removed block leaves the browser's own selection -- see merge() on
    // the Python side. placeCaretAt is what actually walks to the offset;
    // this only waits for the block to exist to hand it to.
    focusBlock(id, offset = 0) {
      this.$nextTick(() => {
        const block = this.$refs.body?.querySelector(
          `.transcript-text[data-id="${id}"]`
        );
        if (!block) return;

        this.placeCaretAt(block, offset);
      });
    },

    // Bring a block into view without moving the caret -- what search and
    // autoscroll use once they have picked a caption, and what the activeId
    // watcher above uses too. Wrapped in nextTick since this can follow a
    // render, e.g. when search has just changed which block is highlighted.
    scrollToBlock(id) {
      this.$nextTick(() => {
        const cell = this.$refs.body?.querySelector(
          `.transcript-cell[data-id="${id}"]`
        );
        if (cell) cell.scrollIntoView({ block: "center", behavior: "smooth" });
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

      // The timing belonged to the word that was transcribed here. Once that
      // word has been replaced it describes nothing on screen, so nothing is
      // marked rather than the reader's own word being lit up as if spoken.
      if (found && found.el.hasAttribute("data-changed")) found = null;

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

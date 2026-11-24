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

// scrollWithin() of the transcript component without a browser: the
// component is read from its source, its template and all, and the method is
// called on elements that are just rectangles. Run by
// tests/test_transcript_scroll.py (skipped where there is no node), or
// directly: node --test tests/js/

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "..", "utils", "transcript_editor.js"),
  "utf8"
);

const rect = (top, height) => ({ top, height, bottom: top + height });

// A page: a window with `pageRoom` px to scroll, a scroller whose box is
// `view` ([top, height]) and holds `content` px, and, if `dock` is given, the
// docked Timeline.
function page({ view = [100, 500], content = 2000, scrollTop = 0, pageRoom = 170, dock = null } = {}) {
  const calls = { scrollBy: [], scrollIntoView: 0 };

  const scroller = {
    parentElement: null,
    scrollTop,
    scrollHeight: content,
    clientHeight: view[1],
    getBoundingClientRect: () => rect(view[0], view[1]),
    scrollTo({ top }) {
      scroller.scrollTop = top;
    },
  };

  const body = { parentElement: null };
  scroller.parentElement = body;

  const win = {
    innerHeight: 800,
    scrollY: 0,
    scrollBy({ top }) {
      calls.scrollBy.push(top);
      win.scrollY += top;
    },
  };

  const dockElement = dock
    ? {
        getClientRects: () => (dock.hidden ? [] : [{}]),
        getBoundingClientRect: () => (dock.hidden ? rect(0, 0) : rect(dock.top, 150)),
      }
    : null;

  const document = {
    body,
    documentElement: { scrollHeight: 800 + pageRoom },
    querySelector: (selector) => (selector === ".speech-timeline-docked" ? dockElement : null),
  };

  const context = vm.createContext({
    document,
    window: win,
    getComputedStyle: (el) => ({ overflowY: el === scroller ? "auto" : "visible" }),
    module: {},
  });

  vm.runInContext(source.replace("export default", "module.exports ="), context);
  const { scrollWithin, scrollerOf } = context.module.exports.methods;
  const self = { scrollerOf, pageGiven: 0 };

  const element = (top, height) => ({
    parentElement: scroller,
    getBoundingClientRect: () => rect(top, height),
    scrollIntoView: () => (calls.scrollIntoView += 1),
  });

  return {
    scroller,
    win,
    calls,
    scroll: (el, options) => scrollWithin.call(self, el, options),
    element,
    self,
    orphan: () => ({
      parentElement: null,
      getBoundingClientRect: () => rect(0, 10),
      scrollIntoView: () => (calls.scrollIntoView += 1),
    }),
  };
}

test("centring moves the scroller and not the page", () => {
  const p = page({ view: [100, 500], scrollTop: 0 });

  // Its middle is at 650; the middle of the scroller is at 350.
  p.scroll(p.element(600, 100), { block: "center" });

  assert.equal(p.scroller.scrollTop, 300);
  assert.deepEqual(p.calls.scrollBy, []);
});

test("a caption in view is left where it is by nearest", () => {
  const p = page();

  p.scroll(p.element(200, 80), { block: "nearest" });

  assert.equal(p.scroller.scrollTop, 0);
  assert.deepEqual(p.calls.scrollBy, []);
});

test("the scroller stops at its ends", () => {
  const p = page({ view: [100, 500], content: 600, scrollTop: 0 });

  p.scroll(p.element(580, 100), { block: "center" });

  assert.equal(p.scroller.scrollTop, 100);
});

test("a Timeline that is switched off is no dock, however empty its rectangle", () => {
  const p = page({ dock: { hidden: true, top: 0 } });

  p.scroll(p.element(300, 80), { block: "center" });
  p.scroll(p.element(500, 80), { block: "nearest" });

  assert.deepEqual(p.calls.scrollBy, [], "the page did not move for a dock that is not there");
});

test("with the Timeline docked, a caption that cannot be scrolled clear of it moves the page by what it takes", () => {
  const p = page({ view: [100, 700], content: 800, scrollTop: 100, dock: { top: 650 } });

  // At the end of the scroller already; the caption's foot is 40 px under the dock.
  p.scroll(p.element(610, 80), { block: "center" });

  assert.deepEqual(p.calls.scrollBy, [40]);
  assert.equal(p.self.pageGiven, 40);
});

test("the page is given back when a caption no longer needs it, and no more than was given", () => {
  const p = page({ view: [100, 700], content: 800, scrollTop: 100, dock: { top: 650 } });
  p.win.scrollY = 90; // the reader scrolled 50 px of this
  p.self.pageGiven = 40;

  p.scroll(p.element(200, 80), { block: "nearest" });

  assert.deepEqual(p.calls.scrollBy, [-40]);
  assert.equal(p.self.pageGiven, 0);
  assert.equal(p.win.scrollY, 50);
});

test("a paragraph taller than the scroller that spans both edges stays where it is", () => {
  const p = page({ view: [100, 500], scrollTop: 300 });

  p.scroll(p.element(-50, 900), { block: "nearest" });

  assert.equal(p.scroller.scrollTop, 300);
  assert.deepEqual(p.calls.scrollBy, []);
});

test("nearest aligns an edge the way scrollIntoView does", () => {
  // Head above, foot in view, shorter than the scroller: the head.
  let p = page({ view: [100, 500], scrollTop: 300 });
  p.scroll(p.element(80, 200), { block: "nearest" });
  assert.equal(p.scroller.scrollTop, 280);

  // Head above, foot in view, taller than the scroller: the foot.
  p = page({ view: [100, 500], scrollTop: 300 });
  p.scroll(p.element(0, 580), { block: "nearest" });
  assert.equal(p.scroller.scrollTop, 280);

  // Head in view, foot below, shorter than the scroller: the foot.
  p = page({ view: [100, 500], scrollTop: 0 });
  p.scroll(p.element(450, 200), { block: "nearest" });
  assert.equal(p.scroller.scrollTop, 50);

  // Head in view, foot below, taller than the scroller: the head.
  p = page({ view: [100, 500], scrollTop: 0 });
  p.scroll(p.element(150, 700), { block: "nearest" });
  assert.equal(p.scroller.scrollTop, 50);
});

test("something taller than what is left above the Timeline does not move the page", () => {
  const p = page({ view: [100, 700], content: 2000, scrollTop: 0, dock: { top: 650 } });

  p.scroll(p.element(120, 900), { block: "nearest" });

  assert.deepEqual(p.calls.scrollBy, []);
});

test("without a scroller scrollIntoView is the fallback", () => {
  const p = page();

  p.scroll(p.orphan(), { block: "center" });

  assert.equal(p.calls.scrollIntoView, 1);
});

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

// The editor page's own keydown listener, run without a browser: read out of
// pages/srt.py, given a window that keeps it, and called with made-up key
// events. Run by tests/test_find_panel.py (skipped where there is no node),
// or directly: node --test tests/js/

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const page = fs.readFileSync(path.join(__dirname, "..", "..", "pages", "srt.py"), "utf8");
const start = page.indexOf("<script>", page.indexOf("window.addEventListener('keydown'") - 200);
const end = page.indexOf("</script>", start);
const script = page.slice(start + "<script>".length, end);

// What the listener was registered with.
function listener() {
  const registered = [];
  const window = {
    addEventListener: (type, fn, capture) => registered.push({ type, fn, capture }),
  };
  const context = vm.createContext({ window, document: { activeElement: null } });
  vm.runInContext(script, context);

  return registered.find((entry) => entry.type === "keydown");
}

// A key event whose target is in the card, or in the transcript.
function key(options, inCard) {
  const event = {
    key: "z",
    ctrlKey: true,
    metaKey: false,
    shiftKey: false,
    altKey: false,
    defaultPrevented: false,
    preventDefault() {
      this.defaultPrevented = true;
    },
    ...options,
  };

  event.target = {
    tagName: "INPUT",
    closest: (selector) => (inCard && selector === ".validation-panel" ? {} : null),
  };

  return event;
}

test("the listener runs first, in the capture phase", () => {
  assert.equal(listener().capture, true);
});

test("undo and redo are cancelled for the page's own sake", () => {
  const { fn } = listener();

  for (const options of [
    { key: "z" },
    { key: "y" },
    { key: "z", shiftKey: true },
    { key: "Z", ctrlKey: false, metaKey: true },
  ]) {
    const event = key(options, false);
    fn(event);
    assert.equal(event.defaultPrevented, true, JSON.stringify(options));
  }
});

test("undo and redo are left alone in a field in a card: Find, Replace, a comment", () => {
  const { fn } = listener();

  for (const options of [
    { key: "z" },
    { key: "y" },
    { key: "z", shiftKey: true },
    { key: "z", ctrlKey: false, metaKey: true },
  ]) {
    const event = key(options, true);
    fn(event);
    assert.equal(event.defaultPrevented, false, JSON.stringify(options));
  }
});

test("what else the page cancels it still cancels in a card", () => {
  const { fn } = listener();

  // Ctrl+S would save the page; Ctrl+F the browser's find.
  for (const letter of ["s", "f"]) {
    const event = key({ key: letter }, true);
    fn(event);
    assert.equal(event.defaultPrevented, true, letter);
  }
});

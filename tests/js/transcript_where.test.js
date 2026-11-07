// Copyright (c) 2025-2026 Sunet.
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

// Where the caret is, said for a screen reader (F-65), without a browser:
// the transcript component is read from its source and its methods run on
// made-up blocks. Run by tests/test_transcript_editor.py (skipped where
// there is no node), or directly: node --test tests/js/

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

const context = vm.createContext({ module: {}, document: {}, window: {} });
vm.runInContext(source.replace("export default", "module.exports ="), context);
const { methods } = context.module.exports;

// An editor of three blocks, in either format. $nextTick runs at once, and
// focusBlock only notes where it was asked to go.
function editor(subtitleMode) {
  const self = {
    subtitleMode,
    where: "",
    focused: [],
    blocks: [
      { id: 1, speaker: "Anna", start_label: "00:00:01.000", end_label: "00:00:04.250" },
      { id: 2, speaker: "", start_label: "00:01:02.040", end_label: "00:01:05.960" },
      { id: 3, speaker: "Bo", start_label: "01:02:03.400", end_label: "01:02:09.000" },
    ],
    $nextTick: (then) => then(),
    focusBlock(id, offset) {
      self.focused.push([id, offset]);
    },
  };

  for (const name of ["blockNoun", "keysText", "spokenTime", "whereText", "sayWhere", "stepBlock"]) {
    self[name] = methods[name].bind(self);
  }

  return self;
}

test("a time is said short: minutes and tenths, hours when there are some", () => {
  const e = editor(true);

  assert.equal(e.spokenTime("00:00:01.000"), "0:01.0");
  assert.equal(e.spokenTime("00:01:02.040"), "1:02.0");
  assert.equal(e.spokenTime("01:02:03.400"), "1:02:03.4");
  // Rounded in whole tenths, so a time a hair short of a second carries.
  assert.equal(e.spokenTime("00:00:09.960"), "0:10.0");
  assert.equal(e.spokenTime("00:00:59.990"), "1:00.0");
  // A comma, as the time fields accept, and something that is no time.
  assert.equal(e.spokenTime("00:00:23,4"), "0:23.4");
  assert.equal(e.spokenTime("soon"), "soon");
});

test("a caption is its number and its times", () => {
  const e = editor(true);

  assert.equal(e.whereText(e.blocks[0]), "Caption 1, 0:01.0 to 0:04.3");
  assert.equal(e.whereText(e.blocks[2]), "Caption 3, 1:02:03.4 to 1:02:09.0");
});

test("a paragraph is its number, its speaker and its start", () => {
  const e = editor(false);

  assert.equal(e.whereText(e.blocks[0]), "Paragraph 1, Anna, 0:01.0");
  // No speaker, no empty place in the sentence.
  assert.equal(e.whereText(e.blocks[1]), "Paragraph 2, 1:02.0");
});

test("the same words again are said again", () => {
  const e = editor(true);

  e.sayWhere(2);
  assert.equal(e.where, "Caption 2, 1:02.0 to 1:06.0");

  // Cleared and put back, which is what makes a live region speak again.
  const said = [];
  e.$nextTick = (then) => {
    said.push(e.where);
    then();
  };
  e.sayWhere(2);
  assert.deepEqual(said, [""]);
  assert.equal(e.where, "Caption 2, 1:02.0 to 1:06.0");
});

test("Alt with the arrows goes to the start of the block before or after", () => {
  const e = editor(true);

  e.stepBlock(2, 1);
  e.stepBlock(2, -1);

  assert.deepEqual(e.focused, [
    [3, 0],
    [1, 0],
  ]);
});

test("at either end nothing moves, and that is said", () => {
  const captions = editor(true);
  captions.stepBlock(3, 1);
  assert.deepEqual(captions.focused, []);
  assert.equal(captions.where, "Last caption. Caption 3, 1:02:03.4 to 1:02:09.0");

  const paragraphs = editor(false);
  paragraphs.stepBlock(1, -1);
  assert.equal(paragraphs.where, "First paragraph. Paragraph 1, Anna, 0:01.0");
});

test("the keys are described in the format's own words", () => {
  assert.match(editor(true).keysText(), /previous or next caption\. Tab goes to this caption's start time/);
  assert.match(editor(false).keysText(), /previous or next paragraph\. Tab goes to this paragraph's speaker/);
});

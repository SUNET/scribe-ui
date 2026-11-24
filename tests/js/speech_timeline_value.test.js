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

// What Timeline's slider says its value is (ariaText), without a browser:
// the component is read from its source and the computed property is run on
// a made-up strip. Run by tests/test_speech_timeline.py (skipped where there
// is no node), or directly: node --test tests/js/

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "..", "utils", "speech_timeline.js"),
  "utf8"
);

const context = vm.createContext({ module: {}, document: {}, window: {} });
vm.runInContext(source.replace("export default", "module.exports ="), context);
const component = context.module.exports;

// A recording of 2:00: speech from 10 s to 20 s and from 40 s to 50 s; a
// caption over the first stretch only, and one over silence at 60-65 s.
function strip(at) {
  const self = {
    ariaPosition: at,
    runs: [
      [10, 20],
      [40, 50],
    ],
    captions: [
      { id: 1, start: 9, end: 21 },
      { id: 2, start: 60, end: 65 },
    ],
    span: () => 120,
  };

  for (const name of ["speakingAt", "moment", "clock"]) {
    self[name] = component.methods[name].bind(self);
  }

  return component.computed.ariaText.call(self);
}

test("speech inside a caption", () => {
  assert.equal(strip(15), "0:15.0 of 2:00, speech, in caption 1");
});

test("speech that no caption covers is said as one thing", () => {
  assert.equal(strip(45), "0:45.0 of 2:00, speech without a caption");
});

test("silence inside a caption", () => {
  assert.equal(strip(62), "1:02.0 of 2:00, silence, in caption 2");
});

test("silence and no caption", () => {
  assert.equal(strip(30), "0:30.0 of 2:00, silence, no caption here");
});

test("the ends of a stretch of speech count as speech, as the readout has it", () => {
  assert.equal(strip(40), "0:40.0 of 2:00, speech without a caption");
  assert.equal(strip(50), "0:50.0 of 2:00, speech without a caption");
});

test("nothing is said before the recording's length is known", () => {
  const self = { ariaPosition: 0, runs: [], captions: [], span: () => 0 };

  assert.equal(component.computed.ariaText.call(self), "");
});

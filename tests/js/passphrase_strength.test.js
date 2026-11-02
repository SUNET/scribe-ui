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

// The passphrase strength judgement and the meter's wiring, without a
// browser: a fake document that holds the meter's elements and a field, and
// timers that run when the test says so. Run by tests/test_passphrase_strength.py
// (skipped where there is no node), or directly: node --test tests/js/

"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const Strength = require(path.join(__dirname, "..", "..", "utils", "passphrase_strength.js"));

const { evaluate } = Strength;

function level(text) {
  return evaluate(text).level;
}

function reason(text) {
  return evaluate(text).reason;
}

test("nothing typed is nothing said", () => {
  assert.deepEqual(evaluate(""), { level: "empty", reason: "empty", label: "", message: "" });
  assert.equal(level(undefined), "empty");
  assert.equal(level(null), "empty");
});

test("under the minimum is too short, whatever it is", () => {
  for (const text of ["a", "abc", "1234567", "Xk9#mQ2", "a b c"]) {
    assert.equal(reason(text), "short", text);
    assert.equal(level(text), "weak", text);
  }
});

test("the levels follow length: 8, 12 and 20 characters", () => {
  // Plain letters that are in no list and make no pattern.
  assert.equal(Strength.MIN_LENGTH, 8);
  assert.equal(Strength.GOOD_LENGTH, 12);
  assert.equal(Strength.STRONG_LENGTH, 20);

  assert.equal(level("kvarnhjul"), "weak"); // 9
  assert.equal(level("kvarnhjulet"), "weak"); // 11
  assert.equal(level("kvarnhjulets"), "good"); // 12
  assert.equal(level("kvarnhjuletsvaxel"), "good"); // 17
  assert.equal(level("kvarnhjuletsvaxelhus"), "strong"); // 20
});

test("a long phrase of words is strong, and its separators count as length", () => {
  assert.equal(level("sommar cykel bibliotek hav"), "strong");
  assert.equal(level("sommar-cykel-bibliotek-hav"), "strong");
  assert.equal(level("sommar_cykel_bibliotek_hav"), "strong");
});

test("a password manager's suggestion is strong", () => {
  // The shape macOS Passwords suggests: three groups, 20 characters.
  assert.equal(level("hobtyr-pyvwa5-vodwuz"), "strong");
  assert.equal(level("xK9$mQ2vLp7#nR4wZ8"), "good"); // 18: not yet 20
  assert.equal(level("xK9$mQ2vLp7#nR4wZ8cT"), "strong");
});

test("a hyphen is a separator like a space, and a run of them is one", () => {
  assert.equal(level("abc-def-ghi-jkl"), level("abc def ghi jkl"));
  // Twenty characters of hyphen is not twenty characters of length.
  assert.equal(evaluate("kvarn" + "-".repeat(30) + "hjul").reason, "weak");
  assert.equal(level("kvarn" + "-".repeat(30) + "hjul"), level("kvarn hjul"));
  assert.equal(evaluate("  kort  ").reason, "short");
});

test("the common ones are too easy to guess, in any dress", () => {
  for (const text of [
    "password",
    "Password",
    "PASSWORD1",
    "Password123!",
    "P@ssw0rd",
    "p4ssw0rd2024",
    "pass word",
    "12345678",
    "123456789",
    "qwertyuiop",
    "Qwerty123",
    "iloveyou",
    "sunetscribe",
    "Sunet Scribe 2026",
    "Sommar2024",
    "Lösenord",
    "Lösenord1!",
    "losenord",
    "correct horse battery staple",
  ]) {
    assert.equal(reason(text), "guessable", text);
    assert.equal(level(text), "weak", text);
  }
});

test("patterns are too easy to guess", () => {
  for (const text of [
    "aaaaaaaa",
    "aaaaaaaaaaaaaaaaaaaaaaaa",
    "abababababab",
    "abcabcabcabc",
    "hav hav hav hav",
    "hav-hav-hav-hav",
    "abcdefghij",
    "zyxwvutsr",
    "asdfghjkl",
    "a-b-c-d-e-f-g-h-i-j",
    "1 2 3 4 5 6 7 8 9",
  ]) {
    assert.equal(reason(text), "guessable", text);
  }
});

test("a long phrase is not made weak by containing a common word", () => {
  assert.equal(level("sommar cykel bibliotek hav"), "strong");
  assert.equal(level("my password is a long sentence"), "strong");
});

test("a common word alone is judged as one, a phrase with it is not", () => {
  assert.equal(reason("sommar"), "short");
  assert.equal(reason("sommarkvall"), "weak");
});

test("accents are looked through when comparing, not counted away", () => {
  // The å/ä/ö of a common word does not make it a new one...
  assert.equal(reason("Hemligt1"), "guessable");
  // ...and they are characters like any other for length.
  assert.equal(level("höstlövsbärså"), "good");
});

test("an emoji is one character, not two", () => {
  assert.equal(reason("\u{1F600}\u{1F601}\u{1F602}\u{1F603}\u{1F604}\u{1F605}\u{1F606}"), "short");
});

test("only the lines the design names are ever said", () => {
  assert.deepEqual(Strength.MESSAGES, {
    short: "Too short – use more words.",
    guessable: "Too easy to guess – avoid common words and patterns.",
    weak: "A longer phrase is stronger than adding symbols.",
    good: "Good – make it longer to make it stronger.",
    strong: "Strong passphrase.",
  });
  assert.deepEqual(Strength.LABELS, { weak: "Weak", good: "Good", strong: "Strong" });

  for (const text of ["abc", "kvarnhjul", "sommar-cykel-bibliotek-hav", "password"]) {
    const judged = evaluate(text);

    assert.deepEqual(Object.keys(judged).sort(), ["label", "level", "message", "reason"]);
  }
});

// ── the page ───────────────────────────────────────────────────────────────

function page() {
  const listeners = {};
  const elements = {};

  function element(id, classes = []) {
    const attributes = {};
    const node = {
      id,
      textContent: "",
      value: "",
      classList: { contains: (name) => classes.includes(name) },
      getAttribute: (name) => (name in attributes ? attributes[name] : null),
      setAttribute: (name, value) => {
        attributes[name] = value;
      },
    };

    elements[id] = node;

    return node;
  }

  const doc = {
    addEventListener: (type, handler) => {
      (listeners[type] = listeners[type] || []).push(handler);
    },
    getElementById: (id) => elements[id] || null,
  };

  const timers = [];
  let next = 1;
  const env = {
    document: doc,
    setTimeout: (fn, ms) => {
      const timer = { id: next++, fn, ms };

      timers.push(timer);

      return timer.id;
    },
    clearTimeout: (id) => {
      const at = timers.findIndex((timer) => timer.id === id);

      if (at >= 0) timers.splice(at, 1);
    },
  };

  const meter = element("passphrase-strength");

  meter.setAttribute("data-empty-hint", "The hint.");
  meter.setAttribute("data-level", "empty");

  const label = element("passphrase-strength-label");
  const text = element("passphrase-strength-text");
  const status = element("passphrase-strength-status");

  text.textContent = "The hint.";

  const field = element("field", ["passphrase-field"]);
  const other = element("other", ["something-else"]);

  Strength.install(env);

  return {
    meter,
    label,
    text,
    status,
    field,
    other,
    timers,
    listeners,
    type(node, value) {
      node.value = value;
      listeners.input.forEach((handler) => handler({ target: node }));
    },
    focus(node) {
      listeners.focusin.forEach((handler) => handler({ target: node }));
    },
    wait() {
      // Everything that is waiting goes off, as the time passes.
      timers.splice(0).forEach((timer) => timer.fn());
    },
  };
}

test("the field is described by the meter's label and advice", () => {
  const p = page();

  assert.equal(p.field.getAttribute("aria-describedby"), null);

  p.focus(p.field);

  assert.equal(p.field.getAttribute("aria-describedby"), "passphrase-strength-label passphrase-strength-text");

  // Another field is left alone.
  p.focus(p.other);
  assert.equal(p.other.getAttribute("aria-describedby"), null);
});

test("typing fills the meter in: level, label and advice", () => {
  const p = page();

  p.type(p.field, "abc");
  assert.equal(p.meter.getAttribute("data-level"), "weak");
  assert.equal(p.label.textContent, "Passphrase strength: Weak");
  assert.equal(p.text.textContent, "Too short – use more words.");

  p.type(p.field, "kvarnhjuletsvaxel");
  assert.equal(p.meter.getAttribute("data-level"), "good");
  assert.equal(p.label.textContent, "Passphrase strength: Good");
  assert.equal(p.text.textContent, Strength.MESSAGES.good);

  p.type(p.field, "sommar cykel bibliotek hav");
  assert.equal(p.meter.getAttribute("data-level"), "strong");
  assert.equal(p.label.textContent, "Passphrase strength: Strong");
  assert.equal(p.text.textContent, "Strong passphrase.");
});

test("emptied, the meter goes back to the hint", () => {
  const p = page();

  p.type(p.field, "abc");
  p.type(p.field, "");

  assert.equal(p.meter.getAttribute("data-level"), "empty");
  assert.equal(p.label.textContent, "");
  assert.equal(p.text.textContent, "The hint.");
});

test("typing elsewhere does nothing", () => {
  const p = page();

  p.type(p.other, "abc");

  assert.equal(p.meter.getAttribute("data-level"), "empty");
  assert.equal(p.timers.length, 0);
});

test("a level is said once the typing stops, not on every key", () => {
  const p = page();

  p.type(p.field, "k");
  p.type(p.field, "kv");
  p.type(p.field, "kvarn");

  // Three keys, one thing waiting, nothing said yet.
  assert.equal(p.timers.length, 1);
  assert.equal(p.timers[0].ms, Strength.SAY_AFTER_MS);
  assert.equal(p.status.textContent, "");

  p.wait();

  assert.equal(p.status.textContent, "Passphrase strength: Weak.");
});

test("it is said when the level changes, and not again while it holds", () => {
  const p = page();

  p.type(p.field, "kvarnhjul");
  p.wait();
  assert.equal(p.status.textContent, "Passphrase strength: Weak.");

  // Still weak, a different line of advice: the status is left as it is.
  p.status.textContent = "(said)";
  p.type(p.field, "kvarnhjule");
  p.wait();
  assert.equal(p.status.textContent, "(said)");

  p.type(p.field, "kvarnhjuletsvaxel");
  p.wait();
  assert.equal(p.status.textContent, "Passphrase strength: Good.");

  p.type(p.field, "kvarnhjuletsvaxelhus");
  p.wait();
  assert.equal(p.status.textContent, "Passphrase strength: Strong.");
});

test("a level passed through on the way is not said", () => {
  const p = page();

  p.type(p.field, "kvarnhjul");
  p.type(p.field, "kvarnhjuletsvaxel");
  p.type(p.field, "kvarnhjuletsvaxelhus");
  p.wait();

  assert.equal(p.status.textContent, "Passphrase strength: Strong.");
});

test("emptied, the status is cleared, and the same level is said again after", () => {
  const p = page();

  p.type(p.field, "kvarnhjul");
  p.wait();
  p.type(p.field, "");
  p.wait();

  assert.equal(p.status.textContent, "");

  p.type(p.field, "kvarnhjul");
  p.wait();

  assert.equal(p.status.textContent, "Passphrase strength: Weak.");
});

test("it listens to typing and to arriving at the field, and to nothing else", () => {
  const p = page();

  assert.deepEqual(Object.keys(p.listeners).sort(), ["focusin", "input"]);
});

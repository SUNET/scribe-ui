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

// Passphrase strength, judged in the browser and nowhere else.
//
// The text typed into the encryption passphrase field is looked at here, by
// a function that returns a level and a line of advice, and goes no further:
// nothing in this file sends, stores or logs it (tests/test_passphrase_strength.py
// reads the source to make sure of that). What is measured is length, since
// that is what a reader can act on -- a longer phrase, not a symbol -- plus
// a short list of passphrases and patterns that are tried first. It is an
// aid, not a guarantee, and the reader is never told a score.
//
// Used by the page in two ways: evaluate(text) is the judgement itself (and
// what tests/js/passphrase_strength.test.js runs), install(env) listens for
// typing in a field marked class="passphrase-field" and fills the meter
// (#passphrase-strength) that utils/passphrase_strength.py draws.

(function (root, factory) {
  "use strict";

  const api = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }

  // Put in the page once per visit; it listens once.
  if (typeof document !== "undefined" && typeof window !== "undefined") {
    root.PassphraseStrength = api;

    if (!window._scribePassphraseStrength) {
      window._scribePassphraseStrength = true;

      api.install({
        document: document,
        setTimeout: window.setTimeout.bind(window),
        clearTimeout: window.clearTimeout.bind(window),
      });
    }
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Under this a passphrase is not accepted at all (the page's own rule,
  // main.py); from there it is only advised on.
  const MIN_LENGTH = 8;
  const GOOD_LENGTH = 12;
  const STRONG_LENGTH = 20;

  // How long to wait after the last key before saying a level aloud.
  const SAY_AFTER_MS = 600;

  const LABELS = { weak: "Weak", good: "Good", strong: "Strong" };

  const MESSAGES = {
    short: "Too short – use more words.",
    guessable: "Too easy to guess – avoid common words and patterns.",
    weak: "A longer phrase is stronger than adding symbols.",
    good: "Good – make it longer to make it stronger.",
    strong: "Strong passphrase.",
  };

  // Passphrases and the words they are made of that anyone tries first,
  // written the way they are compared: lower case, no accents, no separators.
  // Names of the service are in it too. Not a dictionary: a word that is
  // here only counts when it is all there is (plus digits at the end).
  const COMMON = new Set(
    (
      "password passwords passphrase pass secret secrets hello hellothere test testing " +
      "changeme default guest root user username admin administrator login logon master " +
      "welcome letmein trustno1 whatever access computer internet freedom " +
      "123456 1234567 12345678 123456789 1234567890 12345 1234 111111 000000 " +
      "123123 654321 666666 121212 112233 123321 7777777 " +
      "qwerty qwertyuiop qwertz qwerty123 qwe123 123qwe qweasd qweasdzxc qazwsx " +
      "zaq12wsx 1q2w3e4r 1q2w3e 1qaz2wsx q1w2e3 asdf asdfg asdfgh asdfghjkl zxcv zxcvbnm " +
      "abc123 abcdef abcdefg abcd1234 " +
      "iloveyou ilovegod loveme lovely love monkey dragon football baseball basketball " +
      "soccer hockey sunshine princess shadow superman batman spiderman starwars pokemon " +
      "michael jessica charlie jordan hunter ranger buster thomas robert daniel andrew " +
      "joshua matthew jennifer ashley nicole hannah amanda killer tigger flower hottie " +
      "cookie cheese chocolate pepper ginger coffee banana orange cocacola " +
      "summer winter spring autumn january february march april june july august " +
      "september october november december " +
      "sunet scribe sunetscribe transcribe transcriber transcription encryption encrypt " +
      "crypto university student teacher " +
      "losenord losenordet losen losenfras hemligt hemlig hemligtlosenord hemlighet " +
      "kodord nyckel kryptering krypteringslosenord " +
      "hej hejsan hejhej tjena tjenare kalle bamse stockholm goteborg malmo uppsala lund " +
      "sverige svenska sommar vinter varen hosten januari februari mars maj juni juli " +
      "augusti oktober fotboll alskling alskar karlek mamma pappa familjen universitet " +
      "studenten larare " +
      "correcthorsebatterystaple tobeornottobe " +
      // The example in the feature request that asked for the meter (#80),
      // which is public: anyone can copy it from there.
      "sommarcykelbibliotekhav"
    ).split(" ")
  );

  // Things typed by running a finger along a row or through the alphabet.
  const SEQUENCES = [
    "abcdefghijklmnopqrstuvwxyz",
    "0123456789",
    "qwertyuiopasdfghjklzxcvbnm",
    "qwertzuiopasdfghjklyxcvbnm",
    "1qaz2wsx3edc4rfv5tgb6yhn7ujm",
    "zyxwvutsrqponmlkjihgfedcba",
    "9876543210",
  ];

  // The look-alikes that turn a common word into a "clever" one.
  const LEET = { "0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i" };

  function stripAccents(text) {
    return text.normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function decode(text, oneIs) {
    let out = "";

    for (const ch of text) {
      out += ch === "1" ? oneIs : LEET[ch] || ch;
    }

    return out;
  }

  // Words, separated by spaces, hyphens or underscores. A run of them is one
  // separator, so a row of hyphens is not length.
  function wordsOf(text) {
    return text.split(/[\s\-_]+/).filter(Boolean);
  }

  // The words with each repeat taken out, so that saying the same thing again
  // is not length: "the cat sat on the mat" is judged as "the cat sat on mat".
  function distinct(words) {
    const seen = new Set();

    return words.filter((word) => {
      const key = stripAccents(word).toLowerCase();

      if (seen.has(key)) return false;

      seen.add(key);

      return true;
    });
  }

  function isCommon(joined) {
    const bases = [joined, joined.replace(/[0-9!?.,*#]+$/, "")];

    for (const base of bases) {
      if (!base) continue;

      for (const candidate of [base, decode(base, "i"), decode(base, "l")]) {
        if (COMMON.has(candidate)) return true;
      }
    }

    return false;
  }

  function isPattern(words, joined) {
    // Hardly any different characters: aaaaaaaa, abababab.
    if (new Set(joined).size < 6) return true;

    // One bit of text said over and over: hav-hav-hav-hav, abcabcabc.
    if (/^(.+?)\1+$/.test(joined)) return true;

    // Short fragments strung together: a-b-c-d-e-f-g.
    if (words.length >= 3 && words.every((word) => Array.from(word).length <= 2)) return true;

    // A run along the keyboard or the alphabet.
    for (const sequence of SEQUENCES) {
      if (joined.length >= 6 && sequence.includes(joined)) return true;
    }

    return false;
  }

  // The judgement. Returns { level, reason, label, message }:
  // level is "empty", "weak", "good" or "strong"; reason says which line of
  // advice applies (a key of MESSAGES, or "empty").
  function evaluate(text) {
    text = typeof text === "string" ? text : "";

    if (text === "") {
      return { level: "empty", reason: "empty", label: "", message: "" };
    }

    const words = wordsOf(text);

    // Under the page's own minimum it is too short, whatever it is.
    if (Array.from(words.join(" ")).length < MIN_LENGTH) {
      return result("weak", "short");
    }

    // What is compared with the list and the patterns is the whole of what
    // was typed, without the punctuation that is only there to dress it up
    // (the look-alikes @ $ ! are kept for the list to see through).
    const joined = stripAccents(words.join("")).toLowerCase();
    const plain = joined.replace(/[^\p{L}\p{N}@$!]/gu, "");

    // From here on length is of the words with their repeats left out: saying
    // the same thing again is not more to guess.
    const length = Array.from(distinct(words).join(" ")).length;

    if (isPattern(words, joined) || isCommon(plain) || length < MIN_LENGTH) {
      return result("weak", "guessable");
    }

    if (length < GOOD_LENGTH) return result("weak", "weak");
    if (length < STRONG_LENGTH) return result("good", "good");

    return result("strong", "strong");
  }

  function result(level, reason) {
    return { level: level, reason: reason, label: LABELS[level], message: MESSAGES[reason] };
  }

  // The page. A delegated listener, so it does not matter when the dialog
  // that holds the field is built (or built again). `env` is the document and
  // the timer functions, passed in so a test can supply its own.
  function install(env) {
    const doc = env.document;
    const DESCRIBED_BY = "passphrase-strength-label passphrase-strength-text";

    function isField(node) {
      return !!node && !!node.classList && node.classList.contains("passphrase-field");
    }

    function parts() {
      const meter = doc.getElementById("passphrase-strength");

      if (!meter) return null;

      return {
        meter: meter,
        label: doc.getElementById("passphrase-strength-label"),
        text: doc.getElementById("passphrase-strength-text"),
        status: doc.getElementById("passphrase-strength-status"),
      };
    }

    // The field is Quasar's, so the attribute cannot be put on it from the
    // server: it is set here, the first time it is reached.
    function describe(field) {
      if (field.getAttribute("aria-describedby") !== DESCRIBED_BY) {
        field.setAttribute("aria-describedby", DESCRIBED_BY);
      }
    }

    function show(field) {
      const found = parts();

      if (!found) return;

      const judged = evaluate(field.value);

      found.meter.setAttribute("data-level", judged.level);

      if (found.label) {
        found.label.textContent = judged.label ? "Passphrase strength: " + judged.label : "";
      }

      if (found.text) {
        found.text.textContent =
          judged.level === "empty" ? found.meter.getAttribute("data-empty-hint") || "" : judged.message;
      }

      // Said aloud only when the level changes, and a moment after the last
      // key: every key would be a stream of announcements.
      if (found.status) {
        if (found.meter._saying) env.clearTimeout(found.meter._saying);

        found.meter._saying = env.setTimeout(function () {
          found.meter._saying = null;

          if (found.meter._said === judged.level) return;

          found.meter._said = judged.level;
          found.status.textContent = judged.label ? "Passphrase strength: " + judged.label + "." : "";
        }, SAY_AFTER_MS);
      }
    }

    doc.addEventListener("focusin", function (event) {
      if (isField(event.target)) describe(event.target);
    });

    doc.addEventListener("input", function (event) {
      if (!isField(event.target)) return;

      describe(event.target);
      show(event.target);
    });
  }

  return {
    MIN_LENGTH: MIN_LENGTH,
    GOOD_LENGTH: GOOD_LENGTH,
    STRONG_LENGTH: STRONG_LENGTH,
    SAY_AFTER_MS: SAY_AFTER_MS,
    LABELS: LABELS,
    MESSAGES: MESSAGES,
    evaluate: evaluate,
    install: install,
  };
});

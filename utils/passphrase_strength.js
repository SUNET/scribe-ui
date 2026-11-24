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
// reads the source to make sure of that). When the page asks whether a
// passphrase may be set, verdict() answers with the reason alone, never the
// text.
//
// What is judged is what is left once everything an attacker tries first has
// been taken away: common passphrases, the names of universities and places,
// the term, the days and months, numbers in words, common first names and
// surnames, the little words of a sentence, years and digits that only
// decorate a word -- and the reader's own name and user name, which the page
// passes in. Too little left is "too easy to guess", and the page will not
// set it. Otherwise the length of what is left gives the level. It is an aid
// that catches the obvious, not a guarantee, and the reader is never told a
// score.
//
// Used by the page in three ways: evaluate(text, personal) is the judgement
// (and what tests/js/passphrase_strength.test.js runs); install(env) listens
// for typing in a field marked class="passphrase-field" and fills the meter
// (#passphrase-strength) that utils/passphrase_strength.py draws; verdict()
// is what the page asks before it sets a passphrase.

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
  // main.py); from there the level is advice -- except "too easy to guess",
  // which the page refuses as well.
  const MIN_LENGTH = 8;
  const GOOD_LENGTH = 12;
  const STRONG_LENGTH = 20;

  // How long to wait after the last key before saying a level aloud.
  const SAY_AFTER_MS = 600;

  const LABELS = { weak: "Weak", good: "Good", strong: "Strong" };

  const MESSAGES = {
    short: "Too short – use more words.",
    guessable: "Too easy to guess – it can't be used. Avoid common words and patterns.",
    personal: "Too easy to guess – it can't be used. Don't use your own name or user name.",
    place: "Too easy to guess – it can't be used. Avoid names of universities, places and terms.",
    weak: "A longer phrase is stronger than adding symbols.",
    good: "Good – make it longer to make it stronger.",
    strong: "Strong passphrase.",
  };

  // The reasons the page will not set a passphrase for.
  const REFUSED = ["short", "guessable", "personal", "place"];

  function set(text) {
    return new Set(text.split(/\s+/).filter(Boolean));
  }

  // Everything below is written the way it is compared: lower case, no
  // accents (å, ä and ö are a, a and o), no separators.

  // Whole passphrases that anyone tries first, and the words they are made of.
  // The service's own name is here, and the example the feature request that
  // asked for the meter (#80) gave, which is public.
  const COMMON = set(
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
      "killer tigger flower hottie cookie cheese chocolate pepper ginger coffee banana " +
      "orange cocacola sunet scribe sunetscribe transcribe transcriber transcription " +
      "encryption encrypt crypto losenord losenordet losen losenfras hemligt hemlig " +
      "hemligtlosenord hemlighet kodord nyckel kryptering krypteringslosenord " +
      "hej hejsan hejhej tjena tjenare kalle bamse sverige svenska fotboll alskling " +
      "alskar karlek mamma pappa familjen " +
      "correcthorsebatterystaple tobeornottobe sommarcykelbibliotekhav"
  );

  // Swedish universities and university colleges, by name and by the short
  // name they go by, the words such a name is made of, and the places they
  // are in. A "place" in the reason the reader is given.
  const PLACES = set(
    // The kind of institution.
    "universitet universitetet universitets university universiteit hogskola hogskolan " +
      "hogskolans college institutet institute institut tekniska technology kungliga " +
      "royal akademi akademin academy konsthogskolan musikhogskolan " +
      // The institutions.
      "uppsala lund goteborg gothenburg stockholm karolinska umea kth linkoping slu " +
      "lantbruksuniversitet lantbruksuniversitetet lulea ltu karlstad kau orebro oru " +
      "mittuniversitetet miun linneuniversitetet linnaeus lnu malmo mau malardalen mdu " +
      "chalmers handels handelshogskolan hhs sse jonkoping sodertorn boras dalarna " +
      "kristianstad hkr skovde gavle hig halmstad blekinge bth vast forsvarshogskolan " +
      "fhs gih konstfack kkh kmh skh sophiahemmet ersta skondal bracke beckmans " +
      "newmaninstitutet uu lu gu su ki umu liu ju sh hb du his hh hv esb ehs " +
      // Towns and regions.
      "vasteras helsingborg norrkoping sodertalje eskilstuna vaxjo sundsvall ostersund " +
      "trollhattan kalmar falun borlange visby gotland karlskrona nykoping varberg " +
      "uddevalla kiruna skelleftea solna huddinge flemingsberg kista frescati alnarp " +
      "ultuna campus sweden norrland skane svealand gotaland"
  );

  // Their full names, Swedish and English, written together. Matched across
  // words ("University of Arts, Crafts and Design") and inside one, so that a
  // name made of ordinary words is caught as the name it is.
  const FULL_NAMES = set(
    "uppsalauniversitet lundsuniversitet goteborgsuniversitet stockholmsuniversitet " +
      "karolinskainstitutet umeauniversitet kungligatekniskahogskolan " +
      "linkopingsuniversitet sverigeslantbruksuniversitet luleatekniskauniversitet " +
      "karlstadsuniversitet orebrouniversitet malmouniversitet malardalensuniversitet " +
      "chalmerstekniskahogskola handelshogskolanistockholm hogskolanijonkoping " +
      "sodertornshogskola hogskolaniboras hogskolandalarna hogskolankristianstad " +
      "hogskolaniskovde hogskolanigavle hogskolanihalmstad blekingetekniskahogskola " +
      "hogskolanvast gymnastikochidrottshogskolan kungligakonsthogskolan " +
      "kungligamusikhogskolan stockholmskonstnarligahogskola sophiahemmethogskola " +
      "rodakorsetshogskola mariecederschioldhogskola erstaskondalbrackehogskola " +
      "enskildahogskolanstockholm " +
      "uppsalauniversity lunduniversity universityofgothenburg gothenburguniversity " +
      "stockholmuniversity karolinskainstitute umeauniversity " +
      "kthroyalinstituteoftechnology royalinstituteoftechnology linkopinguniversity " +
      "swedishuniversityofagriculturalsciences luleauniversityoftechnology " +
      "karlstaduniversity orebrouniversity midswedenuniversity linnaeusuniversity " +
      "malmouniversity malardalenuniversity chalmersuniversityoftechnology " +
      "stockholmschoolofeconomics jonkopinguniversity sodertornuniversity " +
      "universityofboras dalarnauniversity kristianstaduniversity universityofskovde " +
      "universityofgavle gavleuniversitycollege halmstaduniversity " +
      "blekingeinstituteoftechnology universitywest swedishdefenceuniversity " +
      "swedishschoolofsportandhealthsciences universityofartscraftsanddesign " +
      "royalinstituteofart royalcollegeofmusic stockholmuniversityofthearts " +
      "sophiahemmetuniversity mariecederschiolduniversity redcrossuniversitycollege " +
      "swedishredcrossuniversity universitycollegestockholm " +
      "erstaskondalbrackeuniversitycollege"
  );

  // The term and the year of study: HT25, vt2026, lp3.
  const TERMS = set(
    "ht vt lp termin terminen terminer hosttermin hostterminen vartermin varterminen " +
      "sommartermin lasar lasaret lasperiod semester term quarter"
  );

  // Days, months, seasons and holidays, Swedish and English.
  const CALENDAR = set(
    "mandag tisdag onsdag torsdag fredag lordag sondag monday tuesday wednesday " +
      "thursday friday saturday sunday januari februari mars april maj juni juli " +
      "augusti september oktober november december january february march may june " +
      "july august october var varen sommar sommaren host hosten vinter vintern spring " +
      "summer autumn fall winter jul julafton midsommar pask nyar christmas easter"
  );

  // Numbers in words.
  const NUMBERS = set(
    "noll ett en tva tre fyra fem sex sju atta nio tio elva tolv tretton fjorton " +
      "femton sexton sjutton arton nitton tjugo trettio fyrtio femtio sextio sjuttio " +
      "attio nittio hundra tusen miljon zero one two three four five six seven eight " +
      "nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen " +
      "nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand " +
      "million first second third"
  );

  // The most common first names and surnames in Sweden.
  const NAMES = set(
    "anna eva maria karin kristina lena sara kerstin emma ingrid marie malin jenny " +
      "hanna linda annika susanne elin monica birgitta sofia johanna ulla inger carina " +
      "elisabeth julia linnea ida helena camilla asa anette sandra gunilla marianne ebba " +
      "maja alice astrid elsa wilma olivia agnes freja saga ella alva klara vera stella " +
      "selma lars mikael anders johan per erik karl peter jan thomas daniel fredrik hans " +
      "bengt mats andreas stefan bo magnus mattias nils jonas martin leif bjorn ulf sven " +
      "bertil henrik alexander gustav oskar viktor axel emil anton filip elias william " +
      "hugo lucas liam noah oliver adam isak leo theo ludvig albin simon jakob sebastian " +
      "marcus robert patrik christer roger goran kent kjell rolf tommy ake gunnar olof " +
      "ingvar lennart sten arne jorgen joakim michael jessica charlie jordan hunter " +
      "thomas andrew joshua matthew jennifer ashley nicole amanda " +
      "andersson johansson karlsson nilsson eriksson larsson olsson persson svensson " +
      "gustafsson pettersson jonsson jansson hansson bengtsson lindberg jakobsson " +
      "magnusson olofsson lindstrom lindqvist lindgren berg axelsson bergstrom lundberg " +
      "lind lundgren lundqvist mattsson berglund fredriksson sandberg henriksson " +
      "forsberg sjoberg wallin ali engstrom mohamed eklund danielsson lundin hakansson " +
      "bjork bergman gunnarsson holm wikstrom samuelsson isaksson fransson bergqvist " +
      "nystrom holmberg arvidsson lofgren soderberg nyberg blomqvist claesson nordstrom " +
      "martensson lundstrom ahmed viklund bjorklund eliasson palsson hassan berggren " +
      "sandstrom nordin strom aberg hermansson ekstrom holmgren sundberg hedlund " +
      "dahlberg hellstrom sjogren abrahamsson falk martinsson oberg andreasson " +
      "stromberg mansson hansen akesson dahl lindholm norberg holmqvist"
  );

  // The little words a sentence is held together with, Swedish and English.
  // Only as words of their own: inside a string of mixed characters "i" or
  // "a" is just a letter.
  const SMALL = set(
    "jag du han hon den det vi ni de mig dig sig oss er dem min mitt mina din ditt " +
      "dina sin sitt sina vart vara och eller men att som for till fran med utan pa i " +
      "av om under over efter innan nar dar har ar blir bli blev kan ska skall vill " +
      "maste ha hade inte ej ja nej alla allt nagon nagot inget ingen mycket lite bara " +
      "ocksa sa nu da heter bor min " +
      "the a an and or but if of to in on at by for with from as is are was were be " +
      "been am i you he she it we they me my mine your his her its our their this that " +
      "these those not no yes do does did have has had will would can could shall " +
      "should might must so too very just than then there here what which who whom " +
      "whose when where why how all any some each every only also up down out again " +
      "about into onto off"
  );

  // The words of studying.
  const STUDY = set(
    "student studenter studenten studerande larare forskare forskning doktorand kurs " +
      "kursen program programmet tentamen tenta examen uppsats avhandling teacher " +
      "research thesis exam course"
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

  // Most specific first: the reason the reader is given is the first kind
  // that was found.
  const KINDS = ["personal", "place", "guessable"];

  function normalise(text) {
    return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function decode(text, oneIs) {
    let out = "";

    for (const ch of text) {
      out += ch === "1" ? oneIs : LEET[ch] || ch;
    }

    return out;
  }

  // Words, separated by spaces, hyphens, underscores and the punctuation of
  // a sentence. A run of them is one separator, so a row of hyphens is not
  // length. @ $ and ! stay in the word: they are look-alikes.
  const SEPARATORS = /[\s\-_.,;:/\\()'"+&]+/;

  function wordsOf(text) {
    return text.split(SEPARATORS).filter(Boolean);
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

  // What kind of known word `run` (letters, normalised) is, or null.
  // `alone` is whether it is a word of its own rather than letters among
  // digits and symbols.
  function kindOf(run, alone, personal) {
    const bare = run.length > 3 && run.endsWith("s") ? run.slice(0, -1) : null;
    const has = (words, word) => words.has(word) || (bare !== null && words.has(bare));

    if (has(personal, run)) return "personal";
    if (TERMS.has(run)) return "place";

    // Two letters among digits ("su4") are more likely chance than a name.
    if (!alone && run.length < 3) return null;

    if (has(PLACES, run)) return "place";
    if (COMMON.has(run) || CALENDAR.has(run) || NUMBERS.has(run) || STUDY.has(run) || has(NAMES, run)) {
      return "guessable";
    }
    if (alone && SMALL.has(run)) return "guessable";

    return null;
  }

  // Known words inside a longer one: "lunduniversitet", "annaandersson",
  // "sommarkvall". Only words of five letters or more, and the reader's own
  // of four, so that a short name does not eat an ordinary word.
  const EMBEDDED = [
    ...[...FULL_NAMES].map((word) => [word, "place"]),
    ...[...PLACES].filter((word) => word.length >= 5).map((word) => [word, "place"]),
    ...[...NAMES, ...CALENDAR, ...NUMBERS, ...STUDY, ...COMMON]
      .filter((word) => word.length >= 5 && /^[a-z]+$/.test(word))
      .map((word) => [word, "guessable"]),
  ].sort((a, b) => b[1].length - a[1].length || b[0].length - a[0].length);

  function takeEmbedded(run, personal, found) {
    const known = [
      ...[...personal].filter((word) => word.length >= 4).map((word) => [word, "personal"]),
      ...EMBEDDED,
    ].sort((a, b) => b[0].length - a[0].length);

    let left = run;

    for (const [word, kind] of known) {
      if (left.includes(word)) {
        left = left.split(word).join("|");
        found.add(kind);
      }
    }

    // Nothing known in it: all of it is the reader's own.
    if (!left.includes("|")) return run;

    // What is left between the known words, if it is anything: a letter or
    // two (a genitive s, an "e") is not.
    return left
      .split("|")
      .filter((piece) => piece.length >= 3)
      .join("");
  }

  // One word, split into its runs of letters, digits and other characters.
  // Returns what is left of it once the known runs are taken out, and adds
  // the kinds it found to `found`.
  function remainderOf(word, personal, found) {
    const normal = normalise(word);

    // A common one in disguise: P@ssw0rd!, sommar2024.
    if (isCommon(normal.replace(/[^\p{L}\p{N}@$!]/gu, ""))) {
      found.add("guessable");

      return "";
    }

    const runs = normal.match(/\p{L}+|\p{N}+|[^\p{L}\p{N}]+/gu) || [];
    const alone = runs.length === 1;
    const letters = runs.filter((run) => /^\p{L}/u.test(run));
    const kinds = letters.map((run) => kindOf(run, alone, personal));
    const lettersKnown = kinds.every((kind) => kind !== null);
    let left = "";
    let index = 0;

    runs.forEach((run, at) => {
      if (/^\p{L}/u.test(run)) {
        const kind = kinds[index++];

        if (kind) {
          found.add(kind);
        } else {
          left += takeEmbedded(run, personal, found);
        }
      } else if (/^\p{N}/u.test(run)) {
        // Digits are known when they are a year, when they are all the word
        // is (a date, a number), or when they only decorate known letters:
        // anna80, ht25.
        const year = /^(19|20)\d\d$/.test(run);

        if (year || letters.length === 0 || lettersKnown) {
          found.add(letters.length && kinds.some((kind) => kind === "place") ? "place" : "guessable");
        } else {
          left += run;
        }
      } else if (at !== 0 && at !== runs.length - 1) {
        // A symbol inside a word is part of it; at either end it is dressing.
        left += run;
      }
    });

    return left;
  }

  // Which of the words, by position, make up a university's full name
  // ("Swedish", "University", "of", "Agricultural", "Sciences"). Up to eight
  // words at a time; the longest name found wins.
  function namedWords(words) {
    const normal = words.map((word) => normalise(word).replace(/[^\p{L}]/gu, ""));
    const named = new Set();

    for (let first = 0; first < normal.length; first++) {
      for (let last = Math.min(normal.length, first + 8); last > first + 1; last--) {
        if (FULL_NAMES.has(normal.slice(first, last).join(""))) {
          for (let at = first; at < last; at++) named.add(at);

          break;
        }
      }
    }

    return named;
  }

  // The judgement. Returns { level, reason, label, message }:
  // level is "empty", "weak", "good" or "strong"; reason says which line of
  // advice applies (a key of MESSAGES, or "empty"). `personal` is the
  // reader's own name and user name, as words (see personal_words() in
  // utils/passphrase_strength.py).
  function evaluate(text, personal) {
    text = typeof text === "string" ? text : "";

    if (text === "") {
      return { level: "empty", reason: "empty", label: "", message: "" };
    }

    const own = new Set((personal || []).map(normalise).filter((word) => word.length >= 3));
    const words = wordsOf(text);

    // Under the page's own minimum it is too short, whatever it is.
    if (Array.from(words.join(" ")).length < MIN_LENGTH) {
      return result("weak", "short");
    }

    const joined = normalise(words.join(""));
    const plain = joined.replace(/[^\p{L}\p{N}@$!]/gu, "");

    if (isPattern(words, joined) || isCommon(plain)) {
      return result("weak", "guessable");
    }

    // What is left once the known words are taken out, each word once:
    // saying the same thing again is not more to guess.
    const found = new Set();
    const left = [];
    const named = namedWords(words);

    if (named.size) found.add("place");

    words.forEach((word, at) => {
      if (named.has(at)) return;

      const rest = remainderOf(word, own, found);

      if (rest && !left.includes(rest)) left.push(rest);
    });

    const length = Array.from(left.join(" ")).length;

    if (length < MIN_LENGTH) {
      return result("weak", KINDS.find((kind) => found.has(kind)) || "guessable");
    }

    if (length < GOOD_LENGTH) return result("weak", "weak");
    if (length < STRONG_LENGTH) return result("good", "good");

    return result("strong", "strong");
  }

  function result(level, reason) {
    return { level: level, reason: reason, label: LABELS[level], message: MESSAGES[reason] };
  }

  // The reader's own words, as the meter carries them.
  function personalOf(meter) {
    const words = meter && meter.getAttribute("data-personal");

    return words ? words.split(" ") : [];
  }

  // What the page asks before setting a passphrase: the reason alone, or null
  // when there is no field. Never the text.
  function verdict(doc) {
    doc = doc || (typeof document !== "undefined" ? document : null);

    if (!doc) return null;

    const field = doc.querySelector(".passphrase-field");

    if (!field) return null;

    return evaluate(field.value, personalOf(doc.getElementById("passphrase-strength"))).reason;
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

      const judged = evaluate(field.value, personalOf(found.meter));

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
    REFUSED: REFUSED,
    evaluate: evaluate,
    verdict: verdict,
    install: install,
  };
});

# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The markings an RTF export carries, and how a reader can tell them apart
afterwards: uncertain words at a sensitivity of the reader's choosing, named
character styles for the kinds that have them, a key first in the file to the
kinds that are in it, and the text marked with the language it was
transcribed in.
"""

import pathlib
import re
import shutil
import subprocess
import zipfile

import pytest

from utils.caption import SRTCaption
from utils.settings import get_settings
from utils.srt import SRTEditor
from utils.srt_export import (
    RTF_LANGUAGES,
    RTF_UNCERTAIN_OPTIONS,
    rtf_language,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Whisper's own names for the languages it transcribes (whisper/tokenizer.py,
# LANGUAGES, openai-whisper 20250625), and the six of them Windows has no
# language id for.
WHISPER_NAMES = (
    "english chinese german spanish russian korean french japanese portuguese "
    "turkish polish catalan dutch arabic swedish italian indonesian hindi finnish "
    "vietnamese hebrew ukrainian greek malay czech romanian danish hungarian tamil "
    "norwegian thai urdu croatian bulgarian lithuanian latin maori malayalam welsh "
    "slovak telugu persian latvian bengali serbian azerbaijani slovenian kannada "
    "estonian macedonian breton basque icelandic armenian nepali mongolian bosnian "
    "kazakh albanian swahili galician marathi punjabi sinhala khmer shona yoruba "
    "somali afrikaans occitan georgian belarusian tajik sindhi gujarati amharic "
    "yiddish lao uzbek faroese haitian_creole pashto turkmen nynorsk maltese "
    "sanskrit luxembourgish myanmar tibetan tagalog malagasy assamese tatar "
    "hawaiian lingala hausa bashkir javanese sundanese cantonese"
)
NO_WINDOWS_ID = {"shona", "haitian creole", "malagasy", "lingala", "javanese", "sundanese"}

# Scores 0.1 to 0.9 on the six words: low flags under 0.25, medium under 0.5,
# high under 0.75 (settings.REVIEW_SENSITIVITY_*).
WORDS = {
    "version": 1,
    "words": [
        {"t": "ett", "s": 0.0, "e": 0.5, "c": 0.9},
        {"t": "två", "s": 0.6, "e": 1.0, "c": 0.1},
        {"t": "tre", "s": 1.1, "e": 1.5, "c": 0.4},
        {"t": "fyra", "s": 2.0, "e": 2.4, "c": 0.6},
        {"t": "fem", "s": 2.5, "e": 2.9, "c": 0.3},
        {"t": "sex", "s": 3.0, "e": 3.5, "c": 0.95},
    ],
}


def make_editor(data_format="txt", words=WORDS):
    editor = SRTEditor("job-uuid", data_format, "file")
    editor.load_words(words)
    editor.captions = [
        SRTCaption(1, "00:00:00,000", "00:00:01,500", "ett två tre", speaker="A"),
        SRTCaption(2, "00:00:02,000", "00:00:03,500", "fyra fem sex", speaker="A"),
    ]
    editor.speakers = {"A"}

    return editor


@pytest.fixture
def editor():
    return make_editor()


def export(editor, speakers=False, **kwargs):
    return editor.export_rtf(speakers, False, False, **kwargs)


def body(rtf):
    """The transcript of an export, without the header and the key."""

    return re.split(
        r"\\pard(?:\\plain\\s0)?\\f0\\fs20(?:\\lang\d+)?(?:\\sb200)? ", rtf, maxsplit=1
    )[1]


def key(rtf):
    """The key, or "" when there is none."""

    found = re.search(r"\\pard\\plain\\s1.*?\\par", rtf)

    return found.group(0) if found else ""


def balanced(rtf):
    unescaped = rtf.replace("\\{", "").replace("\\}", "")

    return unescaped.count("{") == unescaped.count("}")


class TestUncertainWords:
    def test_they_are_the_words_under_the_sensitivity_asked_for(self, editor):
        assert body(export(editor, uncertain="low")).count(r"\cs12") == 1
        assert body(export(editor, uncertain="medium")).count(r"\cs12") == 3
        assert body(export(editor, uncertain="high")).count(r"\cs12") == 4

    def test_violet_with_a_dotted_underline_in_a_style_of_their_own(self, editor):
        rtf = export(editor, uncertain="low")

        assert r"ett {\cs12\cf3\uld tv\u229?} tre" in rtf
        assert r"\red109\green81\blue201;" in rtf
        assert r"{\*\cs12\additive\sbasedon10\f0\fs20\cf3\uld Scribe: Uncertain word;}" in rtf

    def test_the_editors_own_level_is_not_what_decides(self, editor):
        editor.review_sensitivity = "high"
        editor.show_uncertain_words = False

        assert body(export(editor, uncertain="low")).count(r"\cs12") == 1
        assert editor.review_sensitivity == "high"

    def test_the_space_between_two_is_not_uncertain(self, editor):
        rtf = export(editor, uncertain="medium")

        assert r"{\cs12\cf3\uld tv\u229?} {\cs12\cf3\uld tre}" in rtf

    def test_a_word_the_reader_changed_is_never_uncertain(self, editor):
        """
        The doubt was about the word that was transcribed. A word marked as
        changed but spelt as before still is a changed word.
        """

        editor.captions[0].edited_words = {1}

        rtf = export(editor, uncertain="low", edits=True)

        assert r"ett {\cs11\cf2\ul tv\u229?} tre" in rtf
        assert r"\cs12" not in body(rtf)

    def test_a_word_retyped_is_not_uncertain_either(self, editor):
        editor.captions[0].text = "ett två tree"

        assert r"tree" in export(editor, uncertain="high")
        assert r"{\cs12\cf3\uld tree}" not in export(editor, uncertain="high")

    def test_changed_and_uncertain_never_go_together(self, editor):
        editor.captions[0].edited_words = {0, 1, 2}
        editor.captions[1].edited_words = {1}

        rtf = body(export(editor, uncertain="high", edits=True, highlights=True))

        assert not re.search(r"\\cs11[^ ]*\\cs12|\\cs12[^ ]*\\cs11", rtf)

    def test_with_a_highlight_the_highlighter_and_the_style(self, editor):
        editor.captions[0].highlighted_words = {1}

        rtf = export(editor, uncertain="low", highlights=True)

        assert r"{\highlight1\cs12\cf3\uld tv\u229?}" in rtf

    @pytest.mark.parametrize("asked", [None, "off", "", "extreme", 3])
    def test_off_or_anything_else_marks_nothing(self, editor, asked):
        assert export(editor, uncertain=asked) == export(editor)

    def test_without_scores_there_is_nothing_to_mark(self):
        plain = make_editor(words={"version": 1, "words": [
            {"t": "ett", "s": 0.0, "e": 0.5}, {"t": "två", "s": 0.6, "e": 1.0},
        ]})

        assert plain.has_confidence is False
        assert export(plain, uncertain="high") == export(plain)

    def test_subtitles_never_carry_them_for_now(self):
        subtitles = make_editor("srt")

        assert export(subtitles, uncertain="high") == export(subtitles)

    def test_the_braces_balance(self, editor):
        editor.captions[0].highlighted_words = {0, 1}
        editor.captions[1].edited_words = {0}

        assert balanced(export(editor, uncertain="high", highlights=True, edits=True, comments=True))


class TestOffered:
    def test_offered_where_there_are_scores(self, editor):
        assert editor.rtf_uncertain_available() is True

    def test_not_without_them_or_for_subtitles(self):
        assert make_editor(words=None).rtf_uncertain_available() is False
        assert make_editor("srt").rtf_uncertain_available() is False

    def test_any_file_of_a_bulk_export_will_do(self):
        assert make_editor(words=None).rtf_uncertain_available([make_editor()]) is True

    def test_off_first_and_the_editors_levels(self):
        assert list(RTF_UNCERTAIN_OPTIONS) == ["off", "low", "medium", "high"]
        assert list(RTF_UNCERTAIN_OPTIONS.values()) == ["Off", "Low", "Medium", "High"]

    def test_the_dialog_offers_it_off_and_only_where_it_can(self):
        source = (ROOT / "utils" / "srt_export.py").read_text()
        built = source[source.index("rtf_uncertain = (") :]
        built = built[: built.index("ui.separator()")]

        assert 'value="off"' in built
        assert 'label="Include uncertain words"' in built
        assert "rtf_uncertain.set_visibility(" in built
        assert "self.rtf_uncertain_available(" in built

        passed = source[source.index("uncertain=(") :]
        passed = passed[: passed.index("),")]
        assert "rtf_uncertain.visible" in passed
        assert 'rtf_uncertain.value != "off"' in passed


class TestTheKey:
    def test_a_clean_export_has_none(self, editor):
        editor.captions[0].highlighted_words = {1}

        assert key(export(editor)) == ""
        assert "stylesheet" not in export(editor)

    def test_asked_for_marks_that_are_not_there_is_a_clean_export(self, editor):
        """A bulk export asks every file; a file without them is clean."""

        assert export(editor, highlights=True, edits=True, comments=True) == export(editor)

    def test_it_comes_first_and_is_a_paragraph_of_its_own(self, editor):
        editor.captions[0].highlighted_words = {1}

        rtf = export(editor, highlights=True)
        at = rtf.index(r"\pard\plain\s1")

        assert at < rtf.index("ett")
        assert key(rtf).endswith(r"\par")
        assert r"\brdrb\brdrs" in key(rtf)
        assert r"{\s1\sbasedon0\f0\fs18\cf4\lang2057 Scribe: Export key;}" in rtf

    def test_it_is_english_and_marked_so(self, editor):
        editor.captions[0].highlighted_words = {1}

        assert r"\lang2057" in key(export(editor, highlights=True))

    @pytest.mark.parametrize(
        "marks, says, says_not",
        [
            ({"highlights": True}, ["Yellow highlight"], ["Teal", "Violet", "Comments", "character style can"]),
            ({"edits": True}, ["Teal, underlined", "Scribe: My edit", "character style can"], ["Yellow", "Violet", "Comments"]),
            ({"uncertain": "medium"}, ["Violet, dotted underline", "sensitivity Medium", "Scribe: Uncertain word"], ["Yellow", "Teal", "Comments"]),
            ({"comments": True}, ["Comments in the margin"], ["Yellow", "Teal", "Violet", "character style can"]),
        ],
    )
    def test_only_what_is_in_the_file(self, editor, marks, says, says_not):
        from utils.caption import WordComment

        editor.captions[0].highlighted_words = {0}
        editor.captions[0].edited_words = {2}
        editor.captions[1].comments = [WordComment({0}, "c")]

        text = key(export(editor, **marks)).replace(r"\u8220?", "").replace(r"\u8221?", "")

        for phrase in says:
            assert phrase in text, phrase
        for phrase in says_not:
            assert phrase not in text, phrase

    def test_it_says_no_more_than_it_needs_to(self, editor):
        from utils.caption import WordComment

        editor.captions[0].highlighted_words = {0}
        editor.captions[0].edited_words = {2}
        editor.captions[1].comments = [WordComment({0}, "c")]

        text = key(export(editor, highlights=True, edits=True, comments=True, uncertain="high"))

        assert r"Yellow highlight} \u8211? your highlights.\line " in text
        assert r"Comments in the margin \u8211? your comments.\line " in text
        for said_too_much in ("highlighter", "not marked", "by "):
            assert said_too_much not in text, said_too_much

    def test_the_samples_are_drawn_without_the_styles(self, editor):
        """Finding every word in a style must find the transcript's, not the key's."""

        editor.captions[0].edited_words = {2}

        text = key(export(editor, edits=True, uncertain="low"))

        assert r"\cs11" not in text and r"\cs12" not in text
        assert r"{\cf2\ul Teal, underlined}" in text
        assert r"{\cf3\uld Violet, dotted underline}" in text

    def test_only_the_styles_in_use_are_defined(self, editor):
        editor.captions[0].highlighted_words = {1}

        rtf = export(editor, highlights=True)

        assert "Scribe: My edit" not in rtf
        assert "Scribe: Uncertain word" not in rtf
        assert "Scribe: Highlight" not in rtf

    def test_each_style_gives_its_font_and_size(self, editor):
        editor.captions[0].edited_words = {2}

        rtf = export(editor, edits=True, uncertain="low")

        for name in ("My edit", "Uncertain word"):
            definition = re.search(r"\{\\\*\\cs1\d[^}]*Scribe: " + name, rtf).group(0)
            assert r"\f0\fs20" in definition, name


class TestTheLanguage:
    def test_every_language_a_recording_can_be_transcribed_in_has_one(self):
        for name in get_settings().WHISPER_LANGUAGES:
            assert rtf_language(name) in RTF_LANGUAGES.values(), name

    def test_every_language_whisper_knows_has_one_where_windows_does(self):
        names = [name.replace("_", " ") for name in WHISPER_NAMES.split(" ")]

        assert len(names) == 100

        for name in names:
            if name in NO_WINDOWS_ID:
                assert rtf_language(name) is None, name
            else:
                assert rtf_language(name) is not None, name

    def test_every_id_is_one_windows_has(self):
        import locale

        known = {lcid & 0xFFFF for lcid in locale.windows_locale}

        for name, lcid in RTF_LANGUAGES.items():
            assert lcid in known, name

    def test_the_variants_chosen(self):
        assert rtf_language("English") == 2057  # en-GB
        assert rtf_language("Norwegian") == 1044  # nb-NO
        assert rtf_language("Nynorsk") == 2068  # nn-NO
        assert rtf_language("Spanish") == rtf_language("Castilian") == 3082  # es-ES
        assert rtf_language("Portuguese") == 2070  # pt-PT
        assert rtf_language("Chinese") == rtf_language("Mandarin") == 2052  # zh-CN
        assert rtf_language("Cantonese") == 3076  # zh-HK
        assert rtf_language("Catalan") == 1027 and rtf_language("Valencian") == 2051
        assert rtf_language("Lule Sámi") == 5179 and rtf_language("Southern Sámi") == 7227

    def test_as_the_job_names_it(self):
        assert rtf_language("Swedish") == 1053
        assert rtf_language("swedish") == 1053
        assert rtf_language("Northern Sámi (Experimental)") == 2107
        assert rtf_language("Northern sámi (experimental)") == 2107
        assert rtf_language("English") == 2057
        assert rtf_language("Klingon") is None
        assert rtf_language(None) is None
        assert rtf_language("") is None

    def test_the_text_is_marked_with_it(self, editor):
        editor.language = "Swedish"

        rtf = export(editor)

        assert rtf.startswith(r"{\rtf1\ansi\deff0\deflang1053{\fonttbl")
        assert r"\pard\f0\fs20\lang1053 ett" in rtf

    def test_and_so_is_the_normal_style_when_there_is_a_key(self, editor):
        editor.language = "Swedish"
        editor.captions[0].highlighted_words = {1}

        rtf = export(editor, highlights=True)

        assert r"{\s0\f0\fs20\lang1053 Normal;}" in rtf
        assert r"\pard\plain\s0\f0\fs20\lang1053\sb200 ett" in rtf

    def test_the_header_lines_are_not_spell_checked(self, editor):
        editor.language = "Swedish"

        rtf = editor.export_rtf(True, True, True)

        assert r"{\b\noproof [1] (00:00:00,000 - 00:00:01,500) A:}\line ett" in rtf

    def test_a_speaker_scribe_named_is_english(self, editor):
        editor.language = "Swedish"
        editor.captions[0].speaker = "Speaker 2"
        editor.captions[1].speaker = "UNKNOWN"

        rtf = export(editor, speakers=True)

        assert r"{\b\noproof {\lang2057 Speaker 2:}}" in rtf
        assert r"{\b\noproof {\lang2057 UNKNOWN:}}" in rtf

    def test_a_speaker_the_reader_named_is_in_the_texts_language(self, editor):
        editor.language = "Swedish"
        editor.captions[0].speaker = "Intervjuare"

        rtf = export(editor, speakers=True)

        assert r"{\b\noproof Intervjuare:}" in rtf

    def test_without_a_language_a_clean_export_is_what_it_was(self, editor):
        before = (
            r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\viewkind4\uc1\pard\f0\fs20 "
            r"\b A:\b0\line ett tv\u229? tre\line\line \b A:\b0\line fyra fem sex\line\line }"
        )

        assert export(editor, speakers=True) == before

        editor.language = "Klingon"
        assert export(editor, speakers=True) == before

    def test_the_page_and_the_bulk_export_say_what_it_is(self):
        page = (ROOT / "pages" / "srt.py").read_text()
        bulk = (ROOT / "utils" / "common.py").read_text()

        assert "editor.language = language" in page
        assert 'editor.language = row.get("language")' in bulk


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_a_word_processor_reads_the_styles_the_languages_and_the_comment(tmp_path):
    """
    What LibreOffice makes of it, as .docx: the styles by name, the text in
    Swedish, the key in British English, and the comment by Scribe.
    """

    from utils.caption import WordComment

    editor = make_editor()
    editor.language = "Swedish"
    editor.captions[0].highlighted_words = {0}
    editor.captions[0].edited_words = {2}
    editor.captions[1].comments = [WordComment({1}, "kolla")]

    source = tmp_path / "export.rtf"
    source.write_text(
        editor.export_rtf(True, False, False, highlights=True, edits=True, comments=True, uncertain="high"),
        encoding="ascii",
    )
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "docx", "--outdir", str(tmp_path), str(source)],
        capture_output=True,
        timeout=120,
    )

    with zipfile.ZipFile(tmp_path / "export.docx") as docx:
        styles = docx.read("word/styles.xml").decode()
        document = docx.read("word/document.xml").decode()
        comments = docx.read("word/comments.xml").decode()

    for name in ("Scribe: My edit", "Scribe: Uncertain word", "Scribe: Export key"):
        assert f'w:val="{name}"' in styles, name

    assert 'w:val="sv-SE"' in styles
    assert 'w:val="en-GB"' in styles
    assert 'w:highlight w:val="yellow"' in document
    assert 'w:author="Scribe"' in comments

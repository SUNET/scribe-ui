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
Exporting a transcription: the format menu and the writers behind it.

The dialog builds txt, csv and tsv inline because each carries its own
options -- separators, header rows, which timestamps and in what format.
The writers here are the ones with nothing to configure.
"""

import json
import re
import unicodedata
from datetime import datetime
from typing import Optional

from nicegui import ui

from urllib.parse import quote

from utils.drive import display_name as drive_display_name, drive_status
from utils.drive_dialogs import save_to_drive
from utils.export_zip import prepare_zip
from utils.helpers import sanitize_filename
from utils.recording_api import ORIGINAL_PREFIX
from utils.settings import get_settings
from utils.styles import default_styles

# The languages a recording can be transcribed in, as the Windows language ids
# RTF marks text with, so a word processor checks the spelling in the right
# language whatever its own is set to, and a screen reader reads it with the
# right voice. Every language Whisper names (its LANGUAGES, and the other
# names it takes for some of them, TO_LANGUAGE_CODE) and the Sámi languages of
# Sweden, so that opening a language in settings.WHISPER_LANGUAGES needs no
# change here. The names are what a job's language is called, lower case and
# without accents or a "(...)" after it (rtf_language).
#
# A name only names a language, so where it has variants one is chosen: the
# language as written where it is mostly spoken or in Europe -- British
# English, Norwegian Bokmål (Nynorsk is a name of its own), European Spanish
# and Portuguese, Mainland Chinese for Chinese and Mandarin and Hong Kong for
# Cantonese, Serbian, Bosnian, Azerbaijani, Uzbek and Hausa in the Latin
# script, and the Sámi languages as written in Sweden. Six languages Whisper
# knows have no Windows id -- Shona, Haitian Creole, Malagasy, Lingala,
# Javanese and Sundanese -- and are left unmarked, like any name not here.
RTF_LANGUAGES = {
    "afrikaans": 1078,  # af-ZA
    "albanian": 1052,  # sq-AL
    "amharic": 1118,  # am-ET
    "arabic": 1025,  # ar-SA
    "armenian": 1067,  # hy-AM
    "assamese": 1101,  # as-IN
    "azerbaijani": 1068,  # az-Latn-AZ
    "bashkir": 1133,  # ba-RU
    "basque": 1069,  # eu-ES
    "belarusian": 1059,  # be-BY
    "bengali": 2117,  # bn-BD
    "bosnian": 5146,  # bs-Latn-BA
    "breton": 1150,  # br-FR
    "bulgarian": 1026,  # bg-BG
    "burmese": 1109,  # my-MM
    "cantonese": 3076,  # zh-HK
    "castilian": 3082,  # es-ES
    "catalan": 1027,  # ca-ES
    "chinese": 2052,  # zh-CN
    "croatian": 1050,  # hr-HR
    "czech": 1029,  # cs-CZ
    "danish": 1030,  # da-DK
    "dutch": 1043,  # nl-NL
    "english": 2057,  # en-GB
    "estonian": 1061,  # et-EE
    "faroese": 1080,  # fo-FO
    "finnish": 1035,  # fi-FI
    "flemish": 1043,  # nl-NL
    "french": 1036,  # fr-FR
    "galician": 1110,  # gl-ES
    "georgian": 1079,  # ka-GE
    "german": 1031,  # de-DE
    "greek": 1032,  # el-GR
    "gujarati": 1095,  # gu-IN
    "hausa": 1128,  # ha-Latn-NG
    "hawaiian": 1141,  # haw-US
    "hebrew": 1037,  # he-IL
    "hindi": 1081,  # hi-IN
    "hungarian": 1038,  # hu-HU
    "icelandic": 1039,  # is-IS
    "indonesian": 1057,  # id-ID
    "italian": 1040,  # it-IT
    "japanese": 1041,  # ja-JP
    "kannada": 1099,  # kn-IN
    "kazakh": 1087,  # kk-KZ
    "khmer": 1107,  # km-KH
    "korean": 1042,  # ko-KR
    "lao": 1108,  # lo-LA
    "latin": 1142,  # la-VA
    "latvian": 1062,  # lv-LV
    "letzeburgesch": 1134,  # lb-LU
    "lithuanian": 1063,  # lt-LT
    "lule sami": 5179,  # smj-SE
    "luxembourgish": 1134,  # lb-LU
    "macedonian": 1071,  # mk-MK
    "malay": 1086,  # ms-MY
    "malayalam": 1100,  # ml-IN
    "maltese": 1082,  # mt-MT
    "mandarin": 2052,  # zh-CN
    "maori": 1153,  # mi-NZ
    "marathi": 1102,  # mr-IN
    "moldavian": 1048,  # ro-RO
    "moldovan": 1048,  # ro-RO
    "mongolian": 1104,  # mn-MN
    "myanmar": 1109,  # my-MM
    "nepali": 1121,  # ne-NP
    "northern sami": 2107,  # se-SE
    "norwegian": 1044,  # nb-NO
    "nynorsk": 2068,  # nn-NO
    "occitan": 1154,  # oc-FR
    "panjabi": 1094,  # pa-IN
    "pashto": 1123,  # ps-AF
    "persian": 1065,  # fa-IR
    "polish": 1045,  # pl-PL
    "portuguese": 2070,  # pt-PT
    "punjabi": 1094,  # pa-IN
    "pushto": 1123,  # ps-AF
    "romanian": 1048,  # ro-RO
    "russian": 1049,  # ru-RU
    "sanskrit": 1103,  # sa-IN
    "serbian": 9242,  # sr-Latn-RS
    "sindhi": 2137,  # sd-Arab-PK
    "sinhala": 1115,  # si-LK
    "sinhalese": 1115,  # si-LK
    "slovak": 1051,  # sk-SK
    "slovenian": 1060,  # sl-SI
    "somali": 1143,  # so-SO
    "southern sami": 7227,  # sma-SE
    "spanish": 3082,  # es-ES
    "swahili": 1089,  # sw-KE
    "swedish": 1053,  # sv-SE
    "tagalog": 1124,  # fil-PH
    "tajik": 1064,  # tg-Cyrl-TJ
    "tamil": 1097,  # ta-IN
    "tatar": 1092,  # tt-RU
    "telugu": 1098,  # te-IN
    "thai": 1054,  # th-TH
    "tibetan": 1105,  # bo-CN
    "turkish": 1055,  # tr-TR
    "turkmen": 1090,  # tk-TM
    "ukrainian": 1058,  # uk-UA
    "urdu": 1056,  # ur-PK
    "uzbek": 1091,  # uz-Latn-UZ
    "valencian": 2051,  # ca-ES-valencia
    "vietnamese": 1066,  # vi-VN
    "welsh": 1106,  # cy-GB
    "yiddish": 1085,  # yi
    "yoruba": 1130,  # yo-NG
}

# British English, for what Scribe itself writes into an export: the key to
# the markings, and the names it gives a speaker it knows nothing about.
RTF_ENGLISH = 2057

# The names Scribe gives speakers itself ("Speaker 2", "SPEAKER_01",
# "UNKNOWN"), as opposed to a name the reader gave one.
DEFAULT_SPEAKER = re.compile(r"(speaker[ _]?\d+|unknown)", re.IGNORECASE)

# The colours an export with markings uses, by their place in the table:
# 1 the highlighter (pure yellow, Word's own), 2 the teal of a changed word,
# 3 the violet of an uncertain word (the editor's --color-review-accent),
# 4 the grey of the key. On white, 2 is 5.3:1, 3 5.7:1 and 4 6.4:1; on the
# yellow, 2 is 4.9:1 and 3 5.3:1.
RTF_COLOURS = (
    r"{\colortbl;\red255\green255\blue0;\red18\green121\blue106;"
    r"\red109\green81\blue201;\red95\green95\blue95;}"
)

# How each mark is written. A changed and an uncertain word each carry a named
# character style, so a reader can see what a word is marked for and find, or
# clear, every one of them at once; the formatting is repeated beside the
# style, as RTF has it. A highlight is the word processor's own highlighter,
# which a style cannot hold -- and so a word has at most one style: changed and
# uncertain never go together (see marked_spans).
RTF_HIGHLIGHT = r"\highlight1"
RTF_EDIT = r"\cs11\cf2\ul"
RTF_UNCERTAIN = r"\cs12\cf3\uld"

RTF_SENSITIVITY_NAMES = {"low": "Low", "medium": "Medium", "high": "High"}

# The export's choice of them, Off first: an export carries no mark unless it
# is asked to.
RTF_UNCERTAIN_OPTIONS = {"off": "Off", **RTF_SENSITIVITY_NAMES}


def rtf_language(name: Optional[str]) -> Optional[int]:
    """
    The RTF language id for a language as the job names it, or None.
    "Northern Sámi (Experimental)" is Northern Sámi.
    """

    if not isinstance(name, str):
        return None

    plain = unicodedata.normalize("NFD", name)
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    plain = plain.split("(")[0].strip().lower()

    return RTF_LANGUAGES.get(plain)


def rtf_text(text: str) -> str:
    """
    Text as RTF: the three characters RTF keeps for itself escaped, and
    everything outside ASCII as a Unicode escape (two, for a character
    outside the Basic Multilingual Plane).
    """

    result = []

    for ch in text:
        code = ord(ch)

        if code < 128:
            result.append("\\" + ch if ch in "\\{}" else ch)
        elif code <= 0xFFFF:
            # BMP character - use signed 16-bit representation
            signed_code = code if code <= 0x7FFF else code - 0x10000
            result.append(f"\\u{signed_code}?")
        else:
            # Supplementary character (outside BMP) - use UTF-16 surrogate pair
            code -= 0x10000
            high_surrogate = 0xD800 + (code >> 10)
            low_surrogate = 0xDC00 + (code & 0x3FF)
            # Surrogates are always > 0x7FFF, convert to signed
            result.append(
                f"\\u{high_surrogate - 0x10000}?\\u{low_surrogate - 0x10000}?"
            )

    return "".join(result)


def rtf_key(found: dict, sensitivity: Optional[str]) -> str:
    """
    The key to the markings, put first in an export that has any: what each
    kind of mark looks like and what it means, for the kinds that are in this
    file and no others. In English, and marked as English, like the rest of
    what Scribe writes; a paragraph of its own, in a style of its own ("Scribe:
    Export key"), with a rule under it, so it can be told from the transcript
    and taken out of it. The samples are drawn with the formatting alone, not
    the styles, so that finding every word in a style finds the transcript's.
    """

    lines = []

    if found["highlight"]:
        lines.append(
            "{" + RTF_HIGHLIGHT + " Yellow highlight}"
            + rtf_text(" \u2013 your highlights.")
        )

    if found["edit"]:
        lines.append(
            r"{\cf2\ul Teal, underlined}"
            + rtf_text(
                f" \u2013 words you changed (character style \u201c{RTF_COMMENT_AUTHOR}: My edit\u201d)."
            )
        )

    if found["uncertain"]:
        level = RTF_SENSITIVITY_NAMES.get(sensitivity, "")
        lines.append(
            r"{\cf3\uld Violet, dotted underline}"
            + rtf_text(
                " \u2013 words the speech recognition was less sure of, at "
                f"sensitivity {level} (character style \u201c{RTF_COMMENT_AUTHOR}: Uncertain "
                "word\u201d)."
            )
        )

    if found["comment"]:
        lines.append(
            rtf_text("Comments in the margin \u2013 your comments.")
        )

    if found["edit"] or found["uncertain"]:
        lines.append(
            rtf_text(
                "A character style can be found, or removed everywhere at once, "
                "from the document\u2019s styles."
            )
        )

    return (
        rf"\pard\plain\s1\f0\fs18\cf4\lang{RTF_ENGLISH}\brdrb\brdrs\brdrw10\brsp80 "
        r"{\b Markings in this export}\line "
        + r"\line ".join(lines)
        + r"\par"
    )


def rtf_stylesheet(found: dict, language: Optional[int]) -> str:
    """
    The styles an export with markings uses: the transcript's own paragraph,
    the key's, and a character style for each kind of mark that has one and
    is in the file. Each gives its font and size, or a word processor draws a
    word in the style in its own default (LibreOffice did).
    """

    lang = rf"\lang{language}" if language else ""
    # The styles are the service's, named for it as the comments' author is.
    service = rtf_text(RTF_COMMENT_AUTHOR)
    styles = [
        rf"{{\s0\f0\fs20{lang} Normal;}}",
        rf"{{\s1\sbasedon0\f0\fs18\cf4\lang{RTF_ENGLISH} {service}: Export key;}}",
        r"{\*\cs10\additive Default Paragraph Font;}",
    ]

    if found["edit"]:
        styles.append(rf"{{\*\cs11\additive\sbasedon10\f0\fs20\cf2\ul {service}: My edit;}}")

    if found["uncertain"]:
        styles.append(rf"{{\*\cs12\additive\sbasedon10\f0\fs20\cf3\uld {service}: Uncertain word;}}")

    return r"{\stylesheet" + "".join(styles) + "}"


# Who a comment in an exported document is from. It is "Scribe" on purpose, not
# the reader's username: the editor could get that (utils/token.get_user_info),
# but it would put a personal identifier into every exported file, and the
# document is only ever the reader's own, so there is no one to tell apart.
settings = get_settings()

RTF_COMMENT_AUTHOR = settings.SERVICE_NAME
RTF_COMMENT_INITIALS = settings.SERVICE_INITIALS



def download_originals(originals: list[tuple[str, str]]) -> None:
    """
    Download the originals in `originals` ((filename, uuid) pairs): one on
    its own, streamed through ORIGINAL_PREFIX (the backend's own
    Content-Disposition names it), several as one ZIP -- more than one file
    is always a ZIP, built as it is sent (utils/export_zip.py) so no
    original is held here whole.
    """

    if len(originals) == 1:
        uuid = originals[0][1]
        ui.download.from_url(f"{ORIGINAL_PREFIX}/{quote(uuid, safe='')}")
        return

    link = prepare_zip("recordings.zip", [], originals)
    if link is None:
        ui.notify("Sign in again to download.", type="negative")
        return

    ui.download.from_url(link)


def originals_label(originals: list[tuple[str, str]]) -> str:
    """The wording of the option, for one recording or several."""

    if len(originals) == 1:
        return "Include the original recording"

    return f"Include the original recordings ({len(originals)})"


def show_originals_dialog(originals: list[tuple[str, str]]) -> None:
    """
    Export for a selection with recordings in it and nothing transcribed:
    the originals are all there is to export.
    """

    with ui.dialog().props('aria-label="Download original recordings"') as dialog:

        def _close_and_delete() -> None:
            dialog.close()
            dialog.delete()

        with ui.card().classes("p-6").style(
            "min-width: min(480px, 100%); background-color: var(--color-bg-surface-alt);"
        ):
            with ui.row().classes("w-full items-center justify-between no-wrap"):
                ui.label(
                    "Download original recording"
                    if len(originals) == 1
                    else "Download original recordings"
                ).classes("text-h5 font-bold")
                ui.button(icon="close", on_click=_close_and_delete).props(
                    "flat round dense color=grey-7 aria-label='Close'"
                )

            ui.label(
                "None of the selected files is transcribed yet. The original "
                "recording is downloaded exactly as it was recorded."
            ).classes("text-body2")

            with ui.column().classes("gap-1 w-full"):
                for name, _ in originals:
                    with ui.row().classes("items-center no-wrap gap-2"):
                        ui.icon("mic", size="18px").props('aria-hidden="true"')
                        ui.label(name).classes("text-body1").style(
                            "overflow-wrap: anywhere;"
                        )

            if len(originals) > 1:
                ui.label(
                    "The recordings are downloaded together as one ZIP file."
                ).classes("text-caption").style("color: var(--color-text-muted);")

            def download() -> None:
                download_originals(originals)
                _close_and_delete()

            async def to_drive() -> None:
                # Closed only afterwards: the Drive dialogs are opened from
                # inside this one, and Quasar does not draw the contents of
                # a dialog that is closed.
                await save_to_drive([], originals)
                _close_and_delete()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Close", on_click=_close_and_delete).props(
                    "outline color=black"
                )
                # Save to Sunet Drive, as in the full export dialog: hidden
                # until the backend says Drive is offered to this reader.
                drive_button = (
                    ui.button("Save to Drive", icon="cloud_upload", on_click=to_drive)
                    .props("flat color=black")
                    .classes("default-style")
                )
                drive_button.set_visibility(False)
                ui.button("Download", icon="download", on_click=download).props(
                    "flat color=white"
                ).classes("button-default-style")

            async def show_drive() -> None:
                status = await drive_status()
                if status.ok and status.result.get("enabled"):
                    drive_button.set_text(
                        f"Save to {drive_display_name(status.result)}"
                    )
                    drive_button.set_visibility(True)

            ui.timer(0.0, show_drive, once=True)

    dialog.open()

class ExportMixin:
    """
    Export formats and the export dialog.
    """

    def rtf_marks_available(self, others: list | None = None) -> tuple:
        """
        Whether there is anything for the RTF export to carry: (highlights,
        changed words). Looked at across this editor and any others exported
        along with it, so a bulk export offers a choice if any file has one.

        Transcriptions only, for now: a set of subtitles does not carry its
        marks into an export.
        """

        editors = [self] + list(others or [])
        captions = [
            caption
            for editor in editors
            if editor.data_format != "srt"
            for caption in editor.captions
        ]

        return (
            any(caption.highlighted_words for caption in captions),
            any(caption.edited_words for caption in captions),
        )

    def rtf_uncertain_available(self, others: list | None = None) -> bool:
        """
        Whether uncertain words can be marked in the export: some
        transcription in it has the scores the editor flags them by. A bulk
        export fetches no word data, so there it is not offered.
        """

        return any(
            editor.has_confidence
            for editor in [self] + list(others or [])
            if editor.data_format != "srt"
        )

    def rtf_comments_available(self, others: list | None = None) -> bool:
        """
        Whether any caption in this editor, or in the others exported along
        with it, has a comment for the RTF export to carry. Transcriptions
        only, for now.
        """

        return any(
            caption.comments
            for editor in [self] + list(others or [])
            if editor.data_format != "srt"
            for caption in editor.captions
        )

    @staticmethod
    def rtf_date(moment: datetime) -> int:
        """
        A moment in the packed form RTF keeps an annotation's date in: minute,
        hour, day, month, years since 1900 and day of the week, in the bits of
        one number.
        """

        weekday = (moment.weekday() + 1) % 7

        return (
            moment.minute
            | (moment.hour << 6)
            | (moment.day << 11)
            | (moment.month << 16)
            | ((moment.year - 1900) << 20)
            | (weekday << 29)
        )

    def comment_ranges(self, caption) -> list:
        """
        The caption's comments as (start, end, text), the offsets counted in
        the caption's text, in the order they occur.
        """

        ranges = []

        for comment in caption.comments:
            span = self.word_range(caption.text, min(comment.words), max(comment.words))

            if span is not None:
                ranges.append((span[0], span[1], comment.text))

        return sorted(ranges)

    def export_rtf(
        self,
        speakers: bool,
        times: bool,
        block_nr: bool,
        ts_which: str = "both",
        ts_fmt: str = "srt",
        highlights: bool = False,
        edits: bool = False,
        comments: bool = False,
        uncertain: Optional[str] = None,
    ) -> str:
        """
        Export captions to RTF format with proper Unicode handling.

        `highlights` carries the reader's highlights as the word processor's
        own yellow highlighter, and `edits` the words they changed, underlined
        and in the teal of the editor's own marking -- underlined as well
        because a printout may have no colour. `uncertain` is a sensitivity
        ("low", "medium", "high"): the words the speech recognition was less
        sure of at it, violet with a dotted underline, as the editor would flag
        them there; a changed word is never one (see marked_spans). All are off
        by default, which is the clean transcript: nothing about the text
        itself changes either way.

        `comments` carries the reader's comments as Word comments on the words
        they are on. Off by default for the same reason.

        An export with any of them starts with a key to them, for the kinds
        that are in it and no others (rtf_key). The text is marked with the
        language it was transcribed in when that is known (self.language,
        rtf_language()), with the lines that say who speaks when left out of
        the spelling check; without a language nothing is marked, and a clean
        export is what it always was.

        Transcriptions only, for now: subtitles never carry the marks.
        """

        if self.data_format == "srt":
            highlights = edits = comments = False
            uncertain = None

        if uncertain not in RTF_SENSITIVITY_NAMES or not self.has_confidence:
            uncertain = None

        language = rtf_language(self.language)

        # One date for the whole export: every comment was made before it.
        stamp = self.rtf_date(datetime.now())
        note_count = 0
        found = {"highlight": False, "edit": False, "uncertain": False, "comment": False}

        def fmt_ts(ts: str, f: str) -> str:
            """
            Format timestamp according to selected format.
            """
            p = ts.replace(",", ":").split(":")
            h, m, s, ms = int(p[0]), int(p[1]), int(p[2]), int(p[3])
            if f == "seconds":
                return f"{h*3600 + m*60 + s + ms/1000:.3f}"
            if f == "ms":
                return str(h * 3600000 + m * 60000 + s * 1000 + ms)
            if f == "vtt":
                return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
            return ts

        to_rtf_unicode = rtf_text

        parts = []

        for caption in self.captions:
            header_parts = []
            if block_nr:
                header_parts.append(to_rtf_unicode(f"[{caption.index}]"))

            if times:
                ts_parts = []
                if ts_which in ["start", "both"]:
                    ts_parts.append(fmt_ts(caption.start_time, ts_fmt))
                if ts_which in ["end", "both"]:
                    ts_parts.append(fmt_ts(caption.end_time, ts_fmt))
                if ts_parts:
                    header_parts.append(to_rtf_unicode(f"({' - '.join(ts_parts)})"))

            if speakers:
                name = to_rtf_unicode(f"{caption.speaker}:")

                # A name Scribe gave ("Speaker 2") is English, whatever the
                # recording is in, and is read out as such.
                if language and DEFAULT_SPEAKER.fullmatch(caption.speaker.strip()):
                    name = rf"{{\lang{RTF_ENGLISH} {name}}}"

                header_parts.append(name)

            # Build RTF data with consistent bold formatting for header. In a
            # text marked with its language the header is left out of the
            # spelling check: numbers, times and names, nothing to correct.
            rtf_data = ""
            if header_parts:
                if language:
                    rtf_data = r"{\b\noproof " + " ".join(header_parts) + r"}\line "
                else:
                    rtf_data = r"\b " + " ".join(header_parts) + r"\b0\line "

            # A comment is anchored by a start and an end marker round the
            # words it is on, and its text follows the end. The pieces are cut
            # where a comment begins or ends, so a marker never lands inside
            # one -- the text between the markers is the caption's own text
            # throughout.
            notes = self.comment_ranges(caption) if comments else []
            numbers = {}

            for note in notes:
                numbers[note] = note_count
                note_count += 1

            cuts = sorted({edge for start, end, _ in notes for edge in (start, end)})
            offset = 0

            for text, highlighted, edited, doubtful in self.marked_spans(
                caption, highlights, edits, uncertain
            ):
                cut_at = [cut - offset for cut in cuts if 0 < cut - offset < len(text)]
                segments = [
                    text[first:last]
                    for first, last in zip([0] + cut_at, cut_at + [len(text)])
                ]

                for segment in segments:
                    here, there = offset, offset + len(segment)
                    offset = there

                    for note in notes:
                        if note[0] == here:
                            rtf_data += r"{\*\atrfstart %d}" % numbers[note]

                    body = to_rtf_unicode(segment).replace("\n", r"\line ")

                    if highlighted or edited or doubtful:
                        # A group, so the formatting ends with the piece. The
                        # one space after a control word is its delimiter and
                        # is not part of the text, so a piece that starts with
                        # a space keeps it.
                        style = (
                            (RTF_HIGHLIGHT if highlighted else "")
                            + (RTF_EDIT if edited else "")
                            + (RTF_UNCERTAIN if doubtful else "")
                        )
                        body = "{" + style + " " + body + "}"

                        found["highlight"] |= highlighted
                        found["edit"] |= edited
                        found["uncertain"] |= doubtful

                    rtf_data += body

                    for note in notes:
                        if note[1] == there:
                            found["comment"] = True
                            note_text = to_rtf_unicode(note[2]).replace(
                                "\n", r"\line "
                            )
                            rtf_data += (
                                r"{\*\atrfend %d}" % numbers[note]
                                + "{\\*\\atnid %s}{\\*\\atnauthor %s}\\chatn"
                                # Escaped like the text: a setting may
                                # hold "å" or a brace, which unescaped
                                # would garble the name or open a group.
                                % (to_rtf_unicode(RTF_COMMENT_INITIALS), to_rtf_unicode(RTF_COMMENT_AUTHOR))
                                + r"{\*\annotation{\*\atnref %d}{\*\atndate %d}"
                                % (numbers[note], stamp)
                                + r"\pard\plain\f0\fs20 "
                                + note_text
                                + "}"
                            )

            rtf_data += r"\line\line "

            parts.append(rtf_data)

        lang = rf"\lang{language}" if language else ""
        marked = any(found.values())

        # The colour table, the styles and the key only when there is a mark,
        # so a clean export is the document it always was.
        rtf_content = (
            r"{\rtf1\ansi\deff0"
            + (rf"\deflang{language}" if language else "")
            + r"{\fonttbl{\f0 Arial;}}"
            + (RTF_COLOURS + rtf_stylesheet(found, language) if marked else "")
            + r"\viewkind4\uc1"
        )

        if marked:
            rtf_content += (
                rtf_key(found, uncertain)
                + rf"\pard\plain\s0\f0\fs20{lang}\sb200 "
            )
        else:
            rtf_content += rf"\pard\f0\fs20{lang} "

        rtf_content += "".join(parts) + "}"

        return rtf_content


    def export_json(self) -> str:
        return {
            "segments": [seg.to_dict() for seg in self.captions],
            "speaker_count": len(self.speakers),
            "full_transcription": " ".join(seg.text for seg in self.captions),
            # These segments are the blocks the reader arranged, so they are to
            # be loaded as they are. Without this, parse_txt would merge
            # neighbouring blocks that share a speaker and re-capitalise the
            # text, undoing their edits on the next reload. Absent from
            # anything saved before this existed, and from the worker's own
            # output, both of which still want tidying on the way in.
            "preserve_segments": True,
        }


    def export_srt(self) -> str:
        """
        Export captions to SRT format.
        """

        return "\n\n".join(caption.to_srt_format() for caption in self.captions)


    def export_vtt(self) -> str:
        """
        Export captions to VTT format.
        """

        parts = ["WEBVTT\n\n"]
        for caption in self.captions:
            parts.append(f"{caption.index}\n")
            parts.append(
                f"{caption.start_time.replace(',', '.')} --> {caption.end_time.replace(',', '.')}\n"
            )
            parts.append(f"{caption.text}\n\n")
        return "".join(parts)


    def show_export_dialog(
        self,
        filename: str,
        bulk_editors: list | None = None,
        originals: list[tuple[str, str]] | None = None,
    ) -> None:
        """
        Show comprehensive export dialog with format options and live preview.
        When bulk_editors is provided (list of (filename, editor) tuples),
        the preview is skipped and files are exported as a zip archive.

        `originals` ((filename, uuid) pairs) are recordings whose original
        can be downloaded alongside -- transcribed or not, in a bulk export.
        Left out, a single export offers the open job's own original when it
        is a recording.
        """
        from pathlib import Path

        filename = sanitize_filename(filename)
        if bulk_editors:
            bulk_editors = [(sanitize_filename(fn), ed) for fn, ed in bulk_editors]

        is_bulk = bulk_editors is not None and len(bulk_editors) > 0
        if originals is None and not is_bulk and self.has_original:
            originals = [(filename, self.uuid)]
        originals = originals or []
        # Bulk export shows the same dialog as a single one, previewing the
        # first file -- subtitles included, which once got a narrow dialog
        # with no preview at all.
        bulk_needs_preview = is_bulk

        # Named for what is open: subtitles are captions, not a transcript.
        # A bulk export is one type, and this editor is its first file's.
        title = (
            "Export captions" if self.data_format == "srt" else "Export transcript"
        )

        ui.add_head_html(default_styles)
        with ui.dialog().props(f'aria-label="{title}"') as dialog:
            # A fresh ui.dialog() is built on every call (Ctrl+E is bound
            # straight to show_export_dialog), and closing one only hides
            # it -- the element stays in the DOM. Deleting it once closed
            # keeps that from piling up over a long editing session, the
            # same accumulation problem as the search dialog above it.
            def _close_and_delete() -> None:
                dialog.close()
                dialog.delete()

            card = (
                ui.card()
                .classes("p-6")
                .style(
                    # A fixed width, not a range the content settles in:
                    # with short captions the preview is narrow, and the
                    # dialog shrank to 1000px around it.
                    (
                        "width: min(1400px, 95vw); max-width: 95vw; "
                        if (not is_bulk or bulk_needs_preview)
                        else "min-width: min(500px, 95vw); max-width: min(700px, 95vw); "
                    )
                    + "max-height: 90vh; overflow-y: auto; "
                    "background-color: var(--color-bg-surface-alt);"
                )
            )
            with card:
                # Header
                with ui.row().classes("w-full items-center justify-between mb-4"):
                    ui.label(title).classes("text-h5 font-bold")
                    ui.button(icon="close", on_click=_close_and_delete).props(
                        "flat round dense color=grey-7 aria-label='Close export dialog'"
                    )

                ui.separator().classes("mb-4")

                if is_bulk:
                    ui.label(f"Exporting {len(bulk_editors)} file(s)").classes(
                        "text-body1 mb-2"
                    )

                # Two-column layout (single column for bulk srt/vtt)
                with ui.row().classes("w-full gap-6"):
                    # Left: Options (fixed width when preview shown)
                    with ui.column().classes("gap-4").style(
                        "flex: 0 0 400px; min-width: 0;"
                        if (not is_bulk or bulk_needs_preview)
                        else "width: 100%;"
                    ):
                        # A recording's original, first in the dialog: below
                        # the preview it had to be scrolled to.  Off by
                        # default: it is a large download nobody asked for by
                        # opening Export.
                        include_originals = None
                        if originals:
                            ui.label(
                                "Original recording"
                                if len(originals) == 1
                                else "Original recordings"
                            ).classes("text-subtitle1 font-semibold")
                            include_originals = ui.checkbox(
                                originals_label(originals), value=False
                            )
                            ui.label(
                                "Exactly as it was recorded, as a separate file."
                            ).classes("text-caption").style(
                                "color: var(--color-text-muted); margin-top: -8px;"
                            )
                            ui.separator()

                        # File format. The heading names the area; the select
                        # carries its own label, as the selects below it do,
                        # because a standalone heading is not tied to a select
                        # and Quasar puts aria-labelledby on the select's
                        # wrapper, not on its combobox input (WCAG 1.3.1,
                        # 4.1.2). The label says what the format applies to:
                        # the text only, never a recording's original, which
                        # is exported as it was recorded.
                        ui.label("File format").classes("text-subtitle1 font-semibold")
                        if self.data_format == "srt":
                            format_opts = {
                                "srt": "SubRip (.srt)",
                                "vtt": "WebVTT (.vtt)",
                            }
                        else:
                            format_opts = {
                                "txt": "Text (.txt)",
                                "json": "JSON (.json)",
                                "rtf": "RTF (.rtf)",
                                "csv": "CSV (.csv)",
                                "tsv": "TSV (.tsv)",
                            }

                        fmt = (
                            ui.select(
                                options=format_opts,
                                value=list(format_opts.keys())[0],
                                label=(
                                    "Caption format"
                                    if self.data_format == "srt"
                                    else "Transcript format"
                                ),
                            )
                            .classes("w-full")
                            .props("outlined dense")
                        )

                        ui.separator()

                        # Options container - will show/hide based on format
                        options_container = ui.column().classes("w-full gap-4")

                        with options_container:
                            # Timestamps (for txt, json, csv, tsv)
                            ts_section = ui.column().classes("w-full gap-2")
                            with ts_section:
                                ui.label("Timestamps").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                ts_incl = ui.checkbox("Include timestamps", value=True)

                                with ui.row().classes("w-full gap-2 items-center"):
                                    ts_which = (
                                        ui.select(
                                            options={
                                                "both": "Start & End",
                                                "start": "Start only",
                                                "end": "End only",
                                            },
                                            value="both",
                                            label="Timestamp range",
                                        )
                                        .classes("flex-1")
                                        .props("dense outlined")
                                    )
                                    ts_pos = (
                                        ui.select(
                                            options={
                                                "before": "Before text",
                                                "after": "After text",
                                            },
                                            value="before",
                                            label="Position",
                                        )
                                        .classes("flex-1")
                                        .props("dense outlined")
                                    )
                                    ts_pos.visible = False

                                ts_fmt = (
                                    ui.select(
                                        options={
                                            "srt": "SRT (00:00:00,000)",
                                            "vtt": "VTT (00:00:00.000)",
                                            "seconds": "Seconds (0.000)",
                                            "ms": "Milliseconds",
                                        },
                                        value="srt",
                                        label="Format",
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                ui.separator()

                            # Text options (for txt only)
                            txt_section = ui.column().classes("w-full gap-2")
                            with txt_section:
                                ui.label("Text options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                txt_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                txt_idx_incl = ui.checkbox(
                                    "Include paragraph numbers", value=False
                                )
                                txt_sep_type = (
                                    ui.select(
                                        options={
                                            "\\n\\n": "Double newline",
                                            "\\n": "Single newline",
                                            "---": "Line",
                                            "custom": "Custom",
                                        },
                                        value="\\n\\n",
                                        label="Separator",
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                txt_sep_custom = (
                                    ui.input(placeholder="Custom separator")
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                txt_sep_custom.visible = False
                                txt_sep_type.on(
                                    "update:model-value",
                                    lambda e: setattr(
                                        txt_sep_custom, "visible", e.args == "custom"
                                    ),
                                )
                                ui.separator()

                            # RTF options
                            rtf_section = ui.column().classes("w-full gap-2")
                            with rtf_section:
                                ui.label("RTF Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                rtf_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                rtf_idx_incl = ui.checkbox(
                                    "Include paragraph numbers", value=False
                                )
                                # Off by default: an export is clean unless
                                # it is asked to carry the marks. And only
                                # offered for a kind of mark that exists in
                                # what is being exported -- a choice about
                                # nothing is just clutter. Transcriptions
                                # only, for now (see rtf_marks_available).
                                has_highlights, has_edits = self.rtf_marks_available(
                                    [editor for _, editor in bulk_editors or []]
                                )
                                rtf_hl_incl = ui.checkbox(
                                    "Include highlights", value=False
                                )
                                rtf_hl_incl.set_visibility(has_highlights)
                                rtf_edits_incl = ui.checkbox(
                                    "Include my edits (underlined)", value=False
                                )
                                rtf_edits_incl.set_visibility(has_edits)
                                rtf_comments_incl = ui.checkbox(
                                    "Include comments", value=False
                                )
                                rtf_comments_incl.set_visibility(
                                    self.rtf_comments_available(
                                        [editor for _, editor in bulk_editors or []]
                                    )
                                )
                                # Uncertain words at a sensitivity of the
                                # reader's choosing -- the editor's own
                                # levels -- and Off unless asked for. Only
                                # where there are word scores to go on.
                                rtf_uncertain = (
                                    ui.select(
                                        options=RTF_UNCERTAIN_OPTIONS,
                                        value="off",
                                        label="Include uncertain words",
                                    )
                                    .classes("w-full")
                                    .props("outlined dense")
                                )
                                rtf_uncertain.set_visibility(
                                    self.rtf_uncertain_available(
                                        [editor for _, editor in bulk_editors or []]
                                    )
                                )
                                ui.separator()

                            # CSV options (for csv only)
                            csv_section = ui.column().classes("w-full gap-2")
                            with csv_section:
                                ui.label("CSV Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                csv_hdr = ui.checkbox("Include header row", value=True)
                                csv_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                csv_qt = (
                                    ui.input(label="Quote character", value='"')
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                csv_delim = (
                                    ui.input(label="Delimiter", value=",")
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                ui.separator()

                            # TSV options (for tsv only)
                            tsv_section = ui.column().classes("w-full gap-2")
                            with tsv_section:
                                ui.label("TSV Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                tsv_hdr = ui.checkbox("Include header row", value=True)
                                tsv_spk_incl = ui.checkbox(
                                    "Include speakers", value=True
                                )
                                tsv_tab_type = (
                                    ui.select(
                                        options={
                                            "\\t": "Real tab character",
                                            "spaces": "Spaces",
                                        },
                                        value="\\t",
                                        label="Tab type",
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                tsv_tab_width = (
                                    ui.number(
                                        label="Tab width (spaces)",
                                        value=4,
                                        min=1,
                                        max=16,
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                tsv_tab_width.visible = False
                                tsv_tab_type.on(
                                    "update:model-value",
                                    lambda e: setattr(
                                        tsv_tab_width, "visible", e.args == "spaces"
                                    ),
                                )
                                ui.separator()

                            # JSON options (for json only)
                            json_section = ui.column().classes("w-full gap-2")
                            with json_section:
                                ui.label("JSON Options").classes(
                                    "text-subtitle1 font-semibold"
                                )
                                json_indent = (
                                    ui.number(
                                        label="Indentation spaces",
                                        value=2,
                                        min=0,
                                        max=8,
                                    )
                                    .classes("w-full mt-2")
                                    .props("dense outlined")
                                )
                                json_ascii = ui.checkbox(
                                    "Escape non-ASCII characters", value=False
                                )
                                ui.separator()

                        def update_options_visibility():
                            """
                            Show/hide options based on selected format
                            """
                            current_fmt = fmt.value

                            # SRT/VTT - no options
                            ts_section.visible = current_fmt in [
                                "txt",
                                "json",
                                "csv",
                                "tsv",
                                "rtf",
                            ]
                            txt_section.visible = current_fmt == "txt"
                            csv_section.visible = current_fmt == "csv"
                            tsv_section.visible = current_fmt == "tsv"
                            json_section.visible = current_fmt == "json"
                            rtf_section.visible = current_fmt == "rtf"

                        fmt.on(
                            "update:model-value", lambda: update_options_visibility()
                        )

                    # Right: Preview (60%) - show for single mode and bulk txt formats
                    show_preview = not is_bulk or bulk_needs_preview
                    if show_preview:
                        preview_col = ui.column().classes("flex-1")
                        with preview_col:
                            if bulk_needs_preview:
                                first_fn = (
                                    bulk_editors[0][0] if bulk_editors else filename
                                )
                                ui.label("Preview").classes(
                                    "text-subtitle1 font-semibold mb-2"
                                ).tooltip(f"Showing: {first_fn}")
                            else:
                                ui.label("Preview").classes(
                                    "text-subtitle1 font-semibold mb-2"
                                )
                            with ui.card().classes("w-full bg-gray-900 p-4").style(
                                "height: 550px; overflow-y: auto;"
                            ):
                                prev = (
                                    ui.html("", sanitize=False)
                                    .classes("text-white")
                                    .style(
                                        "font-family: 'Courier New', monospace; font-size: 13px; white-space: pre-wrap;"
                                    )
                                )
                            cnt_lbl = ui.label("").classes("text-caption mt-2")
                            # The preview's count changes as options change
                            # (WCAG 4.1.3).
                            cnt_lbl.props("role=status aria-live=polite")

                update_options_visibility()

                if show_preview:

                    def upd_prev():
                        try:
                            caps = self.captions[:5]
                            out = ""

                            def fmt_ts(ts, f):
                                p = ts.replace(",", ":").split(":")
                                h, m, s, ms = int(p[0]), int(p[1]), int(p[2]), int(p[3])
                                if f == "seconds":
                                    return f"{h*3600 + m*60 + s + ms/1000:.3f}"
                                if f == "ms":
                                    return str(h * 3600000 + m * 60000 + s * 1000 + ms)
                                if f == "vtt":
                                    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
                                return ts  # srt format

                            def build_ts_str(cap):
                                """
                                Build timestamp string based on options
                                """
                                if not ts_incl.value:
                                    return ""
                                parts = []
                                if ts_which.value in ["start", "both"]:
                                    parts.append(fmt_ts(cap.start_time, ts_fmt.value))
                                if ts_which.value in ["end", "both"]:
                                    parts.append(fmt_ts(cap.end_time, ts_fmt.value))
                                return " - ".join(parts) if parts else ""

                            match fmt.value:
                                case "srt":
                                    out = "\n\n".join(c.to_srt_format() for c in caps)
                                case "vtt":
                                    out = "WEBVTT\n\n" + "\n\n".join(
                                        f"{c.index}\n{c.start_time.replace(',','.')} --> {c.end_time.replace(',','.')}\n{c.text}"
                                        for c in caps
                                    )
                                case "txt":
                                    parts = []
                                    for c in caps:
                                        p_parts = []
                                        if txt_idx_incl and txt_idx_incl.value:
                                            p_parts.append(f"[{c.index}]")

                                        ts_str = build_ts_str(c)
                                        if ts_str and ts_pos.value == "before":
                                            p_parts.append(f"({ts_str})")

                                        if txt_spk_incl and txt_spk_incl.value:
                                            p_parts.append(f"{c.speaker}:")

                                        # Add text on new line or same line
                                        if p_parts:
                                            p = " ".join(p_parts) + "\n" + c.text
                                        else:
                                            p = c.text

                                        if ts_str and ts_pos.value == "after":
                                            p += f"\n({ts_str})"

                                        parts.append(p)
                                    s = (
                                        txt_sep_custom.value
                                        if txt_sep_type.value == "custom"
                                        else txt_sep_type.value.replace("\\n", "\n")
                                    )
                                    out = s.join(parts)
                                case "rtf":
                                    parts = []
                                    for c in caps:
                                        p_parts = []
                                        if rtf_idx_incl and rtf_idx_incl.value:
                                            p_parts.append(f"[{c.index}]")

                                        ts_str = build_ts_str(c)
                                        if ts_str:
                                            p_parts.append(f"({ts_str})")

                                        if rtf_spk_incl and rtf_spk_incl.value:
                                            p_parts.append(f"{c.speaker}:")

                                        # Add text on new line or same line
                                        if p_parts:
                                            p = " ".join(p_parts) + "\n" + c.text
                                        else:
                                            p = c.text

                                        parts.append(p)
                                    out = "\n\n".join(parts)
                                case "json":
                                    d = {"total": len(self.captions), "captions": []}
                                    for c in caps:
                                        cd = {
                                            "index": c.index,
                                            "speaker": c.speaker,
                                            "text": c.text,
                                        }
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                cd["start"] = fmt_ts(
                                                    c.start_time, ts_fmt.value
                                                )
                                            if ts_which.value in ["end", "both"]:
                                                cd["end"] = fmt_ts(
                                                    c.end_time, ts_fmt.value
                                                )
                                        d["captions"].append(cd)
                                    out = json.dumps(
                                        d,
                                        indent=int(json_indent.value),
                                        ensure_ascii=json_ascii.value,
                                    )
                                case "csv":
                                    q = csv_qt.value
                                    delim = csv_delim.value
                                    lines = []
                                    if csv_hdr.value:
                                        h = ["index"]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                h.append("start")
                                            if ts_which.value in ["end", "both"]:
                                                h.append("end")
                                        if csv_spk_incl.value:
                                            h.append("speaker")
                                        h.append("text")
                                        lines.append(
                                            delim.join(f"{q}{x}{q}" for x in h)
                                        )
                                    for c in caps:
                                        r = [str(c.index)]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                r.append(
                                                    fmt_ts(c.start_time, ts_fmt.value)
                                                )
                                            if ts_which.value in ["end", "both"]:
                                                r.append(
                                                    fmt_ts(c.end_time, ts_fmt.value)
                                                )
                                        if csv_spk_incl.value:
                                            r.append(c.speaker)
                                        r.append(
                                            c.text.replace(q, q + q).replace("\n", " ")
                                        )
                                        lines.append(
                                            delim.join(f"{q}{x}{q}" for x in r)
                                        )
                                    out = "\n".join(lines)
                                case "tsv":
                                    # Determine tab character
                                    if tsv_tab_type.value == "\\t":
                                        tab_char = "\t"
                                    else:
                                        tab_char = " " * int(tsv_tab_width.value)

                                    lines = []
                                    if tsv_hdr.value:
                                        h = ["index"]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                h.append("start")
                                            if ts_which.value in ["end", "both"]:
                                                h.append("end")
                                        if tsv_spk_incl.value:
                                            h.append("speaker")
                                        h.append("text")
                                        lines.append(tab_char.join(h))
                                    for c in caps:
                                        r = [str(c.index)]
                                        if ts_incl.value:
                                            if ts_which.value in ["start", "both"]:
                                                r.append(
                                                    fmt_ts(c.start_time, ts_fmt.value)
                                                )
                                            if ts_which.value in ["end", "both"]:
                                                r.append(
                                                    fmt_ts(c.end_time, ts_fmt.value)
                                                )
                                        if tsv_spk_incl.value:
                                            r.append(c.speaker)
                                        r.append(
                                            c.text.replace("\t", "  ").replace(
                                                "\n", " "
                                            )
                                        )
                                        lines.append(tab_char.join(r))
                                    out = "\n".join(lines)
                                case "rtf":
                                    # Show RTF source code for preview
                                    parts = []
                                    for c in caps:
                                        parts.append(
                                            f"{c.speaker}: {c.start_time} - {c.end_time}"
                                        )
                                        parts.append(c.text.replace("\n", "\\line "))
                                        parts.append("")
                                    out = "\n".join(parts)
                                case _:
                                    out = "(RTF preview unavailable)"

                            if len(self.captions) > 5:
                                out += f"\n\n... {len(self.captions)-5} more captions"

                            import html

                            prev.set_content(html.escape(out).replace("\n", "<br>"))
                            cnt_lbl.set_text(
                                f"Total: {len(self.captions)} | Showing: {min(5, len(self.captions))}"
                            )
                        except Exception as e:
                            import html

                            prev.set_content(
                                f"<span style='color:#f88'>{html.escape(str(e))}</span>"
                            )

                    # Connect updates
                    for ctrl in [fmt, ts_incl, ts_fmt, ts_which, ts_pos]:
                        ctrl.on("update:model-value", lambda: upd_prev())

                    # CSV controls
                    csv_hdr.on("update:model-value", lambda: upd_prev())
                    csv_spk_incl.on("update:model-value", lambda: upd_prev())
                    csv_qt.on("blur", lambda: upd_prev())
                    csv_delim.on("blur", lambda: upd_prev())

                    # TSV controls
                    tsv_hdr.on("update:model-value", lambda: upd_prev())
                    tsv_spk_incl.on("update:model-value", lambda: upd_prev())
                    tsv_tab_type.on("update:model-value", lambda: upd_prev())
                    tsv_tab_width.on("blur", lambda: upd_prev())

                    # JSON controls
                    json_indent.on("blur", lambda: upd_prev())
                    json_ascii.on("update:model-value", lambda: upd_prev())

                    # TXT controls
                    txt_spk_incl.on("update:model-value", lambda: upd_prev())
                    txt_idx_incl.on("update:model-value", lambda: upd_prev())
                    txt_sep_type.on("update:model-value", lambda: upd_prev())
                    txt_sep_custom.on("blur", lambda: upd_prev())

                    # RTF controls
                    rtf_spk_incl.on("update:model-value", lambda: upd_prev())
                    rtf_idx_incl.on("update:model-value", lambda: upd_prev())

                    upd_prev()

                ui.separator().classes("my-4")

                # Footer
                with ui.row().classes("w-full justify-between items-center").style(
                    "position: sticky; bottom: -24px; background-color: inherit; padding-bottom: 8px; z-index: 1;"
                ):
                    if is_bulk:
                        ui.label("").bind_text_from(
                            fmt, "value", backward=lambda v: f"Format: .{v}"
                        ).classes("text-body2")
                    else:
                        ui.label(f"File: {Path(filename).stem}.{fmt.value}").classes(
                            "text-body2"
                        )
                    with ui.row().classes("gap-2"):
                        ui.button("Close", on_click=_close_and_delete).props(
                            "outline color=black"
                        )

                        async def exp(to_drive: bool = False):
                            try:

                                def fmt_ts(ts, f):
                                    p = ts.replace(",", ":").split(":")
                                    h, m, s, ms = (
                                        int(p[0]),
                                        int(p[1]),
                                        int(p[2]),
                                        int(p[3]),
                                    )
                                    if f == "seconds":
                                        return f"{h*3600 + m*60 + s + ms/1000:.3f}"
                                    if f == "ms":
                                        return str(
                                            h * 3600000 + m * 60000 + s * 1000 + ms
                                        )
                                    if f == "vtt":
                                        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
                                    return ts

                                def build_ts_str(cap):
                                    """
                                    Build timestamp string based on options
                                    """
                                    if not ts_incl.value:
                                        return ""
                                    parts = []
                                    if ts_which.value in ["start", "both"]:
                                        parts.append(
                                            fmt_ts(cap.start_time, ts_fmt.value)
                                        )
                                    if ts_which.value in ["end", "both"]:
                                        parts.append(fmt_ts(cap.end_time, ts_fmt.value))
                                    return " - ".join(parts) if parts else ""

                                def export_one(editor):
                                    """
                                    Export a single editor to string content.
                                    """
                                    c = None
                                    if fmt.value == "srt":
                                        c = editor.export_srt()
                                    elif fmt.value == "vtt":
                                        c = editor.export_vtt()
                                    elif fmt.value == "rtf":
                                        c = editor.export_rtf(
                                            rtf_spk_incl.value,
                                            ts_incl.value,
                                            rtf_idx_incl.value,
                                            ts_which.value,
                                            ts_fmt.value,
                                            highlights=bool(
                                                rtf_hl_incl.visible
                                                and rtf_hl_incl.value
                                            ),
                                            edits=bool(
                                                rtf_edits_incl.visible
                                                and rtf_edits_incl.value
                                            ),
                                            comments=bool(
                                                rtf_comments_incl.visible
                                                and rtf_comments_incl.value
                                            ),
                                            uncertain=(
                                                rtf_uncertain.value
                                                if rtf_uncertain.visible
                                                and rtf_uncertain.value != "off"
                                                else None
                                            ),
                                        )
                                    elif fmt.value == "txt":
                                        parts = []
                                        sep_str = "\n\n"
                                        if txt_sep_type.value == "custom":
                                            sep_str = txt_sep_custom.value.replace(
                                                "\\n", "\n"
                                            )
                                        elif txt_sep_type.value != "\\n\\n":
                                            sep_str = txt_sep_type.value.replace(
                                                "\\n", "\n"
                                            )

                                        for cap in editor.captions:
                                            p_parts = []
                                            if txt_idx_incl.value:
                                                p_parts.append(f"[{cap.index}]")

                                            ts_str = build_ts_str(cap)
                                            if ts_str and ts_pos.value == "before":
                                                p_parts.append(f"({ts_str})")

                                            if txt_spk_incl.value:
                                                p_parts.append(f"{cap.speaker}:")

                                            if p_parts:
                                                p = " ".join(p_parts) + "\n" + cap.text
                                            else:
                                                p = cap.text

                                            if ts_str and ts_pos.value == "after":
                                                p += f"\n({ts_str})"

                                            parts.append(p)
                                        c = sep_str.join(parts)
                                    elif fmt.value == "csv":
                                        q = csv_qt.value or '"'
                                        d = csv_delim.value or ","
                                        lines = []
                                        if csv_hdr.value:
                                            h = ["index"]
                                            if ts_incl.value:
                                                if ts_which.value in ["start", "both"]:
                                                    h.append("start")
                                                if ts_which.value in ["end", "both"]:
                                                    h.append("end")
                                            if csv_spk_incl.value:
                                                h.append("speaker")
                                            h.append("text")
                                            lines.append(
                                                d.join(f"{q}{x}{q}" for x in h)
                                            )
                                        for cap in editor.captions:
                                            r = [str(cap.index)]
                                            if ts_incl.value:
                                                if ts_which.value in ["start", "both"]:
                                                    r.append(
                                                        fmt_ts(
                                                            cap.start_time, ts_fmt.value
                                                        )
                                                    )
                                                if ts_which.value in ["end", "both"]:
                                                    r.append(
                                                        fmt_ts(
                                                            cap.end_time, ts_fmt.value
                                                        )
                                                    )
                                            if csv_spk_incl.value:
                                                r.append(cap.speaker)
                                            r.append(
                                                cap.text.replace(q, q + q).replace(
                                                    "\n", " "
                                                )
                                            )
                                            lines.append(
                                                d.join(f"{q}{x}{q}" for x in r)
                                            )
                                        c = "\n".join(lines)
                                    elif fmt.value == "tsv":
                                        if tsv_tab_type.value == "\\t":
                                            tab_char = "\t"
                                        else:
                                            tab_char = " " * int(tsv_tab_width.value)

                                        lines = []
                                        if tsv_hdr.value:
                                            h = ["index"]
                                            if ts_incl.value:
                                                if ts_which.value in ["start", "both"]:
                                                    h.append("start")
                                                if ts_which.value in ["end", "both"]:
                                                    h.append("end")
                                            if tsv_spk_incl.value:
                                                h.append("speaker")
                                            h.append("text")
                                            lines.append(tab_char.join(h))
                                        for cap in editor.captions:
                                            r = [str(cap.index)]
                                            if ts_incl.value:
                                                if ts_which.value in ["start", "both"]:
                                                    r.append(
                                                        fmt_ts(
                                                            cap.start_time, ts_fmt.value
                                                        )
                                                    )
                                                if ts_which.value in ["end", "both"]:
                                                    r.append(
                                                        fmt_ts(
                                                            cap.end_time, ts_fmt.value
                                                        )
                                                    )
                                            if tsv_spk_incl.value:
                                                r.append(cap.speaker)
                                            r.append(
                                                cap.text.replace("\t", "  ").replace(
                                                    "\n", " "
                                                )
                                            )
                                            lines.append(tab_char.join(r))
                                        c = "\n".join(lines)
                                    elif fmt.value == "json":
                                        data = editor.export_json()
                                        if ts_incl.value:
                                            for i, cap in enumerate(editor.captions):
                                                if i < len(data["segments"]):
                                                    seg = data["segments"][i]
                                                    if ts_which.value == "start":
                                                        seg["start"] = fmt_ts(
                                                            cap.start_time, ts_fmt.value
                                                        )
                                                        if "end" in seg:
                                                            del seg["end"]
                                                    elif ts_which.value == "end":
                                                        seg["end"] = fmt_ts(
                                                            cap.end_time, ts_fmt.value
                                                        )
                                                        if "start" in seg:
                                                            del seg["start"]
                                                    else:
                                                        seg["start"] = fmt_ts(
                                                            cap.start_time, ts_fmt.value
                                                        )
                                                        seg["end"] = fmt_ts(
                                                            cap.end_time, ts_fmt.value
                                                        )
                                        else:
                                            for seg in data["segments"]:
                                                if "start" in seg:
                                                    del seg["start"]
                                                if "end" in seg:
                                                    del seg["end"]

                                        indent = (
                                            int(json_indent.value)
                                            if json_indent.value
                                            else None
                                        )
                                        c = json.dumps(
                                            data,
                                            indent=indent,
                                            ensure_ascii=json_ascii.value,
                                        )
                                    return c

                                # One list of (name, content) for both
                                # destinations: a download zips it (or not,
                                # for one file); Drive takes each file as
                                # its own, which is what a folder is for.
                                chosen_fmt = fmt.value
                                if is_bulk:
                                    files = []
                                    seen_names = {}

                                    for bfn, beditor in bulk_editors:
                                        content = export_one(beditor)
                                        base_name = f"{Path(bfn).stem}.{chosen_fmt}"

                                        if base_name in seen_names:
                                            seen_names[base_name] += 1
                                            base_name = f"{Path(bfn).stem}_{seen_names[base_name]}.{chosen_fmt}"
                                        else:
                                            seen_names[base_name] = 0

                                        files.append((base_name, content.encode("utf-8")))
                                else:
                                    files = [
                                        (
                                            f"{Path(filename).stem}.{chosen_fmt}",
                                            export_one(self).encode("utf-8"),
                                        )
                                    ]
                            except Exception as e:
                                ui.notify(f"Export failed: {str(e)}", type="negative", timeout=None, close_button="Close")
                                return

                            if to_drive:
                                # The originals go too when the reader asked
                                # for them -- saved by the backend straight
                                # into Drive, decrypted on the way.
                                await save_to_drive(
                                    files,
                                    originals
                                    if include_originals is not None
                                    and include_originals.value
                                    else [],
                                )
                                return

                            chosen_originals = (
                                originals
                                if include_originals is not None
                                and include_originals.value
                                else []
                            )

                            # More than one file is always one ZIP, the
                            # originals in it too: streamed as it is written
                            # (utils/export_zip.py), so an hour of recording
                            # is never held here whole. One file is itself.
                            if len(files) + len(chosen_originals) > 1:
                                zip_name = (
                                    "bulk_export.zip"
                                    if is_bulk
                                    else f"{Path(filename).stem}.zip"
                                )
                                link = prepare_zip(zip_name, files, chosen_originals)
                                if link is None:
                                    ui.notify(
                                        "Sign in again to export.",
                                        type="negative",
                                    )
                                    return
                                ui.download.from_url(link)

                                ui.notify(
                                    f"Exported {len(files) + len(chosen_originals)} "
                                    "files as a ZIP",
                                    type="positive",
                                )
                            else:
                                ui.download(files[0][1], filename=files[0][0])

                                ui.notify(
                                    f"Exported as {chosen_fmt.upper()}",
                                    type="positive",
                                )

                        # Save to Sunet Drive (SUNET/scribe-backend#64):
                        # hidden until the backend says Drive is offered to
                        # this reader, and named as their organisation
                        # names it.
                        drive_button = (
                            ui.button(
                                "Save to Drive",
                                icon="cloud_upload",
                                on_click=lambda: exp(to_drive=True),
                            )
                            .props("flat color=black")
                            .classes("default-style")
                        )
                        drive_button.set_visibility(False)

                        async def show_drive() -> None:
                            status = await drive_status()
                            if status.ok and status.result.get("enabled"):
                                drive_button.set_text(
                                    f"Save to {drive_display_name(status.result)}"
                                )
                                drive_button.set_visibility(True)

                        ui.timer(0.0, show_drive, once=True)

                        ui.button("Download", icon="download", on_click=lambda: exp()).props(
                            "flat color=white"
                        ).classes("button-default-style")

            dialog.open()

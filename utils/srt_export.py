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

from nicegui import ui

from utils.helpers import sanitize_filename
from utils.settings import get_settings
from utils.styles import default_styles

settings = get_settings()


class ExportMixin:
    """
    Export formats and the export dialog.
    """

    def export_rtf(
        self,
        speakers: bool,
        times: bool,
        block_nr: bool,
        ts_which: str = "both",
        ts_fmt: str = "srt",
    ) -> str:
        """
        Export captions to RTF format with proper Unicode handling.
        """

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

        def to_rtf_unicode(text: str) -> str:
            result = []
            for ch in text:
                code = ord(ch)
                if code < 128:
                    if ch in ["\\", "{", "}"]:
                        result.append("\\" + ch)
                    else:
                        result.append(ch)
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

        rtf_content = (
            r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}" r"\viewkind4\uc1\pard\f0\fs20 "
        )

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
                header_parts.append(to_rtf_unicode(f"{caption.speaker}:"))

            # Build RTF data with consistent bold formatting for header
            rtf_data = ""
            if header_parts:
                rtf_data = r"\b " + " ".join(header_parts) + r"\b0\line "

            rtf_data += (
                to_rtf_unicode(caption.text).replace("\n", r"\line ") + r"\line\line "
            )

            parts.append(rtf_data)

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
        self, filename: str, bulk_editors: list | None = None
    ) -> None:
        """
        Show comprehensive export dialog with format options and live preview.
        When bulk_editors is provided (list of (filename, editor) tuples),
        the preview is skipped and files are exported as a zip archive.
        """
        import io
        import zipfile
        from pathlib import Path

        filename = sanitize_filename(filename)
        if bulk_editors:
            bulk_editors = [(sanitize_filename(fn), ed) for fn, ed in bulk_editors]

        is_bulk = bulk_editors is not None and len(bulk_editors) > 0
        # For bulk mode with txt formats: show preview using first file
        bulk_needs_preview = is_bulk and self.data_format == "txt"

        ui.add_head_html(default_styles)
        with ui.dialog().props('aria-label="Export transcript"') as dialog:
            card = (
                ui.card()
                .classes("p-6")
                .style(
                    f"min-width: {'1000' if (not is_bulk or bulk_needs_preview) else '500'}px; "
                    f"max-width: {'1400' if (not is_bulk or bulk_needs_preview) else '700'}px; "
                    "max-height: 90vh; overflow-y: auto; "
                    "background-color: var(--color-bg-surface-alt);"
                )
            )
            with card:
                # Header
                with ui.row().classes("w-full items-center justify-between mb-4"):
                    ui.label("Export transcript").classes("text-h5 font-bold")
                    ui.button(icon="close", on_click=dialog.close).props(
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
                        "flex: 0 0 400px;"
                        if (not is_bulk or bulk_needs_preview)
                        else "width: 100%;"
                    ):
                        # Format
                        ui.label("Format").classes("text-subtitle1 font-semibold")
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
                                options=format_opts, value=list(format_opts.keys())[0]
                            )
                            .classes("w-full")
                            .props("outlined dense")
                        )

                        ui.separator()

                        # Options container - will show/hide based on format
                        options_container = ui.column().classes("gap-4")

                        with options_container:
                            # Timestamps (for txt, json, csv, tsv)
                            ts_section = ui.column().classes("gap-2")
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
                            txt_section = ui.column().classes("gap-2")
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
                            rtf_section = ui.column().classes("gap-2")
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
                                ui.separator()

                            # CSV options (for csv only)
                            csv_section = ui.column().classes("gap-2")
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
                            tsv_section = ui.column().classes("gap-2")
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
                            json_section = ui.column().classes("gap-2")
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

                        bulk_preview_col = None

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

                            # In bulk mode, show/hide preview based on format
                            if bulk_needs_preview and bulk_preview_col is not None:
                                show_prev = current_fmt not in ["srt", "vtt"]
                                bulk_preview_col.visible = show_prev
                                # Resize dialog based on preview visibility
                                card.style(
                                    f"min-width: {'1000' if show_prev else '500'}px; "
                                    f"max-width: {'1400' if show_prev else '700'}px; "
                                    "background-color: var(--color-bg-surface);"
                                )

                        fmt.on(
                            "update:model-value", lambda: update_options_visibility()
                        )

                    # Right: Preview (60%) - show for single mode and bulk txt formats
                    show_preview = not is_bulk or bulk_needs_preview
                    if show_preview:
                        preview_col = ui.column().classes("flex-1")
                        if bulk_needs_preview:
                            bulk_preview_col = preview_col
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
                            with ui.card().classes("bg-gray-900 p-4").style(
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
                        ui.button("Close", on_click=dialog.close).props(
                            "outline color=black"
                        )

                        def exp():
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

                                if is_bulk:
                                    zip_buffer = io.BytesIO()
                                    chosen_fmt = fmt.value
                                    seen_names = {}

                                    with zipfile.ZipFile(
                                        zip_buffer, "w", zipfile.ZIP_DEFLATED
                                    ) as zf:
                                        for bfn, beditor in bulk_editors:
                                            content = export_one(beditor)
                                            base_name = f"{Path(bfn).stem}.{chosen_fmt}"

                                            if base_name in seen_names:
                                                seen_names[base_name] += 1
                                                base_name = f"{Path(bfn).stem}_{seen_names[base_name]}.{chosen_fmt}"
                                            else:
                                                seen_names[base_name] = 0

                                            zf.writestr(base_name, content)

                                    ui.download(
                                        zip_buffer.getvalue(),
                                        filename="bulk_export.zip",
                                    )

                                    ui.notify(
                                        f"Exported {len(bulk_editors)} files as {chosen_fmt.upper()}",
                                        type="positive",
                                    )
                                else:
                                    c = export_one(self)
                                    ui.download(
                                        c.encode("utf-8"),
                                        filename=f"{Path(filename).stem}.{fmt.value}",
                                    )

                                    ui.notify(
                                        f"Exported as {fmt.value.upper()}",
                                        type="positive",
                                    )
                            except Exception as e:
                                ui.notify(f"Export failed: {str(e)}", type="negative")

                        ui.button("Export", icon="download", on_click=exp).props(
                            "flat color=white"
                        ).classes("button-default-style")

            dialog.open()

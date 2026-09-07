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
A model's answer as a Word document.

Study notes and summaries are read and marked up somewhere else -- handed
in, pasted into a course page, worked over by somebody who does not have
Scribe open -- and .txt loses the shape of them while .md is a file most
readers cannot open. So: .docx, with the headings, lists and tables intact
and, above all, **the formulae still formulae** -- OMML equations Word can
draw, edit and search, rather than a picture or a line of raw LaTeX. That
conversion is `utils/omml.py`; this file is the document around it.

A .docx is a zip of XML, and it is written here by hand. python-docx would
be the obvious dependency, but it would have to be broken open for the
maths anyway (it has no idea what an equation is), it drags lxml -- a C
extension -- into the container for it, and the part of the format needed
here is small: a body, a stylesheet, and a numbering definition for the
lists.
"""

import re
import zipfile

from io import BytesIO
from xml.sax.saxutils import escape

from utils.markdown_blocks import (
    INLINE,
    MAX_HEADING,
    Block,
    emphasised,
    link_of,
    parse_markdown,
    plain,
    scripted,
)
from utils.omml import latex_to_omml

# What a list is marked with, one per level. Plain characters rather than
# Symbol's own code points, which need the font to be there to mean
# anything.
BULLETS = ("•", "◦", "▪")

# A twentieth of a point, which is what Word measures in.
HALF_POINT = 2

# How far one level of a list is indented, in twentieths of a point --
# 0.25 inch, Word's own step.
INDENT = 360


def _run(
    text: str,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    script: str = "",
) -> str:
    """
    One run of text in a paragraph.

    Parameters:
        text (str): What it says.
        bold (bool): Whether it is bold.
        italic (bool): Whether it is italic.
        code (bool): Whether it is set in a monospaced face.
        script (str): "subscript", "superscript", or "" for neither.

    Returns:
        str: The run, as WordprocessingML.
    """

    if not text:
        return ""

    # The order these are written in is the schema's, not ours: Word
    # refuses a file whose run properties are out of sequence.
    properties = ""

    if code:
        properties += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>'

    if bold:
        properties += "<w:b/>"

    if italic:
        properties += "<w:i/>"

    # Last, which is where the schema puts it.
    if script:
        properties += f'<w:vertAlign w:val="{script}"/>'

    if properties:
        properties = f"<w:rPr>{properties}</w:rPr>"

    # A soft break rather than a new paragraph: inside a code block the
    # lines are one thing, and Word keeps them together this way.
    body = "<w:br/>".join(
        f'<w:t xml:space="preserve">{escape(part)}</w:t>' for part in text.split("\n")
    )

    return f"<w:r>{properties}{body}</w:r>"


def inline_runs(text: str) -> str:
    """
    A line of Markdown as the runs and equations it is made of.

    Parameters:
        text (str): The line.

    Returns:
        str: WordprocessingML, ready to go inside a paragraph.
    """

    parts = []
    position = 0

    for match in INLINE.finditer(text):
        if before := text[position : match.start()]:
            parts.append(_run(plain(before)))

        found = match.lastgroup
        body = match.group()

        match found:
            case "code":
                parts.append(_run(body.strip("`"), code=True))
            case "display":
                parts.append(latex_to_omml(body[2:-2]))
            case "math":
                parts.append(latex_to_omml(body[1:-1]))
            case "sub":
                parts.append(_run(plain(scripted(body)), script="subscript"))
            case "sup":
                parts.append(_run(plain(scripted(body)), script="superscript"))
            case "bold":
                parts.append(_run(plain(emphasised(body)), bold=True))
            case "italic":
                parts.append(_run(plain(emphasised(body)), italic=True))
            case "line":
                parts.append(_run("\n"))
            case "tag":
                # Markup with nothing an export can do with it. Dropped
                # rather than printed: the tag itself is not what the
                # model meant to say.
                pass
            case "link":
                # The address is worth keeping and is not worth a
                # relationship of its own: a reader can see it and copy it.
                label, address = link_of(body)
                parts.append(_run(plain(label) or address))

                if label and label != address:
                    parts.append(_run(f" ({address})"))

        position = match.end()

    if rest := text[position:]:
        parts.append(_run(plain(rest)))

    return "".join(parts)


DISPLAY_ONLY = re.compile(r"^\s*\$\$(.+?)\$\$\s*$", re.DOTALL)


def _display(text: str) -> str:
    """
    A formula standing on a line of its own.

    Word has a paragraph-level equation for this, which is what centres it
    and gives it the room a displayed formula is written with; the same
    equation dropped in among runs is set inline, at the size of the text
    around it.

    Parameters:
        text (str): The paragraph's Markdown.

    Returns:
        str: The paragraph, or "" when it holds more than a formula.
    """

    if not (only := DISPLAY_ONLY.match(text)):
        return ""

    equation = latex_to_omml(only.group(1))

    if not equation.startswith("<m:oMath>"):
        return ""

    # Not wrapped in a <w:p>: an equation paragraph is a block in its own
    # right, a sibling of the paragraphs rather than something inside one.
    # Only inline equations go in a paragraph.
    return (
        "<m:oMathPara><m:oMathParaPr>"
        '<m:jc m:val="center"/></m:oMathParaPr>'
        f"{equation}</m:oMathPara>"
    )


def _paragraph(body: str, style: str = "", numbering: tuple = ()) -> str:
    """
    One paragraph.

    Parameters:
        body (str): Its runs.
        style (str): The style to set it in, if any.
        numbering (tuple): The list id and indent level, for a list item.

    Returns:
        str: The paragraph, as WordprocessingML.
    """

    properties = ""

    if style:
        properties += f'<w:pStyle w:val="{style}"/>'

    if numbering:
        identifier, level = numbering
        properties += (
            f'<w:numPr><w:ilvl w:val="{level}"/>'
            f'<w:numId w:val="{identifier}"/></w:numPr>'
        )

    if properties:
        properties = f"<w:pPr>{properties}</w:pPr>"

    return f"<w:p>{properties}{body}</w:p>"


def _table(rows: list) -> str:
    """
    A Markdown table as a Word table.

    Parameters:
        rows (list): The cells, row by row, the first row being the header.

    Returns:
        str: The table, as WordprocessingML.
    """

    columns = max(len(row) for row in rows)
    grid = "".join('<w:gridCol w:w="2400"/>' for _ in range(columns))
    drawn = []

    for at, row in enumerate(rows):
        cells = []

        for column in range(columns):
            text = row[column] if column < len(row) else ""
            body = inline_runs(text)

            if at == 0:
                body = inline_runs(f"**{text}**") if text else ""

            cells.append(
                '<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
                f"{_paragraph(body)}</w:tc>"
            )

        drawn.append(f"<w:tr>{''.join(cells)}</w:tr>")

    return (
        '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
        '<w:tblW w:w="0" w:type="auto"/></w:tblPr>'
        f"<w:tblGrid>{grid}</w:tblGrid>{''.join(drawn)}</w:tbl>"
        # A table cannot be the last thing in a document body, and two
        # tables cannot touch: Word wants a paragraph between them.
        "<w:p/>"
    )


def body_xml(blocks: list[Block]) -> tuple[str, list[tuple[int, str]]]:
    """
    The document's body, and the lists it needs numbering for.

    Parameters:
        blocks (list[Block]): The parsed answer.

    Returns:
        tuple: The body's WordprocessingML, and one (id, kind) pair per
            list in it.
    """

    parts = []
    lists: list[tuple[int, str]] = []
    seen: dict[tuple[int, str], int] = {}

    for block in blocks:
        match block.kind:
            case "heading":
                parts.append(
                    _paragraph(
                        inline_runs(block.text), style=f"Heading{block.level}"
                    )
                )
            case "quote":
                parts.append(_paragraph(inline_runs(block.text), style="Quote"))
            case "code":
                for line in block.text.split("\n"):
                    parts.append(
                        _paragraph(_run(line or " ", code=True), style="Code")
                    )
            case "rule":
                parts.append(_paragraph("", style="Rule"))
            case "table":
                parts.append(_table(block.rows))
            case "bullet" | "ordered":
                key = (block.number, block.kind)

                if key not in seen:
                    seen[key] = len(seen) + 1
                    lists.append((seen[key], block.kind))

                parts.append(
                    _paragraph(
                        inline_runs(block.text),
                        style="ListParagraph",
                        numbering=(seen[key], block.level),
                    )
                )
            case _:
                parts.append(
                    _display(block.text) or _paragraph(inline_runs(block.text))
                )

    return "".join(parts), lists


NAMESPACES = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""


def _heading_style(level: int) -> str:
    """
    One heading style.

    Parameters:
        level (int): 1 to MAX_HEADING.

    Returns:
        str: The style, as WordprocessingML.
    """

    size = {1: 32, 2: 26, 3: 22, 4: 20}.get(level, 20) * HALF_POINT // 2

    return (
        f'<w:style w:type="paragraph" w:styleId="Heading{level}">'
        f'<w:name w:val="heading {level}"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr>'
        f'<w:rPr><w:b/><w:color w:val="1F3864"/>'
        f'<w:sz w:val="{size}"/></w:rPr></w:style>'
    )


def styles_xml() -> str:
    """
    The stylesheet the document refers to.

    A .docx that names a style it does not carry gets Word's own idea of
    it, which for a heading is no heading at all -- so the few that are
    used are defined here rather than assumed.

    Returns:
        str: styles.xml.
    """

    headings = "".join(_heading_style(level) for level in range(1, MAX_HEADING + 1))

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {NAMESPACES}>
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/>
</w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>
<w:pPr><w:spacing w:after="120"/></w:pPr></w:style>
{headings}
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/>
<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="60"/></w:pPr>
<w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Note"><w:name w:val="Note"/>
<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="360"/></w:pPr>
<w:rPr><w:i/><w:color w:val="595959"/><w:sz w:val="18"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/>
<w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="{INDENT}"/></w:pPr>
<w:rPr><w:i/><w:color w:val="595959"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/>
<w:basedOn w:val="Normal"/><w:pPr><w:shd w:val="clear" w:fill="F2F2F2"/>
<w:spacing w:after="0"/><w:ind w:left="{INDENT}"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Rule"><w:name w:val="Rule"/>
<w:basedOn w:val="Normal"/><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:color="BFBFBF"/></w:pBdr></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>
<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="60"/><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>
<w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:color="BFBFBF"/><w:left w:val="single" w:sz="4" w:color="BFBFBF"/>
<w:bottom w:val="single" w:sz="4" w:color="BFBFBF"/><w:right w:val="single" w:sz="4" w:color="BFBFBF"/>
<w:insideH w:val="single" w:sz="4" w:color="BFBFBF"/><w:insideV w:val="single" w:sz="4" w:color="BFBFBF"/>
</w:tblBorders></w:tblPr></w:style>
</w:styles>"""


def numbering_xml(lists: list[tuple[int, str]]) -> str:
    """
    The numbering definitions the document's lists refer to.

    Every list gets a definition of its own, so an ordered list following
    another starts at one again rather than carrying on from it.

    Parameters:
        lists (list[tuple[int, str]]): One (id, kind) pair per list.

    Returns:
        str: numbering.xml.
    """

    abstracts = []
    instances = []

    for identifier, kind in lists:
        levels = []

        for level in range(5):
            if kind == "bullet":
                shape = (
                    '<w:numFmt w:val="bullet"/>'
                    f'<w:lvlText w:val="{BULLETS[level % len(BULLETS)]}"/>'
                )
            else:
                shape = (
                    '<w:numFmt w:val="decimal"/>'
                    f'<w:lvlText w:val="%{level + 1}."/>'
                )

            indent = INDENT * (level + 1)
            levels.append(
                f'<w:lvl w:ilvl="{level}"><w:start w:val="1"/>{shape}'
                '<w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{indent}" w:hanging="{INDENT}"/></w:pPr>'
                "</w:lvl>"
            )

        abstracts.append(
            f'<w:abstractNum w:abstractNumId="{identifier}">'
            f'<w:multiLevelType w:val="hybridMultilevel"/>{"".join(levels)}'
            "</w:abstractNum>"
        )
        instances.append(
            f'<w:num w:numId="{identifier}">'
            f'<w:abstractNumId w:val="{identifier}"/></w:num>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:numbering {NAMESPACES}>{''.join(abstracts)}{''.join(instances)}"
        "</w:numbering>"
    )


def core_xml(title: str) -> str:
    """
    The document's properties, so Word has something to call it.

    Parameters:
        title (str): What the document is.

    Returns:
        str: docProps/core.xml.
    """

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{escape(title)}</dc:title>"
        "</cp:coreProperties>"
    )


def document_xml(title: str, note: str, answer: str) -> tuple[str, list]:
    """
    The document itself.

    Parameters:
        title (str): The heading at the top.
        note (str): The line saying what the file is.
        answer (str): The model's answer, in Markdown.

    Returns:
        tuple: document.xml, and the lists it needs numbering for.
    """

    body, lists = body_xml(parse_markdown(answer))

    front = _paragraph(_run(title, bold=True), style="Title") + _paragraph(
        _run(note, italic=True), style="Note"
    )

    # A4, since this is a European deployment and the default is Letter.
    section = (
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1418" w:right="1418" w:bottom="1418" w:left="1418"/>'
        "</w:sectPr>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {NAMESPACES}><w:body>{front}{body}{section}</w:body>"
        "</w:document>",
        lists,
    )


def build_docx(title: str, note: str, answer: str) -> bytes:
    """
    The whole .docx package.

    Parameters:
        title (str): The heading at the top.
        note (str): The line saying what the file is.
        answer (str): The model's answer, in Markdown.

    Returns:
        bytes: The file, ready to be handed to the reader.
    """

    document, lists = document_xml(title, note, answer)
    package = BytesIO()

    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", PACKAGE_RELS)
        archive.writestr("docProps/core.xml", core_xml(title))
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        archive.writestr("word/styles.xml", styles_xml())
        archive.writestr("word/numbering.xml", numbering_xml(lists))

    return package.getvalue()

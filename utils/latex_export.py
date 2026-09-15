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
A model's answer as a LaTeX source file.

The other direction from the Word export, and for the other reader: a
lecture's notes going into a document somebody is already writing in
LaTeX, or a set of formulae to be typeset properly rather than read on a
screen. What the .docx has to convert -- the mathematics -- is the one
thing here that needs no conversion at all: the model writes its formulae
in LaTeX, so `$…$` and `$$…$$` are passed through untouched and are
exactly what the author would have typed.

Everything *around* them is the work. LaTeX reserves ten characters that a
transcription of somebody's speech uses freely -- per cent signs,
ampersands, underscores in a file name -- and a single unescaped one of
them is a document that does not build. So prose is escaped and formulae
are not, which is the whole reason this goes through
`utils.markdown_blocks` rather than over the raw text: the parser is what
says which is which.

The file is a whole document (preamble, `\\begin{document}`, the lot)
rather than a fragment to \\input: a reader who wants a fragment can cut
the middle out of it, while a reader given a fragment has to write a
preamble before they can see anything at all.
"""

import re

from utils.markdown_blocks import (
    INLINE,
    MAX_HEADING,
    Block,
    display_formulas,
    emphasised,
    link_of,
    parse_markdown,
    plain,
    scripted,
)

# The characters LaTeX will not take literally.
SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# One pass, not one replacement after another: three of the replacements
# above contain braces of their own, and a second pass over the text would
# escape those and leave \textbackslash\{\} where a backslash was meant.
SPECIALS = re.compile("[" + re.escape("".join(SPECIAL)) + "]")

# What each level of heading is called. Nothing below \paragraph is worth
# reaching for -- MAX_HEADING stops before it.
SECTIONS = ("section", "subsection", "subsubsection", "paragraph")

# Packages every document gets. Deliberately the ones in every LaTeX
# installation there is: an answer that will not build because the reader
# is missing a package is no better than one that will not build because
# of an unescaped ampersand. inputenc/fontenc are what make a Swedish
# transcription's own letters come out as themselves.
PREAMBLE = r"""\documentclass[11pt,a4paper]{article}

\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=25mm]{geometry}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{hyperref}
"""


def escape_text(text: str) -> str:
    """
    A stretch of prose with LaTeX's own characters made safe.

    Parameters:
        text (str): Text from the answer.

    Returns:
        str: The same text, as LaTeX will read it.
    """

    return SPECIALS.sub(lambda found: SPECIAL[found.group()], text)


def inline_latex(text: str) -> str:
    """
    A line of Markdown as LaTeX.

    Parameters:
        text (str): The line.

    Returns:
        str: The same line, as LaTeX.
    """

    parts = []
    position = 0

    for match in INLINE.finditer(text):
        if before := text[position : match.start()]:
            parts.append(escape_text(plain(before)))

        body = match.group()

        match match.lastgroup:
            case "code":
                parts.append(rf"\texttt{{{escape_text(body.strip('`'))}}}")
            case "display":
                # A formula on a line of its own inside a sentence is still
                # a formula: it is displayed, not escaped.
                parts.append(f"\\[{body[2:-2]}\\]")
            case "math":
                parts.append(body)
            case "sub":
                parts.append(rf"\textsubscript{{{inline_latex(scripted(body))}}}")
            case "sup":
                parts.append(rf"\textsuperscript{{{inline_latex(scripted(body))}}}")
            case "bold":
                parts.append(rf"\textbf{{{inline_latex(emphasised(body))}}}")
            case "italic":
                parts.append(rf"\textit{{{inline_latex(emphasised(body))}}}")
            case "line":
                parts.append("\\\\\n")
            case "tag" | "empty":
                pass
            case "link":
                label, address = link_of(body)

                if label and label != address:
                    parts.append(
                        rf"\href{{{address}}}{{{escape_text(plain(label))}}}"
                    )
                else:
                    parts.append(rf"\url{{{address}}}")

        position = match.end()

    if rest := text[position:]:
        parts.append(escape_text(plain(rest)))

    return "".join(parts)


def _display(text: str) -> str:
    """
    A paragraph that is nothing but a formula.

    Parameters:
        text (str): The paragraph's Markdown.

    Returns:
        str: One display environment per formula, or "" when the paragraph
            holds anything besides them.
    """

    return "\n\n".join(
        f"\\[\n{formula}\n\\]" for formula in display_formulas(text)
    )


def _table(rows: list) -> str:
    """
    A Markdown table as a tabular environment.

    Parameters:
        rows (list): The cells, row by row, the first row being the header.

    Returns:
        str: The table, as LaTeX.
    """

    columns = max(len(row) for row in rows)
    drawn = [
        r"\begin{center}",
        rf"\begin{{tabular}}{{|{'l|' * columns}}}",
        r"\hline",
    ]

    for at, row in enumerate(rows):
        cells = [row[column] if column < len(row) else "" for column in range(columns)]
        written = [inline_latex(cell) for cell in cells]

        if at == 0:
            written = [rf"\textbf{{{cell}}}" if cell else "" for cell in written]

        drawn.append(" & ".join(written) + r" \\")
        drawn.append(r"\hline")

    drawn += [r"\end{tabular}", r"\end{center}"]

    return "\n".join(drawn)


def _list_environment(
    blocks: list[Block], at: int, resume: int = 0
) -> tuple[str, int, int]:
    """
    A list, and everything nested inside it.

    A Markdown list is a flat run of items each carrying a depth; LaTeX
    wants them nested, one environment per level, so the run is read back
    into that shape here.

    Parameters:
        blocks (list[Block]): The whole answer.
        at (int): The first item of the list.
        resume (int): How many items of this list have already been
            written. A list interrupted by something that is not a list --
            a displayed formula under each step of a derivation -- comes
            back as a second environment, and an enumerate started afresh
            numbers the fourth step 1. ``\\setcounter`` rather than
            enumitem's ``[resume]``, which would be a package to install.

    Returns:
        tuple: The environment, the block to carry on from, and how many
            items it wrote.
    """

    kind = blocks[at].kind
    level = blocks[at].level
    number = blocks[at].number
    environment = "itemize" if kind == "bullet" else "enumerate"
    lines = [rf"\begin{{{environment}}}"]
    written = 0

    if resume and environment == "enumerate":
        lines.append(rf"\setcounter{{enumi}}{{{resume}}}")

    while at < len(blocks):
        block = blocks[at]

        if block.kind not in ("bullet", "ordered") or block.number != number:
            break

        if block.level < level:
            break

        if block.level > level:
            nested, at, _ = _list_environment(blocks, at)
            lines.append(nested)

            continue

        if block.kind != kind:
            break

        lines.append(rf"  \item {inline_latex(block.text)}")
        written += 1
        at += 1

    lines.append(rf"\end{{{environment}}}")

    return "\n".join(lines), at, written


def body_latex(blocks: list[Block]) -> str:
    """
    The document's body.

    Parameters:
        blocks (list[Block]): The parsed answer.

    Returns:
        str: LaTeX, ready to go between \\begin{document} and its end.
    """

    parts = []
    counted: dict[int, int] = {}
    at = 0

    while at < len(blocks):
        block = blocks[at]

        match block.kind:
            case "heading":
                section = SECTIONS[min(block.level, MAX_HEADING) - 1]
                parts.append(
                    rf"\{section}*{{{inline_latex(block.text)}}}"
                )
            case "quote":
                parts.append(
                    "\\begin{quote}\n"
                    f"{inline_latex(block.text)}\n"
                    "\\end{quote}"
                )
            case "code":
                # verbatim, so a program's own backslashes and braces are
                # left exactly as the model wrote them.
                parts.append(
                    "\\begin{verbatim}\n" + block.text + "\n\\end{verbatim}"
                )
            case "rule":
                parts.append(r"\begin{center}\rule{0.6\linewidth}{0.4pt}\end{center}")
            case "table":
                parts.append(_table(block.rows))
            case "bullet" | "ordered":
                belongs = block.number
                environment, at, written = _list_environment(
                    blocks, at, counted.get(belongs, 0)
                )
                counted[belongs] = counted.get(belongs, 0) + written
                parts.append(environment)

                continue
            case _:
                parts.append(_display(block.text) or inline_latex(block.text))

        at += 1

    return "\n\n".join(parts)


def build_latex(title: str, note: str, answer: str) -> str:
    """
    The whole .tex file.

    Parameters:
        title (str): The heading at the top.
        note (str): The line saying what the file is.
        answer (str): The model's answer, in Markdown.

    Returns:
        str: The source, ready to be handed to the reader.
    """

    body = body_latex(parse_markdown(answer))

    return (
        f"% {note}\n"
        f"{PREAMBLE}\n"
        "\\begin{document}\n\n"
        "\\begin{center}\n"
        f"{{\\LARGE\\bfseries {escape_text(title)}}}\\\\[0.6em]\n"
        f"{{\\small\\itshape {escape_text(note)}}}\n"
        "\\end{center}\n\n"
        f"{body}\n\n"
        "\\end{document}\n"
    )

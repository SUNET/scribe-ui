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
An answer read as the blocks and runs it is made of.

A model answers in Markdown, and every export has to take it apart the
same way before putting it back together in its own notation -- the same
headings, the same lists, the same tables, and the same formulae. Doing
that once here is what keeps the Word export and the LaTeX one from
disagreeing about what the answer said.

This is deliberately not a Markdown implementation. It reads what the
models actually write, which is the common half of it.
"""

import re

from dataclasses import dataclass, field
from html import unescape


# How deep a hierarchy of headings is worth carrying. Below this a model
# is not really writing one, and no format has a distinct look for it
# anyway.
MAX_HEADING = 4

# The shape of the answer, line by line.
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
ORDERED = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
QUOTE = re.compile(r"^\s*>\s?(.*)$")
FENCE = re.compile(r"^\s*```\s*(\S*)\s*$")
RULE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
TABLE_RULE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

# The inline HTML a model writes into its Markdown. It is written for the
# page -- where the browser draws it, and a chemical formula or a power of
# ten depends on it -- so an export that does not understand it does not
# merely lose the formatting: it prints the tags, and "10<sup>-18</sup> J"
# is what the reader gets in their document.
SUB = "sub"
SUP = "sup"

# Tags carrying no meaning an export can act on, dropped rather than
# printed. Named one by one on purpose: a catch-all for anything between
# angle brackets would eat "a < b and c > d" out of somebody's speech.
TAGS = (
    "u",
    "code",
    "p",
    "span",
    "div",
    "ul",
    "ol",
    "li",
    "h[1-6]",
)

# A line break written as a tag. Kept as one rather than dropped: a model
# writing it into a list item means the item to have two lines.
BREAK = re.compile(r"<br\s*/?>")

# What a run of text can be made of. Order matters: a code span is read
# before anything else, so a dollar sign or an asterisk quoted inside one
# stays what it is, and display maths is read before inline maths, which
# would otherwise take the first two dollars of it as an empty formula.
INLINE = re.compile(
    r"(?P<code>`+[^`]+`+)"
    r"|(?P<display>\$\$.+?\$\$)"
    r"|(?P<math>\$(?!\s)[^$\n]+?(?<!\s)\$)"
    rf"|(?P<sub><{SUB}>.+?</{SUB}>)"
    rf"|(?P<sup><{SUP}>.+?</{SUP}>)"
    r"|(?P<bold>\*\*.+?\*\*|__.+?__|<(?:b|strong)>.+?</(?:b|strong)>)"
    r"|(?P<italic>\*[^*\n]+?\*|_[^_\n]+?_|<(?:i|em)>.+?</(?:i|em)>)"
    r"|(?P<link>\[([^\]]*)\]\(([^)\s]+)[^)]*\))"
    r"|(?P<line><br\s*/?>)"
    rf"|(?P<tag></?(?:{'|'.join(TAGS)})\s*/?>)",
    re.DOTALL,
)

# Read back out of a link once the tokenizer has found one, rather than by
# the group's number: the numbering shifts every time something is added
# to INLINE, and it shifts silently.
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)[^)]*\)")


def link_of(text: str) -> tuple[str, str]:
    """
    A Markdown link's label and address.

    Parameters:
        text (str): The whole link, brackets and all.

    Returns:
        tuple[str, str]: The label and the address.
    """

    if found := LINK.match(text):
        return found.group(1), found.group(2)

    return "", text


def emphasised(text: str) -> str:
    """
    What is inside an emphasis, written either way.

    A model mixes Markdown's own marks with the HTML ones in the same
    answer, and an export has to read both.

    Parameters:
        text (str): The emphasis, marks or tags and all.

    Returns:
        str: What it says.
    """

    if text.startswith("<"):
        return re.sub(r"</?(?:b|strong|i|em)>", "", text)

    return text[2:-2] if text.startswith(("**", "__")) else text[1:-1]


def scripted(text: str) -> str:
    """
    What is inside a <sub> or <sup>.

    Parameters:
        text (str): The element, tags and all.

    Returns:
        str: What it says.
    """

    return re.sub(r"</?su[bp]>", "", text).strip()


def plain(text: str) -> str:
    """
    A stretch of prose as the characters it stands for.

    A model writing HTML into its answer writes HTML entities with it, and
    an export is where "&amp;" has to become an ampersand again -- it is
    going into a file that is not HTML, and every one of them has its own
    escaping to do afterwards.

    Parameters:
        text (str): Text from the answer.

    Returns:
        str: The same text, entities resolved.
    """

    return unescape(text)


@dataclass
class Block:
    """
    One thing in the document: a paragraph, a heading, a list item, a line
    of a code block, or a table.

    Attributes:
        kind (str): What it is.
        text (str): Its Markdown, for everything but a table.
        level (int): The heading level, or the list's indent depth.
        number (int): The list this item belongs to, so that two lists
            running one after the other do not share a count.
        rows (list): A table's cells, row by row.
    """

    kind: str
    text: str = ""
    level: int = 0
    number: int = 0
    rows: list = field(default_factory=list)


def _cells(line: str) -> list[str]:
    """
    One row of a Markdown table.

    Parameters:
        line (str): The row, pipes and all.

    Returns:
        list[str]: What is between the pipes.
    """

    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_markdown(text: str) -> list[Block]:
    """
    An answer cut into the blocks a document is made of.

    Parameters:
        text (str): The model's answer, in Markdown.

    Returns:
        list[Block]: The blocks, in order.
    """

    blocks: list[Block] = []
    lines = text.replace("\r\n", "\n").split("\n")
    paragraph: list[str] = []
    lists = 0
    at = 0

    def flush() -> None:
        nonlocal paragraph

        if joined := " ".join(part.strip() for part in paragraph).strip():
            blocks.append(Block("paragraph", joined))

        paragraph = []

    while at < len(lines):
        line = lines[at]

        if fence := FENCE.match(line):
            flush()
            at += 1
            body = []

            while at < len(lines) and not FENCE.match(lines[at]):
                body.append(lines[at])
                at += 1

            at += 1
            blocks.append(Block("code", "\n".join(body)))

            continue

        if not line.strip():
            flush()
            # A blank line ends a list as well as a paragraph, so the next
            # one starts its own count rather than carrying on from this.
            lists += 1
            at += 1

            continue

        if RULE.match(line):
            flush()
            blocks.append(Block("rule"))
            at += 1

            continue

        if heading := HEADING.match(line):
            flush()
            blocks.append(
                Block(
                    "heading",
                    heading.group(2).strip().rstrip("#").strip(),
                    level=min(len(heading.group(1)), MAX_HEADING),
                )
            )
            at += 1

            continue

        # A table is read whole: its rows only mean anything together, and
        # the row of dashes under the header is not a row at all.
        if TABLE_ROW.match(line) and at + 1 < len(lines) and TABLE_RULE.match(lines[at + 1]):
            flush()
            rows = [_cells(line)]
            at += 2

            while at < len(lines) and TABLE_ROW.match(lines[at]):
                rows.append(_cells(lines[at]))
                at += 1

            blocks.append(Block("table", rows=rows))

            continue

        if quote := QUOTE.match(line):
            flush()
            blocks.append(Block("quote", quote.group(1).strip()))
            at += 1

            continue

        for pattern, kind in ((BULLET, "bullet"), (ORDERED, "ordered")):
            if item := pattern.match(line):
                flush()
                blocks.append(
                    Block(
                        kind,
                        item.group(2).strip(),
                        level=min(len(item.group(1).expandtabs(4)) // 2, 4),
                        number=lists,
                    )
                )

                break
        else:
            paragraph.append(line)
            at += 1

            continue

        at += 1

    flush()

    return blocks

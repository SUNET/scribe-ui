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
LaTeX to Office Math (OMML), by way of MathML.

An answer's formulae are written in LaTeX and drawn in the page as MathML
-- markdown2's latex extra, via latex2mathml, and the browser does the rest
(see `utils/inference_panel.py`). Word understands neither: a .docx carries
its equations as OMML, its own math markup, and a formula pasted in as
text is a formula nobody can edit or search.

The usual route is Microsoft's MML2OMML.XSL, which ships with Office and
is not ours to redistribute, so the mapping is done here instead. It is a
mapping and not a parser: latex2mathml has already done the hard part, and
what arrives is a small, predictable set of elements.

What is not covered falls back to its own children, so an unknown wrapper
costs its decoration rather than the whole formula.
"""

import logging
import re

from xml.etree import ElementTree
from xml.sax.saxutils import escape

import latex2mathml.converter

log = logging.getLogger(__name__)

MATHML = "{http://www.w3.org/1998/Math/MathML}"

class Tag:
    """
    The MathML element names, spelled out.

    A match statement can only test against a literal or an attribute,
    so the namespaced names cannot be built where they are used.
    """

    MFENCED = MATHML + "mfenced"
    MFRAC = MATHML + "mfrac"
    MI = MATHML + "mi"
    MN = MATHML + "mn"
    MO = MATHML + "mo"
    MOVER = MATHML + "mover"
    MROOT = MATHML + "mroot"
    MROW = MATHML + "mrow"
    MSPACE = MATHML + "mspace"
    MSQRT = MATHML + "msqrt"
    MSTYLE = MATHML + "mstyle"
    MSUB = MATHML + "msub"
    MSUBSUP = MATHML + "msubsup"
    MSUP = MATHML + "msup"
    MTABLE = MATHML + "mtable"
    MTEXT = MATHML + "mtext"
    MTR = MATHML + "mtr"
    MUNDER = MATHML + "munder"
    MUNDEROVER = MATHML + "munderover"


# Operators that take limits above and below rather than a plain
# superscript: Word draws these as a "n-ary" object, with the operand
# inside it, and gets the spacing and the size of the sign right by itself.
NARY_UNDER_OVER = "∑∏∐⋃⋂⨁⨂⋀⋁"
NARY_SUB_SUP = "∫∬∭∮∯∰"
NARY = NARY_UNDER_OVER + NARY_SUB_SUP

# An accent is drawn with the combining form of the character, not the
# spacing one the LaTeX macro produces: Word puts the mark over the letter
# itself. \vec gives a plain rightwards arrow, \bar a macron, and so on.
COMBINING = {
    "→": "⃗",
    "←": "⃖",
    "^": "̂",
    "ˆ": "̂",
    "~": "̃",
    "˜": "̃",
    "´": "́",
    "`": "̀",
    "¨": "̈",
    "˙": "̇",
    "ˇ": "̌",
    "˘": "̆",
}

# Drawn as a line over or under the whole expression rather than as a mark
# on one letter.
BAR = "―¯‾_̲"


def _text(node) -> str:
    """
    The text of a MathML leaf, with the whitespace MathML pads it with cut.

    Parameters:
        node (Element): An <mi>, <mn>, <mo> or <mtext>.

    Returns:
        str: What the element says.
    """

    return "".join(node.itertext()).strip()


def _run(text: str, plain: bool) -> str:
    """
    One OMML run.

    Parameters:
        text (str): The characters to draw.
        plain (bool): Whether to draw them upright. OMML italicises by
            default, which is right for a variable and wrong for a digit,
            an operator or a word.

    Returns:
        str: The run, as OMML.
    """

    if not text:
        return ""

    style = '<m:rPr><m:sty m:val="p"/></m:rPr>' if plain else ""

    return f'<m:r>{style}<m:t xml:space="preserve">{escape(text)}</m:t></m:r>'


def _wrap(tag: str, body: str) -> str:
    """
    One of OMML's argument slots.

    Parameters:
        tag (str): The slot's name, e.g. "m:num".
        body (str): What goes in it.

    Returns:
        str: The slot, never empty -- Word wants the element there even
            when there is nothing in it.
    """

    return f"<{tag}>{body}</{tag}>"


def _children(nodes: list) -> str:
    """
    A run of sibling MathML elements as OMML, delimiters and n-ary
    operators taken into account.

    Two things cannot be decided one element at a time. A fenced pair
    (`\\left(` ... `\\right)`) arrives as three siblings and has to become
    one OMML delimiter object, or the brackets do not grow with what is
    between them. And an n-ary operator -- a sum, an integral -- carries
    what follows it as its own operand, so everything after it is folded
    inside.

    Parameters:
        nodes (list): The sibling elements.

    Returns:
        str: The lot, as OMML.
    """

    if fenced := _delimiter(nodes):
        return fenced

    parts = []

    for at, node in enumerate(nodes):
        if nary := _nary(node, nodes[at + 1 :]):
            parts.append(nary)
            break

        parts.append(convert_element(node))

    return "".join(parts)


def _fence(node, form: str) -> str:
    """
    The character an element opens or closes a fenced group with.

    Parameters:
        node (Element): A candidate element.
        form (str): "prefix" or "postfix".

    Returns:
        str: The character, or "" when this is not that kind of element.
    """

    if node.tag != Tag.MO:
        return ""

    if node.get("fence") != "true" or node.get("form") != form:
        return ""

    return _text(node)


def _delimiter(nodes: list) -> str:
    """
    A bracketed group as an OMML delimiter object.

    Parameters:
        nodes (list): The sibling elements.

    Returns:
        str: The delimiter, or "" when the siblings are not a fenced pair.
    """

    if len(nodes) < 2:
        return ""

    opening = _fence(nodes[0], "prefix")
    closing = _fence(nodes[-1], "postfix")

    if not opening and not closing:
        return ""

    properties = (
        f'<m:dPr><m:begChr m:val="{escape(opening)}"/>'
        f'<m:endChr m:val="{escape(closing)}"/><m:ctrlPr/></m:dPr>'
    )

    inside = _children(nodes[1:-1] if closing else nodes[1:])

    return f"<m:d>{properties}{_wrap('m:e', inside)}</m:d>"


def _nary_char(node) -> str:
    """
    The n-ary operator an element is built around, if it is one.

    Parameters:
        node (Element): A candidate element.

    Returns:
        str: The operator, or "" when the element is something else.
    """

    tag = node.tag

    if tag not in (
        Tag.MSUB,
        Tag.MSUP,
        Tag.MSUBSUP,
        Tag.MUNDER,
        Tag.MOVER,
        Tag.MUNDEROVER,
        Tag.MO,
    ):
        return ""

    base = node if tag == Tag.MO else list(node)[0]

    while base is not None and base.tag in (Tag.MROW, Tag.MSTYLE):
        inner = list(base)
        base = inner[0] if len(inner) == 1 else None

    if base is None or base.tag != Tag.MO:
        return ""

    character = _text(base)

    return character if character in NARY else ""


def _nary(node, rest: list) -> str:
    """
    A sum, product or integral with everything after it as its operand.

    Parameters:
        node (Element): The element carrying the operator.
        rest (list): The siblings that follow it.

    Returns:
        str: The n-ary object, or "" when this is not one.
    """

    character = _nary_char(node)

    if not character:
        return ""

    parts = list(node)
    lower = upper = ""

    match node.tag:
        case Tag.MSUB | Tag.MUNDER:
            lower = convert_element(parts[1])
        case Tag.MSUP | Tag.MOVER:
            upper = convert_element(parts[1])
        case Tag.MSUBSUP | Tag.MUNDEROVER:
            lower = convert_element(parts[1])
            upper = convert_element(parts[2])

    location = "undOvr" if character in NARY_UNDER_OVER else "subSup"

    properties = (
        f'<m:naryPr><m:chr m:val="{escape(character)}"/>'
        f'<m:limLoc m:val="{location}"/>'
        f'<m:subHide m:val="{0 if lower else 1}"/>'
        f'<m:supHide m:val="{0 if upper else 1}"/><m:ctrlPr/></m:naryPr>'
    )

    return (
        f"<m:nary>{properties}{_wrap('m:sub', lower)}"
        f"{_wrap('m:sup', upper)}{_wrap('m:e', _children(rest))}</m:nary>"
    )


def _script(node, parts: list) -> str:
    """
    A sub- or superscript.

    A function name carrying a subscript -- `\\lim_{x \\to 0}` -- is not a
    subscript at all but a limit, and Word has an object for it that puts
    the condition under the word rather than beside it.

    Parameters:
        node (Element): The <msub>, <msup> or <msubsup>.
        parts (list): Its children.

    Returns:
        str: The script, as OMML.
    """

    base = convert_element(parts[0])
    word = parts[0].tag == Tag.MO and len(_text(parts[0])) > 1

    match node.tag:
        case Tag.MSUB:
            if word:
                return (
                    "<m:limLow><m:limLowPr><m:ctrlPr/></m:limLowPr>"
                    f"{_wrap('m:e', base)}"
                    f"{_wrap('m:lim', convert_element(parts[1]))}</m:limLow>"
                )

            return (
                "<m:sSub><m:sSubPr><m:ctrlPr/></m:sSubPr>"
                f"{_wrap('m:e', base)}"
                f"{_wrap('m:sub', convert_element(parts[1]))}</m:sSub>"
            )
        case Tag.MSUP:
            return (
                "<m:sSup><m:sSupPr><m:ctrlPr/></m:sSupPr>"
                f"{_wrap('m:e', base)}"
                f"{_wrap('m:sup', convert_element(parts[1]))}</m:sSup>"
            )

    return (
        "<m:sSubSup><m:sSubSupPr><m:ctrlPr/></m:sSubSupPr>"
        f"{_wrap('m:e', base)}"
        f"{_wrap('m:sub', convert_element(parts[1]))}"
        f"{_wrap('m:sup', convert_element(parts[2]))}</m:sSubSup>"
    )


def _over_under(node, parts: list) -> str:
    """
    Something written over or under an expression: an accent, a bar, or a
    limit.

    Parameters:
        node (Element): The <mover>, <munder> or <munderover>.
        parts (list): Its children.

    Returns:
        str: The construct, as OMML.
    """

    base = convert_element(parts[0])
    mark = _text(parts[1]) if len(parts) > 1 else ""

    if node.tag == Tag.MOVER:
        if mark in BAR:
            return (
                '<m:bar><m:barPr><m:pos m:val="top"/><m:ctrlPr/></m:barPr>'
                f"{_wrap('m:e', base)}</m:bar>"
            )

        if len(mark) == 1 and (mark in COMBINING or node.get("accent") == "true"):
            character = COMBINING.get(mark, mark)

            return (
                f'<m:acc><m:accPr><m:chr m:val="{escape(character)}"/>'
                f"<m:ctrlPr/></m:accPr>{_wrap('m:e', base)}</m:acc>"
            )

        return (
            "<m:limUpp><m:limUppPr><m:ctrlPr/></m:limUppPr>"
            f"{_wrap('m:e', base)}{_wrap('m:lim', convert_element(parts[1]))}"
            "</m:limUpp>"
        )

    if node.tag == Tag.MUNDER:
        if mark in BAR:
            return (
                '<m:bar><m:barPr><m:pos m:val="bot"/><m:ctrlPr/></m:barPr>'
                f"{_wrap('m:e', base)}</m:bar>"
            )

        return (
            "<m:limLow><m:limLowPr><m:ctrlPr/></m:limLowPr>"
            f"{_wrap('m:e', base)}{_wrap('m:lim', convert_element(parts[1]))}"
            "</m:limLow>"
        )

    lower = (
        "<m:limLow><m:limLowPr><m:ctrlPr/></m:limLowPr>"
        f"{_wrap('m:e', base)}{_wrap('m:lim', convert_element(parts[1]))}"
        "</m:limLow>"
    )

    return (
        "<m:limUpp><m:limUppPr><m:ctrlPr/></m:limUppPr>"
        f"{_wrap('m:e', lower)}{_wrap('m:lim', convert_element(parts[2]))}"
        "</m:limUpp>"
    )


def _matrix(node) -> str:
    """
    A MathML table as an OMML matrix.

    Parameters:
        node (Element): The <mtable>.

    Returns:
        str: The matrix, as OMML.
    """

    rows = [row for row in node if row.tag == Tag.MTR]
    columns = max((len(list(row)) for row in rows), default=1)

    properties = (
        f'<m:mPr><m:mcs><m:mc><m:mcPr><m:count m:val="{columns}"/>'
        '<m:mcJc m:val="center"/></m:mcPr></m:mc></m:mcs><m:ctrlPr/></m:mPr>'
    )

    drawn = []

    for row in rows:
        cells = "".join(_wrap("m:e", _children(list(cell))) for cell in row)
        drawn.append(f"<m:mr>{cells}</m:mr>")

    return f"<m:m>{properties}{''.join(drawn)}</m:m>"


def convert_element(node) -> str:
    """
    One MathML element as OMML.

    Parameters:
        node (Element): The element.

    Returns:
        str: The same thing, as OMML.
    """

    parts = list(node)

    match node.tag:
        case Tag.MI:
            # A single letter is a variable and is set in italics; a word
            # is a function name -- sin, log -- and is not.
            text = _text(node)

            return _run(text, plain=len(text) > 1)
        case Tag.MN | Tag.MO | Tag.MTEXT:
            return _run(_text(node), plain=True)
        case Tag.MSPACE:
            return _run(" ", plain=True)
        case Tag.MFRAC:
            return (
                "<m:f><m:fPr><m:ctrlPr/></m:fPr>"
                f"{_wrap('m:num', convert_element(parts[0]))}"
                f"{_wrap('m:den', convert_element(parts[1]))}</m:f>"
            )
        case Tag.MSQRT:
            return (
                '<m:rad><m:radPr><m:degHide m:val="1"/><m:ctrlPr/></m:radPr>'
                f"{_wrap('m:deg', '')}{_wrap('m:e', _children(parts))}</m:rad>"
            )
        case Tag.MROOT:
            return (
                '<m:rad><m:radPr><m:degHide m:val="0"/><m:ctrlPr/></m:radPr>'
                f"{_wrap('m:deg', convert_element(parts[1]))}"
                f"{_wrap('m:e', convert_element(parts[0]))}</m:rad>"
            )
        case Tag.MSUB | Tag.MSUP | Tag.MSUBSUP:
            return _script(node, parts)
        case Tag.MOVER | Tag.MUNDER | Tag.MUNDEROVER:
            return _over_under(node, parts)
        case Tag.MTABLE:
            return _matrix(node)
        case Tag.MFENCED:
            opening = node.get("open", "(")
            closing = node.get("close", ")")
            separator = node.get("separators", ",")
            properties = (
                f'<m:dPr><m:begChr m:val="{escape(opening)}"/>'
                f'<m:sepChr m:val="{escape(separator[:1])}"/>'
                f'<m:endChr m:val="{escape(closing)}"/>'
                "<m:ctrlPr/></m:dPr>"
            )
            inside = "".join(_wrap("m:e", convert_element(part)) for part in parts)

            return f"<m:d>{properties}{inside}</m:d>"

    # Anything else -- <mrow>, <mstyle>, <mpadded>, <semantics>, whatever a
    # later latex2mathml starts emitting -- is a wrapper, and its children
    # are the formula. Losing the wrapper costs its decoration; refusing
    # the element would cost the formula.
    if parts:
        return _children(parts)

    return _run(_text(node), plain=True)


def mathml_to_omml(markup: str) -> str:
    """
    A MathML document as the contents of an OMML equation.

    Parameters:
        markup (str): MathML, as latex2mathml produces it.

    Returns:
        str: OMML, without the <m:oMath> wrapper.
    """

    root = ElementTree.fromstring(markup)

    return _children(list(root))


def latex_to_omml(latex: str) -> str:
    """
    A LaTeX formula as an OMML equation Word can draw and edit.

    A formula that cannot be converted is not worth failing a whole export
    for: it comes back as the LaTeX it was, set as text, which is at least
    what the model wrote.

    Parameters:
        latex (str): The formula, without its delimiters.

    Returns:
        str: An <m:oMath> element, or a plain run when it could not be
            converted.
    """

    try:
        markup = latex2mathml.converter.convert(latex.strip())
        body = mathml_to_omml(markup)
    except Exception as error:
        log.warning("Could not convert a formula to OMML: %s", error)

        return _run(latex.strip(), plain=True)

    if not body.strip():
        return _run(latex.strip(), plain=True)

    return f"<m:oMath>{body}</m:oMath>"

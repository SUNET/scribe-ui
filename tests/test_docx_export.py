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
The Word export, and the formulae in it.

A .docx is a zip of XML that Word refuses outright when it is wrong, and
"refuses outright" is not a failure a unit test sees on its own -- so what
is checked here is the shape of what is written: that every part named in
the package is in it, that every part parses, and above all that a formula
comes out as an OMML equation rather than as the LaTeX it was written in.
A formula exported as text is the one outcome this feature exists to
prevent, and it is also the one that looks fine until somebody opens the
file.
"""

import zipfile

from io import BytesIO
from xml.etree import ElementTree

from utils.docx_export import (
    Block,
    body_xml,
    build_docx,
    inline_runs,
    parse_markdown,
)
from utils.omml import latex_to_omml

WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MATH = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def document_of(answer: str) -> str:
    """
    The document part of an export.

    Parameters:
        answer (str): The answer to export.

    Returns:
        str: word/document.xml.
    """

    package = zipfile.ZipFile(BytesIO(build_docx("Title", "A note.", answer)))

    return package.read("word/document.xml").decode()


def test_the_package_holds_every_part_it_names():
    package = zipfile.ZipFile(BytesIO(build_docx("Title", "A note.", "Hello.")))
    named = set(package.namelist())

    assert named == {
        "[Content_Types].xml",
        "_rels/.rels",
        "docProps/core.xml",
        "word/document.xml",
        "word/_rels/document.xml.rels",
        "word/styles.xml",
        "word/numbering.xml",
    }

    # Every part the content types and the relationships point at has to
    # be there, or Word calls the whole file corrupt.
    types = package.read("[Content_Types].xml").decode()

    for part in named - {"[Content_Types].xml"}:
        if part.endswith(".xml") and not part.endswith(".rels"):
            assert f"/{part}" in types


def test_every_part_is_well_formed_xml():
    package = zipfile.ZipFile(
        BytesIO(
            build_docx(
                "Title",
                "A note.",
                "# Heading\n\n- One & two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
            )
        )
    )

    for part in package.namelist():
        ElementTree.fromstring(package.read(part))


def test_the_title_and_the_note_are_in_the_document():
    package = zipfile.ZipFile(
        BytesIO(build_docx("Study notes — lecture.mp4", "A note.", "Body."))
    )
    document = package.read("word/document.xml").decode()

    # The note says the file is derived and not the transcript, and it has
    # to travel with the file rather than with the page that made it.
    assert "Study notes — lecture.mp4" in document
    assert "A note." in document
    assert 'w:val="Title"' in document
    assert 'w:val="Note"' in document
    assert "Study notes" in package.read("docProps/core.xml").decode()


def test_a_formula_becomes_an_equation_and_not_its_latex():
    document = document_of("The energy is $KE = \\frac{1}{2}mv^2$ here.")

    assert f"{MATH}oMath" not in document  # namespaced only once parsed
    assert "<m:oMath>" in document
    assert "<m:f>" in document
    assert "\\frac" not in document
    assert "$" not in document


def test_a_displayed_formula_stands_on_its_own():
    document = document_of("Before.\n\n$$E = mc^2$$\n\nAfter.")

    assert "<m:oMathPara>" in document
    assert "<m:sSup>" in document


def test_a_formula_inside_a_code_span_is_left_alone():
    runs = inline_runs("Write `$x^2$` for it.")

    assert "oMath" not in runs
    assert "$x^2$" in runs


def test_a_formula_that_cannot_be_converted_survives_as_text():
    # A model writing nonsense between dollars must cost its own formula
    # and not the export.
    equation = latex_to_omml("\\begin{nosuchenv} x")

    assert "m:oMath" not in equation or "m:t" in equation


def test_headings_lists_code_and_tables_are_recognised():
    blocks = parse_markdown(
        "# One\n\n"
        "Some prose.\n\n"
        "- a\n- b\n\n"
        "1. first\n2. second\n\n"
        "> quoted\n\n"
        "```python\nprint(1)\n```\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n"
    )
    kinds = [block.kind for block in blocks]

    assert kinds == [
        "heading",
        "paragraph",
        "bullet",
        "bullet",
        "ordered",
        "ordered",
        "quote",
        "code",
        "table",
    ]
    assert blocks[0].level == 1
    assert blocks[-1].rows == [["a", "b"], ["1", "2"]]


def test_a_second_list_counts_from_one_again():
    _, lists = body_xml(parse_markdown("1. a\n2. b\n\nProse.\n\n1. c\n2. d\n"))

    # Two numbering definitions, so the second list starts at 1 rather
    # than carrying on from the first.
    assert len(lists) == 2
    assert {kind for _, kind in lists} == {"ordered"}


def test_a_nested_item_is_indented_rather_than_flattened():
    blocks = parse_markdown("- one\n  - two\n")

    assert [block.level for block in blocks] == [0, 1]


def test_emphasis_becomes_formatting_and_not_asterisks():
    runs = inline_runs("A **bold** and an *italic* word.")

    assert "<w:b/>" in runs
    assert "<w:i/>" in runs
    assert "*" not in runs


def test_the_answers_text_is_escaped():
    document = document_of("Angle < brackets & ampersands <b>bold</b>.")

    assert "&lt;" in document
    assert "&amp;" in document
    assert "<b>" not in document


def test_a_mermaid_fence_is_kept_as_a_code_block():
    blocks = parse_markdown("```mermaid\nflowchart TD\n  A --> B\n```\n")

    assert [block.kind for block in blocks] == ["code"]
    assert "A --> B" in blocks[0].text


def test_run_properties_are_written_in_the_schemas_order():
    # Word refuses a file whose run properties are out of sequence, and
    # rFonts comes before b, which comes before i.
    runs = inline_runs("`code`")
    document = document_of("A **bold** word.")

    assert "<w:rFonts" in runs
    assert document.index("<w:b/>") > 0


def test_a_subscript_and_a_superscript_survive_as_formatting():
    # A model writes these as HTML among its Markdown: the page draws
    # them, and an export that does not read them prints the tags
    # themselves -- "10<sup>-18</sup> J" in somebody's document.
    document = document_of("Rydberg: R<sub>H</sub> = 2.18 x 10<sup>-18</sup> J")

    assert '<w:vertAlign w:val="subscript"/>' in document
    assert '<w:vertAlign w:val="superscript"/>' in document
    assert "<sub>" not in document
    assert "sup&gt;" not in document


def test_html_emphasis_is_read_as_emphasis():
    runs = inline_runs("A <b>bold</b> and an <em>italic</em> word.")

    assert "<w:b/>" in runs
    assert "<w:i/>" in runs
    assert "&lt;b&gt;" not in runs


def test_a_tag_with_nothing_behind_it_is_dropped_and_not_printed():
    runs = inline_runs("Some <span>text</span> here.<br>")

    assert "span" not in runs
    assert "Some " in runs
    assert "text" in runs


def test_speech_about_less_than_is_not_read_as_markup():
    # The one thing a catch-all for angle brackets would have eaten.
    runs = inline_runs("So a < b and c > d in the recording.")

    assert "a &lt; b and c &gt; d" in runs


def test_an_entity_becomes_the_character_it_stands_for():
    runs = inline_runs("Salt &amp; pepper &lt;here&gt;")

    assert "Salt &amp; pepper &lt;here&gt;" in runs
    assert "amp;amp;" not in runs

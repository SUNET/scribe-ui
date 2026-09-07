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
The LaTeX export.

Two things decide whether the file is any use, and they pull against each
other: a formula has to come through exactly as the model wrote it, and
everything that is not a formula has to be escaped, because one loose per
cent sign is a document that does not build. So most of what is checked
here is which of the two a given stretch of the answer was treated as.
"""

from utils.latex_export import (
    PREAMBLE,
    body_latex,
    build_latex,
    escape_text,
    inline_latex,
)
from utils.markdown_blocks import parse_markdown


def document_of(answer: str) -> str:
    """
    An exported document.

    Parameters:
        answer (str): The answer to export.

    Returns:
        str: The .tex source.
    """

    return build_latex("Title", "A note.", answer)


def test_the_file_is_a_document_and_not_a_fragment():
    document = document_of("Hello.")

    assert r"\documentclass" in document
    assert r"\begin{document}" in document
    assert document.rstrip().endswith(r"\end{document}")
    assert PREAMBLE in document


def test_prose_is_escaped():
    # Every one of these is a document that does not build if it reaches
    # LaTeX as it stands.
    assert escape_text("50% of R&D") == r"50\% of R\&D"
    assert escape_text("file_name.txt") == r"file\_name.txt"
    assert escape_text("a #tag {here}") == r"a \#tag \{here\}"
    assert escape_text("a\\b") == r"a\textbackslash{}b"


def test_a_formula_is_passed_through_untouched():
    latex = inline_latex("The energy is $KE = \\frac{1}{2}mv^2$ here.")

    # The braces and the backslash are the formula's own and must not be
    # escaped; the words around it are not a formula.
    assert "$KE = \\frac{1}{2}mv^2$" in latex
    assert r"\_" not in latex


def test_a_displayed_formula_gets_a_display_environment():
    document = document_of("Before.\n\n$$E = mc^2$$\n\nAfter.")

    assert "\\[\nE = mc^2\n\\]" in document


def test_a_formula_in_a_code_span_is_text_and_not_maths():
    latex = inline_latex("Write `$x_1$` for it.")

    assert r"\texttt{" in latex
    assert r"\$x\_1\$" in latex


def test_headings_become_sections():
    document = body_latex(parse_markdown("# One\n\n## Two\n\n### Three\n"))

    # Starred, so LaTeX does not number them over the top of whatever
    # numbering the answer itself uses.
    assert r"\section*{One}" in document
    assert r"\subsection*{Two}" in document
    assert r"\subsubsection*{Three}" in document


def test_a_list_is_nested_rather_than_flattened():
    document = body_latex(parse_markdown("- one\n  - two\n- three\n"))

    assert document.count(r"\begin{itemize}") == 2
    assert document.count(r"\end{itemize}") == 2
    assert document.count(r"\item") == 3


def test_an_ordered_list_is_an_enumerate():
    document = body_latex(parse_markdown("1. one\n2. two\n"))

    assert r"\begin{enumerate}" in document
    assert r"\begin{itemize}" not in document


def test_a_table_becomes_a_tabular_with_a_column_per_cell():
    document = body_latex(
        parse_markdown("| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n")
    )

    assert r"\begin{tabular}{|l|l|l|}" in document
    assert r"1 & 2 & 3 \\" in document
    assert r"\textbf{a}" in document


def test_a_code_block_is_verbatim_and_not_escaped():
    document = body_latex(
        parse_markdown("```python\nvalue = {a: 100 % b}\n```\n")
    )

    assert r"\begin{verbatim}" in document
    assert "value = {a: 100 % b}" in document
    assert r"\textbackslash" not in document
    assert r"\%" not in document


def test_emphasis_and_links_are_carried_over():
    latex = inline_latex("A **bold** and [a link](https://example.org/a_b).")

    assert r"\textbf{bold}" in latex
    assert r"\href{https://example.org/a_b}{a link}" in latex


def test_the_note_says_the_file_is_derived():
    document = build_latex("Study notes — lecture.mp4", "Not the transcript.", "Body.")

    assert "Not the transcript." in document
    assert "Study notes" in document


def test_a_titles_own_special_characters_are_escaped():
    document = build_latex("Q&A — 100%.mp4", "A note.", "Body.")

    assert r"Q\&A — 100\%.mp4" in document


def test_a_subscript_and_a_superscript_become_typeset_ones():
    latex = inline_latex("Rydberg: R<sub>H</sub> = 2.18 x 10<sup>-18</sup> J")

    assert r"R\textsubscript{H}" in latex
    assert r"10\textsuperscript{-18}" in latex
    assert "<sub>" not in latex


def test_html_emphasis_is_read_as_emphasis():
    latex = inline_latex("A <b>bold</b> and an <em>italic</em> word.")

    assert r"\textbf{bold}" in latex
    assert r"\textit{italic}" in latex


def test_a_tag_with_nothing_behind_it_is_dropped():
    latex = inline_latex("Some <span>text</span> here.")

    assert "span" not in latex
    assert "text" in latex


def test_speech_about_less_than_is_not_read_as_markup():
    latex = inline_latex("So a < b and c > d in the recording.")

    assert "a < b and c > d" in latex


def test_an_entity_becomes_the_character_it_stands_for_and_is_then_escaped():
    latex = inline_latex("Salt &amp; pepper")

    assert latex == r"Salt \& pepper"

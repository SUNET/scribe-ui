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
Charts that can be read without seeing them (utils/chart_tables.py), and the
group statistics page that uses them -- the one local administrators see too.
"""

import pathlib
import re

import plotly.graph_objects as go
import pytest

import utils.chart_tables as module
from utils.styles import chart_colors

ROOT = pathlib.Path(__file__).resolve().parent.parent
GROUPS = (ROOT / "pages" / "admin" / "groups.py").read_text()


class TestTheChartIsAPicture:
    def test_no_hover_no_toolbar(self):
        figure = module.static_chart(go.Figure(data=[go.Bar(x=["a"], y=[1])]))

        assert figure["config"] == {
            "staticPlot": True,
            "displayModeBar": False,
            "responsive": True,
        }
        assert figure["data"][0]["type"] == "bar"

    def test_a_plain_dict_will_do(self):
        figure = module.static_chart({"data": [], "layout": {}})

        assert figure["config"]["staticPlot"] is True

    def test_assistive_technology_is_told_to_skip_it(self):
        source = pathlib.Path(module.__file__).read_text()
        section = source[source.index("def chart_section") :]

        wrapper = section.index('.props(\'aria-hidden="true"\')')
        chart = section.index("ui.plotly(static_chart(figure))")

        assert wrapper < chart


class TestTheNumbersAreATable:
    def table(self, **kwargs):
        defaults = dict(
            summary="Show the minutes per day for this month as a table",
            caption="Transcribed minutes per day, this month",
            headers=("Date", "Minutes"),
            rows=[("2026-10-01", "12.0"), ("2026-10-02", "3.5")],
            numeric=(1,),
        )
        defaults.update(kwargs)

        return module.data_table(**defaults)

    def test_behind_a_native_disclosure(self):
        table = self.table()

        assert table.startswith('<details class="chart-data"><summary>')
        assert "<summary>Show the minutes per day for this month as a table</summary>" in table
        assert table.endswith("</table></details>")
        # Shut until asked for: no "open".
        assert "<details open" not in table

    def test_with_a_caption_and_headers_for_columns_and_rows(self):
        table = self.table()

        assert "<caption>Transcribed minutes per day, this month</caption>" in table
        assert '<th scope="col">Date</th>' in table
        assert '<th scope="col" class="chart-number">Minutes</th>' in table
        assert '<tr><th scope="row">2026-10-01</th><td class="chart-number">12.0</td></tr>' in table
        assert table.count("<tr>") == 3

    def test_everything_from_the_backend_is_escaped(self):
        table = self.table(rows=[("<b>x</b>", "1 & 2")], caption='a "c" <d>')

        assert "<b>x</b>" not in table
        assert "&lt;b&gt;x&lt;/b&gt;" in table
        assert "1 &amp; 2" in table
        assert "a &quot;c&quot; &lt;d&gt;" in table

    def test_no_rows_is_still_a_table(self):
        table = self.table(rows=[])

        assert "<tbody></tbody>" in table


class TestTheSentence:
    def test_the_total_the_days_and_the_busiest(self):
        said = module.minutes_summary(
            {"2026-10-01": 12.0, "2026-10-02": 0, "2026-10-03": 85.4}
        )

        assert said == "97 minutes in all, on 2 days. The most on 2026-10-03: 85.4 minutes."

    def test_one_day(self):
        assert module.minutes_summary({"2026-10-05": 7}) == (
            "7 minutes in all, on 1 day. The most on 2026-10-05: 7.0 minutes."
        )

    @pytest.mark.parametrize("per_day", [{}, {"2026-10-01": 0}, {"2026-10-01": None}])
    def test_nothing(self, per_day):
        assert module.minutes_summary(per_day) == "No minutes were transcribed."


class TestTheDisclosureLooksLikeOne:
    def test_a_triangle_that_turns_and_an_underline(self):
        styles = module.CHART_STYLES

        assert 'content: "\\25B8";' in styles
        assert '.chart-data[open] > summary::before {\n        content: "\\25BE";' in styles
        # Drawn, not said.
        assert 'content: "\\25B8" / "";' in styles
        assert 'content: "\\25BE" / "";' in styles
        assert "text-decoration: underline;" in styles
        assert ".chart-data summary:focus-visible" in styles


class TestTheSection:
    def test_heading_sentence_picture_table_in_that_order(self, monkeypatch):
        made = []

        class Element:
            def __init__(self, kind, *args, **kwargs):
                self.kind, self.args, self.kwargs = kind, args, kwargs
                self.given = {}
                made.append(self)

            def classes(self, value):
                self.given["classes"] = value
                return self

            def props(self, value):
                self.given["props"] = value
                return self

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        class UI:
            label = staticmethod(lambda *a, **k: Element("label", *a, **k))
            element = staticmethod(lambda *a, **k: Element("element", *a, **k))
            plotly = staticmethod(lambda *a, **k: Element("plotly", *a, **k))
            html = staticmethod(lambda *a, **k: Element("html", *a, **k))

        monkeypatch.setattr(module, "ui", UI)

        module.chart_section(
            "Minutes per day",
            "97 minutes in all.",
            go.Figure(data=[go.Bar(x=["a"], y=[1])]),
            table_summary="Show as a table",
            caption="Minutes per day",
            headers=("Date", "Minutes"),
            rows=[("a", "1.0")],
            numeric=(1,),
        )

        assert [e.kind for e in made] == ["label", "label", "element", "plotly", "html"]
        heading, sentence, wrapper, chart, table = made
        assert heading.args == ("Minutes per day",)
        assert heading.given["props"] == "role=heading aria-level=2"
        assert sentence.args == ("97 minutes in all.",)
        assert wrapper.given["props"] == 'aria-hidden="true"'
        assert chart.args[0]["config"]["staticPlot"] is True
        assert table.kwargs == {"sanitize": False}
        assert "<caption>Minutes per day</caption>" in table.args[0]


class TestTheGroupStatisticsPage:
    def test_both_charts_are_sections(self):
        assert "chart_section(" in GROUPS
        assert '"Transcribed minutes per day, this month"' in GROUPS
        assert '"Transcribed minutes per day, previous month"' in GROUPS
        assert "ui.plotly(" not in GROUPS
        assert "ui.add_head_html(chart_head())" in GROUPS

    def test_the_days_are_labels_not_hours(self):
        assert 'xaxis=dict(type="category")' in GROUPS

    def test_no_hover_text_and_no_title_inside_the_picture(self):
        assert "hovertemplate" not in GROUPS
        assert "title=\"Transcribed" not in GROUPS

    def test_the_tables_under_them_have_headings_too(self):
        for name in ("Transcribed minutes per user this month", "Job queue for group"):
            at = GROUPS.index(f'ui.label("{name}")')
            assert 'props("role=heading aria-level=2")' in GROUPS[at : at + 200], name


def luminance(colour: str) -> float:
    def linear(value: int) -> float:
        value /= 255

        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(int(colour[i : i + 2], 16)) for i in (1, 3, 5))

    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)

    return (lighter + 0.05) / (darker + 0.05)


class TestTheBarsCanBeSeen:
    """1.4.11: the bars against the card they are drawn on."""

    @pytest.mark.parametrize("bar", ["bar_current", "bar_previous"])
    def test_light(self, bar):
        assert contrast(chart_colors["light"][bar], "#ffffff") >= 3

    @pytest.mark.parametrize("bar", ["bar_current", "bar_previous"])
    def test_dark(self, bar):
        for surface in ("#16181d", "#000000"):
            assert contrast(chart_colors["dark"][bar], surface) >= 3

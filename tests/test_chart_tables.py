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
from utils.bar_chart import BAR_CHART_STYLES

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

        assert wrapper < section.index("ui.plotly(static_chart(figure))")
        assert wrapper < section.index("ui.html(figure, sanitize=False)")


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

        assert said == "97.4 minutes in all, on 2 days. The most on 3 Oct: 85.4 minutes."

    def test_one_day(self):
        assert module.minutes_summary({"2026-10-05": 7}) == (
            "7.0 minutes in all, on 1 day. The most on 5 Oct: 7.0 minutes."
        )

    def test_the_total_in_the_same_figures_as_the_day(self):
        """Not "1 minutes in all" beside "1.3 minutes" for the same day."""

        said = module.minutes_summary({"2026-10-15": 1.33})

        assert said.startswith("1.3 minutes in all")

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


class TestAnEmptyChart:
    def test_only_the_heading_and_the_sentence(self, monkeypatch):
        made = []

        class Element:
            def __init__(self, kind, *args, **kwargs):
                made.append(kind)

            def classes(self, value):
                return self

            def props(self, value):
                return self

        class UI:
            label = staticmethod(lambda *a, **k: Element("label", *a, **k))
            element = staticmethod(lambda *a, **k: Element("element", *a, **k))
            plotly = staticmethod(lambda *a, **k: Element("plotly", *a, **k))
            html = staticmethod(lambda *a, **k: Element("html", *a, **k))

        monkeypatch.setattr(module, "ui", UI)

        module.chart_section(
            "Minutes", "No minutes were transcribed.", {"data": [], "layout": {}},
            table_summary="x", caption="x", headers=("Date", "Minutes"), rows=[], empty=True,
        )

        assert made == ["label", "label"]

    def test_the_page_says_when_a_month_is_empty(self):
        assert "empty=not any(value and value > 0 for value in minutes.values())" in GROUPS


class TestTheGroupStatisticsPage:
    def test_both_charts_are_sections(self):
        assert "chart_section(" in GROUPS
        assert '"Transcribed minutes per day, this month"' in GROUPS
        assert '"Transcribed minutes per day, previous month"' in GROUPS
        assert "ui.plotly(" not in GROUPS
        assert "ui.add_head_html(chart_head())" in GROUPS

    def test_the_charts_are_drawn_by_the_page_not_plotly(self):
        assert "bar_chart(" in GROUPS
        assert "import plotly" not in GROUPS and "ui.plotly(" not in GROUPS
        # In the theme's own colours, so no reload on a change of theme.
        stats = GROUPS[GROUPS.index("async def statistics") :]
        stats = stats[: stats.index("\ndef create(")]
        assert "reload_on_theme_change()" not in stats

    def test_both_months_whole_and_on_one_scale(self):
        stats = GROUPS[GROUPS.index("async def statistics") :]
        stats = stats[: stats.index("\ndef create(")]

        assert stats.count("month_days(") == 1 and "highest=highest" in stats
        assert "per_day_previous_month" in stats[stats.index("highest = max(") :][:200]
        # An empty month is still shown, as its heading and a sentence.
        assert "if not minutes:" not in stats

    def test_nothing_on_the_page_exports_user_names_for_now(self):
        assert "ui.download(" not in GROUPS and "csv" not in GROUPS.lower()

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
    """1.4.11: the bars against the card they are drawn on, in both themes."""

    def token(self, name, dark=False):
        styles = (ROOT / "utils" / "styles.py").read_text()
        values = re.findall(rf"{name}: (#[0-9a-f]{{6}});", styles)

        return values[1] if dark else values[0]

    def own(self, name, dark=False):
        rule = BAR_CHART_STYLES.split(".body--dark .bar-chart {")[1 if dark else 0]

        return re.search(rf"{name}: (#[0-9a-f]{{6}});", rule).group(1)

    def test_this_months_bars(self):
        assert "--chart-bar: var(--color-brand-primary);" in BAR_CHART_STYLES
        assert contrast(self.token("--color-brand-primary"), "#ffffff") >= 3
        assert contrast(self.token("--color-brand-primary", dark=True), "#16181d") >= 3

    def test_the_second_series(self):
        assert contrast(self.own("--chart-bar-previous"), "#ffffff") >= 3
        assert contrast(self.own("--chart-bar-previous", dark=True), "#16181d") >= 3

    def test_the_labels(self):
        assert "color: var(--color-text-tertiary);" in BAR_CHART_STYLES
        assert contrast(self.token("--color-text-tertiary"), "#ffffff") >= 4.5
        assert contrast(self.token("--color-text-tertiary", dark=True), "#16181d") >= 4.5

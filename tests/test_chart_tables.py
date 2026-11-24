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
        assert table.endswith("</table></div></details>")
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

    def test_in_a_region_of_its_own_that_scrolls_not_the_page(self):
        table = self.table(caption='a "c" <d>')

        assert '<div class="chart-scroll" role="region" tabindex="0" aria-label="a &quot;c&quot; &lt;d&gt;"><table>' in table
        styles = module.CHART_STYLES
        scroll = styles[styles.index("    .chart-scroll {") :][:80]
        assert "max-width: 100%;" in scroll and "overflow-x: auto;" in scroll
        assert ".chart-scroll:focus-visible" in styles
        # Its least width never more than the card has.
        assert "min-width: min(16rem, 100%);" in styles
        assert "min-width: 16rem;" not in styles

    def test_no_rows_is_still_a_table(self):
        table = self.table(rows=[])

        assert "<tbody></tbody>" in table


class TestTheSentence:
    def test_the_total_the_days_and_the_busiest(self):
        said = module.minutes_summary(
            {"2026-10-01": 12.0, "2026-10-02": 0, "2026-10-03": 85.4}
        )

        assert said == "97\u00a0minutes in\u00a0all. Busiest day: 3\u00a0Oct, 85\u00a0minutes."

    def test_one_day(self):
        assert module.minutes_summary({"2026-10-05": 1.33}) == (
            "1\u00a0minute in\u00a0all. Busiest day: 5\u00a0Oct, 1\u00a0minute."
        )
        assert module.minutes_summary({"2026-10-05": 1.33}, decimals=1) == (
            "1.3\u00a0minutes in\u00a0all. Busiest day: 5\u00a0Oct, 1.3\u00a0minutes."
        )

    def test_the_total_is_the_sum_of_the_days_as_they_are(self):
        """Of 24.4 and 0.4 and 0.4: 25 in all, not 24 + 0.4 + 0.4 rounded."""

        said = module.minutes_summary({"2026-10-01": 24.4, "2026-10-02": 0.4, "2026-10-03": 0.4})

        assert said == "25\u00a0minutes in\u00a0all. Busiest day: 1\u00a0Oct, 24\u00a0minutes."

    def test_not_how_many_days(self):
        said = module.minutes_summary({"2026-10-01": 5, "2026-10-02": 6})

        assert " day" not in said.replace("Busiest day", "")

    def test_on_a_tie_the_first_day(self):
        said = module.minutes_summary({"2026-10-01": 5, "2026-10-02": 9, "2026-10-03": 9})

        assert said.endswith("Busiest day: 2\u00a0Oct, 9\u00a0minutes.")

    def test_a_month_under_way_is_so_far(self):
        said = module.minutes_summary({"2026-11-01": 20, "2026-11-03": 37.2}, so_far=True)

        assert said == "57\u00a0minutes so\u00a0far. Busiest day: 3\u00a0Nov, 37\u00a0minutes."
        assert module.minutes_summary({}, so_far=True) == "Nothing has been transcribed so\u00a0far."

    def test_the_days_to_come_are_no_figures_yet(self):
        # The backend fills the whole month with noughts.
        per_day = {"2026-11-01": 3, "2026-11-02": 0, "2026-11-03": 0, "2026-11-04": 0, "2026-11-05": 2}

        assert module.days_so_far(per_day, "2026-11-03") == {
            "2026-11-01": 3, "2026-11-02": 0, "2026-11-03": 0, "2026-11-05": 2,
        }
        assert module.days_so_far({}, "2026-11-03") == {}
        assert module.days_so_far({"2026-11-04": None}, "2026-11-03") == {}

    def test_the_page_leaves_the_days_to_come_out_of_tooltips_and_table(self):
        stats = GROUPS[GROUPS.index("async def statistics") :]
        assert "shown = days_so_far(minutes, today.isoformat()) if under_way else minutes" in stats
        assert '"values": [shown.get(day) for day in days]' in stats
        assert "rows=[(day, rounded(value, decimals)) for day, value in shown.items()]" in stats

    def test_the_page_says_so_far_for_this_month_only(self):
        assert "(per_day, this_month, this_name, True)" in GROUPS
        assert "(per_day_previous_month, previous_month, previous_name, False)" in GROUPS
        assert "minutes_summary(minutes, decimals, so_far=under_way)" in GROUPS
        assert "future_after=today.isoformat() if under_way else None" in GROUPS

    @pytest.mark.parametrize("per_day", [{}, {"2026-10-01": 0}, {"2026-10-01": None}])
    def test_nothing(self, per_day):
        assert module.minutes_summary(per_day) == "Nothing was transcribed."


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
            "97\u00a0minutes in\u00a0all.",
            go.Figure(data=[go.Bar(x=["a"], y=[1])]),
            table_summary="Show as a table",
            caption="Minutes per day",
            headers=("Date", "Minutes"),
            rows=[("a", "1.0")],
            numeric=(1,),
        )

        assert [e.kind for e in made] == ["html", "html", "element", "plotly", "html"]
        heading, sentence, wrapper, chart, table = made
        assert heading.args == ('<span class="chart-sentence"><span class="chart-phrase">Minutes per day</span></span>',)
        assert heading.given["props"] == "role=heading aria-level=2"
        assert sentence.args == (
            '<span class="chart-sentence"><span class="chart-phrase">97\u00a0minutes in\u00a0all.</span></span>',
        )
        assert heading.kwargs == sentence.kwargs == {"sanitize": False}
        assert wrapper.given["props"] == 'aria-hidden="true"'
        assert chart.args[0]["config"]["staticPlot"] is True
        assert table.kwargs == {"sanitize": False}
        assert "<caption>Minutes per day</caption>" in table.args[0]


class TestPhrases:
    """A heading or a sentence breaks between its phrases in a narrow card."""

    def test_sentences_of_phrases(self):
        assert module.phrased("Transcribed minutes per day, November\u00a02026") == (
            '<span class="chart-sentence">'
            '<span class="chart-phrase">Transcribed minutes per day,</span> '
            '<span class="chart-phrase">November\u00a02026</span>'
            "</span>"
        )
        said = module.phrased("1.3\u00a0minutes in\u00a0all. Busiest day: 15\u00a0Oct, 1.3\u00a0minutes.")
        assert said.count("chart-sentence") == 2
        assert said.count("chart-phrase") == 3

    def test_not_inside_a_figure(self):
        assert module.phrased("1.3 minutes").count("chart-phrase") == 1

    def test_escaped(self):
        assert "<b>" not in module.phrased("<b>, x")

    def test_read_out_as_the_words_with_spaces_between(self):
        assert re.sub(r"<[^>]+>", "", module.phrased("a, b. c")) == "a, b. c"

    def test_on_a_phone_the_same_breaks_every_time(self):
        rule = module.CHART_STYLES[module.CHART_STYLES.index("@media (max-width: 600px)") :]
        rule = rule[: rule.index("</style>")]

        assert ".chart-heading .chart-phrase,\n        .chart-summary .chart-sentence {\n            display: block;" in rule
        assert ".chart-heading {\n            font-size: 1.125rem;" in rule


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
            "Minutes", "Nothing was transcribed.", {"data": [], "layout": {}},
            table_summary="x", caption="x", headers=("Date", "Minutes"), rows=[], empty=True,
        )

        assert made == ["html", "html"]

    def test_the_page_says_when_a_month_is_empty(self):
        assert "empty=not any(value and value > 0 for value in minutes.values())" in GROUPS


class TestTheGroupStatisticsPage:
    def test_both_charts_are_sections(self):
        assert "chart_section(" in GROUPS
        assert 'heading = f"Transcribed minutes per day, {name}"' in GROUPS
        assert "(per_day, this_month, this_name, True)" in GROUPS
        assert "(per_day_previous_month, previous_month, previous_name, False)" in GROUPS
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

        assert stats.count("month_days(") == 2 and "highest=highest" in stats
        assert "per_day_previous_month" in stats[stats.index("highest = max(") :][:200]
        # An empty month is still shown, as its heading and a sentence.
        assert "if not minutes:" not in stats

    def test_nothing_on_the_page_exports_user_names_for_now(self):
        assert "ui.download(" not in GROUPS and "csv" not in GROUPS.lower()

    def test_the_months_by_name_not_this_and_previous(self):
        stats = GROUPS[GROUPS.index("async def statistics") :]
        stats = stats[: stats.index("\ndef create(")]

        for old in ('"Transcribed minutes per day, this month"', "Transcribed files this month",
                    "Transcribed minutes last month", "per user this month"):
            assert old not in stats, old
        for label in ('("Users", ', "this_name,\n", "previous_name,\n",
                      "minutes per user, {this_name}", "for {name} as a table"):
            assert label in stats, label

    def test_headings_sentences_and_the_cards_lines_break_in_balance(self):
        assert ".chart-phrase {\n        display: inline-block;" in module.CHART_STYLES
        source = (ROOT / "utils" / "chart_tables.py").read_text()
        assert 'ui.html(phrased(heading), sanitize=False).classes(\n        "chart-heading ' in source
        assert 'ui.html(phrased(summary), sanitize=False).classes("chart-summary ' in source
        stats = GROUPS[GROUPS.index("async def statistics") :]
        stats = stats[: stats.index("\ndef create(")]
        assert 'f"{count}{NBSP}files"' in stats

    def test_the_summary_is_a_list_of_cards_like_on_home(self):
        stats = GROUPS[GROUPS.index("async def statistics") :]
        stats = stats[: stats.index("\ndef create(")]
        source = (ROOT / "utils" / "chart_tables.py").read_text()
        cards = source[source.index("def summary_cards(") :]
        styles = (ROOT / "utils" / "styles.py").read_text()

        assert "summary_cards(tiles)" in stats
        assert 'ui.element("ul").classes("stats-tiles").props(\'role="list"\')' in cards
        assert 'ui.element("li")' in cards
        assert 'ui.card().props("flat bordered").classes("stats-tile")' in cards
        assert "Number of users" not in stats and "Transcribed files in" not in stats
        # The page's own styles, shared with the Groups page.
        assert "list-style: none;" in styles
        # Never wider than the card, whatever the text size; the month's
        # name may break inside the card.
        assert "grid-template-columns: repeat(auto-fit, minmax(min(13rem, 100%), 1fr));" in styles
        assert "minmax(13rem, 1fr)" not in styles
        assert 'ui.label(name.replace(NBSP, " ")).classes("stats-tile-name")' in cards
        # The figures in the body size, the name a step above it.
        assert ".stats-tile-name {\n        font-size: 1.125rem;" in styles
        assert ".stats-tile-meta {\n        font-size: 1rem;" in styles

    def test_less_room_round_the_cards_on_a_phone(self):
        rule = module.CHART_STYLES[module.CHART_STYLES.index("@media (max-width: 600px)") :]

        assert ".stats-card.stats-summary,\n        .chart-container {\n            padding: 1rem;" in rule

    def test_the_same_room_under_the_title_as_between_the_cards(self):
        styles = (ROOT / "utils" / "styles.py").read_text()
        rule = styles[styles.index("    .stats-container {") :]
        rule = rule[: rule.index("}")]

        assert "gap: 2rem;" in rule and "padding: 0 1rem 2rem;" in rule

    def test_one_precision_for_the_page(self):
        stats = GROUPS[GROUPS.index("async def statistics") :]
        stats = stats[: stats.index("\ndef create(")]

        assert "decimals = decimals_for(" in stats
        assert ":.0f" not in stats and ":.1f" not in stats
        assert stats.count("decimals=decimals") >= 2

    def test_no_hover_text_and_no_title_inside_the_picture(self):
        assert "hovertemplate" not in GROUPS
        assert "title=\"Transcribed" not in GROUPS

    def test_the_tables_under_them_have_headings_too(self):
        for name in ('f"Transcribed minutes per user, {this_name}"', '"Job queue for group"'):
            at = GROUPS.index(f"ui.label({name})")
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

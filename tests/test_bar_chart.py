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

"""The page's own bar chart (utils/bar_chart.py)."""

import re
from datetime import date

import pytest

from utils.bar_chart import (
    BAR_CHART_STYLES,
    bar_chart,
    day_label,
    amount,
    decimals_for,
    figure,
    month_days,
    month_name,
    rounded,
    nice_ticks,
)


def days(n, month="2026-10"):
    return [f"{month}-{d:02d}" for d in range(1, n + 1)]


class TestTheScale:
    @pytest.mark.parametrize(
        "highest, ticks",
        [
            (1.33, [0, 0.5, 1, 1.5]),
            (85.4, [0, 25, 50, 75, 100]),
            (31, [0, 10, 20, 30, 40]),
            (412, [0, 250, 500]),
            (1000, [0, 250, 500, 750, 1000]),
        ],
    )
    def test_round_steps_from_nought_to_just_above(self, highest, ticks):
        assert nice_ticks(highest) == ticks

    @pytest.mark.parametrize(
        "highest, ticks",
        [(1.33, [0, 1, 2]), (0.2, [0, 1]), (9, [0, 5, 10]), (85.4, [0, 25, 50, 75, 100])],
    )
    def test_whole_steps_only_where_asked(self, highest, ticks):
        assert nice_ticks(highest, whole=True) == ticks

    def test_the_chart_has_no_decimals_on_its_scale(self):
        chart = bar_chart(days(1), [{"name": "x", "values": [1.33]}])
        scale = chart.split('<div class="bar-chart-ticks">')[1].split("</div>")[0]

        assert re.findall(r">([^<]+)</span>", scale) == ["0", "1", "2"]

    @pytest.mark.parametrize("highest", [0, None, -3])
    def test_nothing_is_nought_to_one(self, highest):
        assert nice_ticks(highest) == [0, 1]

    @pytest.mark.parametrize("highest", [0.2, 1, 7, 33.3, 99, 120, 5000])
    def test_never_more_than_four_steps_and_never_below_the_highest(self, highest):
        ticks = nice_ticks(highest)

        assert ticks[0] == 0
        assert ticks[-1] >= highest
        assert len(ticks) - 1 <= 4

    def test_figures(self):
        assert figure(2.0) == "2"
        assert figure(2.5) == "2.5"
        assert figure(1.33) == "1.3"


class TestTheLabels:
    def test_a_date_reads_as_a_day(self):
        assert day_label("2026-10-15") == "15 Oct"
        assert day_label("2026-01-01") == "1 Jan"
        assert day_label("not a date") == "not a date"

    def test_at_most_eight_shown(self):
        chart = bar_chart(days(31), [{"name": "x", "values": [1] * 31}])
        labels = re.search(r'<div class="bar-chart-labels">(.*?)</div>', chart).group(1)
        shown = [label for label in re.findall(r"<span[^>]*>(.*?)</span>", labels) if label]

        assert len(re.findall(r"<span", labels)) == 31
        assert shown == ["1 Oct", "5 Oct", "9 Oct", "13 Oct", "17 Oct", "21 Oct", "25 Oct", "29 Oct"]

    def test_all_of_a_short_month(self):
        chart = bar_chart(days(4), [{"name": "x", "values": [1] * 4}])

        assert chart.count(">4 Oct</span>") == 1

    def test_a_few_labels_all_stay(self):
        chart = bar_chart(days(4), [{"name": "x", "values": [1] * 4}])

        assert "is-minor" not in chart

    def test_every_other_one_goes_in_a_narrow_chart(self):
        chart = bar_chart(days(31), [{"name": "x", "values": [1] * 31}])

        assert '<span>1 Oct</span>' in chart
        assert '<span class="is-minor">5 Oct</span>' in chart
        assert '<span>9 Oct</span>' in chart
        assert "@container (max-width: 34rem)" in BAR_CHART_STYLES
        assert "container-type: inline-size;" in BAR_CHART_STYLES
        assert "grid-template-columns: auto minmax(0, 1fr);" in BAR_CHART_STYLES


class TestTheBars:
    def test_one_slot_per_label_and_a_bar_where_there_is_a_value(self):
        chart = bar_chart(days(3), [{"name": "x", "values": [0, 1.3, None]}])

        assert chart.count('class="bar-chart-slot"') == 3
        assert chart.count('class="bar-chart-bar"') == 1

    def test_heights_against_the_top_of_the_scale(self):
        chart = bar_chart(days(2), [{"name": "x", "values": [10, 20]}])

        assert 'style="height: 50.0%"' in chart
        assert 'style="height: 100.0%"' in chart

    def test_each_slot_says_its_day_and_value_under_a_pointer(self):
        chart = bar_chart(days(2), [{"name": "x", "values": [0, 1.33]}], decimals=1)

        assert 'title="1 Oct: 0.0 minutes"' in chart
        assert 'title="2 Oct: 1.3 minutes"' in chart

    def test_a_day_still_to_come_has_no_tooltip_but_a_nought_says_so(self):
        chart = bar_chart(days(3), [{"name": "x", "values": [0, 2, None]}])

        assert 'title="1 Oct: 0 minutes"' in chart
        assert 'title="2 Oct: 2 minutes"' in chart
        assert "3 Oct:" not in chart
        assert chart.count('<div class="bar-chart-slot">') == 1

    def test_two_charts_on_one_scale(self):
        small = bar_chart(days(2), [{"name": "x", "values": [10, 20]}], highest=75)

        assert 'style="height: 26.667%"' in small  # 20 of 75
        assert ">75</span>" in small

    def test_the_scale_still_fits_a_value_above_highest(self):
        chart = bar_chart(days(1), [{"name": "x", "values": [90]}], highest=10)

        assert ">100</span>" in chart

    def test_two_series_side_by_side_named_in_the_tooltip(self):
        chart = bar_chart(
            ["1", "2"],
            [
                {"name": "November", "values": [2, 0], "tone": "current"},
                {"name": "October", "values": [1, 4], "tone": "previous"},
            ],
            legend=True,
        )

        assert 'title="1: November: 2 minutes; October: 1 minute"' in chart
        assert chart.count("bar-chart-bar is-previous") == 2
        assert '<div class="bar-chart-legend">' in chart
        assert '<i class="is-previous"></i>October' in chart

    def test_names_are_escaped(self):
        chart = bar_chart(["<b>"], [{"name": "<i>", "values": [1]}], unit="<u>", legend=True)

        assert "<b>" not in chart and "<u>" not in chart and "<i>" not in chart.replace("<i class", "")


class TestTheLook:
    def test_the_pages_type_and_colours(self):
        assert "font-family: var(--font-sans);" in BAR_CHART_STYLES
        assert "--chart-bar: var(--color-brand-primary);" in BAR_CHART_STYLES
        assert "color: var(--color-text-tertiary);" in BAR_CHART_STYLES

    def test_text_sized_in_rem_so_it_follows_the_readers_text_size(self):
        assert "font-size: 0.8125rem;" in BAR_CHART_STYLES
        assert "--chart-height: 13rem;" in BAR_CHART_STYLES
        assert "px;\n        color" not in BAR_CHART_STYLES

    def test_a_second_series_is_striped_not_only_coloured(self):
        assert "repeating-linear-gradient(" in BAR_CHART_STYLES

    def test_high_contrast_keeps_the_bars(self):
        block = BAR_CHART_STYLES[BAR_CHART_STYLES.index("@media (forced-colors: active)") :]

        assert "forced-color-adjust: none;" in block
        assert "background: CanvasText;" in block


class TestAWholeMonth:
    """Both charts show their whole month, so they are drawn alike."""

    def test_the_month_of_the_days_given(self):
        whole = month_days(["2026-11-03", "2026-11-04"], date(2026, 1, 1))

        assert whole[0] == "2026-11-01" and whole[-1] == "2026-11-30"
        assert len(whole) == 30

    def test_february_and_a_leap_year(self):
        assert len(month_days(["2026-02-10"], date(2026, 1, 1))) == 28
        assert len(month_days(["2028-02-10"], date(2026, 1, 1))) == 29

    def test_no_days_is_the_fallbacks_month(self):
        whole = month_days([], date(2026, 10, 9))

        assert len(whole) == 31 and whole[0] == "2026-10-01"

    def test_days_that_are_not_dates_are_left_as_they_are(self):
        assert month_days(["week 1", "week 2"], date(2026, 1, 1)) == ["week 1", "week 2"]

    def test_the_labels_of_a_30_and_a_31_day_month_fall_on_the_same_days(self):
        def shown(n, month):
            chart = bar_chart(days(n, month), [{"name": "x", "values": [1] * n}])
            labels = chart.split('<div class="bar-chart-labels">')[1]

            return re.findall(r"<span(?: class=\"is-minor\")?>(\d+) ", labels)

        assert shown(30, "2026-11") == shown(31, "2026-10")


class TestHowMinutesAreShown:
    """One precision for a page; the figures underneath are not rounded."""

    @pytest.mark.parametrize(
        "values, decimals",
        [
            ([85.4, 1.3], 0),
            ([10, 0.4], 0),
            ([9.96], 0),  # shown as 10.0, so whole
            ([9.94, 1.3], 1),
            ([1.33], 1),
            ([], 1),
            ([None, 0], 1),
        ],
    )
    def test_a_decimal_for_the_page_only_when_its_largest_figure_is_under_10(
        self, values, decimals
    ):
        assert decimals_for(values) == decimals

    @pytest.mark.parametrize(
        "value, decimals, shown",
        [
            (0, 0, "0 minutes"),
            (None, 0, "0 minutes"),
            (0.4, 0, "under 1 minute"),
            (0.5, 0, "1 minute"),
            (1.33, 0, "1 minute"),
            (12.5, 0, "13 minutes"),  # half up, not to the even 12
            (100.8, 0, "101 minutes"),
            (0, 1, "0.0 minutes"),
            (0.04, 1, "under 0.1 minute"),
            (0.25, 1, "0.3 minutes"),  # half up, not to the even 0.2
            (1.33, 1, "1.3 minutes"),
            (7, 1, "7.0 minutes"),  # so a column lines up
        ],
    )
    def test_amounts(self, value, decimals, shown):
        assert amount(value, decimals=decimals) == shown

    def test_a_column_of_figures_lines_up(self):
        assert [rounded(value, 1) for value in (7, 0, 1.33)] == ["7.0", "0.0", "1.3"]
        assert [rounded(value) for value in (85.4, 0, 0.2)] == ["85", "0", "<1"]

    def test_a_day_with_a_bar_never_says_nought(self):
        chart = bar_chart(days(1), [{"name": "x", "values": [0.02]}], decimals=1)

        assert 'class="bar-chart-bar"' in chart
        assert 'title="1 Oct: under 0.1 minute"' in chart

    def test_the_month_by_name_in_english_whatever_the_locale(self):
        assert month_name("2026-11-03") == "November 2026"
        assert month_name("2027-01-01") == "January 2027"
        assert month_name("next") == "next"


class TestTheDaysToCome:
    """This month's days after today are toned, with an edge where they begin."""

    def chart(self, **kwargs):
        return bar_chart(days(5, "2026-11"), [{"name": "x", "values": [3, 4, 5, None, None]}], **kwargs)

    def test_after_today_only(self):
        chart = self.chart(future_after="2026-11-03")

        assert chart.count("is-future") == 2
        assert chart.count("is-first-future") == 1
        slots = chart.split('<div class="bar-chart-slot')[1:]
        assert "is-first-future" in slots[3] and "is-future" not in slots[2]

    def test_today_itself_is_not_to_come(self):
        assert self.chart(future_after="2026-11-05").count("is-future") == 0

    def test_a_whole_month_has_none(self):
        assert "is-future" not in self.chart()

    def test_the_tone_and_the_edge_in_both_themes(self):
        light = BAR_CHART_STYLES.split(".body--dark .bar-chart {")[0]
        dark = BAR_CHART_STYLES.split(".body--dark .bar-chart {")[1].split("}")[0]

        assert "--chart-future: rgba(15, 23, 42, 0.065);" in light
        assert "--chart-future: rgba(255, 255, 255, 0.065);" in dark
        assert "border-left: 1px dashed var(--chart-future-edge);" in BAR_CHART_STYLES
        assert "--chart-future-edge: var(--color-text-secondary);" in BAR_CHART_STYLES

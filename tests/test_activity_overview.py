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

"""The Activity overview (pages/admin/analytics.py): what it counts (utils/activity.py) and how it draws it."""

import pathlib
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from utils import activity
from utils.bar_chart import BAR_CHART_STYLES, stacked_chart
from utils.chart_tables import CHART_STYLES, HEAT_TONES, _mix, contrast, heat_table, shown_table

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "admin" / "analytics.py").read_text()
NBSP = " "


def rows(*items):
    return [{"path": path, "date": day, "views": count} for path, day, count in items]


class TestWhatIsCounted:
    def test_actions_by_name_table_and_kind(self):
        assert activity.action("/action/upload") == ("Uploads", "user", "uploads")
        assert activity.action("/action/bulk_export") == ("Bulk exports", "user", "exports")
        assert activity.action("/action/set_admin") == ("Admin rights granted", "admin", "admin")
        # Not known here: its own table, named from its path.
        assert activity.action("/action/merge_files") == ("Merge files", "other", "other")
        # A page is not an action, and is left out.
        assert activity.action("/home") is None

    def test_the_kinds_and_their_names(self):
        assert [name for _, name in activity.KINDS] == ["Uploads", "Transcriptions", "Exports", "Administrative actions"]

    def test_two_periods_of_30_days_and_a_week_more_fetched(self):
        now, before = activity.periods(date(2026, 11, 5))
        assert (now[0], now[-1], len(now)) == ("2026-10-07", "2026-11-05", 30)
        assert (before[0], before[-1], len(before)) == ("2026-09-07", "2026-10-06", 30)
        assert activity.HISTORY == 66

    def test_counted_by_day_and_kind_actions_only(self):
        kinds, paths = activity.per_day(rows(
            ("/action/transcription", "2026-11-05T00:00:00", 2),
            ("/action/bulk_transcription", "2026-11-05", 1),
            ("/home", "2026-11-05", 40),
        ))
        assert kinds == {"2026-11-05": {"transcriptions": 3}}
        assert paths["2026-11-05"] == {"/action/transcription": 2, "/action/bulk_transcription": 1}

    def test_whole_when_the_log_goes_back_further_than_fetched(self):
        views = rows(("/action/upload", "2026-11-05", 3))
        assert activity.counted_from(views, [{"path": "/action/upload", "total_views": 90}]) is None
        # Began within the days fetched: from its first day.
        assert activity.counted_from(views, [{"path": "/action/upload", "total_views": 3}]) == "2026-11-05"
        assert activity.has_whole(["2026-11-01"], None)
        assert not activity.has_whole(["2026-11-01"], "2026-11-05")

    def test_a_7_day_average_only_where_the_log_covers_the_week(self):
        kinds = {f"2026-11-{day:02d}": {"uploads": 7} for day in range(1, 11)}
        days = [f"2026-11-{day:02d}" for day in range(1, 11)]
        averages = activity.rolling_average(kinds, days, "2026-11-01")
        assert averages[:6] == [None] * 6
        assert averages[6:] == [7.0] * 4
        # A log older than the days: every day, its noughts real.
        assert activity.rolling_average(kinds, days, None)[0] == 1.0


class TestTheTrend:
    def test_up_and_down_with_the_share(self):
        assert activity.trend(359, 322) == ("trending_up", f"+37 (+11{NBSP}%)", f" on the 30{NBSP}days before")
        assert activity.trend(200, 300)[:2] == ("trending_down", f"−100 (−33{NBSP}%)")

    def test_within_5_percent_about_the_same(self):
        icon, figure, words = activity.trend(302, 311)
        assert (icon, figure) == ("trending_flat", "−9")
        assert "about the same" in words

    def test_said_when_there_is_nothing_to_compare_with(self):
        assert activity.trend(3, None) == ("remove", "", "No figures for the 30 days before")
        assert "when there were none" in activity.trend(5, 0)[2]


class TestWhenAndWhat:
    def test_the_heat_map_in_the_readers_time_zone_monday_first(self):
        # PostgreSQL's Sunday 23:00 UTC is Monday 00:00 an hour east.
        assert activity.heat([{"dow": 0, "hour": 23, "views": 4}], 1)[0][0] == 4
        # Monday 00:00 UTC is Sunday 23:00 an hour west.
        assert activity.heat([{"dow": 1, "hour": 0, "views": 2}], -1)[6][23] == 2

    def test_latest_in_the_readers_time_with_the_year_when_not_this_years(self):
        zone = ZoneInfo("Europe/Stockholm")
        when = activity.moment("2026-11-05T15:53:00", zone)
        assert activity.when_label(when, date(2026, 11, 5)) == f"5{NBSP}Nov, 16:53"
        assert activity.when_label(datetime(2025, 3, 1, 9, 5, tzinfo=zone), date(2026, 11, 5)) == f"1{NBSP}Mar 2025, 09:05"
        assert activity.moment("not a time", zone) is None


class TestTheStackedChart:
    CHART = stacked_chart(
        ["2026-11-01", "2026-11-02", "2026-11-03"],
        [{"name": "Uploads", "values": [3, 0, 0]}, {"name": "Exports", "values": [2, 1, 0]}],
        line={"name": "7-day average", "values": [None, 2.4, 1.0]},
        counted_from="2026-11-02",
    )

    def test_a_segment_per_kind_in_its_colour(self):
        assert "background: var(--chart-s2)" in self.CHART
        assert "--chart-s1: #2a78d6;" in BAR_CHART_STYLES and "--chart-s1: #3987e5;" in BAR_CHART_STYLES

    def test_the_tooltip_says_every_kind_and_the_average(self):
        assert 'title="2 Nov: 1 action; 7-day average 2"' in self.CHART.replace(NBSP, " ")

    def test_days_before_the_statistics_are_toned_not_drawn_as_noughts(self):
        assert 'class="bar-chart-slot is-uncounted" title="1 Nov: no figures"' in self.CHART.replace(NBSP, " ")

    def test_the_average_a_grey_dashed_line_over_a_ring_skipping_what_it_cannot_say(self):
        assert self.CHART.count("<polyline") == 2
        points = re.search(r'class="is-line" points="([^"]*)"', self.CHART).group(1)
        assert len(points.split()) == 2
        assert "stroke-dasharray: 6 4;" in BAR_CHART_STYLES
        assert "--chart-line: #6b7280;" in BAR_CHART_STYLES

    def test_a_legend_for_every_kind_and_the_line(self):
        assert '<i class="is-line"></i>7-day average' in self.CHART
        assert self.CHART.count("<span><i") == 3

    def test_high_contrast(self):
        forced = BAR_CHART_STYLES[BAR_CHART_STYLES.index("@media (forced-colors: active)"):]
        assert ".bar-chart-segment" in forced and "stroke: Highlight;" in forced


class TestTheHeatTable:
    TABLE = heat_table(["Monday", "Tuesday"], ["00", "01"], [[0, 3], [6, 1]], "Actions by day and hour", lambda d, h: f"D{d} H{h}")

    def test_two_tables_one_shown_by_the_cards_width(self):
        assert '<table class="heat-wide">' in self.TABLE and '<table class="heat-tall">' in self.TABLE
        assert "@container (max-width: 44rem)" in CHART_STYLES

    def test_totals_for_rows_and_columns(self):
        assert '<td class="heat-total">3</td>' in self.TABLE  # Monday
        assert '<td class="heat-total">10</td>' in self.TABLE  # all

    def test_each_cell_named_in_its_tooltip(self):
        assert 'title="D1 H0: 6 actions"' in self.TABLE.replace(NBSP, " ")

    def test_the_ink_has_contrast_in_every_tone_and_both_themes(self):
        for base, full, inks in HEAT_TONES.values():
            for step in range(1, 101):
                tone = _mix(base, full, 0.15 + 0.85 * step / 100)
                assert max(contrast(ink, tone) for ink in inks) >= 4.5, tone

    def test_a_table_shown_without_a_disclosure(self):
        table = shown_table("Caption", ("Action", "Count"), [("Uploads", 3)], numeric=(1,))
        assert "<details" not in table and "<caption>Caption</caption>" in table


class TestThePage:
    def test_no_plotly_and_no_reload_on_a_theme_change(self):
        assert "plotly" not in PAGE and "reload_on_theme_change" not in PAGE

    def test_fetches_this_period_the_one_before_and_a_week(self):
        assert "fetch_overview(days=activity.PERIOD, history_days=activity.HISTORY" in PAGE

    def test_the_parts_and_their_headings(self):
        for text in ('"Actions per day, the last 30 days"', 'heading("When it is used")', 'heading("Actions by type")',
                     '("user", "User actions"), ("admin", "Administrative actions")', 'heading("Latest actions")'):
            assert text in PAGE, text

    def test_the_trend_arrow_is_not_read_out(self):
        assert 'ui.icon(icon).props("aria-hidden=true")' in PAGE

    def test_the_comparison_says_when_the_figures_are_missing(self):
        assert "the statistics do not reach back over the whole of the 30 days before" in PAGE
        assert "The statistics begin on" in PAGE

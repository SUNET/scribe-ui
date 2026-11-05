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

"""The health page: what is read from the workers, the charts, the page."""

import json
import pathlib
from datetime import timezone

import pytest

from utils import worker_health as wh
from utils.line_chart import LINE_CHART_STYLES, STYLES, line_chart, runs, sparkline, time_marks

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "admin" / "health.py").read_text()
STYLESHEET = (ROOT / "utils" / "styles.py").read_text()

NOW = 1_800_000_000.0
GPU = {"index": 0, "name": "NVIDIA A100 80GB PCIe", "memory_used": 20480, "memory_total": 81920,
       "utilization": 71, "temperature": 64, "power_draw": 212}


def sample(seen, cpu=12.5, memory=40.0, gpus=(GPU,)):
    return {"load_avg": cpu, "memory_usage": memory, "gpu_usage": list(gpus), "seen": seen}


class TestWhatAWorkerReports:
    def test_a_gpu_as_scribe_worker_sends_it(self):
        (gpu,) = wh.gpus_of([GPU])

        assert (gpu.index, gpu.name, gpu.use, gpu.memory) == (0, "NVIDIA A100 80GB PCIe", 71.0, 25.0)

    def test_other_shapes_are_read_as_well_as_they_can_be(self):
        assert wh.gpus_of(GPU)[0].use == 71.0  # one dict
        assert wh.gpus_of(json.dumps([GPU]))[0].use == 71.0  # a JSON string
        assert wh.gpus_of(0) == [] and wh.gpus_of(None) == [] and wh.gpus_of("nonsense") == []
        assert wh.gpus_of([GPU, "x", 3]) and len(wh.gpus_of([GPU, "x", 3])) == 1

    def test_what_cannot_be_read_is_left_out_not_nought(self):
        (gpu,) = wh.gpus_of([{"index": 1, "utilization": None, "memory_used": 5, "memory_total": 0}])

        assert gpu.use is None and gpu.memory is None and gpu.index == 1
        assert wh.number("x") is None and wh.number(True) is None and wh.number(float("nan")) is None
        assert wh.percent(None) == "–"

    def test_load_avg_is_the_cpu_in_per_cent(self):
        (worker,) = wh.workers_of({"w": [sample(NOW - 5, cpu=37.4)]}, NOW)

        assert worker.readings[-1].cpu == 37.4
        assert "psutil.cpu_percent()" in (ROOT / "utils" / "worker_health.py").read_text()

    def test_readings_oldest_first_and_broken_ones_left_out(self):
        (worker,) = wh.workers_of({"w": [sample(NOW - 5), {"seen": "x"}, "x", sample(NOW - 15)]}, NOW)

        assert [r.seen for r in worker.readings] == [NOW - 15, NOW - 5]

    def test_a_worker_with_no_readings_is_not_shown(self):
        assert wh.workers_of({"w": []}, NOW) == [] and wh.workers_of(None, NOW) == []


class TestOnlineAndOffline:
    def test_offline_after_thirty_seconds(self):
        workers = wh.workers_of({"a": [sample(NOW - 29)], "b": [sample(NOW - 31)]}, NOW)

        assert {w.worker_id: w.online for w in workers} == {"a": True, "b": False}

    def test_the_offline_first_then_by_name_and_the_long_quiet_put_away(self):
        workers = wh.workers_of({
            "b-online": [sample(NOW - 5)],
            "a-online": [sample(NOW - 5)],
            "z-offline": [sample(NOW - 600)],
            "old": [sample(NOW - 3 * 86400)],
            "older": [sample(NOW - 5 * 86400)],
        }, NOW)
        shown, away = wh.arranged(workers, NOW)

        assert [w.worker_id for w in shown] == ["z-offline", "a-online", "b-online"]
        assert [w.worker_id for w in away] == ["old", "older"]

    def test_the_put_away_not_read_beyond_when_last_heard(self):
        (worker,) = wh.workers_of({"old": [sample(NOW - 3 * 86400 - 10), sample(NOW - 3 * 86400), "x"]}, NOW)

        assert worker.readings == [] and worker.last_seen == NOW - 3 * 86400 and not worker.online

    def test_an_offline_card_drawn_a_minute_at_a_time(self):
        on, off = wh.Worker("a", [], True, NOW), wh.Worker("b", [], False, NOW - 100)
        went = NOW - 100 + wh.OFFLINE_AFTER

        assert wh.drawn_at(on, NOW) == NOW
        assert wh.drawn_at(off, went) == went and wh.drawn_at(off, went + 59) == went
        assert wh.drawn_at(off, went + 60) == went + 60 and wh.drawn_at(off, went + 130) == went + 120

    def test_the_count_line(self):
        on, off = wh.Worker("a", [], True, NOW), wh.Worker("b", [], False, NOW)

        assert wh.count_line([off, on, on]) == "1 offline, 2 online."
        assert wh.count_line([on, on]) == "All 2 workers online."
        assert wh.count_line([off]) == "The worker is offline."
        assert wh.count_line([]) == "No worker has been heard from in the last 24 hours."

    def test_how_long_ago(self):
        assert wh.ago(720) == "12 minutes ago"
        assert wh.ago(60) == "1 minute ago"
        assert wh.ago(7200) == "2 hours ago"
        assert wh.ago(2) == "just now"

    def test_a_gpu_is_numbered_only_where_there_are_several(self):
        assert wh.gpu_label(0, [0]) == "GPU"
        assert wh.gpu_label(1, [0, 1]) == "GPU 1"


class TestTheChart:
    def chart(self, **kwargs):
        series = kwargs.pop("series", [("CPU", [(NOW - 600, 10), (NOW - 590, 20)])])
        return line_chart("CPU, %", series, NOW - wh.WINDOW, NOW, timezone.utc, **kwargs)

    def test_a_picture_only_its_title_included(self):
        chart = self.chart()

        assert chart.startswith('<div class="line-chart" aria-hidden="true">')
        assert "<h4" not in chart and '<div class="line-chart-title">CPU, %</div>' in chart

    def test_a_gap_breaks_the_line(self):
        points = [(0, 1), (10, 2), (20, 3), (100, 4), (110, None), (120, 5)]

        assert runs(points) == [[(0, 1), (10, 2), (20, 3)], [(100, 4)], [(120, 5)]]

    def test_offline_is_toned_and_said_not_drawn_as_noughts(self):
        chart = self.chart(quiet_from=NOW - 590)

        assert 'class="line-chart-offline"' in chart and "<span>Offline</span>" in chart
        assert "Offline" not in self.chart()

    def test_nothing_in_the_window_says_so(self):
        chart = self.chart(series=[("CPU", [(NOW - 5000, 10)])], empty="No readings in the last 30 minutes.")

        assert "line-chart-empty" in chart and "No readings in the last 30 minutes." in chart

    def test_several_series_have_a_legend_and_dashes_one_has_neither(self):
        two = self.chart(series=[("GPU 0", [(NOW - 60, 1)]), ("GPU 1", [(NOW - 60, 2)])])

        assert "line-chart-legend" in two and 'stroke-dasharray="6 4"' in two
        assert "line-chart-legend" not in self.chart()

    def test_a_lone_series_in_the_colour_it_is_given(self):
        assert f'stroke="{STYLES[0][0]}"' in self.chart(single=STYLES[0])
        assert 'stroke="var(--line-s3)"' in self.chart()

    def test_the_times_are_whole_ten_minutes(self):
        assert all(mark % 600 == 0 for mark in time_marks(NOW - wh.WINDOW, NOW))

    def test_escaped(self):
        chart = line_chart("<b>", [("<i>", [(NOW - 60, 1)]), ("x", [(NOW - 60, 2)])], NOW - 600, NOW)

        assert "<b>" not in chart and "<i>" not in chart

    def test_a_trend_line_is_a_picture_broken_where_readings_are_missing(self):
        line = sparkline([(NOW - 600, 10), (NOW - 590, 20), (NOW - 100, 30), (NOW - 90, None)], NOW - wh.WINDOW, NOW)

        assert line.startswith('<svg class="sparkline" aria-hidden="true"')
        assert line.count("<polyline") == 2
        assert "is-quiet" not in line
        assert 'class="is-quiet"' in sparkline([(NOW - 600, 10)], NOW - wh.WINDOW, NOW, quiet_from=NOW - 600)

    def test_the_colours_reach_the_trend_lines_too(self):
        # The custom properties were on .line-chart only, and a trend line
        # outside one had no colour at all.
        assert ".line-chart,\n    .sparkline {\n        --line-s1:" in LINE_CHART_STYLES
        assert ".body--dark .line-chart,\n    .body--dark .sparkline {" in LINE_CHART_STYLES

    def test_high_contrast_and_text_in_rem(self):
        assert "@media (forced-colors: active)" in LINE_CHART_STYLES
        assert "font-size: 0.75rem;" in LINE_CHART_STYLES


class TestThePage:
    def test_no_plotly_and_no_reload_on_a_theme_change(self):
        assert "plotly" not in PAGE and "reload_on_theme_change" not in PAGE

    def test_the_update_choices_and_off(self):
        assert wh.REFRESH_CHOICES == {0: "Off", 5: "5 s", 10: "10 s", 30: "30 s", 60: "1 min"}
        assert "ui.toggle(wh.REFRESH_CHOICES, value=chosen)" in PAGE
        assert 'role=group aria-labelledby="health-refresh-label"' in PAGE
        assert "poll.deactivate()" in PAGE and "poll.interval = seconds" in PAGE
        assert 'app.storage.user["health_refresh"] = seconds' in PAGE
        assert "update_now.on_click(render_health)" in PAGE

    def test_only_what_has_changed_is_changed(self):
        # A card is built once and then updated; its disclosure is not
        # redrawn, only the table inside it, so an open table stays open.
        assert "if element.content != content:" in PAGE
        assert 'ui.element("details").classes("chart-data")' in PAGE
        assert "self.table = ui.html(" in PAGE
        assert "if order != shown_order:" in PAGE

    def test_compact_the_charts_behind_a_disclosure_shut_at_each_opening(self):
        assert 'ui.label("Show the charts and the readings")' in PAGE
        assert 'self.more = ui.element("details").classes("chart-data health-more")' in PAGE
        # Kept while the page is open, so a card built again opens as it was.
        assert "opened: dict = {}" in PAGE and "if opened.get(worker_id):" in PAGE
        assert 'TOLD = "(event) => emit(event.target.open)"' in PAGE
        assert "app.storage" not in PAGE[PAGE.index("opened: dict = {}") - 200 : PAGE.index("opened: dict = {}")]

    def test_an_offline_card_drawn_a_minute_at_a_time(self):
        assert "now = wh.drawn_at(worker, now)" in PAGE
        assert PAGE.index("now = wh.drawn_at(worker, now)") > PAGE.index("Last heard from {when(worker.last_seen, now, zone)}")

    def test_focus_kept_when_the_cards_are_built_again(self):
        assert 'self.card._props["data-worker"] = worker_id' in PAGE
        assert "ui.add_body_html(KEEP_FOCUS)" in PAGE
        rebuilt = PAGE[PAGE.index("grid.clear()") : PAGE.index("shown_order = order")]
        assert 'ui.run_javascript("window.healthKeepFocus && window.healthKeepFocus()")' in rebuilt
        # Not taken back from wherever the user has gone on to.
        assert "if (now && now !== document.body) return;" in PAGE

    def test_the_charts_and_the_table_built_only_while_open(self):
        # Shut, they would be sent again with every update; the table alone
        # is some 1 000 elements a worker.
        assert 'self.set(self.cpu, cpu_group(worker, now, zone) if more else "")' in PAGE
        assert 'self.set(self.table, readings_table(worker, now, zone) if table else "")' in PAGE
        assert "table = more and bool(self.opened.get(self.key_table))" in PAGE
        assert PAGE.count("js_handler=TOLD") == 2
        assert "self.toggled(self.key, e.args)" in PAGE and "self.toggled(self.key_table, e.args)" in PAGE

    def test_the_figures_with_their_trend_lines(self):
        assert "f\"{sparkline(points, start, now, colour, quiet)}</li>\"" in PAGE
        assert '("CPU", latest.cpu,' in PAGE and '("Memory", latest.memory,' in PAGE
        assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in STYLESHEET

    def test_expand_all_and_collapse_all_in_the_browser(self):
        assert 'ui.button("Expand all", color=None)' in PAGE
        assert 'ui.button("Collapse all", color=None)' in PAGE
        assert "document.querySelectorAll('details.health-more').forEach(d => d.open = true)" in PAGE
        assert "document.querySelectorAll('details.health-more').forEach(d => d.open = false)" in PAGE

    def test_the_sentence_is_read_out_always_and_seen_with_the_charts(self):
        assert '"health-sentence chart-summary text-body1 text-theme-secondary"' in PAGE
        hidden = STYLESHEET[STYLESHEET.index("    .health-sentence {") :][:250]
        assert "clip: rect(0 0 0 0);" in hidden and "display: none" not in hidden
        assert ".health-card:has(> details.health-more[open]) .health-sentence {" in STYLESHEET

    def test_the_count_is_said_once_when_it_changes(self):
        assert 'count = ui.label("").classes("health-count").props("role=status")' in PAGE
        assert "if count.text != line:" in PAGE

    def test_headings(self):
        assert '<h2 id="{self.heading}">' in PAGE
        assert '<h3 class="health-group-title">CPU</h3>' in PAGE
        assert '<h3 class="health-group-title">GPU</h3>' in PAGE
        assert 'props(f\'aria-labelledby="{heading}"\')' in PAGE

    def test_offline_in_words_and_figures_not_guessed(self):
        assert "Last heard from" in PAGE

    def test_the_heartbeat_line_keeps_its_height_online(self):
        # Empty on an online worker, not hidden: the figures sit as far
        # below the name on every card.
        assert "self.last.set_visibility" not in PAGE
        assert '"" if worker.online else' in PAGE
        rule = STYLESHEET.split(".health-last {", 1)[1].split("}", 1)[0]
        assert "min-height: 1.5em" in rule and "line-height: 1.5" in rule
        assert "html.escape(wh.percent(value)) if worker.online else NOT_KNOWN" in PAGE
        assert 'NOT_KNOWN = \'<span aria-hidden="true">–</span><span class="sr-only">not known</span>\'' in PAGE
        assert ">Offline</span>" in PAGE and ">Online</span>" in PAGE

    def test_the_readings_in_a_table_newest_first(self):
        assert "reversed(wh.in_window(worker, now))" in PAGE
        assert "return table_html(" in PAGE
        # The region kept, so focus on it stays while the table changes.
        assert 'region = ui.element("div").classes("chart-scroll").props("role=region tabindex=0")' in PAGE
        assert 'region._props["aria-label"] = readings_caption(worker_id)' in PAGE

    def test_times_in_the_readers_zone(self):
        assert 'app.storage.user.get("timezone", "UTC")' in PAGE
        assert "Times are in {zone_name}." in PAGE

    def test_the_states_look(self):
        rule = STYLESHEET[STYLESHEET.index("    .health-state {") :]
        assert "border-radius: 999px;" in rule[:300]
        assert ".health-state.is-offline .health-dot {\n        border: 2px solid #b91c1c;" in STYLESHEET
        assert ".health-card.is-offline {\n        border-color: var(--color-status-error-border);" in STYLESHEET
        assert "grid-template-columns: repeat(auto-fit, minmax(min(26rem, 100%), 1fr));" in STYLESHEET
        assert "align-items: start;" in STYLESHEET[STYLESHEET.index("    .health-grid {") :][:300]

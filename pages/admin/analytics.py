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
Activity overview: what has been done in the service, from the backend's log
of actions. BOFH only.

Four summary cards (this period against the one before, with a trend arrow
said in words), the actions per day stacked by kind with a 7-day average,
a heat map of weekday and hour that is a table, the actions by type in two
tables, and the latest actions. Drawn by the page in HTML and CSS
(utils/bar_chart.py, utils/chart_tables.py), so it follows the theme
without a reload, and every chart has its figures in a table. What is
counted, and how, is in utils/activity.py.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from nicegui import app, ui

from db.analytics import fetch_overview
from utils import activity
from utils.bar_chart import NBSP, amount, day_label, figure, stacked_chart
from utils.chart_tables import chart_section, head_html, heat_table, phrased, shown_table, summary_cards
from utils.common import page_init
from utils.styles import default_styles



def number(value: int) -> str:
    """ "3 980": thousands set apart by a space that does not break."""

    return f"{value:,}".replace(",", NBSP)


def heading(text: str, level: int = 2) -> None:
    ui.html(phrased(text), sanitize=False).classes(
        "chart-heading text-xl font-semibold text-theme-primary"
    ).props(f"role=heading aria-level={level}")


def sentence(text: str) -> None:
    ui.html(phrased(text), sanitize=False).classes("chart-summary text-body1 text-theme-secondary")


@ui.page("/admin/analytics")
async def analytics() -> None:
    """
    Activity overview. BOFH only.
    """

    user_data = await page_init(use_drawer=True, title="Activity overview")

    if not (user_data or {}).get("bofh"):
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)
    ui.add_head_html(head_html())

    zone_name = app.storage.user.get("timezone", "UTC")

    try:
        zone = ZoneInfo(zone_name)
    except Exception:
        zone, zone_name = timezone.utc, "UTC"

    now = datetime.now(zone)
    offset = int(now.utcoffset().total_seconds() // 3600)
    today = now.date()

    data = await fetch_overview(days=activity.PERIOD, history_days=activity.HISTORY, recent_limit=50)
    summary, views, recent = data["summary"], data["views"], data["recent"]
    kinds, paths = activity.per_day(views)
    counted = activity.counted_from(views, summary)
    days, before_days = activity.periods(today)
    whole_before = activity.has_whole(before_days, counted)
    shown_kinds = list(activity.KINDS) + (
        [activity.OTHER] if activity.total(kinds, days + before_days, "other") else []
    )

    ui.label("Activity overview").classes("text-3xl font-bold").props("role=heading aria-level=1")
    ui.label(f"What has been done in the last 30 days. Times are in {zone_name}.").classes(
        "text-theme-secondary"
    )

    with ui.element("div").classes("stats-container w-full"):
        # ── The cards: this period against the one before ──
        def trend_line(kind: str):
            now_count = activity.total(kinds, days, kind)
            before = activity.total(kinds, before_days, kind) if whole_before else None
            compared = activity.trend(now_count, before)

            def draw() -> None:
                # No comparison where the log does not reach back over the
                # 30 days before: nothing is shown rather than a guess.
                if compared is None:
                    return

                icon, figure_text, words = compared

                with ui.element("div").classes("stats-trend"):
                    ui.icon(icon).props("aria-hidden=true")
                    ui.html(
                        f'<span><span class="stats-trend-figure">{figure_text}</span>{words}</span>',
                        sanitize=False,
                    )

            return draw

        def count_line(kind: str):
            def draw() -> None:
                ui.label(number(activity.total(kinds, days, kind))).classes("stats-tile-count")
                ui.label("in the last 30 days").classes("stats-tile-meta")

            return draw

        summary_cards([(name, [count_line(kind), trend_line(kind)]) for kind, name in shown_kinds])

        # ── The actions per day, by kind, and a 7-day average ──
        with ui.element("div").classes("chart-container"):
            per_kind = {kind: [kinds.get(day, {}).get(kind, 0) for day in days] for kind, _ in shown_kinds}
            all_days = [sum(per_kind[kind][at] for kind, _ in shown_kinds) for at in range(len(days))]
            averages = activity.rolling_average(kinds, days, counted)
            everything = sum(all_days)
            heading_text = "Actions per day, the last 30 days"

            if everything:
                busiest = max(range(len(days)), key=lambda at: all_days[at])
                words = (
                    f"{number(everything)} actions in all. Busiest day: {day_label(days[busiest])}, "
                    f"{amount(all_days[busiest], 'Actions')}"
                )
                kind, name = max(shown_kinds, key=lambda one: per_kind[one[0]][busiest])

                # Said only where one kind was most of the day.
                if per_kind[kind][busiest] > all_days[busiest] / 2 and len(shown_kinds) > 1:
                    words += f", {per_kind[kind][busiest]} of them {name.lower()}"

                words += "."

                # The log began within the period: say from when.
                if counted and days[0] < counted <= days[-1]:
                    words += f" The statistics begin on {day_label(counted)}."

                drawn = [value for value in averages if value is not None]

                if len(drawn) > 1:
                    words += (
                        f" 7-day average: {figure(round(drawn[-1]))} a{NBSP}day, "
                        f"from {figure(round(drawn[0]))} on {day_label(days[averages.index(drawn[0])])}."
                    )
            else:
                words = "Nothing was done in the last 30 days."

            chart_section(
                heading_text,
                words,
                stacked_chart(
                    days,
                    [{"name": name, "values": per_kind[kind]} for kind, name in shown_kinds],
                    unit="Actions",
                    line={"name": "7-day average", "values": averages},
                    counted_from=counted if counted and counted > days[0] else None,
                ),
                table_summary="Show the actions per day as a table",
                caption=heading_text,
                headers=("Date", *[name for _, name in shown_kinds], "All", "7-day average"),
                # The days counted only: a day before the statistics began
                # is not a day with nothing done.
                rows=[
                    (
                        day,
                        *[per_kind[kind][at] for kind, _ in shown_kinds],
                        all_days[at],
                        "–" if averages[at] is None else figure(round(averages[at])),
                    )
                    for at, day in enumerate(days)
                    if not (counted and day < counted)
                ],
                numeric=tuple(range(1, len(shown_kinds) + 3)),
                empty=not everything,
                wide=True,
            )

        # ── When: weekday and hour, as a heat map that is a table ──
        with ui.element("div").classes("chart-container"):
            matrix = activity.heat(data["heatmap"], offset)
            hours = [f"{hour:02d}" for hour in range(24)]
            heading("When it is used")

            if any(any(row) for row in matrix):
                day_at = max(range(7), key=lambda d: sum(matrix[d]))
                hour_at = max(range(24), key=lambda h: sum(matrix[d][h] for d in range(7)))
                peak = max(((d, h) for d in range(7) for h in range(24)), key=lambda one: matrix[one[0]][one[1]])
                sentence(
                    f"Busiest: {activity.WEEKDAYS[peak[0]]}s {peak[1]:02d}–{(peak[1] + 1) % 24:02d}. "
                    f"Busiest day: {activity.WEEKDAYS[day_at]}. Busiest hour: {hour_at:02d}–{(hour_at + 1) % 24:02d}."
                )
                ui.html(
                    heat_table(
                        list(activity.WEEKDAYS),
                        hours,
                        matrix,
                        f"Actions by day of the week and hour, the last 30 days, in {zone_name}",
                        lambda d, h: f"{activity.WEEKDAYS[d]} {h:02d}–{(h + 1) % 24:02d}",
                    ),
                    sanitize=False,
                ).classes("w-full")
            else:
                sentence("Nothing was done in the last 30 days.")

        # ── By type: the last 30 days, the 30 before, and all time ──
        with ui.element("div").classes("chart-container"):
            heading("Actions by type")
            sentence(
                "The last 30 days, the 30 days before, and since the statistics began."
                if whole_before
                else "The last 30 days, and since the statistics began."
            )
            # The 30 days before, only where the log covers them.
            headers = ("Action", "Last 30 days", "30 days before", "All time") if whole_before else ("Action", "Last 30 days", "All time")
            all_time = {row["path"]: int(row.get("total_views") or 0) for row in summary if activity.action(row.get("path", ""))}
            known = sorted(
                set(all_time) | {path for day in paths.values() for path in day},
                key=lambda path: list(activity.ACTIONS).index(path) if path in activity.ACTIONS else len(activity.ACTIONS),
            )

            def count(path: str, period) -> int:
                return sum(paths.get(day, {}).get(path, 0) for day in period)

            with ui.element("div").classes("chart-table-grid"):
                for table, title in (("user", "User actions"), ("admin", "Administrative actions"), ("other", "Other actions")):
                    chosen = [path for path in known if activity.action(path)[1] == table]

                    if table == "other" and not chosen:
                        continue

                    # Every action the backend logs, in its order; one it
                    # no longer logs only where there is something to count.
                    if table != "other":
                        chosen = [
                            path
                            for path, (_, group, _) in activity.ACTIONS.items()
                            if group == table
                            and (path not in activity.LEGACY or all_time.get(path) or count(path, days + before_days))
                        ]

                    with ui.element("div"):
                        heading(title, level=3)
                        ui.html(
                            shown_table(
                                title,
                                headers,
                                [
                                    (
                                        activity.action(path)[0],
                                        number(count(path, days)),
                                        *([number(count(path, before_days))] if whole_before else []),
                                        number(all_time.get(path, 0)),
                                    )
                                    for path in chosen
                                ],
                                numeric=tuple(range(1, len(headers))),
                            ),
                            sanitize=False,
                        ).classes("w-full")


        # ── The latest actions ──
        with ui.element("div").classes("chart-container"):
            heading("Latest actions")
            latest = []

            for row in recent:
                known_action = activity.action(row.get("path", ""))
                when = activity.moment(row.get("timestamp"), zone)

                if known_action and when:
                    latest.append((activity.when_label(when, today), known_action[0]))

            if latest:
                ui.html(
                    shown_table("The latest actions, newest first", ("Time", "Action"), latest[:10]),
                    sanitize=False,
                ).classes("w-full")
            else:
                sentence("Nothing has been done yet.")

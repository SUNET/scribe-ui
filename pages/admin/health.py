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
The worker health page: a card for each worker, online or offline in
words, its CPU and its GPU as figures, charts and a table.

What a worker reports, and how it is read, is in utils/worker_health.py;
the charts are utils/line_chart.py.

The page reads the backend again on a timer the reader chooses (or not at
all), and then changes only what has changed: the figures, the charts, the
tables. A card is not built again unless the workers or their order
change, so focus, an open table and the scroll stay where they were
(2.2.2). How many are online is said in a status line, once, when it
changes (4.1.3).
"""

import html
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from nicegui import app, ui
from utils import worker_health as wh
from utils.chart_tables import head_html as chart_head, phrased, table_region
from utils.common import page_init
from utils.line_chart import LINE_CHART_STYLES, SINGLE, STYLES, clock, line_chart, sparkline
from utils.styles import default_styles
from utils.settings import get_settings
from utils.token import (
    get_auth_header,
)

settings = get_settings()


def when(moment: float, now: float, zone) -> str:
    """A time today as 18:27:50; another day's as "4 Nov, 18:27:50"."""

    then = datetime.fromtimestamp(moment, zone)

    if then.date() == datetime.fromtimestamp(now, zone).date():
        return then.strftime("%H:%M:%S")

    return f"{then.day} {then.strftime('%b')}, {then.strftime('%H:%M:%S')}"


def summary_sentence(worker: wh.Worker, now: float, zone) -> str:
    """What the charts show, in a sentence: the highest of each, and when."""

    readings = wh.in_window(worker, now)

    if not readings:
        return "No readings in the last 30 minutes."

    parts = []
    cpu = wh.peak(readings, lambda r: r.cpu)

    if cpu:
        parts.append(f"CPU at most {wh.percent(cpu[1])} at {clock(cpu[0].seen, zone)}")

    indexes = worker.gpu_indexes
    best = None

    for index in indexes:
        found = wh.peak(readings, lambda r, i=index: wh.gpu_value(r, i, "use"))
        if found and (best is None or found[1] > best[2]):
            best = (index, found[0], found[1])

    if best:
        parts.append(f"{wh.gpu_label(best[0], indexes)} at most {wh.percent(best[2])} at {clock(best[1].seen, zone)}")

    if not parts:
        return "No figures in the last 30 minutes."

    lead = "The last 30 minutes" if worker.online else "Before that"

    return f"{lead}: {', '.join(parts)}."


def tiles(worker: wh.Worker, now: float, zone) -> str:
    """
    The latest figures as a list of tiles, each with a trend line of the
    last 30 minutes: CPU and Memory, then use and memory for each GPU.
    An offline worker's figures are "–": what it is doing now is not known.
    """

    readings = wh.in_window(worker, now)
    latest = worker.readings[-1]
    start, quiet = now - wh.WINDOW, None if worker.online else worker.last_seen
    indexes = worker.gpu_indexes
    items = [
        ("CPU", latest.cpu, [(r.seen, r.cpu) for r in readings], SINGLE[0]),
        ("Memory", latest.memory, [(r.seen, r.memory) for r in readings], SINGLE[0]),
    ]

    for index in indexes:
        label = wh.gpu_label(index, indexes)
        items += [
            (label, wh.gpu_value(latest, index, "use"),
             [(r.seen, wh.gpu_value(r, index, "use")) for r in readings], STYLES[0][0]),
            (f"{label} memory", wh.gpu_value(latest, index, "memory"),
             [(r.seen, wh.gpu_value(r, index, "memory")) for r in readings], STYLES[0][0]),
        ]

    return (
        '<ul class="health-figures" role="list">'
        + "".join(
            f'<li><span class="health-figure-label">{html.escape(label)}</span>'
            f'<span class="health-figure-value">{html.escape(wh.percent(value) if worker.online else "–")}</span>'
            f"{sparkline(points, start, now, colour, quiet)}</li>"
            for label, value, points, colour in items
        )
        + "</ul>"
    )


def cpu_group(worker: wh.Worker, now: float, zone) -> str:
    readings = wh.in_window(worker, now)
    start, quiet = now - wh.WINDOW, None if worker.online else worker.last_seen

    return (
        '<h3 class="health-group-title">CPU</h3>'
        '<div class="health-charts">'
        + line_chart("CPU, %", [("CPU", [(r.seen, r.cpu) for r in readings])], start, now, zone, quiet)
        + line_chart("Memory, %", [("Memory", [(r.seen, r.memory) for r in readings])], start, now, zone, quiet)
        + "</div>"
    )


def gpu_group(worker: wh.Worker, now: float, zone) -> str:
    indexes = worker.gpu_indexes
    readings = wh.in_window(worker, now)
    start, quiet = now - wh.WINDOW, None if worker.online else worker.last_seen
    name = worker.gpu_name()

    def series(what):
        return [
            (wh.gpu_label(index, indexes), [(r.seen, wh.gpu_value(r, index, what)) for r in readings])
            for index in indexes
        ]

    return (
        '<h3 class="health-group-title">GPU</h3>'
        + (f'<p class="health-group-sub">{html.escape(name)}</p>' if name else "")
        + '<div class="health-charts">'
        # The GPU's lines in the first colours (blue, then orange), the
        # CPU's in the green of a lone series: the two groups read apart.
        + line_chart("GPU use, %", series("use"), start, now, zone, quiet, single=STYLES[0])
        + line_chart("GPU memory, %", series("memory"), start, now, zone, quiet, single=STYLES[0])
        + "</div>"
    )


def readings_table(worker: wh.Worker, now: float, zone) -> str:
    indexes = worker.gpu_indexes
    headers = ["Time", "CPU", "Memory"]

    for index in indexes:
        label = wh.gpu_label(index, indexes)
        headers += [label, f"{label} memory"]

    rows = []

    for reading in reversed(wh.in_window(worker, now)):
        row = [clock(reading.seen, zone, seconds=True), wh.percent(reading.cpu), wh.percent(reading.memory)]
        for index in indexes:
            row += [wh.percent(wh.gpu_value(reading, index, "use")), wh.percent(wh.gpu_value(reading, index, "memory"))]
        rows.append(row)

    return table_region(
        f"Readings for {worker.worker_id}, the last 30 minutes, newest first",
        headers,
        rows,
        numeric=tuple(range(1, len(headers))),
    )


# A details element tells the server when it is opened or shut.
TOLD = "(event) => emit(event.target.open)"


class WorkerCard:
    """
    One worker's card, built once and then only changed. Compact: the name,
    the state, and the figures with their trend lines; the charts and the
    readings behind "Show the charts and the readings", shut each time the
    page is opened (and kept as they are while it is open).

    The charts and the table are only built, and only sent, while they are
    open: shut, they would be sent again with every update all the same,
    and the readings table alone is some 1 000 elements a worker.
    """

    count = 0

    def __init__(self, worker: wh.Worker, now: float, zone, opened: dict) -> None:
        WorkerCard.count += 1
        heading = f"health-worker-{WorkerCard.count}"
        worker_id = worker.worker_id
        self.opened = opened
        self.key = worker_id
        self.key_table = (worker_id, "table")

        with ui.element("section").classes("health-card").props(f'aria-labelledby="{heading}"') as self.card:
            self.head = ui.html("", sanitize=False)
            self.heading = heading
            self.last = ui.html("", sanitize=False).classes("health-last")
            self.tiles = ui.html("", sanitize=False)
            # What the charts show, in words: read out always, seen with the
            # charts (utils/styles.py, .health-sentence).
            self.sentence = ui.html("", sanitize=False).classes(
                "health-sentence chart-summary text-body1 text-theme-secondary"
            )

            # Built once, and its open state told to the server, so a card
            # built again (the workers' order changed) opens as it was.
            self.more = ui.element("details").classes("chart-data health-more")
            if opened.get(worker_id):
                self.more.props("open")
            self.more.on("toggle", lambda e: self.toggled(self.key, e.args), js_handler=TOLD)

            with self.more:
                with ui.element("summary"):
                    ui.label("Show the charts and the readings")

                with ui.element("div").classes("health-groups"):
                    self.cpu = ui.html("", sanitize=False).classes("health-group")
                    self.gpu = ui.html("", sanitize=False).classes("health-group")

                # Only the table inside is changed, so it stays open while
                # the figures come in.
                with ui.element("details").classes("chart-data") as box:
                    if opened.get(self.key_table):
                        box.props("open")
                    box.on("toggle", lambda e: self.toggled(self.key_table, e.args), js_handler=TOLD)
                    with ui.element("summary"):
                        ui.label("Show the readings as a table")
                    self.table = ui.html("", sanitize=False).classes("w-full")

        self.update(worker, now, zone)

    def update(self, worker: wh.Worker, now: float, zone) -> None:
        name = html.escape(worker.worker_id)
        state = (
            '<span class="health-state is-online"><span class="health-dot" aria-hidden="true"></span>Online</span>'
            if worker.online
            else '<span class="health-state is-offline"><span class="health-dot" aria-hidden="true"></span>Offline</span>'
        )

        self.card.classes(remove="is-offline" if worker.online else "", add="" if worker.online else "is-offline")
        self.set(self.head, f'<div class="health-head"><h2 id="{self.heading}">{name}</h2>{state}</div>')
        # An offline worker's last heartbeat. The line keeps its height,
        # empty, on an online worker, so the figures sit as far below the
        # name on every card and the closed cards are the same height.
        self.set(
            self.last,
            "" if worker.online else
            f"Last heard from {when(worker.last_seen, now, zone)}, {wh.ago(now - worker.last_seen)}.",
        )
        # From here on, an offline worker's card a minute at a time.
        now = wh.drawn_at(worker, now)
        self.set(self.tiles, tiles(worker, now, zone))
        self.set(self.sentence, phrased(summary_sentence(worker, now, zone)))
        self.now_showing = (worker, now, zone)
        self.fill()

    def toggled(self, key, is_open) -> None:
        self.opened[key] = bool(is_open)
        self.fill()

    def fill(self) -> None:
        """The charts and the table, while they are open; else nothing."""

        worker, now, zone = self.now_showing
        more = bool(self.opened.get(self.key))
        table = more and bool(self.opened.get(self.key_table))

        self.set(self.cpu, cpu_group(worker, now, zone) if more else "")
        self.set(self.gpu, gpu_group(worker, now, zone) if more and worker.gpu_indexes else "")
        self.gpu.set_visibility(bool(worker.gpu_indexes))
        self.set(self.table, readings_table(worker, now, zone) if table else "")

    @staticmethod
    def set(element, content: str) -> None:
        # Only what has changed is sent: an unchanged part is left alone.
        if element.content != content:
            element.set_content(content)


@ui.page("/health")
async def health() -> None:
    """
    Health check dashboard displaying backend system metrics.
    """

    user_data = await page_init(use_drawer=True, title="System health")
    # The charts are drawn by the page in the theme's own custom properties
    # (utils/line_chart.py), so a change of theme needs no reload here.

    if not (user_data or {}).get("bofh"):
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)
    ui.add_head_html(chart_head())
    ui.add_head_html(LINE_CHART_STYLES)

    zone_name = app.storage.user.get("timezone", "UTC")

    try:
        zone = ZoneInfo(zone_name)
    except Exception:
        zone, zone_name = timezone.utc, "UTC"

    chosen = app.storage.user.get("health_refresh", wh.REFRESH_DEFAULT)
    if chosen not in wh.REFRESH_CHOICES:
        chosen = wh.REFRESH_DEFAULT

    with ui.element("div").classes("health"):
        with ui.element("div").classes("health-bar"):
            with ui.element("div"):
                ui.label("System status").classes("text-3xl font-bold").props("role=heading aria-level=1")
                # Said when it changes, and only then (4.1.3).
                count = ui.label("").classes("health-count").props("role=status")

            with ui.element("div").classes("health-controls"):
                ui.label("Update").classes("health-refresh-label").props('id="health-refresh-label"')
                refresh_choice = ui.toggle(wh.REFRESH_CHOICES, value=chosen).classes("health-refresh").props(
                    'no-caps unelevated role=group aria-labelledby="health-refresh-label"'
                )
                # color=None: the theme's text colour (utils/styles.py), not
                # Quasar's primary, which is 3:1 on the dark card.
                # Every card's charts at once, in the browser: each card tells
                # the server its own (WorkerCard, "toggle").
                with ui.element("div").classes("health-all"):
                    ui.button("Expand all", color=None).props("flat no-caps").classes("health-all-button").on(
                        "click", js_handler="() => document.querySelectorAll('details.health-more').forEach(d => d.open = true)"
                    )
                    ui.button("Collapse all", color=None).props("flat no-caps").classes("health-all-button").on(
                        "click", js_handler="() => document.querySelectorAll('details.health-more').forEach(d => d.open = false)"
                    )
                update_now = ui.button("Update now", icon="refresh", color=None).props("flat no-caps").classes(
                    "health-update-now"
                )
                updated = ui.label("").classes("health-updated")

        reachability_alert = ui.label("Backend is not reachable").classes("text-lg").style(
            "color: var(--color-text-danger);"
        ).props("role=alert")
        reachability_alert.set_visibility(False)
        last_backend_reachable = None

        grid = ui.element("div").classes("health-grid")
        put_away = ui.element("div")
        ui.label(
            f"Times are in {zone_name}. A worker is offline when it has not been heard from "
            f"for {wh.OFFLINE_AFTER} seconds; one not heard from in 24 hours is put away at the foot of the page."
        ).classes("health-note")

    cards: dict = {}
    # Which cards' charts are open, while the page is: shut at each opening.
    opened: dict = {}
    shown_order: list = []
    away_order: list = []

    async def render_health() -> None:
        nonlocal last_backend_reachable, shown_order, away_order
        # Awaited, so the poll below leaves the event loop free while the
        # backend answers. A blocking call here would stall every other
        # page this server is serving, not just this one.
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(
                    settings.API_URL + "/api/v1/healthcheck",
                    headers=get_auth_header(),
                )
            res.raise_for_status()
            data = res.json()["result"]
            backend_reachable = True
        except Exception:
            data = {}
            backend_reachable = False

        if backend_reachable != last_backend_reachable:
            reachability_alert.set_text(
                "" if backend_reachable else "Backend is not reachable"
            )
            reachability_alert.set_visibility(not backend_reachable)
            last_backend_reachable = backend_reachable

        if not backend_reachable:
            return

        now = time.time()
        shown, away = wh.arranged(wh.workers_of(data, now), now)
        order = [(w.worker_id, w.online) for w in shown]

        if order != shown_order:
            # Other workers, or another order (one has gone offline and
            # comes first now): the cards are built again.
            grid.clear()
            cards.clear()

            with grid:
                for worker in shown:
                    cards[worker.worker_id] = WorkerCard(worker, now, zone, opened)

            shown_order = order
        else:
            for worker in shown:
                cards[worker.worker_id].update(worker, now, zone)

        names = [(w.worker_id, w.last_seen) for w in away]

        if names != away_order:
            put_away.clear()

            if away:
                with put_away:
                    with ui.element("details").classes("chart-data health-put-away"):
                        with ui.element("summary"):
                            ui.label(f"Not heard from in 24 hours ({len(away)})")
                        ui.html(
                            '<ul class="health-away-list">'
                            + "".join(
                                f"<li>{html.escape(w.worker_id)}, last heard from {when(w.last_seen, now, zone)}</li>"
                                for w in away
                            )
                            + "</ul>",
                            sanitize=False,
                        )

            away_order = names

        line = wh.count_line(shown)

        if count.text != line:
            count.set_text(line)

        updated.set_text(f"Updated {clock(now, zone, seconds=True)}")

    def choose(event) -> None:
        seconds = event.value if event.value in wh.REFRESH_CHOICES else wh.REFRESH_DEFAULT
        app.storage.user["health_refresh"] = seconds

        if seconds:
            poll.interval = seconds
            poll.activate()
        else:
            poll.deactivate()

    await render_health()

    # Read again as often as the reader has chosen, or not at all ("Off"):
    # the picture then holds still for reading and comparing (2.2.2), and
    # "Update now" reads once.
    poll = ui.timer(chosen or wh.REFRESH_DEFAULT, render_health, active=bool(chosen))
    refresh_choice.on_value_change(choose)
    update_now.on_click(render_health)

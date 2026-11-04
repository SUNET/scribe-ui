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
A bar chart drawn by the page itself, in its own colours and type.

Plotly drew its charts in a look of its own, in one theme's colours worked
out on the server, so a page with one had to reload when the system changed
between light and dark. This is plain HTML and CSS: the bars take the theme's
custom properties, so they change with it, and the labels are text in the
page's own face, so they grow with the reader's text size (WCAG 1.4.4) and do
not shrink with the width of the chart, as text in an SVG drawn to a viewBox
does.

It is a picture. chart_section() (utils/chart_tables.py) puts it inside a
wrapper that assistive technology skips and gives the numbers as a table, so
nothing here has to be read out or reached with a keyboard. A bar carries its
value in a title attribute, which the browser shows as its own tooltip under a
pointer: a convenience, the same figures as the table.
"""

import calendar
import html
import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional, Sequence

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Written out, not calendar.month_name: that follows the server's locale,
# and the page is in English.
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# Between a figure and its unit, a day and its month, a month and its year:
# a narrow card breaks the line elsewhere, not into "1.3 / minutes".
NBSP = "\u00a0"

# At most this many labels under the bars; the rest are left out, evenly.
MAX_LABELS = 8

BAR_CHART_STYLES = """
<style>
    .bar-chart {
        --chart-bar: var(--color-brand-primary);
        --chart-bar-previous: #6d8fb8;
        --chart-grid: #e5e7eb;
        /* The days still to come: a tone over them, and an edge where they
           begin. The tone is a help only (it is under 3:1); the sentence
           says "so far" for a month under way. */
        --chart-future: rgba(15, 23, 42, 0.065);
        --chart-future-edge: var(--color-text-secondary);
        --chart-height: 13rem;
        font-family: var(--font-sans);
        font-size: 0.8125rem;
        color: var(--color-text-tertiary);
        display: grid;
        /* minmax(0, ...): without it the labels' own width could push the
           plot out of a narrow card. */
        grid-template-columns: auto minmax(0, 1fr);
        container-type: inline-size;
        grid-template-rows: auto var(--chart-height) auto;
        column-gap: 0.5rem;
        width: 100%;
        margin: 0.75rem 0 0.25rem;
    }
    .body--dark .bar-chart {
        --chart-bar-previous: #c7ccd3;
        --chart-grid: #2c313a;
        --chart-future: rgba(255, 255, 255, 0.065);
    }
    .bar-chart-unit {
        grid-column: 1 / 3;
        margin-bottom: 0.25rem;
    }
    .bar-chart-ticks {
        position: relative;
        grid-row: 2;
        min-width: 2rem;
        text-align: right;
        font-variant-numeric: tabular-nums;
    }
    .bar-chart-ticks span {
        position: absolute;
        right: 0;
        transform: translateY(50%);
        line-height: 1;
    }
    .bar-chart-plot {
        position: relative;
        grid-row: 2;
        display: flex;
        align-items: flex-end;
        gap: 2px;
        border-bottom: 1px solid var(--color-border-subtle);
    }
    .bar-chart-grid {
        position: absolute;
        left: 0;
        right: 0;
        border-top: 1px solid var(--chart-grid);
        pointer-events: none;
    }
    /* A column for each label: the whole height, so a short bar is as easy
       to point at as a tall one, and the tooltip is the column's. */
    .bar-chart-slot {
        position: relative;
        flex: 1 1 0;
        height: 100%;
        display: flex;
        align-items: flex-end;
        justify-content: center;
        gap: 1px;
        min-width: 0;
    }
    .bar-chart-bar {
        flex: 0 1 70%;
        max-width: 2.5rem;
        background: var(--chart-bar);
        border-radius: 3px 3px 0 0;
    }
    .bar-chart-slot:hover .bar-chart-bar {
        filter: brightness(1.2);
    }
    /* Over the gaps between the slots too, so the tone is one piece. */
    .bar-chart-slot.is-future {
        background: var(--chart-future);
        box-shadow: -1px 0 0 var(--chart-future), 1px 0 0 var(--chart-future);
    }
    .bar-chart-slot.is-future.is-first-future {
        box-shadow: 1px 0 0 var(--chart-future);
    }
    .bar-chart-slot.is-first-future::before {
        content: "";
        position: absolute;
        top: 0;
        bottom: 0;
        left: -1px;
        border-left: 1px dashed var(--chart-future-edge);
    }
    /* Two series side by side are told apart by more than colour (1.4.1):
       the second is striped. */
    .bar-chart-bar.is-previous,
    .bar-chart-legend i.is-previous {
        background: repeating-linear-gradient(
            135deg,
            var(--chart-bar-previous) 0 3px,
            transparent 3px 6px
        );
        box-shadow: inset 0 0 0 1px var(--chart-bar-previous);
    }
    .bar-chart-labels {
        grid-column: 2;
        display: flex;
        gap: 2px;
        margin-top: 0.375rem;
    }
    .bar-chart-labels span {
        flex: 1 1 0;
        min-width: 0;
        text-align: center;
        white-space: nowrap;
        overflow: visible;
    }
    /* In a narrow chart every other label goes, so they do not run into
       each other. */
    @container (max-width: 34rem) {
        .bar-chart-labels span.is-minor {
            visibility: hidden;
        }
    }
    .bar-chart-legend {
        grid-column: 2;
        display: flex;
        gap: 1.25rem;
        margin-top: 0.5rem;
        color: var(--color-text-secondary);
    }
    .bar-chart-legend i {
        display: inline-block;
        width: 0.75rem;
        height: 0.75rem;
        margin-right: 0.375rem;
        border-radius: 2px;
        vertical-align: -0.1em;
        background: var(--chart-bar);
    }
    /* Windows high contrast takes backgrounds away; the bars keep a colour. */
    @media (forced-colors: active) {
        .bar-chart-bar,
        .bar-chart-legend i {
            forced-color-adjust: none;
            background: CanvasText;
        }
        .bar-chart-bar.is-previous,
        .bar-chart-legend i.is-previous {
            background: GrayText;
        }
    }
</style>
"""


def day_label(day: str) -> str:
    """ "2026-10-15" as "15 Oct"; anything else as it is. """

    try:
        moment = date.fromisoformat(day)
    except (TypeError, ValueError):
        return str(day)

    return f"{moment.day}{NBSP}{MONTHS[moment.month - 1]}"


def nice_ticks(highest: float, count: int = 4, whole: bool = False) -> list:
    """
    Round numbers for the scale, from 0 to the first at or above `highest`:
    steps of 1, 2, 2.5 or 5 times a power of ten, no more than `count` of
    them, and the top as close above the highest value as they allow (more
    steps where two come out the same). `whole` keeps to whole steps of at
    least 1, for a scale with no decimals in it.
    """

    if not highest or highest <= 0:
        return [0, 1]

    power = math.floor(math.log10(highest / count))
    candidates = [
        n * 10.0**p for p in (power - 1, power, power + 1) for n in (1, 2, 2.5, 5)
    ]
    if whole:
        power = max(power, 0)
        candidates = [
            n * 10.0**p for p in (power - 1, power, power + 1) for n in (1, 2, 2.5, 5)
        ]
        candidates = [step for step in candidates if step >= 1 and float(step).is_integer()]

    fitting = [step for step in candidates if math.ceil(highest / step - 1e-9) <= count]
    step = min(
        fitting,
        key=lambda step: (math.ceil(highest / step - 1e-9) * step, step),
    )
    steps = math.ceil(highest / step - 1e-9)

    return [round(step * n, 10) for n in range(steps + 1)]


def decimals_for(values: Iterable) -> int:
    """
    How many decimals a page shows its minutes with: one when its largest
    figure is under 10 (where 7 and 7.4 are not far apart, but 0 and 0.4
    are), none otherwise. One precision for the whole page, so that a
    column of figures lines up and two months read alike.
    """

    highest = max((float(value or 0) for value in values), default=0)

    return 1 if highest < 9.95 else 0


def rounded(value, decimals: int = 0) -> str:
    """
    A figure as it is shown: to `decimals` places, half up ("7.0" when
    there is one, so a column lines up). The sums are made of the figures
    as they are; only what is shown is rounded. Above nought but too small
    to show is "<1" or "<0.1", so a day with a bar never says 0.
    """

    value = Decimal(str(float(value or 0)))
    step = Decimal(1).scaleb(-decimals)

    if value <= 0:
        return f"{Decimal(0).quantize(step):f}"

    shown = value.quantize(step, rounding=ROUND_HALF_UP)

    if shown == 0:
        return f"<{step:f}"

    return f"{shown:f}"


def amount(value, unit: str = "Minutes", decimals: int = 0) -> str:
    """ "12 minutes", "1 minute", "7.4 minutes", "under 1 minute", "0 minutes". """

    shown = rounded(value, decimals)
    word = unit.lower()
    one = word[:-1] if word.endswith("s") else word

    if shown.startswith("<"):
        return f"under {shown[1:]}{NBSP}{one}"

    return f"{shown}{NBSP}{one if shown == '1' else word}"


def month_name(day: str) -> str:
    """ "2026-11-03" as "November 2026"; anything else as it is. """

    try:
        moment = date.fromisoformat(str(day))
    except ValueError:
        return str(day)

    return f"{MONTH_NAMES[moment.month - 1]}{NBSP}{moment.year}"


def figure(value: float) -> str:
    """A tick or a value: whole numbers without a decimal, others with one."""

    return f"{value:.0f}" if float(value).is_integer() else f"{value:.1f}"


def month_days(days: Iterable[str], fallback: date) -> list:
    """
    Every day of the month that `days` are in ("2026-11-01" to "2026-11-30"),
    or of `fallback`'s month when there are none: a chart of a month is the
    whole month, so two months are drawn to the same width and a day so far
    this month is where it will be at the end of it. Days that are not dates
    are given back as they are.
    """

    days = list(days)
    parsed = []

    for day in days:
        try:
            parsed.append(date.fromisoformat(str(day)))
        except ValueError:
            return days

    first = (parsed[0] if parsed else fallback).replace(day=1)
    length = calendar.monthrange(first.year, first.month)[1]

    return [first.replace(day=n).isoformat() for n in range(1, length + 1)]


def bar_chart(
    labels: Sequence[str],
    series: Sequence[dict],
    unit: str = "Minutes",
    legend: bool = False,
    label_every: Optional[int] = None,
    highest: Optional[float] = None,
    decimals: int = 0,
    future_after: Optional[str] = None,
) -> str:
    """
    A bar chart as HTML. `labels` are the slots along the bottom (dates are
    shown as "15 Oct"); `series` is one or more {"name", "values", "tone"}
    ("current" or "previous"), drawn side by side in each slot. A value of
    nothing (None) draws no bar and no tooltip -- a day still to come; a
    nought draws no bar but says so. Each slot's tooltip gives its values.
    `highest` puts the scale at least that high, so two charts read alike;
    `decimals` is how the tooltips show the figures (decimals_for()).
    `future_after` is today, as "2026-11-04": the days after it are toned,
    with an edge where they begin (labels compared as ISO dates).
    """

    values = [value or 0 for one in series for value in one["values"]]
    ticks = nice_ticks(max(values + [highest or 0]), whole=True)
    top = ticks[-1] or 1
    every = label_every or max(1, math.ceil(len(labels) / MAX_LABELS))

    def bar(value, tone) -> str:
        if not value or value <= 0:
            return ""

        height = round(100 * value / top, 3)
        previous = " is-previous" if tone == "previous" else ""

        return f'<span class="bar-chart-bar{previous}" style="height: {height}%"></span>'

    slots = []
    first_future = True

    for at, label in enumerate(labels):
        shown = [
            (one, one["values"][at] if at < len(one["values"]) else None) for one in series
        ]
        tip = "; ".join(
            (f"{one['name']}: " if len(series) > 1 else "")
            + amount(value, unit, decimals)
            for one, value in shown
        )
        title = (
            ""
            if all(value is None for _, value in shown)
            else f' title="{html.escape(day_label(label) + ": " + tip, quote=True)}"'
        )
        future = ""

        if future_after and str(label) > future_after:
            future = " is-future" + (" is-first-future" if first_future else "")
            first_future = False

        slots.append(
            f'<div class="bar-chart-slot{future}"{title}>'
            + "".join(bar(value, one.get("tone", "current")) for one, value in shown)
            + "</div>"
        )

    grid = "".join(
        f'<div class="bar-chart-grid" style="bottom: {round(100 * tick / top, 3)}%"></div>'
        for tick in ticks[1:]
    )
    scale = "".join(
        f'<span style="bottom: {round(100 * tick / top, 3)}%">{figure(tick)}</span>'
        for tick in ticks
    )
    shown = math.ceil(len(labels) / every)

    def name(at: int, label: str) -> str:
        if at % every:
            return "<span></span>"

        # Only where there are enough labels for them to crowd.
        minor = ' class="is-minor"' if shown > 4 and (at // every) % 2 else ""

        return f"<span{minor}>{html.escape(day_label(label))}</span>"

    names = "".join(name(at, label) for at, label in enumerate(labels))
    key = ""

    if legend:
        key = '<div class="bar-chart-legend">' + "".join(
            f'<span><i class="{"is-previous" if one.get("tone") == "previous" else ""}"></i>'
            f"{html.escape(one['name'])}</span>"
            for one in series
        ) + "</div>"

    return (
        '<div class="bar-chart">'
        f'<div class="bar-chart-unit">{html.escape(unit)}</div>'
        f'<div class="bar-chart-ticks">{scale}</div>'
        f'<div class="bar-chart-plot">{grid}{"".join(slots)}</div>'
        f'<div class="bar-chart-labels">{names}</div>'
        f"{key}"
        "</div>"
    )

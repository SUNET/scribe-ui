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
A line chart over time, drawn by the page: figures in per cent along a
window of time that ends now (the health page).

The scale, the times and the legend are HTML, in rem, so they grow with the
browser's text size (1.4.4); only the lines are an SVG, stretched to the
plot with lines of one width whatever its size. The chart is a picture for
those who see it, its title included: the page gives the latest figures
under a heading of their own, says what the charts show in a sentence and
has the same figures in a table, so the whole chart is aria-hidden.

A line breaks where readings are missing rather than being drawn across
the gap, and the time after the last reading of a worker that has gone
quiet is toned and marked "Offline": no figures, not noughts. A nought
would say the GPU stood idle; a worker that has hung may as well be at
100 %.
"""

import html
from datetime import datetime, timezone, tzinfo
from typing import Optional, Sequence

# The series' colours (the data-viz palette's first slots, validated for
# colour blindness against the cards in both themes, as on the activity
# overview) and dashes, so two lines read apart by more than their hue.
STYLES = (
    ("var(--line-s1)", ""),
    ("var(--line-s2)", "6 4"),
    ("var(--line-s4)", "2 3"),
    ("var(--line-s5)", "10 3 2 3"),
)
# A single series in a group of its own (the CPU's two charts).
SINGLE = ("var(--line-s3)", "")

# A gap of more than this between two readings breaks the line: a worker
# posts every ten seconds, so this is two missed.
GAP = 35

LINE_CHART_STYLES = """
<style>
    /* The colours, for the charts and the tiles' trend lines alike. */
    .line-chart,
    .sparkline {
        --line-s1: #2a78d6;
        --line-s2: #eb6834;
        --line-s3: #1baf7a;
        --line-s4: #eda100;
        --line-s5: #e87ba4;
        --line-grid: #e5e7eb;
        min-width: 0;
    }
    .body--dark .line-chart,
    .body--dark .sparkline {
        --line-s1: #3987e5;
        --line-s2: #d95926;
        --line-s3: #199e70;
        --line-s4: #c98500;
        --line-s5: #d55181;
        --line-grid: #2c2f36;
    }
    .line-chart-title {
        font-size: 0.9375rem;
        font-weight: 600;
        margin: 0 0 0.625rem;
        color: var(--color-text-primary);
    }
    .line-chart-plot {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr);
        column-gap: 0.5rem;
    }
    .line-chart-scale {
        position: relative;
        width: 2.75rem;
        height: 6.5rem;
        font-size: 0.75rem;
        color: var(--color-text-secondary);
    }
    .line-chart-scale span {
        position: absolute;
        right: 0;
        transform: translateY(50%);
        white-space: nowrap;
    }
    .line-chart-area {
        position: relative;
        height: 6.5rem;
        border-bottom: 1px solid var(--color-border-subtle);
    }
    .line-chart-area svg {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        overflow: visible;
    }
    .line-chart-area polyline {
        fill: none;
        stroke-width: 2.25;
        stroke-linejoin: round;
    }
    .line-chart-grid {
        position: absolute;
        left: 0;
        right: 0;
        border-top: 1px solid var(--line-grid);
    }
    /* After the last reading of a worker gone quiet: toned and marked, so
       the quiet is seen as quiet, not as noughts. */
    .line-chart-offline {
        position: absolute;
        top: 0;
        bottom: 0;
        right: 0;
        border-left: 1px dashed var(--color-text-secondary);
        background: repeating-linear-gradient(
            -45deg,
            color-mix(in srgb, var(--color-text-secondary) 12%, transparent) 0 6px,
            transparent 6px 12px
        );
    }
    /* The word at the chart's right edge, so it is whole however little
       of the time is toned: it reaches back over the lines when it has to,
       on the card's own colour, and never out past the chart. */
    .line-chart-offline span {
        position: absolute;
        top: 0.125rem;
        right: 0.25rem;
        padding: 0 0.25rem;
        border-radius: 0.25rem;
        background: var(--color-bg-surface);
        font-size: 0.75rem;
        font-weight: 600;
        color: var(--color-text-secondary);
        white-space: nowrap;
    }
    .line-chart-times {
        grid-column: 2;
        position: relative;
        height: 1.25rem;
        margin-top: 0.25rem;
        font-size: 0.75rem;
        color: var(--color-text-secondary);
    }
    .line-chart-times span {
        position: absolute;
        transform: translateX(-50%);
        white-space: nowrap;
    }
    .line-chart-legend {
        list-style: none;
        margin: 0.375rem 0 0;
        padding: 0;
        display: flex;
        flex-wrap: wrap;
        gap: 0.25rem 1rem;
        font-size: 0.875rem;
        color: var(--color-text-primary);
    }
    .line-chart-legend li {
        display: inline-flex;
        align-items: center;
        gap: 0.375rem;
    }
    .line-chart-legend svg {
        width: 1.5rem;
        height: 0.5rem;
        overflow: visible;
    }
    .line-chart-empty {
        height: 6.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px dashed var(--color-border-subtle);
        border-radius: 0.5rem;
        color: var(--color-text-secondary);
        font-size: 0.875rem;
    }
    /* A trend line in a figure's tile: the same 30 minutes, no scale, no
       times; the time after a quiet worker's last reading toned. */
    .sparkline {
        display: block;
        width: 100%;
        height: 1.75rem;
        margin-top: 0.25rem;
        overflow: visible;
    }
    .sparkline polyline {
        fill: none;
        stroke-width: 1.75;
        stroke-linejoin: round;
    }
    .sparkline .is-quiet {
        fill: color-mix(in srgb, var(--color-text-secondary) 16%, transparent);
    }
    /* Windows high contrast: the lines in the system's colours; the
       dashes still tell them apart. */
    @media (forced-colors: active) {
        .line-chart-area polyline,
        .line-chart-legend line,
        .sparkline polyline {
            stroke: CanvasText !important;
        }
        .line-chart-offline {
            background: none;
            border-left-color: GrayText;
        }
    }
</style>
"""


def clock(moment: float, zone: tzinfo = timezone.utc, seconds: bool = False) -> str:
    """A time as the reader's clock shows it: "18:40", or "18:40:05"."""

    return datetime.fromtimestamp(moment, zone).strftime("%H:%M:%S" if seconds else "%H:%M")


def time_marks(start: float, end: float, every: int = 600) -> list:
    """The whole ten minutes (`every`) between `start` and `end`, inclusive."""

    first = -(-int(start) // every) * every

    return list(range(first, int(end) + 1, every))


def runs(points: Sequence, gap: float = GAP) -> list:
    """
    (time, value) pairs as unbroken runs: a new run where two readings are
    more than `gap` seconds apart, or where a value is missing.
    """

    out, run, last = [], [], None

    for moment, value in points:
        if value is None:
            if run:
                out.append(run)
            run, last = [], None
            continue

        if last is not None and moment - last > gap and run:
            out.append(run)
            run = []

        run.append((moment, value))
        last = moment

    if run:
        out.append(run)

    return out


def line_chart(
    title: str,
    series: Sequence,
    start: float,
    end: float,
    zone: tzinfo = timezone.utc,
    quiet_from: Optional[float] = None,
    empty: str = "No readings in this time.",
    single: tuple = SINGLE,
) -> str:
    """
    A chart titled `title` of `series`, (name, [(time, per cent), ...])
    pairs, from `start` to `end` (seconds since the epoch), on a scale of 0
    to 100 %. A lone series is drawn in `single` (colour, dash), so that the
    groups of a card can each have their own colour. `quiet_from` is a worker's last reading when it has gone
    offline: the time after it is toned and marked "Offline". A series
    with no readings in the window draws `empty` instead of a plot.
    """

    span = max(end - start, 1)

    def x(moment: float) -> float:
        return max(0.0, min(100.0, 100 * (moment - start) / span))

    def y(value: float) -> float:
        return 100 - max(0.0, min(100.0, float(value)))

    # A title, not a heading: the chart is hidden from assistive technology,
    # and a heading there would lead to nothing.
    heading = f'<div class="line-chart-title">{html.escape(title)}</div>'
    shown = [(name, [(t, v) for t, v in points if start <= t <= end]) for name, points in series]

    if not any(points for _, points in shown):
        return f'<div class="line-chart" aria-hidden="true">{heading}<div class="line-chart-empty">{html.escape(empty)}</div></div>'

    styles = [single] if len(shown) == 1 else [STYLES[at % len(STYLES)] for at in range(len(shown))]

    lines = "".join(
        f'<polyline points="{" ".join(f"{x(t):.2f},{y(v):.2f}" for t, v in run)}" stroke="{colour}"'
        + (f' stroke-dasharray="{dash}"' if dash else "")
        + ' vector-effect="non-scaling-stroke"/>'
        for (name, points), (colour, dash) in zip(shown, styles)
        for run in runs(points)
    )
    grid = "".join(f'<div class="line-chart-grid" style="bottom: {tick}%"></div>' for tick in (50, 100))
    scale = "".join(f'<span style="bottom: {tick}%">{tick}{chr(0xA0)}%</span>' for tick in (0, 50, 100))
    # The whole ten minutes only, not the window's own ends: those fall a
    # few minutes from a mark and would run into its label.
    times = "".join(
        f'<span style="left: {x(mark):.2f}%">{clock(mark, zone)}</span>'
        for mark in time_marks(start, end)
        if 6 < x(mark) < 94
    )
    quiet = ""

    if quiet_from is not None and quiet_from < end:
        quiet = f'<div class="line-chart-offline" style="left: {x(quiet_from):.2f}%"><span>Offline</span></div>'

    legend = ""

    if len(shown) > 1:
        legend = '<ul class="line-chart-legend">' + "".join(
            '<li><svg viewBox="0 0 24 8">'
            f'<line x1="0" y1="4" x2="24" y2="4" stroke="{colour}" stroke-width="3"'
            + (f' stroke-dasharray="{dash}"' if dash else "")
            + f"/></svg>{html.escape(name)}</li>"
            for (name, _), (colour, dash) in zip(shown, styles)
        ) + "</ul>"

    return (
        f'<div class="line-chart" aria-hidden="true">{heading}'
        '<div class="line-chart-plot">'
        f'<div class="line-chart-scale">{scale}</div>'
        f'<div class="line-chart-area">{grid}{quiet}'
        f'<svg viewBox="0 0 100 100" preserveAspectRatio="none">{lines}</svg></div>'
        f'<div class="line-chart-times">{times}</div>'
        f"</div>{legend}</div>"
    )


def sparkline(
    points: Sequence,
    start: float,
    end: float,
    colour: str = SINGLE[0],
    quiet_from: Optional[float] = None,
) -> str:
    """
    A trend line for a figure's tile: (time, per cent) pairs from `start` to
    `end`, 0 to 100 %, broken where readings are missing, with the time
    after `quiet_from` toned. A picture only (aria-hidden): the figure and
    the charts behind it say the same in words and numbers.
    """

    span = max(end - start, 1)

    def x(moment: float) -> float:
        return max(0.0, min(100.0, 100 * (moment - start) / span))

    shown = [(t, v) for t, v in points if start <= t <= end and v is not None]
    lines = "".join(
        f'<polyline points="{" ".join(f"{x(t):.2f},{100 - max(0.0, min(100.0, float(v))):.2f}" for t, v in run)}"'
        f' stroke="{colour}" vector-effect="non-scaling-stroke"/>'
        for run in runs(shown)
    )
    quiet = ""

    if quiet_from is not None and quiet_from < end:
        quiet = f'<rect class="is-quiet" x="{x(quiet_from):.2f}" y="0" width="{100 - x(quiet_from):.2f}" height="100"/>'

    return (
        '<svg class="sparkline" aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none">'
        f"{quiet}{lines}</svg>"
    )

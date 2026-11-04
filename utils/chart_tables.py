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
Charts that can be read without seeing them.

A Plotly chart is a picture: the numbers in it are not there for a screen
reader (WCAG 1.1.1, 1.3.1), the details only come up under a pointer, not for
a keyboard (2.1.1), and its toolbar's buttons have no names a screen reader
can use (4.1.2). So a chart is drawn as one part of three, the numbers first:

- a heading of its own, and a sentence that says what the chart shows;
- the chart, as a still picture (no hover, no toolbar) that assistive
  technology is told to skip, since everything in it is in the words;
- the same numbers as a real table, with a caption and headers, behind a
  "Show ... as a table" that is a native disclosure (<details>): reachable
  with the keyboard, announced as expanded or collapsed, and no script.

chart_section() does all three. The pieces are separate so they can be
tested without a page.
"""

import html
from typing import Iterable, Sequence

from nicegui import ui

from utils.bar_chart import BAR_CHART_STYLES, amount, day_label

CHART_STYLES = """
<style>
    /* Lines of about the same length when a heading or a sentence has to
       break in a narrow card, not one word left on its own. */
    .chart-heading,
    .chart-summary,
    .stats-line {
        text-wrap: balance;
    }
    .chart-data {
        width: 100%;
        margin-top: 0.75rem;
    }
    /* The page's reset takes the browser's own triangle away, which left
       the disclosure looking like a line of text. It is drawn here, and the
       line is underlined like a link, so it reads as something to press. */
    .chart-data summary {
        cursor: pointer;
        width: fit-content;
        padding: 0.25rem 0;
        font-weight: 500;
        color: var(--color-text-primary);
        text-decoration: underline;
        text-underline-offset: 3px;
        list-style: none;
    }
    .chart-data summary::-webkit-details-marker {
        display: none;
    }
    /* The triangle is drawn, not said: the second content, with an empty
       alternative after the slash, keeps it out of the name a screen reader
       reads (it says "expanded"/"collapsed" itself). A browser that does not
       know the slash keeps the first. */
    .chart-data summary::before {
        content: "\\25B8";
        content: "\\25B8" / "";
        display: inline-block;
        width: 1em;
        text-decoration: none;
    }
    .chart-data[open] > summary::before {
        content: "\\25BE";
        content: "\\25BE" / "";
    }
    .chart-data summary:focus-visible {
        outline: 3px solid var(--color-brand-primary);
        outline-offset: 2px;
    }
    .chart-data table {
        border-collapse: collapse;
        margin-top: 0.5rem;
        min-width: 16rem;
        color: var(--color-text-primary);
    }
    .chart-data caption {
        text-align: left;
        font-weight: 600;
        padding-bottom: 0.25rem;
    }
    .chart-data th,
    .chart-data td {
        text-align: left;
        padding: 0.25rem 1rem 0.25rem 0;
        border-bottom: 1px solid var(--color-border-subtle);
    }
    .chart-data thead th {
        font-weight: 600;
    }
    .chart-data tbody th {
        font-weight: 400;
    }
    .chart-data .chart-number {
        text-align: right;
        font-variant-numeric: tabular-nums;
    }
</style>
"""


def static_chart(figure) -> dict:
    """
    A figure as a still picture: no hover, no toolbar, nothing to focus or
    to reach with a pointer only. What the hover said is in the table.
    """

    data = figure.to_dict() if hasattr(figure, "to_dict") else dict(figure)
    data["config"] = {
        "staticPlot": True,
        "displayModeBar": False,
        "responsive": True,
    }

    return data


def data_table(
    summary: str,
    caption: str,
    headers: Sequence[str],
    rows: Iterable[Sequence],
    numeric: Sequence[int] = (),
) -> str:
    """
    The numbers behind a chart as a table behind a native disclosure.

    The first column heads each row (th scope=row): a date, a name. Columns
    whose index is in `numeric` are set right and in figures of one width,
    so they line up. Everything is escaped: dates and names come from the
    backend.
    """

    def cell(at: int, value) -> str:
        text = html.escape(str(value))
        number = ' class="chart-number"' if at in numeric else ""

        if at == 0:
            return f'<th scope="row"{number}>{text}</th>'

        return f"<td{number}>{text}</td>"

    number = ' class="chart-number"'
    head = "".join(
        f'<th scope="col"{number if at in numeric else ""}>{html.escape(name)}</th>'
        for at, name in enumerate(headers)
    )
    body = "".join(
        "<tr>" + "".join(cell(at, value) for at, value in enumerate(row)) + "</tr>"
        for row in rows
    )

    return (
        '<details class="chart-data">'
        f"<summary>{html.escape(summary)}</summary>"
        f"<table><caption>{html.escape(caption)}</caption>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
        "</details>"
    )


def minutes_summary(per_day: dict, decimals: int = 0, so_far: bool = False) -> str:
    """
    Two short sentences about minutes per day: the total and the busiest
    day, what a glance at the chart would tell. Not on how many days: "on 4
    days" next to "so far" reads as days gone by, and needs explaining. `so_far` for a
    month under way: what the tone over the days to come says in the chart.
    """

    days = {day: minutes for day, minutes in per_day.items() if minutes and minutes > 0}

    if not days:
        return "Nothing has been transcribed so far." if so_far else "Nothing was transcribed."

    total = sum(days.values())
    busiest = max(days, key=lambda day: days[day])

    # Minutes as everywhere on the page (`decimals`, decimals_for()); the
    # total is the sum of the days as they are, not of what is shown. On a
    # tie, the first of the days.
    return (
        f"{amount(total, decimals=decimals)} {'so far' if so_far else 'in all'}. "
        f"Busiest day: {day_label(busiest)}, {amount(days[busiest], decimals=decimals)}."
    )


def chart_section(
    heading: str,
    summary: str,
    figure,
    table_summary: str,
    caption: str,
    headers: Sequence[str],
    rows: Iterable[Sequence],
    numeric: Sequence[int] = (),
    level: int = 2,
    empty: bool = False,
) -> None:
    """
    A chart that can be read without seeing it: heading, sentence, the
    chart as a picture to skip, and the numbers as a table.

    `empty` is a chart of nothing (every value 0): the heading and the
    sentence say so, and neither an empty picture nor a table of noughts
    is drawn under them.
    """

    ui.label(heading).classes("chart-heading text-xl font-semibold text-theme-primary").props(
        f"role=heading aria-level={level}"
    )
    ui.label(summary).classes("chart-summary text-body1 text-theme-secondary")

    if empty:
        return

    # A chart drawn by the page (utils/bar_chart.py, HTML) or a Plotly figure.
    with ui.element("div").classes("w-full").props('aria-hidden="true"'):
        if isinstance(figure, str):
            ui.html(figure, sanitize=False).classes("w-full")
        else:
            ui.plotly(static_chart(figure)).classes("w-full")

    ui.html(
        data_table(table_summary, caption, headers, rows, numeric), sanitize=False
    ).classes("w-full")


def head_html() -> str:
    """The styles, for the head of a page with chart sections."""

    return CHART_STYLES + BAR_CHART_STYLES

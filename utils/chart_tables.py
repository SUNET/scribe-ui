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
import re
from typing import Iterable, Sequence

from nicegui import ui

from utils.bar_chart import BAR_CHART_STYLES, NBSP, amount, day_label

CHART_STYLES = """
<style>
    /* A heading or a sentence that has to break in a narrow card breaks
       between its phrases ("Transcribed minutes per day," / "November
       2026"), the same way in every card; a phrase too long for the line
       breaks inside itself. */
    .chart-phrase {
        display: inline-block;
    }
    /* On a phone the same breaks every time: "Transcribed minutes per
       day," / "November 2026", and "1.3 minutes in all." / "Busiest day:
       ...", fitting or not; the heading a step smaller, so its first
       phrase is one line at 360px. */
    @media (max-width: 600px) {
        .chart-heading {
            font-size: 1.125rem;
        }
        .chart-heading .chart-phrase,
        .chart-summary .chart-sentence {
            display: block;
        }
    }
    /* Less room round the cards on a phone, where it is width they lack:
       enough for "Transcribed minutes per day," on one line at 360px. */
    @media (max-width: 600px) {
        .stats-card.stats-summary,
        .chart-container {
            padding: 1rem;
        }
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
    /* The table scrolls sideways in a region of its own if it is ever
       wider than the card (a larger text size on a phone), not the page;
       the region can be reached and scrolled with the keyboard. */
    .chart-scroll {
        max-width: 100%;
        overflow-x: auto;
    }
    .chart-scroll:focus-visible {
        outline: 3px solid var(--color-brand-primary);
        outline-offset: 2px;
    }
    .chart-data table {
        border-collapse: collapse;
        margin-top: 0.5rem;
        min-width: min(16rem, 100%);
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
    /* A summary card's figure, large, and how it compares: an arrow and
       a sentence, the arrow in the text's colour (more is not good, fewer
       not bad) and not read out, since the sentence says it. */
    .stats-tile-count {
        font-size: 1.75rem;
        font-weight: 700;
        line-height: 1.2;
        color: var(--color-text-primary);
        font-variant-numeric: tabular-nums;
    }
    .stats-trend {
        display: flex;
        align-items: flex-start;
        gap: 0.375rem;
        margin-top: 0.25rem;
        line-height: 1.4;
        color: var(--color-text-secondary);
    }
    .stats-trend .q-icon {
        flex: none;
        font-size: 1.25rem;
        color: var(--color-text-primary);
    }
    .stats-trend-figure {
        font-weight: 600;
        color: var(--color-text-primary);
    }
    /* A table wider than its card (the actions per day, of eight or nine
       columns, on a phone) keeps each figure on one line and scrolls in
       its region (.chart-scroll above), not the page. */
    .chart-scroll th,
    .chart-scroll td {
        white-space: nowrap;
    }
    /* A table shown, not behind a disclosure: as wide as its card, its
       caption said by the heading above it. */
    .chart-table table {
        width: 100%;
        min-width: 0;
    }
    .chart-table caption,
    .heat-table caption {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip: rect(0 0 0 0);
        white-space: nowrap;
    }
    /* The cards straight in the page's column take its width, as the
       charts under them do, rather than the narrow column of their own
       that a centred flex item gets. */
    .stats-container > .stats-tiles {
        width: 100%;
    }
    .chart-table-grid {
        margin-top: 1rem;
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(min(100%, 24rem), 1fr));
        gap: 1rem 2.5rem;
        width: 100%;
    }
    .chart-note {
        margin-top: 0.75rem;
        font-size: 0.875rem;
        color: var(--color-text-secondary);
    }
    /* A heat map that is a table: the figure in each cell, the cell toned
       by it, the ink chosen per cell for contrast (heat_table()). Days as
       rows on a wide card; on a narrow one hours as rows, the days across. */
    .heat-table {
        container-type: inline-size;
        width: 100%;
        margin-top: 0.75rem;
    }
    .heat-table table {
        border-collapse: separate;
        border-spacing: 2px;
        width: 100%;
        font-size: 0.75rem;
        font-variant-numeric: tabular-nums;
    }
    .heat-table th {
        font-weight: 500;
        color: var(--color-text-secondary);
        padding: 0.125rem 0.25rem;
        text-align: center;
    }
    .heat-table tbody th {
        text-align: left;
    }
    .heat-table td {
        text-align: center;
        padding: 0.25rem 0;
        border-radius: 3px;
        background: var(--heat, var(--color-bg-surface-alt));
        color: var(--heat-ink, var(--color-text-primary));
    }
    .body--dark .heat-table td {
        background: var(--heat-dark, var(--color-bg-surface-alt));
        color: var(--heat-dark-ink, var(--color-text-primary));
    }
    .heat-table .heat-total,
    .body--dark .heat-table .heat-total {
        background: none;
        font-weight: 600;
        color: var(--color-text-primary);
    }
    .heat-table .heat-tall {
        display: none;
    }
    @container (max-width: 44rem) {
        .heat-table .heat-wide {
            display: none;
        }
        .heat-table .heat-tall {
            display: table;
        }
    }
    @media (forced-colors: active) {
        .heat-table td {
            border: 1px solid CanvasText;
        }
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

    The table is in a region of its own, named by its caption, that scrolls
    sideways if the table is ever wider than its card, rather than taking
    the page with it (1.4.10); tabindex, so the keyboard can reach and
    scroll it.

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

    name = html.escape(caption, quote=True)

    return (
        '<details class="chart-data">'
        f"<summary>{html.escape(summary)}</summary>"
        f'<div class="chart-scroll" role="region" tabindex="0" aria-label="{name}">'
        f"<table><caption>{html.escape(caption)}</caption>"
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
        "</div></details>"
    )


def days_so_far(per_day: dict, today: str) -> dict:
    """
    The days of a month under way that have come: up to `today` (as
    "2026-11-04"), and any later day with minutes (the server that counts
    may be in another time zone). The backend fills every day of the month
    with a nought, the days to come too; they are no figures yet, so no
    tooltip and no row in the table.
    """

    return {day: value for day, value in per_day.items() if str(day) <= today or (value and value > 0)}


def phrased(text: str) -> str:
    """
    `text` as HTML, in sentences (split after a full stop and a space) of
    phrases (split after a comma and a space), each phrase kept whole on a
    line where it fits. On a phone each sentence of a chart's sentence, and
    each phrase of its heading, has a line of its own (CHART_STYLES).
    Escaped; read out as the words with spaces between.
    """

    def sentence(part: str) -> str:
        return " ".join(
            f'<span class="chart-phrase">{html.escape(phrase)}</span>'
            for phrase in re.split(r"(?<=,)\s+", part)
            if phrase
        )

    return " ".join(
        f'<span class="chart-sentence">{sentence(part)}</span>'
        for part in re.split(r"(?<=\.)\s+", text.strip())
        if part
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
        # "so far" kept together, or a narrow card leaves "far." on its own.
        return "Nothing has been transcribed so\u00a0far." if so_far else "Nothing was transcribed."

    total = sum(days.values())
    busiest = max(days, key=lambda day: days[day])

    # Minutes as everywhere on the page (`decimals`, decimals_for()); the
    # total is the sum of the days as they are, not of what is shown. On a
    # tie, the first of the days.
    return (
        f"{amount(total, decimals=decimals)} {'so' + NBSP + 'far' if so_far else 'in' + NBSP + 'all'}. "
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

    ui.html(phrased(heading), sanitize=False).classes(
        "chart-heading text-xl font-semibold text-theme-primary"
    ).props(f"role=heading aria-level={level}")
    ui.html(phrased(summary), sanitize=False).classes("chart-summary text-body1 text-theme-secondary")

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


def summary_cards(cards: Sequence) -> None:
    """
    A summary as cards, in the look of the files on /home: each a name and
    a line or two under it ((name, [line, ...]) pairs; a line may be a
    function that draws it). A list, so it is
    read as so many of a kind; role="list" because Safari leaves a list
    without its markers out of the accessibility tree as a list unless it
    is told. The styles are the page's own (utils/styles.py, .stats-tiles).
    """

    with ui.element("ul").classes("stats-tiles").props('role="list"'):
        for name, lines in cards:
            with ui.element("li"):
                with ui.card().props("flat bordered").classes("stats-tile"):
                    # A plain space: "November 2026" may break in a card,
                    # which at a larger text size on a phone is narrower
                    # than the name.
                    ui.label(name.replace(NBSP, " ")).classes("stats-tile-name")

                    for line in lines:
                        # A line that draws itself, for more than a sentence.
                        line() if callable(line) else ui.label(line).classes("stats-tile-meta")


def head_html() -> str:
    """The styles, for the head of a page with chart sections."""

    return CHART_STYLES + BAR_CHART_STYLES


# The heat map's tones: from the card's light grey to the brand's dark blue
# (light), or to a light blue on the dark card (dark). The ink per cell is
# black or white, whichever has the more contrast: one of the two always
# has at least 4.58:1, which the page's own text colours do not in the
# middle tones.
HEAT_TONES = {
    "": ("#f3f4f6", "#1d4f91", ("#000000", "#ffffff")),
    "-dark": ("#1e2128", "#7fb2e5", ("#ffffff", "#000000")),
}


def _luminance(colour: str) -> float:
    channels = [int(colour[at : at + 2], 16) / 255 for at in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]

    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    """WCAG's contrast ratio of two colours as #rrggbb."""

    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)

    return (light + 0.05) / (dark + 0.05)


def _mix(base: str, full: str, share: float) -> str:
    def channel(at):
        return round(int(base[at : at + 2], 16) * (1 - share) + int(full[at : at + 2], 16) * share)

    return "#" + "".join(f"{channel(at):02x}" for at in (1, 3, 5))


def heat_tone(value: int, highest: int) -> str:
    """The style for a cell: its tone in both themes and an ink with the more contrast."""

    if not value or not highest:
        return ""

    share = 0.15 + 0.85 * value / highest
    style = []

    for suffix, (base, full, inks) in HEAT_TONES.items():
        tone = _mix(base, full, share)
        ink = max(inks, key=lambda one: contrast(one, tone))
        style.append(f"--heat{suffix}: {tone}; --heat{suffix}-ink: {ink}")

    return ' style="' + "; ".join(style) + '"'


def heat_table(
    rows: Sequence[str],
    columns: Sequence[str],
    values: Sequence[Sequence[int]],
    caption: str,
    tip,
    unit: str = "Actions",
) -> str:
    """
    A heat map as two tables of the same figures: `rows` down and `columns`
    across on a wide card, turned on a narrow one, with a total for each
    row and column. The figure is in each cell, the tone says how many
    beside the rest, and `tip(row, column)` names the cell in its tooltip
    ("Thursday 13–14"). Only one of the two is shown, so only one is read.
    """

    highest = max((value for row in values for value in row), default=0)
    row_totals = [sum(row) for row in values]
    column_totals = [sum(values[r][c] for r in range(len(rows))) for c in range(len(columns))]

    def cell(r: int, c: int) -> str:
        value = values[r][c]
        title = html.escape(f"{tip(r, c)}: {amount(value, unit)}", quote=True)

        return f'<td{heat_tone(value, highest)} title="{title}">{value}</td>'

    def table(kind: str, down, across, pick, down_totals, across_totals, short) -> str:
        head = "".join(f'<th scope="col">{html.escape(short(name, False))}</th>' for name in across)
        body = "".join(
            f'<tr><th scope="row">{html.escape(short(name, True))}</th>'
            + "".join(pick(d, a) for a in range(len(across)))
            + f'<td class="heat-total">{down_totals[d]}</td></tr>'
            for d, name in enumerate(down)
        )
        foot = (
            '<tr><th scope="row" class="heat-total">All</th>'
            + "".join(f'<td class="heat-total">{value}</td>' for value in across_totals)
            + f'<td class="heat-total">{sum(down_totals)}</td></tr>'
        )

        return (
            f'<table class="heat-{kind}"><caption>{html.escape(caption)}</caption>'
            f'<thead><tr><td class="heat-total"></td>{head}<th scope="col">All</th></tr></thead>'
            f"<tbody>{body}{foot}</tbody></table>"
        )

    wide = table("wide", rows, columns, cell, row_totals, column_totals, lambda name, _: name[:3] if len(name) > 3 else name)
    tall = table("tall", columns, rows, lambda c, r: cell(r, c), column_totals, row_totals, lambda name, _: name[:3] if len(name) > 3 else name)

    return f'<div class="heat-table">{wide}{tall}</div>'


def shown_table(caption: str, headers: Sequence[str], rows: Iterable[Sequence], numeric: Sequence[int] = ()) -> str:
    """
    A table shown as it is (data_table() without the disclosure), named by
    its caption for a screen reader and by the heading above it for the eye.
    """

    table = data_table("", caption, headers, rows, numeric)
    start = table.index("<table>")

    return '<div class="chart-data chart-table">' + table[start : table.index("</details>")] + "</div>"

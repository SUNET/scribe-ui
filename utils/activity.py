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
What the Activity overview counts, worked out from the backend's log of
actions: which kind each action is, the last 30 days against the 30 before,
a 7-day average, when in the week things are done, and what was done last.
Pure functions, so the page (pages/admin/analytics.py) only draws them.

The log holds actions ("/action/upload"), not page views; a path that is not
an action is left out. Days are the backend's; hours and weekdays are moved
to the reader's time zone.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from utils.bar_chart import NBSP

# The four kinds the page shows (cards, the chart's colours), in this order;
# an action of a kind not known here is "Other actions".
KINDS = (
    ("uploads", "Uploads"),
    ("transcriptions", "Transcriptions"),
    ("exports", "Exports"),
    ("admin", "Administrative actions"),
)
OTHER = ("other", "Other actions")

# Each action: its name, its table (user or admin) and its kind.
ACTIONS = {
    "/action/upload": ("Uploads", "user", "uploads"),
    "/action/transcription": ("Transcriptions", "user", "transcriptions"),
    "/action/bulk_transcription": ("Bulk transcriptions", "user", "transcriptions"),
    "/action/export": ("Exports", "user", "exports"),
    "/action/bulk_export": ("Bulk exports", "user", "exports"),
    "/action/create_group": ("Groups created", "admin", "admin"),
    "/action/edit_group": ("Groups edited", "admin", "admin"),
    "/action/delete_group": ("Groups deleted", "admin", "admin"),
    "/action/activate_user": ("Users activated", "admin", "admin"),
    "/action/deactivate_user": ("Users deactivated", "admin", "admin"),
    "/action/remove_user": ("Users removed", "admin", "admin"),
    "/action/set_admin": ("Admin rights granted", "admin", "admin"),
    "/action/remove_admin": ("Admin rights revoked", "admin", "admin"),
    "/action/set_domains": ("Domains updated", "admin", "admin"),
}

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Days in a period, and the days the backend is asked for: this period, the
# one before, and six more for the first days' 7-day average.
PERIOD = 30
HISTORY = 2 * PERIOD + 6


def action(path: str) -> Optional[tuple]:
    """(name, table, kind) for an action's path; None for one that is not an action."""

    if not str(path).startswith("/action/"):
        return None

    if path in ACTIONS:
        return ACTIONS[path]

    return (path[len("/action/"):].replace("_", " ").capitalize(), "other", "other")


def day_of(value) -> str:
    """A backend date ("2026-10-15", "2026-10-15T00:00:00") as "2026-10-15"."""

    return str(value)[:10]


def periods(today: date) -> tuple:
    """(this period's days, the period before's days), oldest first, as ISO dates."""

    now = [(today - timedelta(days=PERIOD - 1 - at)).isoformat() for at in range(PERIOD)]
    before = [(today - timedelta(days=2 * PERIOD - 1 - at)).isoformat() for at in range(PERIOD)]

    return now, before


def per_day(views: Iterable[dict]) -> dict:
    """{day: {kind: count}} and {day: {path: count}} from the backend's rows, actions only."""

    kinds, paths = {}, {}

    for row in views:
        known = action(row.get("path", ""))

        if not known:
            continue

        day = day_of(row.get("date"))
        count = int(row.get("views") or 0)
        kinds.setdefault(day, {}).setdefault(known[2], 0)
        kinds[day][known[2]] += count
        paths.setdefault(day, {}).setdefault(row["path"], 0)
        paths[day][row["path"]] += count

    return kinds, paths


def older_than_fetched(summary: Iterable[dict], views: Iterable[dict]) -> bool:
    """
    Whether the log goes back further than the days fetched: more actions
    in all (the summary's all-time count) than in the days fetched. Then
    every day fetched is a real figure, a nought included.
    """

    all_time = sum(int(row.get("total_views") or 0) for row in summary if action(row.get("path", "")))
    fetched = sum(int(row.get("views") or 0) for row in views if action(row.get("path", "")))

    return all_time > fetched


def counted_from(views: Iterable[dict], summary: Iterable[dict]) -> Optional[str]:
    """
    The first day the figures are whole from: None when the log goes back
    further than the days fetched, else the first day it has anything for
    (it began within them), or today's date when it has nothing at all.
    """

    views = list(views)

    if older_than_fetched(summary, views):
        return None

    days = [day_of(row.get("date")) for row in views if action(row.get("path", ""))]

    return min(days) if days else "9999-12-31"


def has_whole(days: list, counted: Optional[str]) -> bool:
    """Whether the log covers every one of these days."""

    return counted is None or counted <= days[0]


def total(kinds: dict, days: Iterable[str], kind: Optional[str] = None) -> int:
    """Actions on these days, of one kind or of all."""

    return sum(
        (counts.get(kind, 0) if kind else sum(counts.values()))
        for day, counts in kinds.items()
        if day in set(days)
    )


def rolling_average(kinds: dict, days: list, counted: Optional[str], width: int = 7) -> list:
    """
    The average a day over each day and the six before it; None for a day
    whose week the log does not cover (it began within it).
    """

    out = []

    for day in days:
        moment = date.fromisoformat(day)
        week = [(moment - timedelta(days=back)).isoformat() for back in range(width)]

        if counted is not None and counted > week[-1]:
            out.append(None)
            continue

        out.append(total(kinds, week) / width)

    return out


def trend(now: int, before: Optional[int]) -> tuple:
    """
    (icon, figure, words) for a card: how this period compares with the one
    before. Within 5% either way it is "about the same", so a small swing
    does not read as a trend. In words, not in colour: more or fewer is
    neither good nor bad here.
    """

    if before is None:
        return ("remove", "", "No figures for the 30 days before")

    difference = now - before
    sign = "+" if difference >= 0 else "−"

    if before and abs(difference) / before < 0.05:
        return ("trending_flat", f"{sign}{abs(difference)}", f", about the same as the 30{NBSP}days before")

    if not before:
        return ("trending_up" if now else "trending_flat", f"+{now}", f" on the 30{NBSP}days before, when there were none")

    share = round(100 * abs(difference) / before)

    return (
        "trending_up" if difference > 0 else "trending_down",
        f"{sign}{abs(difference)} ({sign}{share}{NBSP}%)",
        f" on the 30{NBSP}days before",
    )


def heat(rows: Iterable[dict], offset_hours: int) -> list:
    """
    The backend's counts by weekday and hour (PostgreSQL's dow, 0 = Sunday;
    hours in UTC) as a 7 x 24 matrix in the reader's time zone, Monday
    first.
    """

    matrix = [[0] * 24 for _ in range(7)]

    for row in rows:
        hour = int(row.get("hour") or 0) + offset_hours
        shift = -1 if hour < 0 else (1 if hour >= 24 else 0)
        monday_first = (int(row.get("dow") or 0) - 1) % 7
        matrix[(monday_first + shift) % 7][hour % 24] += int(row.get("views") or 0)

    return matrix


def moment(value, zone) -> Optional[datetime]:
    """A backend timestamp, in UTC unless it says otherwise, in the reader's time zone."""

    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    return when.astimezone(zone)


def when_label(when: datetime, today: date) -> str:
    """ "5 Nov, 16:53"; with the year when it is not this year's."""

    year = "" if when.year == today.year else f" {when.year}"

    return f"{when.day}{NBSP}{MONTHS[when.month - 1]}{year}, {when:%H:%M}"

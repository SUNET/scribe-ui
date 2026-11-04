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
A group's statistics as one CSV file: what the statistics page shows, in rows
that each say what they are.

    section,month,date,user,users,files,minutes
    summary,2026-11,,,2,0,0.0
    per day,2026-10,2026-10-15,,,,1.3
    per user,2026-11,,anna@lu.se,,,12.5

- Months as "2026-11", not "this month": a file is read long after it was
  made.
- Standard CSV: UTF-8, commas, a full stop for decimals, a header row.
- Rows per user are personal data. They are only written when the reader has
  asked for them (`include_users`), never by default.
- A cell that a spreadsheet would take for a formula (=, +, -, @, a tab or a
  carriage return first) is written with an apostrophe in front, so opening
  the file runs nothing (CSV injection). Only names can start like that; the
  figures are written by this file.
"""

import csv
import io
from datetime import date
from typing import Optional

COLUMNS = ("section", "month", "date", "user", "users", "files", "minutes")

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe(value) -> str:
    """A cell that a spreadsheet will not run."""

    text = "" if value is None else str(value)

    return "'" + text if text.startswith(FORMULA_STARTS) else text


def previous_month(month: str) -> str:
    year, number = (int(part) for part in month.split("-"))

    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def month_of(days: dict, fallback: str) -> str:
    """The month the days are in ("2026-10-15" -> "2026-10"), or the fallback."""

    for day in days:
        if isinstance(day, str) and len(day) >= 7 and day[4] == "-":
            return day[:7]

    return fallback


def statistics_csv(result: dict, include_users: bool = False, today: Optional[date] = None) -> str:
    """
    The statistics in `result` (the backend's group statistics) as CSV text.
    """

    today = today or date.today()
    per_day = result.get("transcribed_minutes_per_day") or {}
    per_day_before = result.get("transcribed_minutes_per_day_last_month") or {}
    per_user = result.get("transcribed_minutes_per_user") or {}

    this_month = month_of(per_day, today.strftime("%Y-%m"))
    last_month = month_of(per_day_before, previous_month(this_month))

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)

    writer.writerow(
        (
            "summary",
            this_month,
            "",
            "",
            result.get("total_users", 0),
            result.get("transcribed_files", 0),
            f"{result.get('total_transcribed_minutes', 0) or 0:.1f}",
        )
    )
    writer.writerow(
        (
            "summary",
            last_month,
            "",
            "",
            "",
            result.get("transcribed_files_last_month", 0),
            f"{result.get('total_transcribed_minutes_last_month', 0) or 0:.1f}",
        )
    )

    for month, days in ((this_month, per_day), (last_month, per_day_before)):
        for day, minutes in days.items():
            writer.writerow(("per day", month, safe(day), "", "", "", f"{minutes or 0:.1f}"))

    if include_users:
        for user, minutes in per_user.items():
            writer.writerow(("per user", this_month, "", safe(user), "", "", f"{minutes or 0:.1f}"))

    return out.getvalue()


def statistics_filename(group: str, today: Optional[date] = None) -> str:
    """scribe-statistics-<group>-<date>.csv, the group made safe for a name."""

    today = today or date.today()
    name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(group)).strip("-")

    return f"scribe-statistics-{name or 'group'}-{today.isoformat()}.csv"

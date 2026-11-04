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

"""A group's statistics as CSV (utils/statistics_export.py)."""

import csv
import io
import pathlib
from datetime import date

import pytest

from utils.statistics_export import (
    COLUMNS,
    previous_month,
    safe,
    statistics_csv,
    statistics_filename,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent

RESULT = {
    "total_users": 2,
    "transcribed_files": 3,
    "transcribed_files_last_month": 9,
    "total_transcribed_minutes": 14.0,
    "total_transcribed_minutes_last_month": 1.333,
    "transcribed_minutes_per_day": {"2026-11-01": 0, "2026-11-02": 14.0},
    "transcribed_minutes_per_day_last_month": {"2026-10-15": 1.333},
    "transcribed_minutes_per_user": {"anna@example.org": 12.5, "=cmd|calc": 1.5},
}


def rows(text):
    return list(csv.reader(io.StringIO(text)))


class TestTheFile:
    def test_a_header_and_rows_that_say_what_they_are(self):
        table = rows(statistics_csv(RESULT))

        assert tuple(table[0]) == COLUMNS
        assert table[1] == ["summary", "2026-11", "", "", "2", "3", "14.0"]
        assert table[2] == ["summary", "2026-10", "", "", "", "9", "1.3"]
        assert table[3] == ["per day", "2026-11", "2026-11-01", "", "", "", "0.0"]
        assert table[5] == ["per day", "2026-10", "2026-10-15", "", "", "", "1.3"]

    def test_standard_csv_commas_and_a_full_stop(self):
        text = statistics_csv(RESULT)

        assert text.startswith("section,month,date,user,users,files,minutes\n")
        assert ";" not in text
        assert "1,3" not in text

    def test_months_as_months_not_this_or_last(self):
        text = statistics_csv(RESULT)

        assert "this month" not in text and "last month" not in text

    def test_without_days_the_months_come_from_the_date(self):
        table = rows(statistics_csv({}, today=date(2026, 1, 20)))

        assert table[1][1] == "2026-01"
        assert table[2][1] == "2025-12"

    def test_previous_month(self):
        assert previous_month("2026-11") == "2026-10"
        assert previous_month("2026-01") == "2025-12"


class TestPersonalData:
    def test_no_user_is_in_it_unless_asked_for(self):
        text = statistics_csv(RESULT)

        assert "per user" not in text
        assert "anna@example.org" not in text

    def test_asked_for_each_user_is_a_row(self):
        table = rows(statistics_csv(RESULT, include_users=True))
        users = [row for row in table if row[0] == "per user"]

        assert ["per user", "2026-11", "", "anna@example.org", "", "", "12.5"] in users

    def test_a_name_that_looks_like_a_formula_is_not_one(self):
        table = rows(statistics_csv(RESULT, include_users=True))

        assert ["per user", "2026-11", "", "'=cmd|calc", "", "", "1.5"] in table

    @pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
    def test_every_formula_start(self, start):
        assert safe(start + "x") == "'" + start + "x"

    def test_anything_else_as_it_is(self):
        assert safe("anna") == "anna" and safe(None) == "" and safe(3) == "3"


class TestTheName:
    def test_group_and_date(self):
        assert statistics_filename("12", today=date(2026, 11, 4)) == (
            "scribe-statistics-12-2026-11-04.csv"
        )

    def test_made_safe(self):
        assert statistics_filename("../a b", today=date(2026, 11, 4)) == (
            "scribe-statistics-a-b-2026-11-04.csv"
        )


class TestOnThePage:
    def page(self):
        source = (ROOT / "pages" / "admin" / "groups.py").read_text()

        return source[source.index("async def statistics") :]

    def test_the_choice_is_off_every_time_and_only_where_there_are_users(self):
        page = self.page()

        assert '"Include minutes per user (user names)", value=False' in page
        assert "include_users.set_visibility(bool(per_user))" in page

    def test_the_download_is_the_csv_in_utf_8(self):
        page = self.page()

        assert "include_users=bool(include_users.value)" in page
        assert '.encode("utf-8")' in page
        assert 'media_type="text/csv"' in page
        assert "statistics_filename(group_id)" in page

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
The billing report has to stay interchangeable with the one
transcribe-backend/scripts/customer_billing.py prints, so its shape is pinned
here rather than left to inspection.
"""

import pytest

from utils.helpers import BILLING_HEADER, MINUTES_PER_BLOCK, format_billing_data


def customer(abbr, base_fee=0, blocks=0, minutes=0):
    return {
        "customer_abbr": abbr,
        "base_fee": base_fee,
        "blocks_purchased": blocks,
        "stats": {"total_transcribed_minutes_last_month": minutes},
    }


class TestReportShape:
    def test_first_line_is_the_report_date(self):
        report = format_billing_data([], "2026-08-18")

        assert report.splitlines()[0] == "DATE:2026-08-18"

    def test_second_line_is_the_swedish_header(self):
        report = format_billing_data([], "2026-08-18")

        assert report.splitlines()[1] == "Kund;Grund;Block;Minuter"
        assert BILLING_HEADER == "Kund;Grund;Block;Minuter"

    def test_ends_with_a_newline(self):
        assert format_billing_data([customer("SU")], "2026-08-18").endswith("\n")

    def test_fields_are_semicolon_separated(self):
        report = format_billing_data([customer("SU", 5000, 2, 9500)], "2026-08-18")

        assert report.splitlines()[2] == "SU;5000;2;1500"

    def test_rows_are_sorted_by_customer(self):
        report = format_billing_data(
            [customer("SU"), customer("GIH"), customer("KTH")], "2026-08-18"
        )

        assert [line.split(";")[0] for line in report.splitlines()[2:]] == [
            "GIH",
            "KTH",
            "SU",
        ]


class TestOverage:
    """
    Only minutes beyond the purchased blocks are billed.
    """

    @pytest.mark.parametrize(
        "blocks,minutes,expected",
        [
            (0, 0, 0),
            (0, 120, 120),
            (1, MINUTES_PER_BLOCK, 0),
            (1, MINUTES_PER_BLOCK + 1, 1),
            (2, 9500, 9500 - 2 * MINUTES_PER_BLOCK),
            # Under the allowance is never negative.
            (3, 100, 0),
        ],
    )
    def test_overage_is_minutes_beyond_the_blocks(self, blocks, minutes, expected):
        report = format_billing_data(
            [customer("SU", 0, blocks, minutes)], "2026-08-18"
        )

        assert report.splitlines()[2].split(";")[3] == str(expected)

    def test_block_size_matches_the_script(self):
        assert MINUTES_PER_BLOCK == 4000


class TestMissingData:
    """
    The API returns nulls for a customer that has not been fully configured.
    """

    def test_null_fee_and_blocks_count_as_zero(self):
        report = format_billing_data(
            [{"customer_abbr": "MDU", "base_fee": None,
              "blocks_purchased": None, "stats": None}],
            "2026-08-18",
        )

        assert report.splitlines()[2] == "MDU;0;0;0"

    def test_absent_keys_count_as_zero(self):
        report = format_billing_data([{"customer_abbr": "MDU"}], "2026-08-18")

        assert report.splitlines()[2] == "MDU;0;0;0"

    def test_null_abbreviation_does_not_raise(self):
        """
        customer_abbr is nullable, and the shell script sorts on it without
        guarding -- it raises TypeError on this input. Here the customer is
        reported with an empty name instead of taking the export down.
        """

        report = format_billing_data(
            [customer(None, 1, 1, 0), customer("SU")], "2026-08-18"
        )

        assert report.splitlines()[2] == ";1;1;0"

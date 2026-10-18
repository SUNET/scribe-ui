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
What a reader types into Quick Jump, and what it means.

Kept apart from the dialog so the rules can be tested without a browser and
cannot drift from what the dialog's hint says. Three kinds of input, told
apart by their first character so nothing is ambiguous:

  #123      a block (caption) number
  +30 -1:05 a time relative to where the recording is now
  1:15:23   a time

A time is read the way it is spoken, from the right. With colons the fields
are hours:minutes:seconds counted from the right, and an empty field is
zero: "1:15" is 1 min 15 s, "10:" is 10 minutes, "1::30" is 1 h 0 min 30 s.
Without colons the digits are taken two at a time from the right as seconds,
minutes and hours: "123" is 1:23, "011523" is 1:15:23, and "90" is 90
seconds. A field that overflows is simply added up ("1:90" is 2:30), and the
seconds may have decimals ("1:15.5"), so a time copied from the editor's own
labels works.
"""

import re

from typing import Tuple

KIND_BLOCK = "block"
KIND_TIME = "time"
KIND_RELATIVE = "relative"

# What the dialog shows under the field. One place, so it is tested against
# the parser rather than trusted to stay right.
HINT = "Time: 1:15:23, 1:15, 90 or 123. Relative: +30 or -1:05. Block: #12."

_DIGITS = re.compile(r"\d+")
_SECONDS = re.compile(r"(\d+)(?:[.,](\d+))?")


class JumpError(ValueError):
    """
    The input is not something Quick Jump understands. The message is shown
    to the reader as it is.
    """


def parse_jump(text: str) -> Tuple[str, float]:
    """
    Read the input. Returns (kind, value): a block number, a number of
    seconds from the start of the recording, or a signed number of seconds
    to move by. Raises JumpError, with something to say to the reader.
    """

    text = (text or "").strip()

    if not text:
        raise JumpError("Type a time, like 1:15, or a block number, like #12")

    if text.startswith("#"):
        digits = text[1:].strip()

        if not _DIGITS.fullmatch(digits) or int(digits) < 1:
            raise JumpError("A block number is # and a number from 1, like #12")

        return (KIND_BLOCK, int(digits))

    if text[0] in "+-":
        sign = -1.0 if text[0] == "-" else 1.0
        body = text[1:].strip()

        if not body:
            raise JumpError("Say how far, like +30 or -1:05")

        return (KIND_RELATIVE, sign * parse_time(body))

    return (KIND_TIME, parse_time(text))


def parse_time(text: str) -> float:
    """
    A time, in seconds. See the module's description for the rules.
    """

    text = text.strip()

    if ":" in text:
        fields = text.split(":")

        if len(fields) > 3:
            raise JumpError("A time has at most hours, minutes and seconds")

        # Counted from the right, so "10:" is minutes and "1::" is hours.
        fields = [""] * (3 - len(fields)) + fields
        hours, minutes, seconds = fields

        for field in (hours, minutes):
            if field and not _DIGITS.fullmatch(field):
                raise JumpError(_not_a_time(text))

        return (
            (int(hours) if hours else 0) * 3600
            + (int(minutes) if minutes else 0) * 60
            + _seconds(seconds, text)
        )

    # No colons: digits two at a time from the right, the last group being
    # the seconds -- and the seconds are all of the last two digits, so "90"
    # is ninety of them.
    match = _SECONDS.fullmatch(text)

    if not match:
        raise JumpError(_not_a_time(text))

    whole, fraction = match.group(1), match.group(2)
    seconds = int(whole[-2:])
    minutes = int(whole[-4:-2] or 0)
    hours = int(whole[:-4] or 0)

    return hours * 3600 + minutes * 60 + seconds + _fraction(fraction)


def _seconds(field: str, text: str) -> float:
    if not field:
        return 0.0

    match = _SECONDS.fullmatch(field)

    if not match:
        raise JumpError(_not_a_time(text))

    return int(match.group(1)) + _fraction(match.group(2))


def _fraction(digits) -> float:
    return float("0." + digits) if digits else 0.0


def _not_a_time(text: str) -> str:
    return f'"{text}" is not a time. Try 1:15, 90 or 1:15:23'

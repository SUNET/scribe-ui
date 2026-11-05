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
What the health page shows of the workers, as pure functions.

The backend's GET /api/v1/healthcheck gives, for each worker_id, its
readings oldest first: {"load_avg", "memory_usage", "gpu_usage", "seen"}.
What a worker posts is scribe-worker's healthcheck() (main.py), every ten
seconds:

- "load_avg" is the CPU in per cent (psutil.cpu_percent()), whatever its
  name says;
- "memory_usage" is the memory in use, in per cent;
- "gpu_usage" is a list with one entry per GPU: "index", "name",
  "memory_used" and "memory_total" (MiB), "utilization" (per cent),
  "temperature" and "power_draw". A server with more than one GPU posts each
  as a worker of its own, "<host>-<index>", with the same CPU and memory.

Older readings, and other workers, may give "gpu_usage" as one dict, a
number, a JSON string or nothing; all are read as well as they can be, and
what cannot be read is left out rather than shown as nought.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

# A worker is offline when it has not been heard from for this long: three
# missed posts.
OFFLINE_AFTER = 30
# The charts' window, as in the team's Grafana.
WINDOW = 30 * 60
# Workers not heard from for this long are put away, under a heading of
# their own: someone would have acted on them long before.
PUT_AWAY_AFTER = 24 * 3600

# How often the page may read again, in seconds; 0 is off.
REFRESH_CHOICES = {0: "Off", 5: "5 s", 10: "10 s", 30: "30 s", 60: "1 min"}
REFRESH_DEFAULT = 10


@dataclass
class GPU:
    index: int
    name: str
    use: Optional[float]
    memory: Optional[float]  # per cent of the card's memory


@dataclass
class Reading:
    seen: float
    cpu: Optional[float]
    memory: Optional[float]
    gpus: list = field(default_factory=list)


@dataclass
class Worker:
    worker_id: str
    readings: list
    online: bool
    last_seen: float

    @property
    def gpu_indexes(self) -> list:
        """Every GPU index in the readings, in order."""

        return sorted({gpu.index for reading in self.readings for gpu in reading.gpus})

    def gpu_name(self) -> str:
        """The latest name a GPU of this worker was given, or ""."""

        for reading in reversed(self.readings):
            for gpu in reading.gpus:
                if gpu.name:
                    return gpu.name

        return ""


def number(value) -> Optional[float]:
    """A figure, or None: never a guess, never a nought for nothing."""

    if isinstance(value, bool) or value is None:
        return None

    try:
        figure = float(value)
    except (TypeError, ValueError):
        return None

    return figure if figure == figure else None  # not NaN


def gpus_of(value) -> list:
    """A reading's "gpu_usage", whatever its shape, as GPUs."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []

    if isinstance(value, dict):
        value = [value]

    if not isinstance(value, list):
        return []

    out = []

    for at, entry in enumerate(value):
        if not isinstance(entry, dict):
            continue

        used, total = number(entry.get("memory_used")), number(entry.get("memory_total"))
        index = entry.get("index", at)

        out.append(
            GPU(
                index=index if isinstance(index, int) and not isinstance(index, bool) else at,
                name=str(entry.get("name") or ""),
                use=number(entry.get("utilization")),
                memory=100 * used / total if used is not None and total else None,
            )
        )

    return out


def reading_of(sample) -> Optional[Reading]:
    if not isinstance(sample, dict):
        return None

    seen = number(sample.get("seen"))

    if seen is None:
        return None

    return Reading(
        seen=seen,
        cpu=number(sample.get("load_avg")),
        memory=number(sample.get("memory_usage")),
        gpus=gpus_of(sample.get("gpu_usage")),
    )


def workers_of(result, now: float) -> list:
    """The backend's result as Workers, each with its readings oldest first."""

    if not isinstance(result, dict):
        return []

    out = []

    for worker_id, samples in result.items():
        readings = sorted(
            (r for r in (reading_of(s) for s in (samples or [])) if r is not None),
            key=lambda r: r.seen,
        )

        if not readings:
            continue

        last = readings[-1].seen
        out.append(Worker(str(worker_id), readings, now - last < OFFLINE_AFTER, last))

    return out


def arranged(workers: list, now: float) -> tuple:
    """
    (shown, put away): the offline first, so they are seen without
    scrolling, then the online, each by name; and apart from them those not
    heard from for PUT_AWAY_AFTER, the longest quiet last.
    """

    shown = [w for w in workers if now - w.last_seen < PUT_AWAY_AFTER]
    away = [w for w in workers if now - w.last_seen >= PUT_AWAY_AFTER]

    shown.sort(key=lambda w: (w.online, w.worker_id.lower()))
    away.sort(key=lambda w: -w.last_seen)

    return shown, away


def count_line(shown: list) -> str:
    """How many are offline and online, the offline first."""

    if not shown:
        return "No worker has been heard from in the last 24 hours."

    offline = sum(1 for w in shown if not w.online)
    online = len(shown) - offline

    if not offline:
        return f"All {online} workers online." if online > 1 else "The worker is online."

    if not online:
        return f"All {offline} workers offline." if offline > 1 else "The worker is offline."

    return f"{offline} offline, {online} online."


def ago(seconds: float) -> str:
    """ "12 minutes ago", "1 hour ago", "3 days ago"."""

    seconds = max(0, int(seconds))

    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"

    return "just now" if seconds < 5 else f"{seconds} seconds ago"


def in_window(worker: Worker, now: float, window: int = WINDOW) -> list:
    return [r for r in worker.readings if r.seen >= now - window]


def percent(value: Optional[float]) -> str:
    return "–" if value is None else f"{round(value)} %"


def gpu_label(index: int, indexes: list) -> str:
    """ "GPU" for a worker's only GPU, "GPU 1" where there are several."""

    return "GPU" if len(indexes) <= 1 else f"GPU {index}"


def gpu_value(reading: Reading, index: int, what: str) -> Optional[float]:
    for gpu in reading.gpus:
        if gpu.index == index:
            return getattr(gpu, what)

    return None


def peak(readings: list, value) -> Optional[tuple]:
    """(reading, figure) where `value(reading)` is highest, the first on a tie."""

    best = None

    for reading in readings:
        figure = value(reading)

        if figure is not None and (best is None or figure > best[1]):
            best = (reading, figure)

    return best

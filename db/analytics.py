import asyncio

import httpx

from utils.settings import get_settings
from utils.token import get_auth_header

settings = get_settings()


async def _fetch(client: httpx.AsyncClient, path: str, default, **params):
    try:
        response = await client.get(
            f"{settings.API_URL}{path}",
            headers=get_auth_header(),
            params=params or None,
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return default


async def get_page_views(days: int = 30) -> list[dict]:
    """Page views grouped by path + day."""
    async with httpx.AsyncClient() as client:
        return await _fetch(
            client, "/api/v1/admin/analytics/views", [], days=days
        )


async def get_page_views_summary() -> list[dict]:
    """Total views per page: all time and last 30 days."""
    async with httpx.AsyncClient() as client:
        return await _fetch(client, "/api/v1/admin/analytics/summary", [])


async def get_views_per_day(days: int = 30) -> list[dict]:
    """Total views per day."""
    async with httpx.AsyncClient() as client:
        return await _fetch(
            client, "/api/v1/admin/analytics/daily", [], days=days
        )


async def get_recent_views(limit: int = 50) -> list[dict]:
    """Most recent page views."""
    async with httpx.AsyncClient() as client:
        return await _fetch(
            client, "/api/v1/admin/analytics/recent", [], limit=limit
        )


async def get_hourly_heatmap(days: int = 30) -> list[dict]:
    """Views by day-of-week and hour-of-day for heatmap."""
    async with httpx.AsyncClient() as client:
        return await _fetch(
            client, "/api/v1/admin/analytics/heatmap", [], days=days
        )


async def get_hourly_distribution(days: int = 30) -> list[dict]:
    """Views per hour-of-day."""
    async with httpx.AsyncClient() as client:
        return await _fetch(
            client, "/api/v1/admin/analytics/hourly", [], days=days
        )


async def get_week_over_week() -> dict:
    """Week-over-week comparison."""
    async with httpx.AsyncClient() as client:
        return await _fetch(
            client,
            "/api/v1/admin/analytics/wow",
            {"this_week": 0, "last_week": 0, "change_pct": None},
        )


async def get_total_stats() -> dict:
    """Aggregate stats for summary cards."""
    async with httpx.AsyncClient() as client:
        return await _fetch(
            client,
            "/api/v1/admin/analytics/stats",
            {
                "total_views": 0,
                "views_30d": 0,
                "top_page": {"path": "N/A", "cnt": 0},
            },
        )


async def fetch_all(days: int = 30, recent_limit: int = 50) -> dict:
    """Fetch every analytics endpoint in parallel over a single client.

    Returns a dict keyed by the logical name used by the analytics page.
    """
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            _fetch(client, "/api/v1/admin/analytics/stats",
                   {"total_views": 0, "views_30d": 0, "top_page": {"path": "N/A", "cnt": 0}}),
            _fetch(client, "/api/v1/admin/analytics/wow",
                   {"this_week": 0, "last_week": 0, "change_pct": None}),
            _fetch(client, "/api/v1/admin/analytics/summary", []),
            _fetch(client, "/api/v1/admin/analytics/heatmap", [], days=days),
            _fetch(client, "/api/v1/admin/analytics/hourly", [], days=days),
            _fetch(client, "/api/v1/admin/analytics/views", [], days=days),
            _fetch(client, "/api/v1/admin/analytics/daily", [], days=days),
            _fetch(client, "/api/v1/admin/analytics/recent", [], limit=recent_limit),
        )
    keys = (
        "stats",
        "wow",
        "summary",
        "heatmap",
        "hourly",
        "page_views",
        "daily",
        "recent",
    )
    return dict(zip(keys, results))

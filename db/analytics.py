import requests

from utils.settings import get_settings
from utils.token import get_auth_header

settings = get_settings()


def get_page_views(days: int = 30) -> list[dict]:
    """
    Page views grouped by path + day.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/views",
            headers=get_auth_header(),
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return []


def get_page_views_summary() -> list[dict]:
    """
    Total views per page: all time and last 30 days.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/summary",
            headers=get_auth_header(),
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return []


def get_views_per_day(days: int = 30) -> list[dict]:
    """
    Total views per day.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/daily",
            headers=get_auth_header(),
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return []


def get_recent_views(limit: int = 50) -> list[dict]:
    """
    Most recent page views.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/recent",
            headers=get_auth_header(),
            params={"limit": limit},
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return []


def get_hourly_heatmap(days: int = 30) -> list[dict]:
    """
    Views by day-of-week and hour-of-day for heatmap.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/heatmap",
            headers=get_auth_header(),
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return []


def get_hourly_distribution(days: int = 30) -> list[dict]:
    """
    Views per hour-of-day.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/hourly",
            headers=get_auth_header(),
            params={"days": days},
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return []


def get_week_over_week() -> dict:
    """
    Week-over-week comparison.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/wow",
            headers=get_auth_header(),
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return {"this_week": 0, "last_week": 0, "change_pct": None}


def get_total_stats() -> dict:
    """
    Aggregate stats for summary cards.
    """
    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/admin/analytics/stats",
            headers=get_auth_header(),
        )
        response.raise_for_status()
        return response.json()["result"]
    except Exception:
        return {
            "total_views": 0,
            "views_30d": 0,
            "top_page": {"path": "N/A", "cnt": 0},
        }

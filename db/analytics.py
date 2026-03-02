import threading

import requests

from utils.settings import get_settings
from utils.token import get_auth_header

settings = get_settings()


def log_page_view(path: str) -> None:
    """Log an anonymous page view via the backend API (fire-and-forget)."""
    if not path:
        return
    # Capture auth header on the calling thread (NiceGUI storage is thread-local)
    headers = get_auth_header()
    threading.Thread(
        target=_send_page_view, args=(path, headers), daemon=True
    ).start()


def _send_page_view(path: str, headers: dict) -> None:
    try:
        requests.post(
            f"{settings.API_URL}/api/v1/admin/analytics/log",
            headers=headers,
            json={"path": path},
            timeout=2,
        )
    except Exception:
        pass


def get_page_views(days: int = 30) -> list[dict]:
    """Page views grouped by path + day."""
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
    """Total views per page: all time and last 30 days."""
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
    """Total views per day."""
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
    """Most recent page views."""
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


def get_total_stats() -> dict:
    """Aggregate stats for summary cards."""
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

"""
The backend's Sunet Drive endpoints (SUNET/scribe-backend#64), as plain
async calls. The dialogs that use them are in utils/drive_dialogs.py.

Every call answers a `DriveResult` rather than raising: `ok`, the backend's
`result` when it worked, and otherwise a message fit to show the reader and
the backend's `reason` code -- "disabled", "not_connected", "exists",
"too_large", "not_found", "unavailable", "invalid". The dialogs
act on the reason; the message is only ever shown.

Scribe never sees the reader's Drive password. Connecting sends them to
their Drive in a tab of its own (Nextcloud's Login Flow v2), and the
backend holds the grant Drive issues for an idle hour at most.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from nicegui import app

from utils.helpers import storage_decrypt
from utils.settings import get_settings, short_service_name
from utils.token import get_auth_header

settings = get_settings()

DEFAULT_DISPLAY_NAME = "Sunet Drive"

# Listing and connecting are quick; a transfer of an hour of video from
# Drive into Scribe is not, and the backend answers only once it is done.
TIMEOUT = httpx.Timeout(30.0)
TRANSFER_TIMEOUT = httpx.Timeout(30.0, read=60.0 * 30)


@dataclass
class DriveResult:
    ok: bool
    result: Any = None
    error: str = ""
    reason: Optional[str] = None
    status: int = 0
    extra: dict = field(default_factory=dict)


def _url(path: str) -> str:
    return f"{settings.API_URL}/api/v1/drive{path}"


def _answer(response: httpx.Response) -> DriveResult:
    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.is_success:
        return DriveResult(True, result=body.get("result"), status=response.status_code)

    return DriveResult(
        False,
        error=body.get("error") or f"Drive request failed ({response.status_code}).",
        reason=body.get("reason"),
        status=response.status_code,
    )


async def _call(method: str, path: str, timeout=TIMEOUT, **kwargs) -> DriveResult:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method, _url(path), headers=get_auth_header(), **kwargs
            )
    except httpx.HTTPError:
        return DriveResult(
            False, error=f"{short_service_name()} could not be reached. Try again.", reason="unavailable"
        )

    return _answer(response)


async def drive_status() -> DriveResult:
    """
    {"enabled", "display_name", and when enabled: "instance" (the
    organisation's -- readers do not choose one), "connected", "pending"}.
    """

    return await _call("GET", "")


async def drive_connect() -> DriveResult:
    """
    Start signing in to Drive: result["login_url"] is where the reader goes.
    """

    return await _call("POST", "/connect")


async def drive_poll() -> DriveResult:
    """
    result["state"]: "connected", "pending" or "none".
    """

    return await _call("GET", "/connect")


async def drive_logout() -> DriveResult:
    """
    Log out of Drive: the backend revokes Scribe's access in Drive too.
    """

    return await _call("DELETE", "/connect")


async def drive_list(path: str = "") -> DriveResult:
    """
    result: {"path", "entries": [{"name", "path", "is_dir", "size", "mime",
    "modified", "media"}]}, folders first.
    """

    return await _call("GET", "/files", params={"path": path})


async def drive_import(path: str) -> DriveResult:
    """
    Bring a file in from Drive as a new job. result: {"uuid", "filename",
    ...}.
    """

    return await _call("POST", "/import", timeout=TRANSFER_TIMEOUT, json={"path": path})


async def drive_save(
    folder: str, name: str, content: bytes, overwrite: bool = False
) -> DriveResult:
    """
    Save `content` as `name` in `folder` of the reader's Drive. Without
    `overwrite`, an existing file answers reason "exists".
    """

    return await _call(
        "PUT",
        "/files",
        timeout=TRANSFER_TIMEOUT,
        params={
            "path": folder,
            "name": name,
            "overwrite": "true" if overwrite else "false",
        },
        content=content,
    )


async def drive_save_original(
    job_id: str,
    folder: str,
    name: Optional[str] = None,
    overwrite: bool = False,
) -> DriveResult:
    """
    Save a recording's original to the reader's Drive. The backend decrypts
    it with the reader's encryption password -- the same check downloading
    it makes -- and streams it straight into Drive; it never passes through
    here. `name` defaults to the recording's own; an existing file answers
    reason "exists" unless `overwrite`.
    """

    return await _call(
        "POST",
        "/save-original",
        timeout=TRANSFER_TIMEOUT,
        json={
            "job_id": job_id,
            "encryption_password": storage_decrypt(
                app.storage.user.get("encryption_password")
            ),
            "path": folder,
            "name": name,
            "overwrite": overwrite,
        },
    )


def display_name(status: Optional[dict]) -> str:
    """
    What to call the reader's Drive: their organisation's own name for it,
    or "Sunet Drive".
    """

    return ((status or {}).get("display_name") or "").strip() or DEFAULT_DISPLAY_NAME

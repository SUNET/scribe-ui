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

import requests

from nicegui import app, ui
from typing import Optional
from utils.crypto import decrypt_string, encrypt_string, get_browser_id
from utils.settings import get_settings
from utils.token import get_auth_header

settings = get_settings()


def storage_encrypt(plaintext: str) -> str:
    """
    Encrypt a string using the current user's browser-bound key.
    """

    return encrypt_string(
        plaintext,
        app.storage.browser["_scribe_bk"] + settings.STORAGE_SECRET,
        get_browser_id().encode(),
        b"scribe-secret",
    )


def storage_decrypt(encrypted: Optional[str]) -> Optional[str]:
    """
    Decrypt a string using the current user's browser-bound key.

    Returns None for falsy inputs (None, empty string) and redirects
    to the login page if decryption fails (e.g. stale or migrated data).
    """

    if not encrypted:
        return None

    try:
        return decrypt_string(
            encrypted,
            app.storage.browser["_scribe_bk"] + settings.STORAGE_SECRET,
            get_browser_id().encode(),
            b"scribe-secret",
        )
    except Exception:
        app.storage.user["encryption_password"] = None
        ui.navigate.to("/")
        return None


def encryption_password_set(password: str) -> None:
    """
    Set the encryption password for the user.
    This is a placeholder function. Implement the logic to store
    the encryption password securely.
    """

    try:
        response = requests.put(
            f"{settings.API_URL}/api/v1/me",
            headers=get_auth_header(),
            json={"encryption": True, "encryption_password": password},
        )
        response.raise_for_status()
        data = response.json()

        return data["result"]

    except requests.exceptions.RequestException:
        return None


def encryption_password_verify(password: str) -> bool:
    """
    Verify the encryption password for the user.
    This is a placeholder function. Implement the logic to verify
    the encryption password with the backend.
    """

    try:
        response = requests.put(
            f"{settings.API_URL}/api/v1/me",
            headers=get_auth_header(),
            json={"encryption_password": password, "verify_password": True},
        )
        response.raise_for_status()

        return True

    except requests.exceptions.RequestException:
        return False


def reset_password() -> None:
    """
    Reset the encryption password for the user.
    This is a placeholder function. Implement the logic to reset
    the encryption password with the backend.
    """

    def do_reset():
        try:
            response = requests.put(
                f"{settings.API_URL}/api/v1/me",
                headers=get_auth_header(),
                json={"reset_password": True},
            )
            response.raise_for_status()

            ui.notify(
                "Encryption passphrase has been reset. All previously encrypted files have been removed.",
                color="positive",
            )
            app.storage.user["encryption_password"] = None
            ui.navigate.to("/")

        except requests.exceptions.RequestException:
            ui.notify("Failed to reset encryption passphrase.", color="negative")

    with ui.dialog() as dialog:
        with ui.card():
            ui.label("Reset encryption passphrase").classes("text-h6")
            ui.label(
                "Are you sure you want to reset your encryption passphrase? This will remove all your files and cannot be undone."
            ).classes("text-subtitle2").style("margin-bottom: 10px;")

            with ui.row().classes("justify-between w-full"):
                ui.button(
                    "Cancel",
                    on_click=lambda: ui.navigate.to("/"),
                ).props(
                    "color=black"
                ).style("margin-top: 10px;")
                ui.button(
                    "Reset Passphrase",
                    on_click=lambda: do_reset(),
                ).props(
                    "color=red"
                ).style("margin-top: 10px;")
        dialog.open()


def export_customers_csv() -> None:
    """
    Export customers data as CSV.
    """
    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/customers/export/csv",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        csv_data = res.content.decode("utf-8")

        ui.download.content(str(csv_data), filename="customers_export.csv")

    except requests.RequestException:
        ui.notify("Error when exporting customers", color="red")


def save_customer(
    customber_abbr: str,
    customer_id: str,
    partner_id: str,
    name: str,
    contact_email: str,
    support_contact_email: str,
    priceplan: str,
    base_fee: int,
    selected_realms: list,
    new_realms: str,
    notes: str,
    blocks_purchased: int,
) -> None:
    # Combine selected and new realms
    new_realm_list = [r.strip() for r in new_realms.split(",") if r.strip()]
    all_realms = list(set(selected_realms + new_realm_list))
    realms_str = ",".join(all_realms)

    try:
        res = requests.put(
            settings.API_URL + f"/api/v1/admin/customers/{customer_id}",
            headers=get_auth_header(),
            json={
                "customer_abbr": customber_abbr,
                "partner_id": partner_id,
                "name": name,
                "contact_email": contact_email,
                "support_contact_email": support_contact_email,
                "priceplan": priceplan,
                "base_fee": int(base_fee) if base_fee else 0,
                "realms": realms_str,
                "notes": notes,
                "blocks_purchased": int(blocks_purchased) if blocks_purchased else 0,
            },
        )
        res.raise_for_status()
        ui.navigate.to("/admin/customers")
    except requests.RequestException as e:
        ui.notify(f"Error saving customer: {e}", type="negative")


def customers_get() -> list:
    """
    Fetch all customers from backend.
    """
    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/customers", headers=get_auth_header()
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching customers: {e}")
        return []


def realms_get() -> list:
    """
    Fetch all realms from backend.
    """
    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/realms", headers=get_auth_header()
        )
        res.raise_for_status()
        return res.json()["result"]
    except requests.RequestException as e:
        print(f"Error fetching realms: {e}")
        return []


def groups_get() -> list:
    """
    Fetch all groups from backend.
    """

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/groups", headers=get_auth_header()
        )
        res.raise_for_status()

        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching groups: {e}")
        return []


def user_statistics_get(group_id: str) -> dict:
    """
    Fetch user statistics for a group from backend.
    """

    try:
        res = requests.get(
            settings.API_URL + f"/api/v1/admin/groups/{group_id}/stats",
            headers=get_auth_header(),
        )
        res.raise_for_status()

        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching user statistics: {e}")
        return {}


def email_save(email: str) -> None:
    """
    Save and test the notification email address.

    Parameters:
        email (str): The email address to save.
    """

    try:
        response = requests.put(
            f"{settings.API_URL}/api/v1/me",
            headers=get_auth_header(),
            json={"email": email},
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data.get("result", {}):
            ui.notify(f"Error: {data['result']['error']}", color="red")
            return None

        ui.notify("E-mail address saved successfully", color="green")
        return data["result"]

    except requests.exceptions.RequestException:
        ui.notify("Failed to save e-mail address", color="red")
        return None


def email_get() -> str:
    """
    Get the current notification email address.

    Returns:
        str: The current email address.
    """

    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/me", headers=get_auth_header(), json={}
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data.get("result", {}):
            ui.notify(f"Error: {data['result']['error']}", color="red")
            return ""

        return data["result"].get("email", "")

    except requests.exceptions.RequestException:
        ui.notify("Failed to retrieve e-mail address", color="red")
        return ""


def email_save_notifications(
    job: Optional[bool] = None,
    deletion: Optional[bool] = None,
    user: Optional[bool] = None,
    quota: Optional[bool] = None,
    weekly_report: Optional[bool] = None,
) -> None:
    """
    Save notification preferences for the user.

    Parameters:
        job (bool | None): Whether to receive notifications for transcription jobs.
        deletion (bool | None): Whether to receive notifications for file deletions.
        user (bool | None): Whether to receive notifications for new users.
        quota (bool | None): Whether to receive notifications when quota nears limit.
        weekly_report (bool | None): Whether to receive weekly usage reports.
    """

    payload = {
        "notifications": {
            "notify_on_job": job,
            "notify_on_deletion": deletion,
            "notify_on_user": user,
            "notify_on_quota": quota,
            "notify_on_weekly_report": weekly_report,
        }
    }

    try:
        response = requests.put(
            f"{settings.API_URL}/api/v1/me",
            headers=get_auth_header(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data.get("result", {}):
            ui.notify(f"Error: {data['result']['error']}", color="red")
            return

        ui.notify("Notification preferences updated", color="green")

    except requests.exceptions.RequestException:
        ui.notify("Failed to update notification preferences", color="red")


def email_save_notifications_get() -> dict:
    """
    Get the current notification preferences for the user.

    Returns:
        dict: A dictionary containing the current notification preferences.
    """

    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/me", headers=get_auth_header(), json={}
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data.get("result", {}):
            ui.notify(f"Error: {data['result']['error']}", color="red")
            return {}

        notifications = data["result"].get("notifications", {})

        if notifications is None:
            return {}

        return notifications

    except requests.exceptions.RequestException:
        ui.notify("Failed to retrieve notification preferences", color="red")
        return {}


def test_all_notifications() -> None:
    """
    Trigger all notification types to be sent to the current user's email.
    Temporary function for testing email notifications.
    """

    try:
        response = requests.post(
            f"{settings.API_URL}/api/v1/me/test-notifications",
            headers=get_auth_header(),
        )
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            ui.notify(f"Error: {data['error']}", color="red")
            return

        result = data.get("result", {})
        count = result.get("count", 0)
        sent_to = result.get("sent_to", "unknown")
        ui.notify(
            f"{count} test notifications queued for {sent_to}",
            color="green",
        )

    except requests.exceptions.RequestException:
        ui.notify("Failed to send test notifications", color="red")


def save_group(
    selected_rows: list, name: str, description: str, group_id: str, quota_seconds: int
) -> None:
    """
    Save group details and assigned users via the backend API.
    """

    usernames = [row["username"] for row in selected_rows]

    try:
        res = requests.put(
            settings.API_URL + f"/api/v1/admin/groups/{group_id}",
            headers=get_auth_header(),
            json={
                "name": name,
                "description": description,
                "usernames": usernames,
                "quota": int(quota_seconds) * 60,
            },
        )

        res.raise_for_status()

        ui.navigate.to("/admin")
    except requests.RequestException:
        error = res.json()

        with ui.dialog() as dialog:
            with ui.card():
                ui.label("Error saving group").classes("text-h6")
                ui.label(error["error"])
                ui.button("Close", on_click=lambda: dialog.close()).props(
                    "color=black"
                ).style("margin-top: 10px;")

        dialog.open()


def remove_user(selected_rows: list) -> None:
    """
    Remove selected users via the backend API.
    """

    for user in selected_rows:
        try:
            res = requests.delete(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
            )
            res.raise_for_status()
        except requests.RequestException as e:
            ui.notify(
                f"Error removing user {user['username']}: {e}",
                type="negative",
            )
            return

    ui.navigate.to("/admin/users")


def set_active_status(selected_rows: list, make_active: bool) -> None:
    """
    Set or remove active status for selected users.
    """

    for user in selected_rows:
        try:
            res = requests.put(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
                json={"active": make_active},
            )
            res.raise_for_status()
            ui.navigate.to("/admin/users")
        except requests.RequestException as e:
            ui.notify(
                f"Error updating active status for {user['username']}: {e}",
                type="negative",
            )


def set_admin_status(
    selected_rows: list, make_admin: bool, dialog: ui.dialog, group_id: str
) -> None:
    """
    Set or remove admin status for selected users.
    """

    for user in selected_rows:
        try:
            res = requests.put(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
                json={"admin": make_admin},
            )
            res.raise_for_status()

            if dialog:
                dialog.close()
                ui.navigate.to(f"/admin/edit/{group_id}")
            else:
                ui.navigate.to("/admin/users")
        except requests.RequestException as e:
            ui.notify(
                f"Error updating admin status for {user['username']}: {e}",
                type="negative",
            )


def save_domains(
    selected_rows: list, domains: list, dialog: ui.dialog
) -> None:
    """
    Save allowed domains for selected users.
    """

    domains_str = ",".join(domains) if domains else ""

    for user in selected_rows:
        try:
            res = requests.put(
                settings.API_URL + f"/api/v1/admin/{user['username']}",
                headers=get_auth_header(),
                json={"admin_domains": domains_str},
            )
            res.raise_for_status()
            ui.navigate.to("/admin/users")
        except requests.RequestException as e:
            ui.notify(
                f"Error updating domains for {user['username']}: {e}", type="negative"
            )

    dialog.close()


def get_customer_realms(user_realms: set[str]) -> list[str]:
    """
    Return the realms belonging to the customer(s) that match the given user realms.
    Falls back to realms_get() if the customers API is not accessible.
    """

    customers_data = customers_get()
    customers = (
        customers_data.get("result", [])
        if isinstance(customers_data, dict)
        else []
    )

    customer_realms = []
    for c in customers:
        c_realms = [
            r.strip() for r in (c.get("realms") or "").split(",") if r.strip()
        ]
        if user_realms & set(c_realms):
            customer_realms.extend(c_realms)
    realms = sorted(set(customer_realms))

    if not realms:
        realms = [r for r in realms_get() if r and "." in r]

    return realms


def set_domains(selected_rows: list, all_users: list) -> None:
    """
    Show a dialog with an input to set allowed domains.
    """

    user_realms = {u["realm"] for u in selected_rows if u.get("realm")}
    realms = get_customer_realms(user_realms)

    if not realms:
        realms = sorted(
            {u["realm"] for u in all_users if u.get("realm") and "." in u["realm"]}
        )

    domains = []

    for user in selected_rows:
        if not user.get("admin_domains"):
            continue
        for domain in user["admin_domains"].split(","):
            if domain.strip() in realms:
                domains.append(domain.strip())

    with ui.dialog() as domain_dialog:
        with ui.card().style("width: 500px; max-width: 90vw;"):
            ui.label("Set domains the user can administer").classes(
                "text-2xl font-bold"
            )
            domains_select = (
                ui.select(
                    realms,
                    label="Allowed domains",
                    multiple=True,
                    value=domains,
                )
                .classes("w-full")
                .props("outlined use-chips")
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: domain_dialog.close())
                ui.button("Save").classes("default-style").props("color=black flat").on(
                    "click",
                    lambda: save_domains(
                        selected_rows,
                        domains_select.value,
                        domain_dialog,
                    ),
                )

        domain_dialog.open()


def rules_get() -> list:
    """
    Fetch all attribute rules from backend.
    """

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/rules", headers=get_auth_header()
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error fetching rules: {e}")
        return []


def rule_create(data: dict) -> dict | None:
    """
    Create a new attribute rule.
    """

    try:
        res = requests.post(
            settings.API_URL + "/api/v1/admin/rules",
            headers=get_auth_header(),
            json=data,
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error creating rule: {e}")
        return None


def rule_update(rule_id: int, data: dict) -> dict | None:
    """
    Update an existing attribute rule.
    """

    try:
        res = requests.put(
            settings.API_URL + f"/api/v1/admin/rules/{rule_id}",
            headers=get_auth_header(),
            json=data,
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error updating rule: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response body: {e.response.text}")
        return None


def rule_delete(rule_id: int) -> bool:
    """
    Delete an attribute rule.
    """

    try:
        res = requests.delete(
            settings.API_URL + f"/api/v1/admin/rules/{rule_id}",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error deleting rule: {e}")
        return False


def attributes_get() -> list:
    """
    Fetch all onboarding attributes from backend.
    """

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/attributes",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        return res.json().get("result", [])
    except requests.RequestException as e:
        print(f"Error fetching attributes: {e}")
        return []


def attribute_create(data: dict) -> dict | None:
    """
    Add a new onboarding attribute.
    """

    try:
        res = requests.post(
            settings.API_URL + "/api/v1/admin/attributes",
            headers=get_auth_header(),
            json=data,
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error creating attribute: {e}")
        return None


def attribute_delete(attribute_id: int) -> bool:
    """
    Delete an onboarding attribute.
    """

    try:
        res = requests.delete(
            settings.API_URL + f"/api/v1/admin/attributes/{attribute_id}",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error deleting attribute: {e}")
        return False


def rules_test(rule_ids: list[int]) -> list:
    """
    Test which users would be matched by the given rules.
    """

    try:
        res = requests.post(
            settings.API_URL + "/api/v1/admin/rules/test",
            headers=get_auth_header(),
            json={"rule_ids": rule_ids},
        )
        res.raise_for_status()
        return res.json().get("result", [])
    except requests.RequestException as e:
        print(f"Error testing rules: {e}")
        return []


def announcements_get() -> list:
    """Fetch all announcements from backend."""

    try:
        res = requests.get(
            settings.API_URL + "/api/v1/admin/announcements",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        return res.json().get("result", [])
    except requests.RequestException as e:
        print(f"Error fetching announcements: {e}")
        return []


def announcement_create(data: dict) -> dict | None:
    """Create a new announcement."""

    try:
        res = requests.post(
            settings.API_URL + "/api/v1/admin/announcements",
            headers=get_auth_header(),
            json=data,
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error creating announcement: {e}")
        return None


def announcement_update(announcement_id: int, data: dict) -> dict | None:
    """Update an existing announcement."""

    try:
        res = requests.put(
            settings.API_URL + f"/api/v1/admin/announcements/{announcement_id}",
            headers=get_auth_header(),
            json=data,
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        print(f"Error updating announcement: {e}")
        return None


def announcement_delete(announcement_id: int) -> bool:
    """Delete an announcement."""

    try:
        res = requests.delete(
            settings.API_URL + f"/api/v1/admin/announcements/{announcement_id}",
            headers=get_auth_header(),
        )
        res.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error deleting announcement: {e}")
        return False

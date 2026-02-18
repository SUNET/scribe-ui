import requests

from nicegui import ui
from typing import Optional
from utils.settings import get_settings
from utils.storage import storage
from utils.token import get_auth_header

settings = get_settings()


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
            storage["encryption_password"] = None
            ui.navigate.to("/")

        except requests.exceptions.RequestException:
            ui.notify("Failed to reset encryption passphrase.", color="negative")

    with ui.dialog() as dialog:
        with ui.card():
            ui.label("Reset Encryption Passphrase").classes("text-h6")
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
) -> None:
    """
    Save notification preferences for the user.

    Parameters:
        job (bool | None): Whether to receive notifications for transcription jobs.
        deletion (bool | None): Whether to receive notifications for file deletions.
        user (bool | None): Whether to receive notifications for new users.
    """

    payload = {
        "notifications": {
            "notify_on_job": job,
            "notify_on_deletion": deletion,
            "notify_on_user": user,
            # "notify_on_quota": quota,
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


def save_group(
    selected_rows: list, name: str, description: str, group_id: str, quota_seconds: int
) -> None:
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
    selected_rows: list, domains: list, domains_str: str, dialog: ui.dialog
) -> None:
    """
    Save allowed domains for selected users.
    """

    selected_domains = domains if domains else []
    new_domains = [r.strip() for r in domains_str.split(",") if r.strip()]
    all_domains = list(set(selected_domains + new_domains))
    domains_str = ",".join(all_domains)

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


def set_domains(selected_rows: list) -> None:
    """
    Show a dialog with an input to set allowed domains.
    Domains should be separated by commas.
    """

    realms = realms_get()
    domains = []
    domains_str = ""

    for user in selected_rows:
        if not user.get("admin_domains"):
            continue
        for domain in user["admin_domains"].split(","):
            if domain.strip() in realms:
                domains.append(domain.strip())
            else:
                domains_str += domain.strip() + ", "

    with ui.dialog() as domain_dialog:
        with ui.card().style("width: 500px; max-width: 90vw;"):
            ui.label("Set domains the user can administer").classes(
                "text-2xl font-bold"
            )
            domains_select = (
                ui.select(
                    realms,
                    label="Allowed domains (existing domains)",
                    multiple=True,
                    value=domains,
                )
                .classes("w-full")
                .props("outlined")
            )

            domains_input = (
                ui.input("Add new domains (comma-separated)", value=domains_str.strip())
                .classes("w-full")
                .props("outlined")
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
                        domains_input.value,
                        domain_dialog,
                    ),
                )

        domain_dialog.open()

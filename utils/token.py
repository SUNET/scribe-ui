import jwt
import requests
import time

from nicegui import app
from utils.settings import get_settings


settings = get_settings()


def token_refresh_call() -> str:
    try:
        token_refresh = app.storage.user.get("refresh_token")
        response = requests.post(
            settings.OIDC_APP_REFRESH_ROUTE,
            json={"token": token_refresh},
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return None

    return response.json().get("access_token")


def token_refresh() -> bool:
    """
    Refresh the token using the refresh token.
    """

    token_auth = app.storage.user.get("token")

    try:
        jwt_instance = jwt.JWT()
        jwt_decoded = jwt_instance.decode(token_auth, do_verify=False)
    except Exception:
        token = token_refresh_call()
        if not token:
            return None
        jwt_decoded = jwt_instance.decode(token, do_verify=False)
        app.storage.user["token"] = token
    try:
        # Only refresh if the token is about to expire within 60 seconds.
        if jwt_decoded["exp"] - int(time.time()) > 60:
            return True

        token = token_refresh_call()
        app.storage.user["token"] = token
    except requests.exceptions.RequestException:
        return None

    return True


def get_auth_header() -> dict[str, str]:
    """
    Get the authorization header for API requests.
    """

    token = app.storage.user.get("token")

    try:
        jwt_instance = jwt.JWT()
        jwt_instance.decode(token, do_verify=False)
    except Exception:
        return None

    return {"Authorization": f"Bearer {token}"}


def get_user_info() -> tuple[str, int] | None:
    """
    Get user information from token.
    """

    token = app.storage.user.get("token")

    if not token:
        return None, None

    try:
        jwt_instance = jwt.JWT()
        decoded_token = jwt_instance.decode(token, do_verify=False)
        lifetime = decoded_token["exp"] - int(time.time())

        if "eduPersonPrincipalName" in decoded_token:
            username = decoded_token["eduPersonPrincipalName"]
        elif "preferred_username" in decoded_token:
            username = decoded_token["preferred_username"]
        elif "username" in decoded_token:
            username = decoded_token["username"]
        else:
            username = "Unknown"
    except Exception:
        return None, None

    return username, lifetime


def get_user_data() -> dict:
    """
    Get user data.
    """

    try:
        response = requests.get(
            f"{settings.API_URL}/api/v1/me", headers=get_auth_header()
        )
        response.raise_for_status()
        data = response.json()

        return data["result"]

    except requests.exceptions.RequestException:
        return None


def get_admin_status() -> bool:
    """
    Check if the user is an admin based on the token.
    """
    try:
        return get_user_data()["user"]["admin"]
    except (KeyError, TypeError):
        return False


def get_user_status() -> bool:
    """
    Check if the user is a normal user based on the token.
    """
    try:
        return get_user_data()["user"]["active"]
    except (KeyError, TypeError):
        return False

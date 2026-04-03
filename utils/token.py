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

import jwt
import httpx
import time

from nicegui import app
from utils.settings import get_settings


settings = get_settings()


async def token_refresh_call() -> str:
    try:
        refresh_token = app.storage.user.get("refresh_token")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.OIDC_APP_REFRESH_ROUTE,
                json={"token": refresh_token},
                timeout=10,
            )
        response.raise_for_status()
    except (httpx.HTTPError, Exception):
        return None

    return response.json().get("access_token")


async def token_refresh() -> bool:
    """
    Refresh the token using the refresh token.
    """

    token_auth = app.storage.user.get("token")

    try:
        jwt_instance = jwt.JWT()
        jwt_decoded = jwt_instance.decode(token_auth, do_verify=False)
    except Exception:
        token = await token_refresh_call()
        if not token:
            return None
        jwt_decoded = jwt_instance.decode(token, do_verify=False)
        app.storage.user["token"] = token
    try:
        # Only refresh if the token is about to expire within 60 seconds.
        if jwt_decoded["exp"] - int(time.time()) > 60:
            return True

        token = await token_refresh_call()
        app.storage.user["token"] = token
    except (httpx.HTTPError, Exception):
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
        response = httpx.get(
            f"{settings.API_URL}/api/v1/me", headers=get_auth_header()
        )
        response.raise_for_status()
        data = response.json()

        return data["result"]

    except httpx.HTTPError:
        return None


def get_admin_status() -> bool:
    """
    Check if the user is an admin based on the token.
    """
    try:
        return get_user_data()["admin"]
    except (KeyError, TypeError):
        return False


def get_user_status() -> bool:
    """
    Check if the user is a normal user based on the token.
    """
    try:
        return get_user_data()["active"]
    except (KeyError, TypeError):
        return False


def get_token_is_valid() -> bool:
    """
    Check if the current token is valid and not expired.
    """
    token = app.storage.user.get("token")
    if not token:
        return False

    try:
        jwt_instance = jwt.JWT()
        decoded_token = jwt_instance.decode(token, do_verify=False)
        return decoded_token["exp"] > int(time.time())
    except Exception:
        return False


def get_bofh_status():
    """
    Check if the user has BOFH status based on the token.
    """
    try:
        return get_user_data()["bofh"]
    except (KeyError, TypeError):
        return False

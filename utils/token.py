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

# How many times in a row refreshing may fail to reach the provider before
# the session is given up on. At page_init's own 30 second timer that is
# five minutes of a provider being unreachable.
MAX_REFRESH_FAILURES = 10


class RefreshUnavailable(Exception):
    """
    The refresh endpoint could not be reached, or answered with a server
    error. Says nothing about whether the session is still valid.

    Kept apart from a refusal on purpose: treating the two the same logged
    a reader out on any network blip, and on the editor page that takes
    every unsaved caption with it.
    """


async def token_refresh_call() -> str:
    """
    A fresh access token from the refresh endpoint.

    None means the session was refused and is over. RefreshUnavailable means
    the question could not be asked -- the caller should try again rather
    than end the session on it.
    """

    try:
        refresh_token = app.storage.user.get("refresh_token")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.OIDC_APP_REFRESH_ROUTE,
                json={"token": refresh_token},
                timeout=10,
            )
    except httpx.HTTPError as error:
        raise RefreshUnavailable("the refresh endpoint could not be reached") from error

    # 4xx is an answer: this session is not getting another token. 5xx is the
    # provider having a bad minute, which is not the reader's session ending.
    if response.status_code >= 500:
        raise RefreshUnavailable(f"the refresh endpoint answered {response.status_code}")

    if response.status_code >= 400:
        return None

    try:
        return response.json().get("access_token")
    except ValueError as error:
        raise RefreshUnavailable("the refresh endpoint answered with no token") from error


async def token_refresh() -> bool:
    """
    Refresh the token using the refresh token.

    True means the session is good. False means it is over. Raises
    RefreshUnavailable when the provider could not be asked -- see
    token_refresh_or_wait, which is what pages actually call.
    """

    token_auth = app.storage.user.get("token")
    jwt_instance = jwt.JWT()

    try:
        jwt_decoded = jwt_instance.decode(token_auth, do_verify=False)
    except Exception:
        token = await token_refresh_call()

        if not token:
            return False

        jwt_decoded = jwt_instance.decode(token, do_verify=False)
        app.storage.user["token"] = token

    # Only refresh if the token is about to expire within 60 seconds.
    if jwt_decoded["exp"] - int(time.time()) > 60:
        return True

    token = await token_refresh_call()

    if not token:
        return False

    app.storage.user["token"] = token

    return True


async def token_refresh_or_wait(failures: int = 0) -> bool:
    """
    Whether to keep the session, given how many times refreshing has already
    failed to reach the provider in a row.

    A provider that cannot be reached is not a session that has ended, so it
    buys the reader another few minutes rather than logging them out --
    tolerating a blip, a suspended laptop or a provider restart. Only a
    refusal, or failing for MAX_REFRESH_FAILURES attempts running, ends the
    session. On the editor page ending it means losing every unsaved caption.
    """

    try:
        return await token_refresh()
    except RefreshUnavailable:
        return failures + 1 < MAX_REFRESH_FAILURES


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

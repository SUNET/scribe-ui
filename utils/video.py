# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin

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

from fastapi import Request
from fastapi.responses import Response
from nicegui import app
from utils.common import get_auth_header
from utils.helpers import storage_decrypt
from utils.settings import get_settings

settings = get_settings()


def create_vtt_proxy() -> Response:
    @app.get("/video/{job_id}/vtt")
    async def video_proxy(request: Request, job_id: str) -> Response:
        headers = dict(request.headers)
        headers_auth = get_auth_header()

        if not headers_auth:
            return Response(
                content="Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        headers["Authorization"] = headers_auth.get("Authorization", "")
        response = requests.get(
            f"{settings.API_URL}/api/v1/transcriber/{job_id}/vtt",
            headers=headers,
        )

        return Response(
            content=response.content,
            media_type=response.headers.get("content-type"),
            headers=response.headers,
            status_code=206,
        )


def create_video_proxy() -> Response:
    """
    Create a video proxy endpoint to handle video streaming requests
    with token authentication.

    This function sets up the FastAPI route for video streaming.
    """

    @app.get("/video/{job_id}")
    async def video_proxy(request: Request, job_id: str) -> Response:
        headers = dict(request.headers)
        headers_auth = get_auth_header()

        if not headers_auth:
            return Response(
                content="Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        encryption_password = storage_decrypt(
            app.storage.user.get("encryption_password"),
        )

        headers["Authorization"] = headers_auth.get("Authorization", "")

        try:
            response = requests.get(
                f"{settings.API_URL}/api/v1/transcriber/{job_id}/videostream",
                headers=headers,
                json={"encryption_password": encryption_password or ""},
            )
        except requests.exceptions.ChunkedEncodingError:
            return Response(
                content="Error streaming video",
                status_code=500,
            )

        return Response(
            content=response.content,
            media_type=response.headers.get("content-type"),
            headers=response.headers,
            status_code=206,
        )

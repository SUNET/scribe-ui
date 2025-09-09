import requests

from fastapi import Request
from fastapi.responses import Response
from nicegui import app
from utils.common import get_auth_header
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

        headers["Authorization"] = headers_auth.get("Authorization", "")
        response = requests.get(
            f"{settings.API_URL}/api/v1/transcriber/{job_id}/videostream",
            headers=headers,
        )

        return Response(
            content=response.content,
            media_type=response.headers.get("content-type"),
            headers=response.headers,
            status_code=206,
        )

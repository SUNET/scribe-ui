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


"""
The worker health page.
"""

import plotly.graph_objects as go
import httpx


from datetime import datetime
from nicegui import app, ui
from utils.common import page_init
from utils.styles import default_styles, chart_colors
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_auth_header,
)

settings = get_settings()


@ui.page("/health")
async def health() -> None:
    """
    Health check dashboard displaying backend system metrics.
    """

    page_init(use_drawer=True)

    if not get_admin_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    # Detect resolved dark mode (handles auto mode with OS preference)
    dark_pref = app.storage.user.get("dark_mode", None)
    if dark_pref is None:
        try:
            await ui.context.client.connected()
            prefers_dark = await ui.run_javascript(
                "window.matchMedia('(prefers-color-scheme: dark)').matches",
                timeout=5.0,
            )
            app.storage.user["_resolved_dark"] = bool(prefers_dark)
        except (TimeoutError, Exception):
            pass

    is_dark = app.storage.user.get("_resolved_dark", False)
    cc = chart_colors["dark" if is_dark else "light"]

    ui.label("System status").classes("text-3xl font-bold mb-4")

    @ui.refreshable
    async def render_health():
        # Awaited, so the ten second poll below leaves the event loop free
        # while the backend answers. A blocking call here would stall every
        # other page this server is serving, not just this one.
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(
                    settings.API_URL + "/api/v1/healthcheck",
                    headers=get_auth_header(),
                )
            res.raise_for_status()
            data = res.json()["result"]
            backend_reachable = True
        except Exception:
            data = {}
            backend_reachable = False

        if not backend_reachable:
            ui.label("Backend is not reachable").classes("text-lg").style("color: var(--color-text-danger);")
            return

        with ui.element("div").classes("health-grid"):
            if not data:
                ui.label("No workers online.").classes("text-lg text-theme-secondary")
                return

            for host, samples in data.items():
                if not samples:
                    continue

                seen = samples[-1]["seen"]
                latest = samples[-1]

                load_vals = [s["load_avg"] for s in samples]
                mem_vals = [s["memory_usage"] for s in samples]

                if "gpu_usage" in samples[-1] and samples[-1]["gpu_usage"]:
                    gpu_cpu_vals = [
                        s["gpu_usage"][0]["utilization"]
                        for s in samples
                        if "gpu_usage" in s
                    ]
                    gpu_mem_vals = [
                        (
                            s["gpu_usage"][0]["memory_used"]
                            / s["gpu_usage"][0]["memory_total"]
                        )
                        * 100
                        for s in samples
                        if "gpu_usage" in s
                    ]

                times = [
                    datetime.fromtimestamp(s["seen"]).strftime("%H:%M:%S")
                    for s in samples
                ]

                with ui.card().classes("health-card"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label(host).classes("text-lg font-medium")

                        status_color = (
                            "status-dot-offline"
                            if (datetime.now().timestamp() - seen) > 30
                            else "status-dot-online"
                        )
                        status = (
                            "Offline"
                            if (datetime.now().timestamp() - seen) > 30
                            else "Online"
                        )

                        ui.html(
                            f'<span class="status-dot {status_color}"></span>{status}',
                            sanitize=False,
                        )

                    ui.label(
                        f"Load Avg: {latest['load_avg']:.1f} | Memory Usage: {latest['memory_usage']:.1f}%"
                    ).classes("text-sm text-theme-secondary mb-2")

                    fig_cpu = go.Figure()
                    fig_cpu.add_trace(
                        go.Scatter(
                            x=times,
                            y=load_vals,
                            mode="lines",
                            name="Load Avg",
                            line=dict(color=cc["line_cpu"], width=2.5, shape="spline"),
                            fill="tozeroy",
                            fillcolor=cc["fill_cpu"],
                            hovertemplate="<b>Load</b>: %{y:.1f}<br><extra></extra>",
                        )
                    )
                    fig_cpu.add_trace(
                        go.Scatter(
                            x=times,
                            y=mem_vals,
                            mode="lines",
                            name="Memory %",
                            line=dict(color=cc["line_memory"], width=2.5, shape="spline"),
                            fill="tozeroy",
                            fillcolor=cc["fill_memory"],
                            hovertemplate="<b>Memory</b>: %{y:.1f}%<br><extra></extra>",
                        )
                    )
                    fig_cpu.update_layout(
                        margin=dict(l=40, r=20, t=30, b=40),
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="center",
                            x=0.5,
                            font=dict(size=11),
                        ),
                        height=200,
                        template="plotly_dark" if is_dark else "plotly_white",
                        xaxis=dict(
                            title="Time",
                            showgrid=True,
                        ),
                        yaxis=dict(
                            title="%",
                            showgrid=True,
                            rangemode="tozero",
                        ),
                        font=dict(size=11),
                        hovermode="x unified",
                    )
                    ui.plotly(fig_cpu).classes("w-full")

                    if "gpu_usage" in samples[-1] and samples[-1]["gpu_usage"]:
                        fig_gpu = go.Figure()
                        fig_gpu.add_trace(
                            go.Scatter(
                                x=times[-len(gpu_cpu_vals) :],
                                y=gpu_cpu_vals,
                                mode="lines",
                                name="GPU Util%",
                                line=dict(color=cc["line_gpu"], width=2.5, shape="spline"),
                                fill="tozeroy",
                                fillcolor=cc["fill_gpu"],
                                hovertemplate="<b>GPU Util</b>: %{y:.1f}%<br><extra></extra>",
                            )
                        )
                        fig_gpu.add_trace(
                            go.Scatter(
                                x=times[-len(gpu_mem_vals) :],
                                y=gpu_mem_vals,
                                mode="lines",
                                name="GPU Mem%",
                                line=dict(color=cc["line_gpu_mem"], width=2.5, shape="spline"),
                                fill="tozeroy",
                                fillcolor=cc["fill_gpu_mem"],
                                hovertemplate="<b>GPU Memory</b>: %{y:.1f}%<br><extra></extra>",
                            )
                        )

                        fig_gpu.update_layout(
                            margin=dict(l=40, r=20, t=30, b=40),
                            legend=dict(
                                orientation="h",
                                yanchor="bottom",
                                y=1.02,
                                xanchor="center",
                                x=0.5,
                                font=dict(size=11),
                            ),
                            height=200,
                            template="plotly_dark" if is_dark else "plotly_white",
                            xaxis=dict(
                                title="Time",
                                showgrid=True,
                            ),
                            yaxis=dict(
                                title="%",
                                showgrid=True,
                                rangemode="tozero",
                            ),
                            font=dict(size=11),
                            hovermode="x unified",
                        )
                        ui.plotly(fig_gpu).classes("w-full")

                    ui.label(f"Last updated: {times[-1]} UTC").classes(
                        "text-xs text-theme-muted mt-1"
                    )

    await render_health()

    # refresh() hands back an AwaitableResponse, which schedules the async
    # render as a background task on its own when it is not awaited.
    ui.timer(10.0, render_health.refresh)

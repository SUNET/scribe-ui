import requests

from datetime import datetime
from nicegui import ui
from plotly import graph_objects as go
from utils.common import default_styles, get_auth_header, page_init
from utils.settings import get_settings

settings = get_settings()


def create() -> None:
    @ui.page("/health")
    def health() -> None:
        """
        Health check dashboard displaying backend system metrics.
        """

        page_init()

        ui.add_head_html(default_styles)
        ui.add_head_html(
            """
            <style>
                body {
                    background-color: #f5f5f5;
                }
                .card {
                    background-color: white;
                    border-radius: 1rem;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    padding: 1.5rem;
                    width: 100%;
                    max-width: 100%;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                }
                .status-dot {
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    display: inline-block;
                    margin-right: 6px;
                }
            </style>
            """
        )

        ui.label("System Health Overview").classes("text-2xl font-semibold mb-4")

        @ui.refreshable
        def render_health():
            try:
                res = requests.get(
                    settings.API_URL + "/api/v1/healthcheck",
                    headers=get_auth_header(),
                    timeout=5,
                )
                res.raise_for_status()
                data = res.json()["result"]
                backend_reachable = True
            except Exception:
                data = {}
                backend_reachable = False

            if not backend_reachable:
                ui.label("Backend is not reachable").classes("text-lg text-red-500")
                return

            with ui.element("div").style(
                "display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; width: 100%;"
            ):
                if not data:
                    ui.label("No workers online.").classes("text-lg text-gray-600")
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

                    with ui.card().classes("card"):
                        with ui.row().classes("items-center justify-between w-full"):
                            ui.label(host).classes("text-lg font-medium")

                            status_color = (
                                "bg-red-500"
                                if (datetime.now().timestamp() - seen) > 30
                                else "bg-green-500"
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

                        ui.separator()
                        ui.label(
                            f"Load Avg: {latest['load_avg']:.1f} | Memory Usage: {latest['memory_usage']:.1f}%"
                        ).classes("text-sm text-gray-600 mb-2")

                        fig_cpu = go.Figure()
                        fig_cpu.add_trace(
                            go.Scatter(
                                x=times,
                                y=load_vals,
                                mode="lines+markers",
                                name="Load Avg",
                                line=dict(shape="spline"),
                            )
                        )
                        fig_cpu.add_trace(
                            go.Scatter(
                                x=times,
                                y=mem_vals,
                                mode="lines+markers",
                                name="Memory %",
                                line=dict(shape="spline"),
                            )
                        )
                        fig_cpu.update_layout(
                            margin=dict(l=20, r=20, t=20, b=20),
                            legend=dict(
                                orientation="h",
                                yanchor="bottom",
                                y=1.1,
                                xanchor="center",
                                x=0.5,
                            ),
                            height=250,
                            template="plotly_white",
                            xaxis_title="Time",
                            yaxis_title="%",
                        )
                        ui.plotly(fig_cpu).classes("w-full h-64")

                        if "gpu_usage" in samples[-1] and samples[-1]["gpu_usage"]:
                            fig_gpu = go.Figure()
                            fig_gpu.add_trace(
                                go.Scatter(
                                    x=times[-len(gpu_cpu_vals) :],
                                    y=gpu_cpu_vals,
                                    mode="lines+markers",
                                    name="GPU CPU%",
                                    line=dict(shape="spline"),
                                )
                            )
                            fig_gpu.add_trace(
                                go.Scatter(
                                    x=times[-len(gpu_mem_vals) :],
                                    y=gpu_mem_vals,
                                    mode="lines+markers",
                                    name="GPU RAM%",
                                    line=dict(shape="spline"),
                                )
                            )

                            fig_gpu.update_layout(
                                margin=dict(l=20, r=20, t=20, b=20),
                                legend=dict(
                                    orientation="h",
                                    yanchor="bottom",
                                    y=1.1,
                                    xanchor="center",
                                    x=0.5,
                                ),
                                height=250,
                                template="plotly_white",
                                xaxis_title="Time",
                                yaxis_title="%",
                            )
                            ui.plotly(fig_gpu).classes("w-full h-64")

                        ui.label(f"Last updated: {times[-1]} UTC").classes(
                            "text-xs text-gray-400 mt-1"
                        )

        render_health()

        ui.timer(10.0, render_health.refresh)

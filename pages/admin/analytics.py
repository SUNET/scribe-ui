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
Usage analytics.
"""

import plotly.graph_objects as go


from collections import defaultdict
from datetime import datetime
from nicegui import app, ui
from utils.common import page_init, reload_on_theme_change
from utils.styles import default_styles, chart_colors
from db.analytics import fetch_all as fetch_analytics
from utils.settings import get_settings
from utils.token import (
    get_bofh_status,
)

settings = get_settings()


@ui.page("/admin/analytics")
async def analytics() -> None:
    """
    Page view analytics dashboard. BOFH only.
    """

    page_init(use_drawer=True, title="Analytics")
    # Plotly draws its charts in one theme's colours server-side and
    # cannot restyle itself, so this page reloads when the OS theme
    # changes. Only pages with charts do -- see reload_on_theme_change.
    reload_on_theme_change()

    if not get_bofh_status():
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
            is_dark = bool(prefers_dark)
            app.storage.user["_resolved_dark"] = is_dark
        except (TimeoutError, Exception):
            is_dark = app.storage.user.get("_resolved_dark", False)
    else:
        is_dark = bool(dark_pref)

    cc = chart_colors["dark" if is_dark else "light"]

    ui.label("Activity overview").classes("text-3xl font-bold mb-4")

    plotly_template = "plotly_dark" if is_dark else "plotly_white"

    # Calculate UTC offset for the user's timezone
    import pytz

    user_tz_name = app.storage.user.get("timezone", "UTC")
    try:
        user_tz = pytz.timezone(user_tz_name)
        utc_offset_hours = int(
            datetime.now(user_tz).utcoffset().total_seconds() // 3600
        )
    except Exception:
        utc_offset_hours = 0

    def shift_hour(h: int) -> int:
        return (h + utc_offset_hours) % 24

    def shift_dow(dow: int, h: int) -> int:
        """Shift day-of-week if hour wraps past midnight."""
        shifted = h + utc_offset_hours
        if shifted >= 24:
            return (dow % 7) + 1  # next day (PostgreSQL dow: 0=Sun..6=Sat)
        elif shifted < 0:
            return (dow - 2) % 7  # previous day
        return dow

    data = await fetch_analytics(days=30, recent_limit=50)
    stats = data["stats"]
    wow = data["wow"]
    summary = data["summary"]
    heatmap_data = data["heatmap"]
    hourly = data["hourly"]
    page_views = data["page_views"]
    daily = data["daily"]
    recent = data["recent"]

    if wow["change_pct"] is not None:
        sign = "+" if wow["change_pct"] >= 0 else ""
        wow_color = cc["wow_positive"] if wow["change_pct"] >= 0 else cc["wow_negative"]
        wow_display = f'{sign}{wow["change_pct"]}%'
    else:
        wow_color = cc["wow_neutral"]
        wow_display = "N/A"

    action_summary = [r for r in summary if r["path"].startswith("/action/")]
    action_labels = {
        "/action/upload": ("Uploads", "upload_file", "#2e7d32"),
        "/action/transcription": ("Transcriptions", "record_voice_over", "#1565c0"),
        "/action/bulk_transcription": (
            "Bulk Transcriptions",
            "dynamic_feed",
            "#6a1b9a",
        ),
        "/action/export": ("Exports", "download", "#e65100"),
        "/action/bulk_export": ("Bulk Exports", "folder_zip", "#00695c"),
        "/action/create_group": ("Groups Created", "group_add", "#00838f"),
        "/action/edit_group": ("Groups Edited", "edit", "#4527a0"),
        "/action/delete_group": ("Groups Deleted", "group_remove", "#b71c1c"),
        "/action/remove_user": ("Users Removed", "person_remove", "#c62828"),
        "/action/activate_user": ("Users Activated", "person_add", "#2e7d32"),
        "/action/deactivate_user": ("Users Deactivated", "person_off", "#e65100"),
        "/action/set_admin": ("Admin Granted", "admin_panel_settings", "#1565c0"),
        "/action/remove_admin": ("Admin Revoked", "remove_moderator", "#bf360c"),
        "/action/set_domains": ("Domains Updated", "domain", "#6a1b9a"),
    }
    action_map = {r["path"]: r for r in action_summary}

    # Peak hours heatmap + hourly distribution
    with ui.row().classes("w-full gap-4 q-mt-lg"):
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label(f"Peak hours (last 30 days, {user_tz_name})").classes(
                "text-h6 font-semibold q-mb-md"
            )

            if heatmap_data:
                day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                hours = list(range(24))
                # Build a 7x24 matrix (rows=days, cols=hours)
                matrix = [[0] * 24 for _ in range(7)]
                for r in heatmap_data:
                    adj_dow = shift_dow(r["dow"], r["hour"])
                    # PostgreSQL dow: 0=Sun, 1=Mon..6=Sat -> remap to Mon=0..Sun=6
                    day_idx = (adj_dow - 1) % 7
                    matrix[day_idx][shift_hour(r["hour"])] += r["views"]

                fig = go.Figure(
                    data=go.Heatmap(
                        z=matrix,
                        x=[f"{h:02d}:00" for h in hours],
                        y=day_names,
                        colorscale=[
                            [0, cc["heatmap_zero"]],
                            [0.25, cc["heatmap_low"]],
                            [0.5, "#42a5f5"],
                            [0.75, "#1565c0"],
                            [1, "#0d47a1"],
                        ],
                        hovertemplate="Day: %{y}<br>Hour: %{x}<br>Views: %{z}<extra></extra>",
                        showscale=True,
                        colorbar=dict(title="Views", thickness=15),
                        xgap=2,
                        ygap=2,
                        texttemplate="%{z}",
                        textfont=dict(size=10),
                    )
                )
                fig.update_layout(
                    template=plotly_template,
                    height=350,
                    margin=dict(l=50, r=20, t=20, b=40),
                    xaxis_title="Hour of Day",
                    xaxis=dict(dtick=1),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label(f"Hourly distribution (last 30 days, {user_tz_name})").classes(
                "text-h6 font-semibold q-mb-md"
            )

            if hourly:
                # Shift UTC hours to user timezone and fill missing with 0
                hourly_map = {}
                for r in hourly:
                    shifted = shift_hour(r["hour"])
                    hourly_map[shifted] = hourly_map.get(shifted, 0) + r["views"]
                all_hours = list(range(24))
                all_views = [hourly_map.get(h, 0) for h in all_hours]

                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=[f"{h:02d}:00" for h in all_hours],
                        y=all_views,
                        marker_color=cc["hourly_bar"],
                    )
                )
                fig.update_layout(
                    xaxis_title="Hour of Day",
                    yaxis_title="Views",
                    template=plotly_template,
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

    # Charts
    with ui.row().classes("w-full gap-4 q-mt-lg"):
        # Line chart: page views per day per path
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Page views per day (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )

            if page_views:
                by_path = defaultdict(lambda: {"dates": [], "views": []})
                for row in page_views:
                    by_path[row["path"]]["dates"].append(row["date"])
                    by_path[row["path"]]["views"].append(row["views"])

                fig = go.Figure()
                for path, data in sorted(by_path.items()):
                    fig.add_trace(
                        go.Scatter(
                            x=data["dates"],
                            y=data["views"],
                            mode="lines+markers",
                            name=path,
                        )
                    )
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Views",
                    template=plotly_template,
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

        # Bar chart: total views per page
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Total views per page").classes("text-h6 font-semibold q-mb-md")
            if summary:
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=[r["path"] for r in summary],
                        y=[r["total_views"] for r in summary],
                        name="All Time",
                        marker_color=cc["bar_primary"],
                    )
                )
                fig.add_trace(
                    go.Bar(
                        x=[r["path"] for r in summary],
                        y=[r["views_30d"] for r in summary],
                        name="Last 30 Days",
                        marker_color=cc["bar_secondary"],
                    )
                )
                fig.update_layout(
                    barmode="group",
                    xaxis_title="Page",
                    yaxis_title="Views",
                    template=plotly_template,
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

    # Daily traffic chart + recent views table
    with ui.row().classes("w-full gap-4 q-mt-lg items-stretch"):
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Total traffic per day (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )

            if daily:
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=[r["date"] for r in daily],
                        y=[r["views"] for r in daily],
                        marker_color=cc["bar_primary"],
                    )
                )
                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Page Views",
                    template=plotly_template,
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No data yet.").classes("text-grey-6")

        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Last visited pages").classes("text-h6 font-semibold q-mb-md")

            if recent:
                columns = [
                    {"name": "path", "label": "Page", "field": "path", "align": "left"},
                    {
                        "name": "timestamp",
                        "label": "Time",
                        "field": "timestamp",
                        "align": "left",
                    },
                ]
                ui.table(
                    columns=columns,
                    rows=recent,
                    row_key="timestamp",
                ).classes(
                    "w-full table-style"
                ).props("dense").style("max-height: 350px;")
            else:
                ui.label("No data yet.").classes("text-grey-6")

    # Action charts
    with ui.row().classes("w-full gap-4 q-mt-lg"):
        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Actions per day (last 30 days)").classes(
                "text-h6 font-semibold q-mb-md"
            )
            action_views = [
                r for r in page_views if r["path"].startswith("/action/")
            ]

            if action_views:
                by_action = defaultdict(lambda: {"dates": [], "views": []})
                for row in action_views:
                    action_name = row["path"].replace("/action/", "")
                    by_action[action_name]["dates"].append(row["date"])
                    by_action[action_name]["views"].append(row["views"])

                fig = go.Figure()
                for action_name, data in sorted(by_action.items()):
                    fig.add_trace(
                        go.Bar(
                            x=data["dates"],
                            y=data["views"],
                            name=action_name,
                        )
                    )
                fig.update_layout(
                    barmode="stack",
                    xaxis_title="Date",
                    yaxis_title="Count",
                    template=plotly_template,
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No action data yet.").classes("text-grey-6")

        with ui.card().classes("flex-1 p-4").style("min-width: 400px;"):
            ui.label("Total actions by type").classes("text-h6 font-semibold q-mb-md")

            if action_summary:
                action_names = [
                    r["path"].replace("/action/", "") for r in action_summary
                ]
                fig = go.Figure()
                fig.add_trace(
                    go.Bar(
                        x=action_names,
                        y=[r["total_views"] for r in action_summary],
                        name="All Time",
                        marker_color=cc["bar_primary"],
                    )
                )
                fig.add_trace(
                    go.Bar(
                        x=action_names,
                        y=[r["views_30d"] for r in action_summary],
                        name="Last 30 Days",
                        marker_color=cc["bar_secondary"],
                    )
                )
                fig.update_layout(
                    barmode="group",
                    xaxis_title="Action",
                    yaxis_title="Count",
                    template=plotly_template,
                    height=350,
                    margin=dict(l=40, r=20, t=20, b=40),
                )
                ui.plotly(fig).classes("w-full")
            else:
                ui.label("No action data yet.").classes("text-grey-6")

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
Service announcements shown to all users.
"""


import re

from nicegui import app, ui
from utils.common import page_init
from utils.styles import default_styles, severity_styles
from utils.helpers import (
    announcements_get,
    announcement_create,
    announcement_update,
    announcement_delete,
)
from utils.settings import get_settings
from utils.token import (
    get_bofh_status,
)

settings = get_settings()




SEVERITY_OPTIONS = {
    "info": "Info",
    "maintenance": "Maintenance",
    "major_incident": "Major incident",
}


def _announcement_preview_dialog(message: str, severity: str = "info") -> None:
    """Show a preview of how the announcement banner will look."""

    style = severity_styles.get(severity, severity_styles["info"])

    with ui.dialog().props('aria-label="Banner preview"') as preview_dialog:
        with ui.card().style("width: 700px; max-width: 90vw; padding: 24px;"):
            ui.label("Banner preview").classes("text-h6 font-bold mb-4")
            with ui.element("div").classes(
                f"announcement-banner {style['css_class']}"
            ).style(
                "border-radius: 4px; padding: 10px 20px; display: flex;"
                " align-items: center; gap: 10px; width: 100%;"
            ):
                ui.icon(style["icon"], size="sm").style(
                    f"color: {style['icon_color']};"
                )
                ui.html(message, sanitize=False).style(
                    "color: var(--color-text-primary); font-size: 0.95rem;"
                )
                if style["dismissible"]:
                    ui.button(icon="close").props(
                        "flat round dense size=sm color=grey-7 disable"
                        ' aria-hidden="true"'
                    )
            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("Close", on_click=preview_dialog.close).classes(
                    "button-close"
                ).props("color=black flat")
        preview_dialog.open()


def _announcement_create_dialog() -> None:
    """Show dialog to create a new announcement."""

    ui.dark_mode(app.storage.user.get("dark_mode", None))

    with ui.dialog().props('aria-label="Create announcement"') as dialog:
        with ui.card().style("width: 600px; max-width: 90vw; padding: 24px;"):
            ui.label("Create announcement").classes("text-h6 font-bold mb-2")

            ui.label(
                "The message supports HTML links, e.g. "
                '<a href="https://example.com">click here</a>'
            ).classes("text-body2 text-theme-muted mb-2")

            message_input = ui.textarea("Message").classes("w-full").props("outlined")

            severity_select = (
                ui.select(
                    options=SEVERITY_OPTIONS,
                    label="Severity",
                    value="info",
                )
                .classes("w-full")
                .props("outlined")
            )

            with ui.row().classes("w-full gap-4"):
                starts_input = (
                    ui.input("Start date/time (optional)")
                    .classes("flex-1")
                    .props("outlined clearable")
                )
                with starts_input:
                    with ui.menu().props("no-parent-event") as starts_menu:
                        with ui.date().bind_value(starts_input).on(
                            "update:model-value", lambda: None
                        ) as starts_date:
                            pass
                    with starts_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", starts_menu.open).classes(
                            "cursor-pointer"
                        )

                ends_input = (
                    ui.input("End date/time (optional)")
                    .classes("flex-1")
                    .props("outlined clearable")
                )
                with ends_input:
                    with ui.menu().props("no-parent-event") as ends_menu:
                        with ui.date().bind_value(ends_input).on(
                            "update:model-value", lambda: None
                        ) as ends_date:
                            pass
                    with ends_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", ends_menu.open).classes(
                            "cursor-pointer"
                        )

            ui.label(
                "Leave dates empty for no time restriction. All times are in server time."
            ).classes("text-body2 text-theme-muted")

            enabled_switch = ui.switch("Enabled", value=True)

            with ui.row().classes("w-full justify-between mt-4"):
                ui.button(
                    "Preview",
                    icon="visibility",
                    on_click=lambda: _announcement_preview_dialog(
                        message_input.value, severity_select.value
                    ),
                ).props("color=black flat")

                with ui.row().classes("gap-2"):
                    ui.button("Cancel", on_click=dialog.close).classes(
                        "button-close"
                    ).props("color=black flat")
                    ui.button(
                        "Create",
                        on_click=lambda: (
                            message_input.value.strip()
                            and announcement_create(
                                {
                                    "message": message_input.value.strip(),
                                    "severity": severity_select.value,
                                    "starts_at": starts_input.value or "",
                                    "ends_at": ends_input.value or "",
                                    "enabled": enabled_switch.value,
                                }
                            )
                            and (
                                dialog.close(),
                                ui.navigate.to("/admin/announcements"),
                            )
                        ),
                    ).classes("default-style").props("color=black flat")

        dialog.open()


def _announcement_edit_dialog(ann: dict) -> None:
    """Show dialog to edit an existing announcement."""

    ui.dark_mode(app.storage.user.get("dark_mode", None))

    with ui.dialog().props('aria-label="Edit announcement"') as dialog:
        with ui.card().style("width: 600px; max-width: 90vw; padding: 24px;"):
            ui.label("Edit announcement").classes("text-h6 font-bold mb-2")

            ui.label(
                "The message supports HTML links, e.g. "
                '<a href="https://example.com">click here</a>'
            ).classes("text-body2 text-theme-muted mb-2")

            message_input = (
                ui.textarea("Message", value=ann.get("message", ""))
                .classes("w-full")
                .props("outlined")
            )

            severity_select = (
                ui.select(
                    options=SEVERITY_OPTIONS,
                    label="Severity",
                    value=ann.get("severity", "info"),
                )
                .classes("w-full")
                .props("outlined")
            )

            starts_val = (
                (ann.get("starts_at") or "").split(" ")[0]
                if ann.get("starts_at")
                else ""
            )
            ends_val = (
                (ann.get("ends_at") or "").split(" ")[0] if ann.get("ends_at") else ""
            )

            with ui.row().classes("w-full gap-4"):
                starts_input = (
                    ui.input("Start date/time (optional)", value=starts_val)
                    .classes("flex-1")
                    .props("outlined clearable")
                )
                with starts_input:
                    with ui.menu().props("no-parent-event") as starts_menu:
                        with ui.date().bind_value(starts_input):
                            pass
                    with starts_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", starts_menu.open).classes(
                            "cursor-pointer"
                        )

                ends_input = (
                    ui.input("End date/time (optional)", value=ends_val)
                    .classes("flex-1")
                    .props("outlined clearable")
                )
                with ends_input:
                    with ui.menu().props("no-parent-event") as ends_menu:
                        with ui.date().bind_value(ends_input):
                            pass
                    with ends_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", ends_menu.open).classes(
                            "cursor-pointer"
                        )

            ui.label(
                "Leave dates empty for no time restriction. All times are in server time."
            ).classes("text-body2 text-theme-muted")

            enabled_switch = ui.switch("Enabled", value=ann.get("enabled", True))

            with ui.row().classes("w-full justify-between mt-4"):
                ui.button(
                    "Preview",
                    icon="visibility",
                    on_click=lambda: _announcement_preview_dialog(
                        message_input.value, severity_select.value
                    ),
                ).props("color=black flat")

                with ui.row().classes("gap-2"):
                    ui.button("Cancel", on_click=dialog.close).classes(
                        "button-close"
                    ).props("color=black flat")
                    ui.button(
                        "Save",
                        on_click=lambda: (
                            message_input.value.strip()
                            and announcement_update(
                                ann["id"],
                                {
                                    "message": message_input.value.strip(),
                                    "severity": severity_select.value,
                                    "starts_at": starts_input.value or "",
                                    "ends_at": ends_input.value or "",
                                    "enabled": enabled_switch.value,
                                },
                            )
                            and (
                                dialog.close(),
                                ui.navigate.to("/admin/announcements"),
                            )
                        ),
                    ).classes("default-style").props("color=black flat")

        dialog.open()


def _announcement_delete_confirm(ann: dict) -> None:
    """Show confirmation dialog before deleting an announcement."""

    ui.dark_mode(app.storage.user.get("dark_mode", None))

    with ui.dialog().props('aria-label="Delete announcement"') as dialog:
        with ui.card().style("width: 400px; max-width: 90vw; padding: 24px;"):
            ui.label("Delete announcement").classes("text-h6 font-bold mb-2")
            ui.label("Are you sure you want to delete this announcement?").classes(
                "text-body1 mb-4"
            )
            ui.html(f'<em>"{ann.get("message", "")[:100]}..."</em>').classes("mb-4")

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).classes(
                    "button-close"
                ).props("color=black flat")
                ui.button(
                    "Delete",
                    on_click=lambda: (
                        announcement_delete(ann["id"]),
                        dialog.close(),
                        ui.navigate.to("/admin/announcements"),
                    ),
                ).classes("delete-style").props("color=red flat")

        dialog.open()


@ui.page("/admin/announcements")
def announcements_page() -> None:
    """Announcement banner management page. BOFH only."""

    page_init(use_drawer=True, title="Announcements")

    if not get_bofh_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    with ui.row().style(
        "justify-content: space-between; align-items: center; width: 100%;"
    ):
        ui.label("Announcements").classes("text-3xl font-bold")
        ui.button("New announcement", icon="add").classes("default-style").props(
            "color=black flat"
        ).on("click", lambda: _announcement_create_dialog())

    ui.label(
        "Manage announcement banners shown to all users. "
        "All times are in server time."
    ).classes("text-body2 mb-4")

    ann_list = announcements_get()

    if not ann_list:
        ui.label("No announcements yet.").classes("text-lg mt-4 text-grey-6")
    else:
        for ann in ann_list:
            ann["starts_label"] = ann.get("starts_at") or "—"
            ann["ends_label"] = ann.get("ends_at") or "—"
            ann["severity_label"] = SEVERITY_OPTIONS.get(
                ann.get("severity", "info"), "Info"
            )
            msg = re.sub(r"<[^>]+>", "", ann.get("message", ""))
            ann["message_short"] = (msg[:80] + "…") if len(msg) > 80 else msg

        def _toggle_enabled(ann_row: dict) -> None:
            new_val = not ann_row.get("enabled", True)
            announcement_update(ann_row["id"], {"enabled": new_val})
            ui.navigate.to("/admin/announcements")

        ann_table = (
            ui.table(
                columns=[
                    {
                        "name": "message_short",
                        "label": "Message",
                        "field": "message_short",
                        "align": "left",
                        "classes": "text-weight-medium",
                        "style": "max-width: 350px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;",
                    },
                    {
                        "name": "severity_label",
                        "label": "Severity",
                        "field": "severity_label",
                        "align": "left",
                    },
                    {
                        "name": "starts_label",
                        "label": "Starts",
                        "field": "starts_label",
                        "align": "left",
                    },
                    {
                        "name": "ends_label",
                        "label": "Ends",
                        "field": "ends_label",
                        "align": "left",
                    },
                    {
                        "name": "enabled",
                        "label": "Enabled",
                        "field": "enabled",
                        "align": "center",
                    },
                    {
                        "name": "created_by",
                        "label": "Created by",
                        "field": "created_by",
                        "align": "left",
                    },
                    {
                        "name": "actions",
                        "label": "Actions",
                        "field": "actions",
                        "align": "center",
                    },
                ],
                rows=ann_list,
                row_key="id",
            )
            .classes("w-full")
            .props("flat bordered")
        )

        ann_table.add_slot(
            "body-cell-message_short",
            r"""
            <q-td :props="props">
                <a
                    class="cursor-pointer text-primary"
                    @click="$parent.$emit('edit', props.row)"
                    style="text-decoration: underline;"
                >
                    {{ props.row.message_short }}
                </a>
            </q-td>
            """,
        )

        ann_table.add_slot(
            "body-cell-enabled",
            """
            <q-td :props="props">
                <q-toggle
                    :model-value="props.row.enabled"
                    @update:model-value="$parent.$emit('toggle_enabled', props.row)"
                    color="positive"
                    :dark="$q.dark.isActive"
                />
            </q-td>
            """,
        )

        ann_table.add_slot(
            "body-cell-actions",
            """
            <q-td :props="props">
                <q-btn flat round dense icon="visibility" size="sm" color="grey-7"
                    aria-label="Preview announcement"
                    @click="$parent.$emit('preview', props.row)" />
                <q-btn flat round dense icon="delete" size="sm" color="red"
                    aria-label="Delete announcement"
                    @click="$parent.$emit('delete', props.row)" />
            </q-td>
            """,
        )

        ann_table.on("toggle_enabled", lambda e: _toggle_enabled(e.args))
        ann_table.on(
            "preview",
            lambda e: _announcement_preview_dialog(
                e.args["message"], e.args.get("severity", "info")
            ),
        )
        ann_table.on("edit", lambda e: _announcement_edit_dialog(e.args))
        ann_table.on("delete", lambda e: _announcement_delete_confirm(e.args))

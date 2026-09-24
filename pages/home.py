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

from nicegui import ui, events
from utils.common import (
    page_init,
    jobs_get,
    table_click,
    table_upload,
    table_delete,
    table_transcribe,
    table_view,
    table_bulk_export,
    table_bulk_transcribe,
)
from utils.recorder import RecorderReminder, current_owner, engine_script
from utils.styles import default_styles, jobs_columns


def create() -> None:
    @ui.refreshable
    @ui.page("/home")
    def home() -> None:
        """
        Main page of the application.
        """
        page_init(use_drawer=True, title="My files")

        # Recordings left on this device -- a recorder closed before its
        # upload finished, a phone that went offline -- are resumed from
        # here too, so they reach this list without the recorder being
        # opened again.
        engine_script()
        reminder = RecorderReminder(owner=current_owner())

        def toggle_buttons(selected: list) -> None:
            """
            Toggle the state of buttons based on selected rows.
            """
            has_selection = bool(selected)
            delete.set_enabled(has_selection)

            # Update delete tooltip
            if has_selection:
                delete_tooltip.text = "Delete selected files"
            else:
                delete_tooltip.text = "Select one or more files to delete"

            # Enable bulk export only when all selected completed jobs share the same type
            completed = [r for r in selected if r.get("status") == "Completed"]
            formats = set(r.get("output_format", "") for r in completed)
            bulk_export.set_enabled(len(completed) >= 1 and len(formats) == 1)

            # Update export tooltip
            if not has_selection:
                export_tooltip.text = "Select one or more files to export"
            elif len(completed) >= 1 and len(formats) > 1:
                export_tooltip.text = (
                    "Subtitles and Transcript can't be exported together."
                )
            elif len(completed) >= 1 and len(formats) == 1:
                export_tooltip.text = "Export selected files"
            else:
                export_tooltip.text = (
                    "Select one or more already completed files to export"
                )

            # Enable bulk transcribe when 1+ uploaded jobs are selected
            uploaded = [r for r in selected if r.get("status") == "Uploaded"]
            already_transcribed = [
                r for r in selected if r.get("status") == "Completed"
            ]
            bulk_transcribe.set_enabled(len(uploaded) >= 1)

            # Update transcribe tooltip
            if not has_selection:
                transcribe_tooltip.text = "Select one or more files to transcribe"
            elif len(uploaded) >= 1 and len(already_transcribed) > 0:
                transcribe_tooltip.text = "One or more files are already transcribed"
            elif len(uploaded) >= 1:
                transcribe_tooltip.text = "Transcribe selected files"
            elif len(already_transcribed) > 0:
                transcribe_tooltip.text = "One or more files are already transcribed"
            else:
                transcribe_tooltip.text = "Select one or more files to transcribe"

        table = ui.table(
            on_select=lambda e: toggle_buttons(e.selection),
            columns=jobs_columns,
            rows=[],
            selection="multiple",
            pagination=10,
        )
        table.props(":selected-rows-label=\"(n) => n + ' files selected'\"")

        # On a phone the seven columns are unreadable and the row's own
        # action -- Transcribe, or View -- is the only part of it anyone
        # came for. Quasar's own grid mode draws each row as a card
        # instead; `item` below is what fills them in. Decided here rather
        # than by a media query because it changes what is rendered, not
        # how it looks -- and the width it is decided on is the phone
        # breakpoint the stylesheet uses, so the cards and the rules that
        # style them appear together.
        #
        # `window.innerWidth`, not `$q.screen`: NiceGUI evaluates a `:`
        # prop with `eval()` in the page's own scope, where Quasar's `$q`
        # -- a component property -- does not exist, and a prop that
        # throws is dropped without a word. Read once, when the table is
        # rendered, which is what a phone needs; a desktop window dragged
        # across 700px keeps its columns until the page is opened again.
        table.props(':grid="window.innerWidth < 700"')
        table.add_slot(
            "item",
            """
            <div class="q-pa-xs col-12">
                <q-card flat bordered class="jobs-card">
                    <div class="row items-start no-wrap">
                        <q-checkbox
                            :aria-label="'Select ' + props.row.filename"
                            v-model="props.selected"
                            class="q-mr-sm"
                        />
                        <div class="col">
                            <div class="jobs-card-name">{{ props.row.filename }}</div>
                            <div class="jobs-card-meta">
                                {{ props.row.job_type }} · {{ props.row.status }}
                            </div>
                            <div class="jobs-card-meta">
                                Created {{ props.row.created_at }}
                            </div>
                            <div
                                class="jobs-card-meta"
                                :class="props.row.deletion_approaching ? 'deletion-warning' : ''"
                            >
                                Deletion date {{ props.row.deletion_date }}
                            </div>
                        </div>
                    </div>
                    <div class="jobs-card-action">
                        <q-btn
                            v-if="props.row.status === 'Uploaded' || props.row.status === 'Completed'"
                            :label="props.row.status === 'Completed' ? 'View' : 'Transcribe'"
                            :aria-label="(props.row.status === 'Completed' ? 'View ' : 'Transcribe ') + props.row.filename"
                            :class="props.row.status === 'Completed' ? 'table-btn-edit' : 'table-btn-transcribe'"
                            @click="$parent.$emit(props.row.status === 'Completed' ? 'table_handle_row_view' : 'table_handle_row_click', props.row)"
                        />
                    </div>
                </q-card>
            </div>
            """,
        )

        # Custom header checkbox that selects/deselects ALL rows across all pages
        table.add_slot(
            "header-selection",
            """
            <q-checkbox
                aria-label="Select all files"
                :model-value="props.selected"
                @update:model-value="val => { if (!val) { $parent.$emit('deselect_all'); } else { props.selected = true; } }"
            />
            """,
        )

        # Row checkboxes are otherwise generated by Quasar from
        # selection="multiple" with no accessible name at all -- announced
        # only as "checkbox". Naming each one after its own row's filename
        # is what a screen reader user needs before a bulk delete/export.
        table.add_slot(
            "body-selection",
            """
            <q-checkbox
                :aria-label="'Select ' + props.row.filename"
                v-model="props.selected"
            />
            """,
        )

        def deselect_all():
            table.selected = []
            toggle_buttons([])

        table.on("deselect_all", deselect_all)

        def table_handle_row_click(e: events.GenericEventArguments) -> None:
            if not e.args.get("uuid"):
                # The row is the table's own placeholder for a file still
                # being registered by the backend -- it is marked "Uploaded"
                # (so it draws this very button) a moment before the real
                # row replaces it, and it has no job to act on.
                ui.notify(
                    "That upload is still being registered. "
                    "Try again in a moment.",
                    type="warning",
                    position="top",
                )
            elif e.args.get("status") == "Completed":
                table_click(e)
            else:
                table_transcribe(
                    e.args, on_complete=lambda: ui.timer(0.1, update_rows, once=True)
                )

        ui.add_head_html(default_styles)

        table.style(
            "width: 100%; height: calc(100vh - 100px - var(--banner-offset, 0px)); box-shadow: none; font-size: 18px;"
        )
        table.classes("table-style")
        # Was one slot (body-cell-status) emitting two <q-td> -- one for
        # its own "status" column, one more for "action" tacked onto the
        # end. Quasar calls a body-cell-<name> slot once per row for that
        # column alone, so status's slot returning two cells left every row
        # with 9 td against the table's 8 th (7 defined columns plus the
        # selection column) -- the extra didn't just look wrong, it shifted
        # every cell after it out of alignment with its header (WCAG
        # 1.3.1). "action" is also a defined column of its own with no
        # slot before this change, so Quasar rendered a second, empty
        # default cell for it on top of the one status's slot already
        # produced. Splitting the markup into its own body-cell-action slot
        # gives Quasar exactly one slot call per column again. Verified by
        # counting th against td in the rendered DOM -- the only check that
        # actually settles this, since both cell counts read the same
        # either way in the editor.
        table.add_slot(
            "body-cell-status",
            """
            <q-td key="status" :props="props">
                <p>{{ props.value }}</p>
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-action",
            """
            <q-td key="action" :props="props">
                <q-btn
                    v-if="props.row.status === 'Uploaded' || props.row.status === 'Completed'"
                    :label="props.row.status === 'Completed' ? 'Edit' : 'Transcribe'"
                    :aria-label="(props.row.status === 'Completed' ? 'Edit ' : 'Transcribe ') + props.row.filename"
                    :class="props.row.status === 'Completed' ? 'table-btn-edit' : 'table-btn-transcribe'"
                    style="width: 120px; height: 40px;"
                    @click="$parent.$emit('table_handle_row_click', props.row)"
                />
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-deletion_date",
            """
            <q-td key="deletion_date" :props="props">
                <div :class="props.row.deletion_approaching ? 'deletion-warning' : ''">
                    <span>{{ props.row.deletion_date }}</span>
                    <q-icon
                        v-if="props.row.deletion_approaching"
                        name="warning"
                        class="deletion-warning-icon"
                        role="img"
                        aria-label="This file will be permanently deleted within 24 hours."
                    >
                        <q-tooltip>This file will be permanently deleted within 24 hours.</q-tooltip>
                    </q-icon>
                </div>
            </q-td>
            """,
        )
        table.on("table_handle_row_click", table_handle_row_click)

        def table_handle_row_view(e: events.GenericEventArguments) -> None:
            # What the card offers on a phone. Same row, same job, read
            # only: the editor puts a recording, a caption list and a
            # timeline side by side and wants a desk, while reading a
            # transcription back -- which is what anyone opens one for on
            # a phone -- needs none of that.
            if not e.args.get("uuid"):
                ui.notify(
                    "That upload is still being registered. "
                    "Try again in a moment.",
                    type="warning",
                    position="top",
                )
            else:
                table_view(e)

        table.on("table_handle_row_view", table_handle_row_view)

        with table.add_slot("top-left"):
            ui.label("My files").classes("text-3xl font-bold page-title")

        with table.add_slot("top-right"):
            with ui.row().classes("items-center jobs-actions"):
                with ui.button("Delete", icon="delete") as delete:
                    delete.props("color=black flat")
                    delete.classes("delete-style")
                    delete.on("click", lambda: table_delete(table))
                    delete.set_enabled(False)
                    delete_tooltip = ui.tooltip("Select one or more files to delete")

                with ui.button("Export", icon="download") as bulk_export:
                    bulk_export.props("color=black flat")
                    bulk_export.classes("default-style")
                    bulk_export.on("click", lambda: table_bulk_export(table))
                    bulk_export.set_enabled(False)
                    export_tooltip = ui.tooltip("Select one or more files to export")

                with ui.button("Transcribe", icon="rtt") as bulk_transcribe:
                    bulk_transcribe.props("color=black flat")
                    bulk_transcribe.classes("default-style")
                    bulk_transcribe.on(
                        "click",
                        lambda: table_bulk_transcribe(
                            table,
                            on_complete=lambda: ui.timer(0.1, update_rows, once=True),
                        ),
                    )
                    bulk_transcribe.set_enabled(False)
                    transcribe_tooltip = ui.tooltip(
                        "Select one or more files to transcribe"
                    )

                # Two ways in, asked before any dialog rather than inside
                # one: someone who came to record should not have to find a
                # recorder under a drop target, and someone uploading a file
                # should not have to read past a recorder.  Recording is its
                # own page (pages/record.py) -- see there for why.
                with ui.button("Upload", icon="upload") as upload:
                    upload.props('color=black flat aria-haspopup="menu"')
                    upload.classes("default-style")
                    with ui.menu():
                        ui.menu_item(
                            "Upload files", lambda: table_upload(table)
                        ).props('aria-label="Upload audio or video files"')
                        ui.menu_item(
                            "Record audio", lambda: ui.navigate.to("/record")
                        ).props('aria-label="Record audio with the microphone"')

        async def update_rows():
            """
            Update the rows in the table.
            """
            rows = await jobs_get()

            # Backend fetch failed; keep existing rows so table doesn't blank
            # out during long operations like uploads.
            if rows is None:
                return

            if not rows:
                delete.set_enabled(False)
                bulk_export.set_enabled(False)
                bulk_transcribe.set_enabled(False)

            table.selection = "multiple" if rows else "none"
            table.update_rows(rows, clear_selection=False)

            has_active = any(
                r["status"].lower() in ("transcribing", "queued", "uploading")
                for r in rows
            )
            poll_timer.interval = 5.0 if has_active else 30.0

        poll_timer = ui.timer(30.0, update_rows, active=False)

        async def recording_arrived(e: events.GenericEventArguments) -> None:
            ui.notify(
                f"Recording uploaded: {e.args.get('name', '')}",
                type="positive",
                position="top",
            )
            await update_rows()

        reminder.on("uploaded", recording_arrived)

        async def initial_load():
            poll_timer.activate()
            await update_rows()

        ui.timer(0.0, initial_load, once=True)

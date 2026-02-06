from nicegui import ui, events
from utils.common import (
    default_styles,
    page_init,
    jobs_get,
    jobs_columns,
    table_click,
    table_upload,
    table_delete,
    table_transcribe,
    table_bulk_transcribe,
    table_bulk_export,
)


def create() -> None:
    @ui.refreshable
    @ui.page("/home")
    def home() -> None:
        """
        Main page of the application.
        """
        page_init()

        def toggle_buttons(selected: list) -> None:
            """
            Toggle the state of buttons based on selected rows.
            """
            delete.set_enabled(bool(selected))
            
            # Enable Bulk Transcribe if at least one selected row has status "Uploaded"
            uploaded_count = sum(1 for row in selected if row["status"] == "Uploaded")
            bulk_transcribe.set_enabled(uploaded_count > 0)
            
            # Enable Bulk Export if at least 2 selected rows have status "Completed" 
            # AND all completed rows have the same output_format
            completed_rows = [row for row in selected if row["status"] == "Completed"]
            if len(completed_rows) >= 2:
                output_formats = set(row.get("output_format") for row in completed_rows)
                bulk_export.set_enabled(len(output_formats) == 1)
            else:
                bulk_export.set_enabled(False)

        table = ui.table(
            on_select=lambda e: toggle_buttons(e.selection),
            columns=jobs_columns,
            rows=jobs_get(),
            selection="multiple",
            pagination=10,
        )

        def table_handle_row_click(e: events.GenericEventArguments) -> None:
            if e.args.get("status") == "Completed":
                table_click(e)
            else:
                table_transcribe(e.args)

        ui.add_head_html(default_styles)

        table.style(
            "width: 100%; height: calc(100vh - 160px); box-shadow: none; font-size: 18px;"
        )
        table.classes("table-style")
        table.add_slot(
            "body-cell-status",
            """
            <q-td key="status" :props="props">
                <p>{{ props.value }}</p>
            </q-td>
            <q-td key="action" :props="props">
                <q-btn
                    v-if="props.row.status === 'Uploaded' || props.row.status === 'Completed'"
                    :label="props.row.status === 'Completed' ? 'Edit' : 'Transcribe'"
                    :color="props.row.status === 'Completed' ? 'white' : 'black'"
                    :text-color="props.row.status === 'Completed' ? 'black' : 'white'"
                    :outline="props.row.status === 'Completed'"
                    style="width: 120px; height: 40px;"
                    @click="$parent.$emit('table_handle_row_click', props.row)"
                />
            </q-td>
            """,
        )
        table.add_slot(
            "body-cell-deletetion_date",
            """
            <q-td key="deletetion_date" :props="props">
                <div :class="props.row.deletion_approaching ? 'deletion-warning' : ''">
                    <span>{{ props.row.deletion_date }}</span>
                    <q-icon
                        v-if="props.row.deletion_approaching"
                        name="warning"
                        class="deletion-warning-icon"
                    >
                        <q-tooltip>This file will be permanently deleted within 24 hours.</q-tooltip>
                    </q-icon>
                </div>
            </q-td>
            """,
        )
        table.on("table_handle_row_click", table_handle_row_click)

        with table.add_slot("top-left"):
            ui.label("My files").classes("text-h5")

        with table.add_slot("top-right"):
            with ui.row().classes("items-center"):
                with ui.button("Upload", icon="upload") as upload:
                    upload.props("color=black flat")
                    upload.classes("default-style")
                    upload.on("click", lambda: table_upload(table))

        with ui.row().classes("items-center"):
            with ui.button("Delete", icon="delete") as delete:
                delete.props("color=black flat")
                delete.classes("delete-style")
                delete.on("click", lambda: table_delete(table))
                delete.set_enabled(False)
                delete.visible = False
            
            with ui.button("Bulk Transcribe", icon="description") as bulk_transcribe:
                bulk_transcribe.props("color=black flat")
                bulk_transcribe.classes("default-style")
                bulk_transcribe.on("click", lambda: table_bulk_transcribe(table))
                bulk_transcribe.set_enabled(False)
                bulk_transcribe.visible = False
            
            with ui.button("Bulk Export", icon="download") as bulk_export:
                bulk_export.props("color=black flat")
                bulk_export.classes("button-default-style")
                bulk_export.on("click", lambda: table_bulk_export(table))
                bulk_export.set_enabled(False)
                bulk_export.visible = False

        def update_rows():
            """
            Update the rows in the table.
            """
            rows = jobs_get()

            if not rows:
                delete.set_enabled(False)
                bulk_transcribe.set_enabled(False)
                bulk_export.set_enabled(False)
            else:
                delete.visible = True
                bulk_transcribe.visible = True
                bulk_export.visible = True

            table.selection = "multiple" if rows else "none"
            table.update_rows(rows, clear_selection=False)

        ui.timer(5.0, lambda: update_rows())

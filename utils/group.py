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

from datetime import date, timedelta

import httpx

from nicegui import ui
from utils.bar_chart import NBSP, amount, month_name
from utils.chart_tables import summary_cards
from utils.settings import get_settings
from utils.token import get_auth_header
settings = get_settings()

# "Show more" only where something is cut. Which text is cut depends on the
# card's width, so the page asks the browser: a toggle whose name and
# description all fit is hidden, and asked again when they change size (a
# window made narrower, a menu opened). Shown while open, so it can close.
# Without the script the button stays, which is the safe way round.
TOGGLE_SCRIPT = """
<style>
    .group-description-toggle[hidden] {
        display: none !important;
    }
</style>
<script>
(function () {
    if (window._scribeGroupToggles) return;
    window._scribeGroupToggles = true;

    function controlled(button) {
        return (button.getAttribute("aria-controls") || "")
            .split(/\\s+/)
            .map(function (id) { return id && document.getElementById(id); })
            .filter(Boolean);
    }

    function check(button) {
        if (button.getAttribute("aria-expanded") === "true") {
            button.hidden = false;
            return;
        }

        button.hidden = !controlled(button).some(function (element) {
            return element.scrollHeight > element.clientHeight + 1;
        });
    }

    function checkAll() {
        document.querySelectorAll(".group-description-toggle").forEach(check);
    }

    var sizes = new ResizeObserver(checkAll);

    function watch() {
        document.querySelectorAll(".group-description-toggle").forEach(function (button) {
            if (!button._scribeWatched) {
                button._scribeWatched = true;
                controlled(button).forEach(function (element) { sizes.observe(element); });
            }

            check(button);
        });
    }

    new MutationObserver(watch).observe(document.documentElement, { childList: true, subtree: true });
    document.addEventListener("DOMContentLoaded", watch);
})();
</script>
"""


class Group:
    def __init__(self, group_id: str, name: str, description: str, created_at: str, users: dict, nr_users: int, stats: dict, quota_seconds: int) -> None:
        self.group_id = group_id
        self.name = name
        self.description = description
        self.created_at = created_at.split(".")[0]
        self.users = users
        self.nr_users = nr_users
        self.stats = stats
        self.quota_seconds = quota_seconds

    def edit_group(self) -> None:
        ui.navigate.to(f"/admin/edit/{self.group_id}")

    def delete_group_dialog(self) -> None:
        with ui.dialog().props('aria-label="Delete group"') as delete_group_dialog:
            with ui.card():
                ui.label("Delete group").classes("text-h6").props("role=heading aria-level=2")
                ui.label(
                    "Are you sure you want to delete this group? This action cannot be undone."
                ).classes("text-subtitle2").style("margin-bottom: 10px;")

                with ui.row().classes("justify-between w-full"):
                    ui.button("Cancel", on_click=lambda: delete_group_dialog.close()).props(
                        "color=black"
                    )
                    ui.button(
                        "Delete",
                        on_click=lambda: (
                            httpx.delete(
                                settings.API_URL + f"/api/v1/admin/groups/{self.group_id}",
                                headers=get_auth_header(),
                            ),
                            delete_group_dialog.close(),
                            ui.navigate.to("/admin"),
                        ),
                    ).props("color=red")

            delete_group_dialog.open()

    # Over this many characters a name is cut to two lines on the card, and
    # a description to three, with one button to show them whole: some
    # names are long, and some descriptions are essays.
    LONG_NAME = 48
    LONG_DESCRIPTION = 120

    def name_and_description(self) -> None:
        """
        The name (a heading) and the description, each cut by CSS when
        long, so the whole text is there for a screen reader either way;
        and when either is cut, one "Show more" / "Show less" button under
        them, with aria-expanded and aria-controls naming what it opens.
        """

        cut = []
        name = ui.label(self.name).classes("group-name").props("role=heading aria-level=2")

        if len(self.name) > self.LONG_NAME:
            cut.append((name, f"group-name-{self.group_id}"))

        if self.description:
            description = ui.label(self.description).classes("group-description")

            if len(self.description) > self.LONG_DESCRIPTION:
                cut.append((description, f"group-description-{self.group_id}"))

        if not cut:
            return

        for element, element_id in cut:
            element.classes("is-clamped")
            element._props["id"] = element_id

        # color=None: NiceGUI's default "primary" is Quasar's .text-primary,
        # 3:1 on a white card and in a CSS layer that wins over the page's
        # own !important; without it the button takes the brand colour.
        toggle = ui.button("Show more", color=None).classes("group-description-toggle").props("flat dense no-caps")
        toggle._props["aria-expanded"] = "false"
        toggle._props["aria-controls"] = " ".join(element_id for _, element_id in cut)

        def flip() -> None:
            opened = toggle._props.get("aria-expanded") == "false"

            for element, _ in cut:
                element.classes(remove="is-clamped") if opened else element.classes(add="is-clamped")

            toggle.text = "Show less" if opened else "Show more"
            toggle._props["aria-expanded"] = "true" if opened else "false"
            toggle.update()

        toggle.on("click", flip)

    def create_card(self) -> None:
        """
        The group as a card: name, description and details, this month and
        the one before as summary cards (whole minutes; months by name,
        from today), and the actions in a column of their own (CSS in
        utils/styles.py, .group-card). Each action is named for its group:
        "Statistics" three times in a row says nothing to a screen reader.
        """

        today = date.today()
        this_first = today.replace(day=1)
        previous_first = (this_first - timedelta(days=1)).replace(day=1)
        limit = (
            "Unlimited"
            if self.quota_seconds == 0
            else f"{self.quota_seconds // 60}{NBSP}minutes"
        )
        members = f"{self.nr_users}{NBSP}member" if self.nr_users == 1 else f"{self.nr_users}{NBSP}members"

        def files(count) -> str:
            return f"{count}{NBSP}file" if count == 1 else f"{count}{NBSP}files"

        def button(text: str, name: str, look: str, props: str, action) -> None:
            control = ui.button(text).classes(look).props(props)
            # Set directly, not through props(): a group's name may hold a
            # quote, which the props string would take apart.
            control._props["aria-label"] = name
            control.on("click", action)

        with ui.card().classes("group-card admin-card my-2"):
            with ui.element("div").classes("group-layout"):
                with ui.element("div").classes("group-info"):
                    self.name_and_description()

                    # One line with separators on a wide card, one to a line
                    # on a narrow one (utils/styles.py, .group-meta-line).
                    with ui.element("div").classes("group-meta-wrap"):
                        with ui.element("div").classes("group-meta-line"):
                            ui.label(members).classes("group-meta")
                            ui.label(f"Monthly limit: {limit}").classes("group-meta")

                            if self.name != "All users":
                                ui.label(f"Created {self.created_at}").classes("group-meta")

                summary_cards(
                    (
                        (
                            month_name(this_first.isoformat()),
                            [
                                f"{files(self.stats['transcribed_files'])} transcribed",
                                amount(self.stats["total_transcribed_minutes"]),
                            ],
                        ),
                        (
                            month_name(previous_first.isoformat()),
                            [
                                f"{files(self.stats['transcribed_files_last_month'])} transcribed",
                                amount(self.stats["total_transcribed_minutes_last_month"]),
                            ],
                        ),
                    )
                )

                with ui.element("div").classes("group-actions"):
                    button(
                        "Statistics",
                        f"Statistics for {self.name}",
                        "button-edit",
                        "color=white flat",
                        lambda: ui.navigate.to(f"/admin/stats/{self.group_id}"),
                    )

                    if self.name == "All users":
                        return

                    button("Edit", f"Edit {self.name}", "button-edit", "color=white flat", lambda: self.edit_group())
                    button(
                        "Delete",
                        f"Delete {self.name}",
                        "button-close",
                        "color=black flat",
                        lambda: self.delete_group_dialog(),
                    )

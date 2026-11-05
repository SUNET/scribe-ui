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
The user administration page.
"""

import json

import httpx

from nicegui import ui
from utils.common import page_init
from utils.styles import default_styles
from utils.helpers import (
    remove_user,
    reset_manual_override,
    set_active_status,
    set_admin_status,
    open_make_admin_dialog,
    set_domains,
)
from utils.settings import get_settings
from utils.token import (
    get_auth_header,
)

settings = get_settings()

# The search and the filters run in the browser, over the rows it already
# has: with thousands of users, sending them again on every key would be
# slow. The table's filter is a JSON string of what is asked for; this
# replaces Quasar's own filter (which only knows a search string) and also
# says how many users are shown, in the page's status line.
FILTER_METHOD = """(rows, terms, cols, getCellValue) => {
    let asked;
    try { asked = JSON.parse(terms); } catch (error) { asked = { q: terms }; }
    const q = String(asked.q || "").trim().toLowerCase();
    // Plain words are found anywhere in a cell. With * (any run of
    // characters) or ? (any one), the pattern is the whole cell:
    // "*@su.se" ends there, "anna*" begins there. Matched by walking the
    // pattern and the cell side by side, going back only to the last *,
    // rather than by a regular expression: "*a*a*a*a*b" made into one
    // backtracks without end on a long name, and this runs on every key.
    const wildcard = (text) => {
        let p = 0, t = 0, star = -1, from = 0;
        while (t < text.length) {
            if (p < q.length && (q[p] === "?" || q[p] === text[t])) { p++; t++; }
            else if (p < q.length && q[p] === "*") { star = p++; from = t; }
            else if (star !== -1) { p = star + 1; t = ++from; }
            else return false;
        }
        while (q[p] === "*") p++;
        return p === q.length;
    };
    const matches = /[*?]/.test(q) ? wildcard : (text) => text.includes(q);
    const shown = rows.filter((row) =>
        ["active", "admin", "provisioning", "realm"].every((key) => !asked[key] || row[key] === asked[key]) &&
        (!asked.group || (asked.group === "__none__"
            ? !(row.group_list || []).length
            : (row.group_list || []).includes(asked.group))) &&
        (!q || cols.some((col) => matches(String(getCellValue(col, row) ?? "").toLowerCase())))
    );
    const count = document.querySelector(".users-count");
    if (count) {
        const all = rows.length === 1 ? "1 user" : rows.length + " users";
        count.textContent = shown.length === rows.length ? all : "Showing " + shown.length + " of " + all;
    }
    return shown;
}"""


@ui.page("/admin/users")
async def users() -> None:
    """
    Page to show all users.
    """
    user_data = await page_init(use_drawer=True, title="Users")

    if not (user_data or {}).get("admin"):
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    try:
        res = httpx.get(
            settings.API_URL + "/api/v1/admin/users", headers=get_auth_header()
        )
        res.raise_for_status()
        users = res.json()["result"]

        # Add an id field to each user for table selection
        for index, user in enumerate(users):
            user["id"] = index
            user["admin"] = "Yes" if user.get("admin", True) else "No"
            # The same words as the Enable and Disable buttons.
            user["active"] = "Enabled" if user.get("active", True) else "Disabled"
            user["provisioning"] = (
                "Manual"
                if user.get("manually_activated") or user.get("manually_deactivated")
                else "Auto"
            )

            # Lists read as "a, b", in the table and on a phone's cards.
            # The groups as they are, for the Group filter: a group's own
            # name may hold a comma ("Krishantering, styrning och samverkan"),
            # so a joined string cannot be split again.
            groups = user.get("groups")
            user["group_list"] = (
                [str(group) for group in groups]
                if isinstance(groups, (list, tuple))
                else ([str(groups)] if groups else [])
            )

            for field in ("groups", "admin_domains"):
                if isinstance(user.get(field), (list, tuple)):
                    user[field] = ", ".join(str(item) for item in user[field])

            # One line on a phone's card for what are three columns here.
            user["status"] = ", ".join(
                part
                for part in (
                    "Admin" if user["admin"] == "Yes" else "",
                    user["active"],
                    f"{user['provisioning']} provisioning",
                )
                if part
            )

    except httpx.HTTPError as e:
        # The raw exception used to go straight to the page (for example a
        # bare "[Errno 111] Connection refused"), which means nothing to the
        # reader. The detail is printed instead, as utils/helpers.py does for
        # its own fetch errors. role=alert: this replaces the whole page body
        # and nothing else announces that anything changed (WCAG 4.1.3).
        print(f"Error fetching users: {e}")
        ui.label("Failed to load users. Please try again later.").classes(
            "text-lg"
        ).style("color: var(--color-text-danger);").props("role=alert")
        return

    users_table = ui.table(
        columns=[
            {
                "name": "username",
                "label": "Username",
                "field": "username",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "realm",
                "label": "Realm",
                "field": "realm",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "role",
                "label": "Admin",
                "field": "admin",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "groups",
                "label": "Groups",
                "field": "groups",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "domains",
                "label": "Domains",
                "field": "admin_domains",
                "align": "left",
                "sortable": False,
                "style": "max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;",
            },
            {
                "name": "active",
                "label": "Status",
                "field": "active",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "provisioning",
                "label": "Provisioning",
                "field": "provisioning",
                "align": "left",
                "sortable": True,
            },
        ],
        rows=users,
        selection="multiple",
        pagination=20,
        on_select=lambda e: None,
    )
    # The height and the type size are in utils/styles.py (.users-table):
    # a height worked out from the window suits a wide table, not a phone's
    # list of cards.
    users_table.classes("table-style users-table")

    asked = {"q": "", "active": "", "admin": "", "provisioning": "", "realm": "", "group": ""}

    def ask(key: str, value: str) -> None:
        # Given to the table in the browser only. Setting the table's filter
        # (or any of its props) here updates the table, and an update sends
        # all its props, the thousands of rows among them, on every key
        # typed. Kept in _props as well, without an update, so that the table
        # has it if it is ever sent again.
        asked[key] = value
        terms = json.dumps(asked)
        with users_table._props.suspend_updates():
            users_table._props["filter"] = terms
        users_table.client.run_javascript(
            f"mounted_app.elements[{users_table.id}].props.filter = {json.dumps(terms)};"
        )

    # Set directly: the function's quotes and spaces would be taken apart
    # by a props string. A ":" prop is evaluated in the browser.
    users_table._props[":filter-method"] = FILTER_METHOD
    users_table.filter = json.dumps(asked)

    # On a phone seven columns cannot be read; Quasar's grid mode draws each
    # user as a card instead, in the look of the files on /home (the same
    # breakpoint and the same reason: see pages/home.py).
    users_table.props(':grid="window.innerWidth < 700"')
    users_table.add_slot(
        "item",
        """
        <div class="q-pa-xs col-12">
            <q-card flat bordered class="jobs-card user-card">
                <div class="row items-start no-wrap">
                    <q-checkbox
                        v-model="props.selected"
                        :aria-label="'Select ' + props.row.username"
                        class="q-mr-sm"
                    />
                    <div class="col">
                        <div class="jobs-card-name">{{ props.row.username }}</div>
                        <div class="jobs-card-meta">{{ props.row.realm }}</div>
                        <div class="jobs-card-meta">{{ props.row.status }}</div>
                        <div v-if="props.row.groups" class="jobs-card-meta">Groups: {{ props.row.groups }}</div>
                        <div v-if="props.row.admin_domains" class="jobs-card-meta">Domains: {{ props.row.admin_domains }}</div>
                    </div>
                </div>
            </q-card>
        </div>
        """,
    )

    # Quasar generates selection checkboxes from selection="multiple" with
    # no accessible name at all -- both the header "select all" and each
    # row's own checkbox are announced only as "checkbox". These slots keep
    # Quasar's own default selection behaviour (v-model="props.selected")
    # and add nothing but a name.
    users_table.add_slot(
        "header-selection",
        """
        <q-checkbox v-model="props.selected" aria-label="Select all users" />
        """,
    )
    users_table.add_slot(
        "body-selection",
        """
        <q-checkbox v-model="props.selected" :aria-label="'Select ' + props.row.username" />
        """,
    )

    # The actions and the search in one bar: side by side on a wide page,
    # the search first and full width on a phone, where finding one user
    # among thousands is what the page is mostly for.
    with users_table.add_slot("top"):
        # The title on the left and the controls on the right, as before;
        # on a phone they wrap, the search first (utils/styles.py).
        with ui.element("div").classes("users-header"):
            ui.label("Users").classes("text-3xl font-bold users-title").props("role=heading aria-level=1")

            with ui.element("div").classes("users-toolbar"):
                # Filters, each with a visible label; "All" is no filter.
                realms = sorted({user.get("realm") for user in users if user.get("realm")})
                filters = [
                    ("active", "Status", {"": "All", "Enabled": "Enabled", "Disabled": "Disabled"}),
                    ("admin", "Admin", {"": "All", "Yes": "Admins", "No": "Not admins"}),
                    ("provisioning", "Provisioning", {"": "All", "Auto": "Auto", "Manual": "Manual"}),
                ]

                # Realm only where there is more than one to choose between;
                # Group wherever there are groups, with "No group" for the
                # users in none. Both can be long lists: typed into to narrow.
                if len(realms) > 1:
                    filters.append(("realm", "Realm", {"": "All", **{realm: realm for realm in realms}}))

                group_names = sorted({group for user in users for group in user["group_list"]}, key=str.lower)

                if group_names:
                    filters.append(
                        ("group", "Group", {"": "All", "__none__": "No group", **{name: name for name in group_names}})
                    )

                # The search, the filter button beside it, and the filters it
                # opens right under them, in one group on the right: one place to
                # find users, in that order for the keyboard too (search, filter
                # button, filters, Clear filters), the actions before it.
                # The search, the filter button beside it, and the filters it
                # opens right under them, in one group: one place to find users.
                # Before the actions, on the screen and for the keyboard alike:
                # find the users, choose them, then say what to do with them.
                with ui.element("div").classes("users-find-group"):
                    with ui.element("div").classes("users-find"):
                        with ui.input(
                            placeholder="Search", on_change=lambda e: ask("q", e.value or "")
                        ).props('type=search aria-label="Search users"').classes("users-search").add_slot("append"):
                            ui.icon("search")

                        # color=None: the theme's text colour (utils/styles.py),
                        # not black on a dark page or Quasar's 3:1 primary.
                        toggle = ui.button(icon="filter_alt", color=None).classes("users-filter-toggle").props(
                            "flat round"
                        )
                        toggle._props["aria-label"] = "Filters"
                        toggle._props["aria-expanded"] = "false"

                        with toggle:
                            badge = ui.badge("", color="red").props("floating").classes("users-filter-badge")
                            badge.set_visibility(False)

                    # A disclosure: the button says whether it is open and which
                    # element it opens; the panel is a group named by the button.
                    panel = ui.element("div").classes("users-filters").props('role="group"')
                    panel.set_visibility(False)
                    toggle._props["aria-controls"] = f"c{panel.id}"
                    panel._props["aria-labelledby"] = f"c{toggle.id}"
                    selects = []

                    with panel:
                        for key, label, options in filters:
                            selects.append(
                                ui.select(
                                    options,
                                    value="",
                                    label=label,
                                    with_input=key in ("realm", "group"),
                                    on_change=lambda e, key=key: (ask(key, e.value or ""), show_in_use()),
                                ).props("outlined dense options-dense").classes("users-filter")
                            )

                        def clear_filters() -> None:
                            for select in selects:
                                select.value = ""

                        ui.button("Clear filters", on_click=clear_filters, color=None).props("flat no-caps").classes(
                            "users-filter-clear"
                        )

                with ui.element("div").classes("users-actions"):
                    ui.button("Enable").classes("button-close").props("color=black flat").on(
                        "click", lambda: set_active_status(users_table.selected, True)
                    )
                    ui.button("Disable").classes("delete-style").props("color=black flat").on(
                        "click", lambda: set_active_status(users_table.selected, False)
                    )

                    def confirm_remove_user():
                        selected = users_table.selected
                        if not selected:
                            ui.notify("No users selected", type="warning", timeout=None, close_button="Close")
                            return

                        usernames = ", ".join(u["username"] for u in selected)

                        with ui.dialog().props('aria-label="Remove users"') as dialog:
                            with ui.card():
                                ui.label("Remove users").classes("text-h6")
                                ui.label(
                                    f"Are you sure you want to remove: {usernames}? "
                                    "Statistics will be preserved until all associated data has been cleaned up."
                                ).classes("text-subtitle2").style("margin-bottom: 10px;")

                                with ui.row().classes("justify-between w-full"):
                                    ui.button("Cancel", on_click=lambda: dialog.close()).props(
                                        "color=black"
                                    )
                                    ui.button(
                                        "Remove",
                                        on_click=lambda: (
                                            dialog.close(),
                                            remove_user(selected),
                                        ),
                                    ).props("color=red")

                        dialog.open()

                    with ui.button("More").classes("button-close").props(
                        "color=black flat icon-right=arrow_drop_down"
                    ):
                        with ui.menu():
                            ui.menu_item(
                                "Domains",
                                on_click=lambda: set_domains(users_table.selected, users),
                            )
                            ui.menu_item(
                                "Make admin",
                                on_click=lambda: open_make_admin_dialog(
                                    users_table.selected, users,
                                ),
                            )       
                            ui.menu_item(
                                "Remove admin",
                                on_click=lambda: set_admin_status(
                                    users_table.selected, False, None, ""
                                ),
                            )
                            ui.menu_item(
                                "Reset to auto provisioning",
                                on_click=lambda: reset_manual_override(users_table.selected),
                            )
                            ui.menu_item(
                                "Remove user",
                                on_click=confirm_remove_user,
                            )

                def show_in_use() -> None:
                    in_use = sum(1 for select in selects if select.value)
                    badge.text = str(in_use)
                    badge.set_visibility(in_use > 0)
                    toggle._props["aria-label"] = (
                        "Filters" if not in_use else f"Filters, {in_use} in use"
                    )
                    toggle.update()

                def flip_filters() -> None:
                    opened = not panel.visible
                    panel.set_visibility(opened)
                    toggle._props["aria-expanded"] = "true" if opened else "false"
                    toggle.update()

                toggle.on("click", flip_filters)

        # How many are shown, said when it changes (4.1.3). Filled in by
        # FILTER_METHOD in the browser.
        # Written here too: the first time Quasar filters, before the page
        # is drawn, there is no label yet for FILTER_METHOD to fill in.
        ui.label(f"{len(users)} user{'s' if len(users) != 1 else ''}").classes(
            "users-count text-theme-secondary"
        ).props('role=status aria-live=polite')

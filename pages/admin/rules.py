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
Onboarding attribute rules, and the attributes they match on.
"""


import re

from nicegui import app, ui
from utils.common import page_init
from utils.styles import default_styles
from utils.helpers import (
    groups_get,
    rules_get,
    rule_create,
    rule_update,
    rule_delete,
    attributes_get,
    attribute_create,
    attribute_delete,
)
from utils.settings import get_settings
from utils.token import (
    get_admin_status,
    get_bofh_status,
    get_user_data,
)
from pages.admin.shared import _get_valid_realms

settings = get_settings()


CONDITION_OPTIONS = {
    "equals": "Equals",
    "not_equals": "Not equals",
    "contains": "Contains",
    "not_contains": "Not contains",
    "starts_with": "Starts with",
    "ends_with": "Ends with",
    "regex_match": "Regex match",
}


def create_rule_dialog(page: callable) -> None:
    """
    Show a dialog to create a new attribute rule.
    """

    # Re-apply dark mode to prevent state loss during dialog creation
    ui.dark_mode(app.storage.user.get("dark_mode", None))

    onboarding_attrs = attributes_get()
    attr_names = [a["name"] for a in onboarding_attrs]
    all_groups = groups_get()
    group_options = {}

    if all_groups:
        group_options = {
            g["id"]: g["name"] for g in all_groups if g["name"] != "All users"
        }

    is_bofh = get_bofh_status()

    if not is_bofh:
        user_data = get_user_data() or {}
        admin_domains = user_data.get("admin_domains") or ""
        allowed_realms = [
            d.strip()
            for d in admin_domains.split(",")
            if d.strip() and "." in d.strip()
        ]

    with ui.dialog() as dialog:
        with ui.card().style("width: 650px; max-width: 90vw;"):
            ui.label("Create provisioning rule").classes("text-2xl font-bold")

            name_input = ui.input("Rule name").classes("w-full").props("outlined")

            attr_select = (
                ui.select(attr_names, label="Attribute name", with_input=True)
                .classes("w-full")
                .props("outlined")
            )
            condition_select = (
                ui.select(CONDITION_OPTIONS, label="Condition")
                .classes("w-full")
                .props("outlined")
            )

            value_input = (
                ui.input("Attribute value").classes("w-full").props("outlined")
            )

            ui.label("Scope").classes("text-lg font-semibold mt-2")
            if is_bofh:
                all_realms = _get_valid_realms()
                realm_input = (
                    ui.select(
                        all_realms,
                        label="Realm",
                        multiple=True,
                        with_input=True,
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )
            else:
                realm_input = (
                    ui.select(
                        allowed_realms,
                        label="Realm",
                        multiple=True,
                        value=[allowed_realms[0]] if allowed_realms else [],
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )

            ui.label("Actions").classes("text-lg font-semibold mt-2")
            with ui.row().classes("w-full gap-4"):
                activate_cb = ui.checkbox("Activate user")
                deny_cb = ui.checkbox("Deactivate user")

            activate_cb.on_value_change(
                lambda e: deny_cb.set_value(False) if e.value else None
            )
            deny_cb.on_value_change(
                lambda e: activate_cb.set_value(False) if e.value else None
            )

            group_select = (
                ui.select(
                    group_options,
                    label="Assign user to group (optional)",
                    clearable=True,
                )
                .classes("w-full")
                .props("outlined")
            )

            ui.label("Default personal notifications").classes("text-lg font-semibold mt-2")
            with ui.row().classes("w-full gap-4"):
                notify_job_cb = ui.checkbox("Transcription completed")
                notify_deletion_cb = ui.checkbox("Upcoming file deletions")

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Create").classes("default-style").props(
                    "color=black flat"
                ).on(
                    "click",
                    lambda: (
                        _do_create_rule(
                            name=name_input.value,
                            attribute_name=attr_select.value,
                            attribute_condition=condition_select.value,
                            attribute_value=value_input.value,
                            realm=realm_input.value,
                            activate=activate_cb.value,
                            deny=deny_cb.value,
                            assign_to_group=group_select.value,
                            notify_job=notify_job_cb.value,
                            notify_deletion=notify_deletion_cb.value,
                        )
                        and (dialog.close(), ui.navigate.to("/admin/rules"))
                    ),
                )

        dialog.open()


def _do_create_rule(**kwargs) -> bool:
    """
    Helper to create a rule from dialog values. Returns True on success.
    """

    realm_val = kwargs["realm"]

    if not realm_val or (isinstance(realm_val, list) and len(realm_val) == 0):
        with ui.dialog() as warn_dlg, ui.card().classes("p-6"):
            ui.label("Realm required").classes("text-h6")
            ui.label("At least one realm must be selected.")
            ui.button("OK", on_click=warn_dlg.close).classes("mt-4 self-end")
        warn_dlg.open()

        return False

    data = {
        "name": kwargs["name"],
        "attribute_name": kwargs["attribute_name"],
        "attribute_condition": kwargs["attribute_condition"].upper(),
        "attribute_value": kwargs["attribute_value"],
        "realm": ",".join(realm_val) if isinstance(realm_val, list) else realm_val,
        "activate": kwargs["activate"],
        "deny": kwargs["deny"],
        "assign_to_group": str(kwargs["assign_to_group"])
        if kwargs["assign_to_group"]
        else None,
        "notify_job": kwargs.get("notify_job", False),
        "notify_deletion": kwargs.get("notify_deletion", False),
    }

    result = rule_create(data)

    if result:
        ui.notify("Rule created successfully.", color="positive")
        return True

    ui.notify("Failed to create rule.", color="negative")

    return False


def edit_rule_dialog(rule: dict, page: callable) -> None:
    """
    Show a dialog to edit an existing attribute rule.
    """

    # Re-apply dark mode to prevent state loss during dialog creation
    ui.dark_mode(app.storage.user.get("dark_mode", None))

    onboarding_attrs = attributes_get()
    attr_names = [a["name"] for a in onboarding_attrs]
    all_groups = groups_get()
    group_options = {}

    if all_groups:
        group_options = {
            g["id"]: g["name"] for g in all_groups if g["name"] != "All users"
        }

    is_bofh = get_bofh_status()

    if not is_bofh:
        user_data = get_user_data() or {}
        admin_domains = user_data.get("admin_domains", "")
        allowed_realms = [
            d.strip()
            for d in admin_domains.split(",")
            if d.strip() and "." in d.strip()
        ]

    with ui.dialog() as dialog:
        with ui.card().style("width: 650px; max-width: 90vw;"):
            ui.label("Edit provisioning rule").classes("text-2xl font-bold")

            name_input = (
                ui.input("Rule name", value=rule["name"])
                .classes("w-full")
                .props("outlined")
            )

            attr_select = (
                ui.select(
                    attr_names,
                    label="Attribute name",
                    value=rule["attribute_name"],
                    with_input=True,
                )
                .classes("w-full")
                .props("outlined")
            )
            condition_select = (
                ui.select(
                    CONDITION_OPTIONS,
                    label="Condition",
                    value=rule["attribute_condition"].lower(),
                )
                .classes("w-full")
                .props("outlined")
            )

            value_input = (
                ui.input("Attribute value", value=rule["attribute_value"])
                .classes("w-full")
                .props("outlined")
            )

            ui.label("Scope").classes("text-lg font-semibold mt-2")
            existing_realms = [
                r.strip() for r in (rule.get("realm") or "").split(",") if r.strip()
            ]
            if is_bofh:
                all_realms = _get_valid_realms()
                realm_options = sorted(set(all_realms + existing_realms))
                realm_input = (
                    ui.select(
                        realm_options,
                        label="Realm",
                        multiple=True,
                        value=existing_realms,
                        with_input=True,
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )
            else:
                realm_options = sorted(set(allowed_realms + existing_realms))
                realm_input = (
                    ui.select(
                        realm_options,
                        label="Realm",
                        multiple=True,
                        value=existing_realms
                        or ([allowed_realms[0]] if allowed_realms else []),
                    )
                    .classes("w-full")
                    .props("outlined use-chips")
                )

            ui.label("Actions").classes("text-lg font-semibold mt-2")
            with ui.row().classes("w-full gap-4"):
                activate_cb = ui.checkbox(
                    "Activate user", value=rule.get("activate", False)
                )
                deny_cb = ui.checkbox("Deactivate user", value=rule.get("deny", False))

            activate_cb.on_value_change(
                lambda e: deny_cb.set_value(False) if e.value else None
            )
            deny_cb.on_value_change(
                lambda e: activate_cb.set_value(False) if e.value else None
            )

            group_value = rule.get("assign_to_group")
            try:
                group_value = int(group_value) if group_value else None
            except (ValueError, TypeError):
                group_value = None

            # If the group was deleted, clear the reference
            if group_value and group_value not in group_options:
                group_value = None

            group_select = (
                ui.select(
                    group_options,
                    label="Assign user to group (optional)",
                    value=group_value,
                    clearable=True,
                )
                .classes("w-full")
                .props("outlined")
            )

            ui.label("Default personal notifications").classes("text-lg font-semibold mt-2")
            with ui.row().classes("w-full gap-4"):
                notify_job_cb = ui.checkbox(
                    "Transcription completed",
                    value=rule.get("notify_job", False),
                )
                notify_deletion_cb = ui.checkbox(
                    "Upcoming file deletions",
                    value=rule.get("notify_deletion", False),
                )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Save").classes("default-style").props("color=black flat").on(
                    "click",
                    lambda: (
                        _do_update_rule(
                            rule_id=rule["id"],
                            name=name_input.value,
                            attribute_name=attr_select.value,
                            attribute_condition=condition_select.value,
                            attribute_value=value_input.value,
                            realm=realm_input.value,
                            activate=activate_cb.value,
                            deny=deny_cb.value,
                            assign_to_group=group_select.value,
                            notify_job=notify_job_cb.value,
                            notify_deletion=notify_deletion_cb.value,
                        )
                        and (dialog.close(), ui.navigate.to("/admin/rules"))
                    ),
                )

        dialog.open()


def _do_update_rule(**kwargs) -> bool:
    """
    Helper to update a rule from dialog values. Returns True on success.
    """

    realm_val = kwargs["realm"]

    if not realm_val or (isinstance(realm_val, list) and len(realm_val) == 0):
        with ui.dialog() as warn_dlg, ui.card().classes("p-6"):
            ui.label("Realm required").classes("text-h6")
            ui.label("At least one realm must be selected.")
            ui.button("OK", on_click=warn_dlg.close).classes("mt-4 self-end")
        warn_dlg.open()

        return False

    data = {
        "name": kwargs["name"],
        "attribute_name": kwargs["attribute_name"],
        "attribute_condition": kwargs["attribute_condition"].upper(),
        "attribute_value": kwargs["attribute_value"],
        "realm": ",".join(realm_val) if isinstance(realm_val, list) else realm_val,
        "activate": kwargs["activate"],
        "deny": kwargs["deny"],
        "assign_to_group": str(kwargs["assign_to_group"])
        if kwargs["assign_to_group"]
        else None,
        "notify_job": kwargs.get("notify_job", False),
        "notify_deletion": kwargs.get("notify_deletion", False),
    }

    if rule_update(kwargs["rule_id"], data):
        ui.notify("Rule updated successfully.", color="positive")
        return True

    ui.notify("Failed to update rule.", color="negative")

    return False


def delete_rule_dialog(rule: dict) -> None:
    """
    Show confirmation dialog to delete a rule.
    """

    ui.dark_mode(app.storage.user.get("dark_mode", None))

    with ui.dialog() as dialog:
        with ui.card().style("width: 400px; max-width: 90vw;"):
            ui.label("Delete rule").classes("text-2xl font-bold")
            ui.label(f'Are you sure you want to delete rule "{rule["name"]}"?').classes(
                "text-body1"
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Delete").classes("delete-style").props("color=red flat").on(
                    "click",
                    lambda: (
                        _do_delete_rule(rule["id"]),
                        dialog.close(),
                        ui.navigate.to("/admin/rules"),
                    ),
                )
        dialog.open()


def _do_delete_rule(rule_id: int) -> None:
    """
    Helper to delete a rule.
    """

    if rule_delete(rule_id):
        ui.notify("Rule deleted.", color="positive")
    else:
        ui.notify("Failed to delete rule.", color="negative")


def add_attribute_dialog() -> None:
    """
    Show a dialog to add a new onboarding attribute.
    """
    ui.dark_mode(app.storage.user.get("dark_mode", None))

    with ui.dialog() as dialog:
        with ui.card().style("width: 450px; max-width: 90vw;"):
            ui.label("Add provisioning attribute").classes("text-2xl font-bold")
            name_input = ui.input("Attribute name").classes("w-full").props("outlined")
            desc_input = ui.input("Description").classes("w-full").props("outlined")
            example_input = (
                ui.input("Example value").classes("w-full").props("outlined")
            )

            with ui.row().style("justify-content: flex-end; width: 100%;"):
                ui.button("Cancel").classes("button-close").props(
                    "color=black flat"
                ).on("click", lambda: dialog.close())
                ui.button("Add").classes("default-style").props("color=black flat").on(
                    "click",
                    lambda: (
                        _do_add_attribute(
                            name_input.value,
                            desc_input.value,
                            example_input.value,
                        ),
                        dialog.close(),
                        ui.navigate.to("/admin/rules"),
                    ),
                )
        dialog.open()


def _do_add_attribute(name: str, description: str, example: str) -> None:
    """
    Helper to add an onboarding attribute.
    """

    result = attribute_create(
        {"name": name, "description": description, "example": example}
    )

    if result:
        ui.notify("Attribute added.", color="positive")
    else:
        ui.notify("Failed to add attribute. It may already exist.", color="negative")


def _evaluate_condition(condition: str, actual_value: str, expected_value: str) -> bool:
    """
    Evaluate a rule condition against an actual attribute value.
    For list-type attributes (comma-separated), check if any item matches.
    """

    condition = (condition or "").lower()
    values = [v.strip() for v in actual_value.split(",")]

    for val in values:
        if condition == "equals" and val == expected_value:
            return True
        if condition == "not_equals" and val != expected_value:
            return True
        if condition == "contains" and expected_value in val:
            return True
        if condition == "not_contains" and expected_value not in val:
            return True
        if condition == "starts_with" and val.startswith(expected_value):
            return True
        if condition == "ends_with" and val.endswith(expected_value):
            return True
        if condition == "regex_match":
            try:
                if re.search(expected_value, val):
                    return True
            except re.error:
                return False

    return False


def test_rules_dialog(selected_rules: list[dict]) -> None:
    """
    Show a dialog where the user enters a value and tests it against the rule.
    The rule already defines which attribute and condition to use.
    For list-type values (e.g. affiliations), enter items separated by commas.
    """

    ui.dark_mode(app.storage.user.get("dark_mode", None))

    rule = selected_rules[0]
    attr_name = rule.get("attribute_name", "")
    condition = rule.get("attribute_condition", "")
    expected = rule.get("attribute_value", "")
    cond_label = CONDITION_OPTIONS.get(condition.lower(), condition)

    with ui.dialog() as dialog, ui.card().style("min-width: 600px; max-width: 800px;"):
        ui.label("Test rule").classes("text-xl font-bold")
        ui.label(f"{rule.get('name', '')}").classes("text-theme-muted")
        ui.label(f'{attr_name} {cond_label} "{expected}"').classes(
            "text-theme-muted text-sm"
        )

        ui.separator()

        test_input = (
            ui.input(
                label=f"Value for {attr_name}",
                placeholder="For lists, separate with commas",
            )
            .classes("w-full")
            .on("keydown.enter", lambda: run_test())
        )

        result_container = ui.column().classes("w-full mt-2")

        def run_test() -> None:
            result_container.clear()
            actual = test_input.value or ""

            matched = _evaluate_condition(condition, actual, expected)

            with result_container:
                if matched:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("check_circle", color="positive").classes("text-lg")
                        ui.label("Match!").classes("text-positive font-bold")
                else:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("cancel", color="negative").classes("text-lg")
                        ui.label("No match.").classes("text-negative")

        with ui.row().classes("w-full justify-end mt-4 gap-2"):
            ui.button("Test", icon="science", on_click=run_test).props("color=primary")
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


def test_all_rules_dialog() -> None:
    """
    Show a dialog where the user enters attribute name/value pairs and
    simulates provisioning against all enabled rules.
    """

    ui.dark_mode(app.storage.user.get("dark_mode", None))

    rules_data = rules_get()
    all_rules = rules_data.get("result", []) if rules_data else []
    enabled_rules = [r for r in all_rules if r.get("enabled")]

    onboarding_attrs = attributes_get()
    attr_names = [a["name"] for a in onboarding_attrs] if onboarding_attrs else []

    all_groups = groups_get()
    group_names: dict[int, str] = {}
    if all_groups:
        group_names = {g["id"]: g["name"] for g in all_groups}

    with ui.dialog() as dialog, ui.card().style("min-width: 600px; max-width: 800px;"):
        ui.label("Simulate provisioning").classes("text-xl font-bold")
        ui.label(
            "Enter attribute values to simulate what would happen when a user logs in."
        ).classes("text-theme-muted")

        ui.separator()

        attr_rows: list[dict] = []
        attrs_container = ui.column().classes("w-full gap-2")

        def add_attr_row(name: str | None = None, value: str = "") -> None:
            row = {}
            with attrs_container:
                with ui.row().classes("w-full items-center gap-2") as row_el:
                    row["element"] = row_el
                    row["name"] = ui.select(
                        attr_names,
                        label="Attribute",
                        value=name,
                        with_input=True,
                        new_value_mode="add",
                    ).classes("w-1/3")
                    row["value"] = (
                        ui.input(
                            label="Value",
                            value=value,
                            placeholder="For lists, separate with commas",
                        )
                        .classes("flex-grow")
                        .on("keydown.enter", lambda: run_test())
                    )
                    ui.button(
                        icon="close",
                        on_click=lambda r=row: remove_attr_row(r),
                    ).props("flat round dense color=grey-6 size=sm")
            attr_rows.append(row)

        def remove_attr_row(row: dict) -> None:
            if len(attr_rows) <= 1:
                return
            attrs_container.remove(row["element"])
            attr_rows.remove(row)

        add_attr_row()

        ui.button("Add attribute", icon="add", on_click=lambda: add_attr_row()).props(
            "flat dense color=primary"
        )

        result_container = ui.column().classes("w-full mt-2")

        def run_test() -> None:
            result_container.clear()

            user_attrs = {}
            for row in attr_rows:
                name = row["name"].value
                value = row["value"].value
                if name and value:
                    user_attrs[name] = value

            if not user_attrs:
                with result_container:
                    ui.label("Enter at least one attribute and value.").classes(
                        "text-negative"
                    )
                return

            matched_rules = []
            unmatched_rules = []

            for rule in enabled_rules:
                attr_name = rule.get("attribute_name", "")
                condition = rule.get("attribute_condition", "")
                expected = rule.get("attribute_value", "")

                actual = user_attrs.get(attr_name)
                if actual is not None and _evaluate_condition(
                    condition, actual, expected
                ):
                    matched_rules.append(rule)
                else:
                    unmatched_rules.append(rule)

            with result_container:
                for rule in matched_rules:
                    cond_label = CONDITION_OPTIONS.get(
                        rule.get("attribute_condition", "").lower(),
                        rule.get("attribute_condition", ""),
                    )
                    actions = []
                    if rule.get("activate"):
                        actions.append("Activate")
                    if rule.get("deny"):
                        actions.append("Deactivate")
                    if rule.get("assign_to_group"):
                        actions.append("Assign to group")
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("check_circle", color="positive").classes("text-lg")
                        ui.label(f"{rule.get('name', '')}").classes(
                            "text-positive font-bold"
                        )
                        ui.label(
                            f'{rule.get("attribute_name")} {cond_label} '
                            f'"{rule.get("attribute_value")}"'
                        ).classes("text-theme-muted text-sm")
                    if actions:
                        ui.label(f"Actions: {', '.join(actions)}").classes(
                            "text-body2 text-theme-secondary ml-8"
                        )

                for rule in unmatched_rules:
                    cond_label = CONDITION_OPTIONS.get(
                        rule.get("attribute_condition", "").lower(),
                        rule.get("attribute_condition", ""),
                    )
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("cancel", color="negative").classes("text-lg")
                        ui.label(f"{rule.get('name', '')}").classes("text-negative")
                        ui.label(
                            f'{rule.get("attribute_name")} {cond_label} '
                            f'"{rule.get("attribute_value")}"'
                        ).classes("text-theme-muted text-sm")

                if not matched_rules and not unmatched_rules:
                    ui.label("No enabled rules to test.").classes("text-theme-muted")

                # Final provisioning result summary
                ui.separator().classes("my-2")
                ui.label("Simulated result").classes("font-bold")
                if not matched_rules:
                    ui.label("None").classes("text-theme-muted")
                else:
                    will_activate = any(r.get("activate") for r in matched_rules)
                    will_deny = any(r.get("deny") for r in matched_rules)
                    # Last matching rule with a group wins
                    final_group = None
                    for r in matched_rules:
                        grp = r.get("assign_to_group")
                        if grp:
                            try:
                                final_group = int(grp)
                            except (ValueError, TypeError):
                                pass

                    results = []
                    if will_deny:
                        results.append("User deactivated")
                    elif will_activate:
                        results.append("User activated")
                    if final_group and final_group in group_names:
                        results.append(
                            f"User assigned to group: {group_names[final_group]}"
                        )
                    if results:
                        for r in results:
                            ui.label(r)
                    else:
                        ui.label("None").classes("text-theme-muted")

        with ui.row().classes("w-full justify-end mt-4 gap-2"):
            ui.button("Simulate", icon="science", on_click=run_test).props(
                "color=primary"
            )
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


def _show_rules_help() -> None:
    """
    Show a help dialog explaining how onboarding rules work.
    """

    with ui.dialog() as dialog, ui.card().style(
        "min-width: 550px; max-width: 700px; padding: 32px;"
    ):
        ui.label("How provisioning rules work").classes("text-2xl font-bold mb-4")

        with ui.column().classes("gap-4"):
            ui.label(
                "Provisioning rules automatically update user accounts based on "
                "attributes received at login. "
                "Rules are evaluated each time a user logs in."
            ).classes("text-body1")

            ui.separator()

            with ui.column().classes("gap-1"):
                ui.label("Rule matching").classes("text-lg font-semibold")
                ui.label(
                    "Each rule specifies an attribute name (for example "
                    "preferred_username, email, or domain), a condition (such as "
                    "equals, contains or starts with), and a value to compare against. "
                    "If the condition matches the user's attribute value, the rule's "
                    "actions are applied."
                ).classes("text-body2 text-theme-secondary")

            with ui.column().classes("gap-1"):
                ui.label("Available actions").classes("text-lg font-semibold")
                with ui.column().classes("gap-0 pl-2"):
                    for action, desc in [
                        ("Activate", "Automatically activate the user account."),
                        ("Deactivate", "Prevent the user from accessing the service."),
                        (
                            "Assign user to group",
                            "Place the user in a specific group.",
                        ),
                    ]:
                        with ui.row().classes("items-start gap-2"):
                            ui.label(f"• {action}").classes(
                                "text-body2 font-medium"
                            ).style("min-width: 140px;")
                            ui.label(f"— {desc}").classes(
                                "text-body2 text-theme-secondary"
                            )

            with ui.column().classes("gap-1"):
                ui.label("Scoping").classes("text-lg font-semibold")
                ui.label(
                    "The Realm field limits which login domains the rule applies to. "
                    "Local administrators can only create rules for the realms "
                    "assigned to their account."
                ).classes("text-body2 text-theme-secondary")

            with ui.column().classes("gap-1"):
                ui.label("Rule evaluation").classes("text-lg font-semibold")
                ui.label(
                    "All enabled rules are evaluated on every login. "
                    "If rules conflict:"
                ).classes("text-body2 text-theme-secondary")
                with ui.column().classes("gap-0 pl-2"):
                    for line in [
                        "Deactivate always wins over Activate.",
                        "For group assignment, the last matching rule wins. "
                        "A user can only belong to one group.",
                    ]:
                        ui.label(f"• {line}").classes("text-body2 text-theme-secondary")

            with ui.column().classes("gap-1"):
                ui.label("Manual override").classes("text-lg font-semibold")
                ui.label(
                    "If an administrator manually deactivates a user, provisioning "
                    "rules that would activate that user will not automatically "
                    "override that decision. "
                    "The user will remain deactivated until an administrator "
                    "reactivates the account."
                ).classes("text-body2 text-theme-secondary")

            with ui.column().classes("gap-1"):
                ui.label("Testing").classes("text-lg font-semibold")
                ui.label(
                    "Use the Test button on each rule to check whether a value would "
                    "match the rule. Enter the value you want to test against the "
                    "rule's attribute and condition. "
                    "For list-type attributes (for example affiliations), enter "
                    "multiple values separated by commas."
                ).classes("text-body2 text-theme-secondary")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Close", on_click=dialog.close).props("flat")

    dialog.open()


@ui.page("/admin/rules")
def rules_page() -> None:
    """
    Onboarding management page.
    """

    page_init(use_drawer=True, title="Provisioning rules")

    if not get_admin_status():
        ui.navigate.to("/home")
        return

    ui.add_head_html(default_styles)

    with ui.row().style(
        "justify-content: space-between; align-items: center; width: 100%;"
    ):
        with ui.row().classes("items-center gap-2"):
            ui.label("User provisioning").classes("text-3xl font-bold")
            ui.button(icon="help_outline").props("flat round dense color=grey-7").on(
                "click", lambda: _show_rules_help()
            )
        with ui.element("div").style("display: flex; gap: 10px;"):
            ui.button("Simulate provisioning").classes("button-close").props(
                "color=black flat bordered"
            ).style("width: 200px;").on("click", lambda: test_all_rules_dialog())
            ui.button("Add rule").classes("default-style").props(
                "color=black flat"
            ).style("min-width: 160px;").on(
                "click", lambda: create_rule_dialog(page=rules_page)
            )

    ui.label(
        "Rules are evaluated on every login. "
        "Deactivate overrides Activate. "
        "The last matching rule determines the user's group."
    ).classes("text-body2")

    rules_data = rules_get()
    rules_list = rules_data.get("result", []) if rules_data else []

    if not rules_list:
        ui.label("No provisioning rules defined yet.").classes("text-lg mt-4")
    else:
        for idx, rule in enumerate(rules_list):
            rule["_idx"] = idx
            actions = []
            if rule.get("activate"):
                actions.append("Activate")
            if rule.get("admin"):
                actions.append("Admin")
            if rule.get("deny"):
                actions.append("Deactivate")
            if rule.get("assign_to_group"):
                actions.append("Group")
            rule["actions_summary"] = ", ".join(actions) if actions else "None"
            rule["enabled_label"] = "Yes" if rule.get("enabled") else "No"
            cond = rule.get("attribute_condition", "")
            rule["condition_label"] = CONDITION_OPTIONS.get(cond.lower(), cond)

        rules_table = (
            ui.table(
                columns=[
                    {
                        "name": "name",
                        "label": "Name",
                        "field": "name",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "attribute_name",
                        "label": "Attribute",
                        "field": "attribute_name",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "condition_label",
                        "label": "Condition",
                        "field": "condition_label",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "attribute_value",
                        "label": "Value",
                        "field": "attribute_value",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "actions_summary",
                        "label": "Actions",
                        "field": "actions_summary",
                        "align": "left",
                    },
                    {
                        "name": "enabled_label",
                        "label": "Enabled",
                        "field": "enabled_label",
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
                        "name": "row_actions",
                        "label": "",
                        "field": "row_actions",
                        "align": "right",
                        "sortable": False,
                    },
                ],
                rows=rules_list,
                row_key="id",
                pagination=20,
            )
            .style("width: 100%; box-shadow: none; font-size: 18px;")
            .classes("table-style")
        )

        with rules_table.add_slot("top-right"):
            with ui.input(placeholder="Search").props("type=search").bind_value(
                rules_table, "filter"
            ).add_slot("append"):
                ui.icon("search")

        rules_table.add_slot(
            "body-cell-enabled_label",
            r"""
            <q-td :props="props">
                <q-toggle
                    :model-value="props.row.enabled"
                    @update:model-value="val => $parent.$emit('toggle_enabled', {id: props.row.id, enabled: val})"
                    color="positive"
                    :dark="$q.dark.isActive"
                    dense
                />
            </q-td>
            """,
        )

        def handle_toggle(msg) -> None:
            rule_id = msg.args["id"]
            new_enabled = msg.args["enabled"]
            result = rule_update(rule_id, {"enabled": new_enabled})
            if result:
                ui.notify(
                    f"Rule {'enabled' if new_enabled else 'disabled'}.",
                    color="positive",
                )
                ui.navigate.to("/admin/rules")
            else:
                ui.notify("Failed to update rule.", color="negative")

        rules_table.on("toggle_enabled", handle_toggle)

        rules_table.add_slot(
            "body-cell-name",
            r"""
            <q-td :props="props">
                <a
                    class="cursor-pointer text-primary"
                    @click="$parent.$emit('edit_rule', props.row)"
                    style="text-decoration: underline;"
                >
                    {{ props.row.name }}
                </a>
            </q-td>
            """,
        )

        def handle_edit(msg) -> None:
            rule = msg.args
            edit_rule_dialog(rule, page=rules_page)

        rules_table.on("edit_rule", handle_edit)
        rules_table.add_slot(
            "body-cell-row_actions",
            r"""
            <q-td :props="props">
                <q-btn flat dense icon="science" size="sm"
                    style="width: 80px;"
                    label="Test"
                    @click="$parent.$emit('test_rule', props.row)"
                >
                </q-btn>
                <q-btn flat dense icon="delete" size="sm"
                    style="width: 80px;"
                    label="Delete"
                    @click="$parent.$emit('delete_rule', props.row)"
                >
                </q-btn>
            </q-td>
            """,
        )

        def handle_test(msg) -> None:
            test_rules_dialog([msg.args])

        def handle_delete(msg) -> None:
            delete_rule_dialog(msg.args)

        rules_table.on("test_rule", handle_test)
        rules_table.on("delete_rule", handle_delete)

    if get_bofh_status():
        ui.separator().classes("mt-6 mb-4")
        with ui.row().style(
            "justify-content: space-between; align-items: center; width: 100%;"
        ):
            ui.label("Attributes (BOFH)").classes("text-2xl font-bold")
            ui.button("Add attribute").classes("default-style").props(
                "color=black flat"
            ).style("min-width: 160px;").on("click", lambda: add_attribute_dialog())

        ui.label(
            "These are the known attribute names available when creating rules."
        ).classes("text-body2 text-theme-muted mb-2")

        attrs = attributes_get()
        if not attrs:
            ui.label("No attributes defined.").classes("text-lg")
        else:
            attrs_table = ui.table(
                columns=[
                    {
                        "name": "name",
                        "label": "Claim name",
                        "field": "name",
                        "align": "left",
                        "sortable": True,
                    },
                    {
                        "name": "description",
                        "label": "Description",
                        "field": "description",
                        "align": "left",
                    },
                    {
                        "name": "example",
                        "label": "Example",
                        "field": "example",
                        "align": "left",
                    },
                    {
                        "name": "attr_actions",
                        "label": "",
                        "field": "attr_actions",
                        "align": "right",
                        "sortable": False,
                    },
                ],
                rows=attrs,
                row_key="id",
                pagination=20,
            ).style("width: 100%; box-shadow: none; font-size: 18px;")

            attrs_table.add_slot(
                "body-cell-attr_actions",
                r"""
                <q-td :props="props">
                    <q-btn flat dense round icon="delete" color="negative" size="sm"
                        @click="$parent.$emit('delete_attr', props.row)"
                    >
                        <q-tooltip>Delete attribute</q-tooltip>
                    </q-btn>
                </q-td>
                """,
            )

            def handle_delete_attr(msg) -> None:
                _do_delete_attribute(msg.args)

            attrs_table.on("delete_attr", handle_delete_attr)


def _do_delete_attribute(attr: dict) -> None:
    """
    Delete a single onboarding attribute.
    """

    attribute_delete(attr["id"])

    ui.notify(f"Deleted attribute '{attr['name']}'.", color="positive")
    ui.navigate.to("/admin/rules")


# ── Announcements ────────────────────────────────────────────────────────



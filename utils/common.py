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

import httpx
import pytz


from datetime import datetime, timedelta
from nicegui import background_tasks, ui, app
from starlette.formparsers import MultiPartParser
from typing import Callable, Optional
from utils.settings import get_settings
from utils.cookies import acknowledge_cookie_notice, is_cookie_notice_acknowledged
from utils.token import (
    get_auth_header,
    get_user_data,
    get_user_data_async,
    token_refresh_or_wait,
)
from utils.helpers import (
    storage_decrypt,
    customers_get,
    dark_mode_save,
    sanitize_filename,
)
from utils.styles import (
    default_styles,
    menu_active_style,
    menu_item_style,
    severity_styles,
)

MultiPartParser.spool_max_size = 1024 * 1024 * 4096
settings = get_settings()


def _get_support_contact_email() -> str:
    """
    Look up the support contact email for the current user's customer.
    """

    try:
        user_data = get_user_data() or {}
        user_realm = user_data.get("realm", "")
        if not user_realm:
            return ""

        customers_data = customers_get()
        customers = (
            customers_data.get("result", []) if isinstance(customers_data, dict) else []
        )

        for c in customers:
            c_realms = [
                r.strip() for r in (c.get("realms") or "").split(",") if r.strip()
            ]
            if user_realm in c_realms:
                return c.get("support_contact_email", "")
    except Exception:
        pass

    return ""


def show_help_dialog() -> None:
    """
    Show a help dialog with information about the application.
    """

    with ui.dialog().props('aria-label="Help & Documentation"') as dialog:
        with (
            ui.card()
            .style("max-width: 900px; padding: 32px;")
            .classes("no-shadow help-dialog-card")
        ):
            with ui.row().classes("w-full items-center justify-between mb-6"):
                ui.label("Help & Documentation").classes("text-h4 font-bold")
                ui.button(icon="close", on_click=dialog.close).props(
                    "flat round dense color=grey-7 aria-label='Close help dialog'"
                )

            with ui.column().classes("w-full gap-6"):
                with ui.card().classes("help-about-card border-l-4").style(
                    "padding: 20px;"
                ):
                    ui.label("About Sunet Scribe").classes("text-h6 font-semibold mb-2")
                    ui.label(
                        "Turn audio and video into searchable text or subtitles. Built for research and education, with privacy and accuracy at its core."
                    ).classes("text-body1")
                    if settings.MANUAL_URL:
                        with ui.row().classes("items-center gap-1 mt-2"):
                            ui.label("Manual:").classes("text-body2")
                            ui.link(
                                "Open the user manual",
                                settings.MANUAL_URL,
                                new_tab=True,
                            ).classes("text-body2")

                ui.label("Getting started").classes("text-h6 font-bold mt-2")

                with ui.grid(columns=2).classes("w-full gap-4"):
                    for step_num, step_title, step_desc, step_icon in [
                        (
                            "1",
                            "Upload Files",
                            "Click Upload to add files. Supports most common audio and video formats.",
                            "upload_file",
                        ),
                        (
                            "2",
                            "Start transcription",
                            "Click Transcribe and choose your settings.",
                            "rtt",
                        ),
                        (
                            "3",
                            "Processing",
                            "Your files are processed in the background. You can safely close the browser in the meantime.",
                            "blender",
                        ),
                        (
                            "4",
                            "Get your result",
                            "Download your result, or open the Editor to review and edit.",
                            "edit_note",
                        ),
                    ]:
                        with ui.card().classes("p-4"):
                            with ui.row().classes("items-center gap-3 mb-2"):
                                ui.icon(step_icon, size="md").classes("help-about-icon")
                                ui.label(f"{step_num}. {step_title}").classes(
                                    "text-subtitle1 font-semibold"
                                )
                            ui.label(step_desc).classes(
                                "text-body2 text-theme-secondary"
                            )

                with ui.row().classes("w-full gap-4 items-stretch"):
                    with ui.card().classes("flex-1 help-privacy-card p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("security", size="sm").classes("help-privacy-icon")
                            ui.label("Privacy").classes("text-subtitle1 font-semibold")
                        ui.label(
                            "Files are encrypted, accessible only to you, and automatically deleted after 7 days."
                        ).classes("text-body2")

                    with ui.card().classes("flex-1 help-support-card p-4"):
                        with ui.row().classes("items-center gap-2 mb-2"):
                            ui.icon("help", size="sm").classes("help-support-icon")
                            ui.label("Support").classes("text-subtitle1 font-semibold")

                        ui.label(
                            "Contact your organisation’s local support for questions or technical support."
                        ).classes("text-body2")

                        support_contact = _get_support_contact_email()
                        if support_contact:
                            is_url = support_contact.startswith(("http://", "https://"))
                            href = (
                                support_contact
                                if is_url
                                else f"mailto:{support_contact}"
                            )
                            label = "Support:" if is_url else "Support email:"
                            with ui.row().classes("items-center gap-1"):
                                ui.label(label).classes("text-body2")
                                ui.link(support_contact, href).classes("text-body2")

        dialog.open()


def logout() -> None:
    """
    Log out the user by clearing the token and navigating to the logout endpoint.
    """

    app.storage.user["token"] = None
    app.storage.user["refresh_token"] = None
    app.storage.user["encryption_password"] = None

    ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)


def render_cookie_notice_row(in_page: bool = False) -> None:
    """
    Show "We use necessary cookies..." as the first row inside the
    current header, until this browser acknowledges it. See issue #140.

    Deliberately not built on _show_announcement_banners below. Those
    banners render inside the page's own content area, underneath the
    already-fixed header, and push the rest of the content down with a
    hand-rolled --banner-offset CSS variable, recalculated per visible
    banner. A row placed inside the header itself needs none of that:
    ui.header already measures its own real rendered height with a
    ResizeObserver and reports it to NiceGUI's layout, so adding or
    removing this row reflows the drawer and page content beneath it
    automatically. It also has to work on pages with no header built by
    page_init at all -- the sign-in page -- so it is a self-contained
    function rather than something woven into _show_announcement_banners.

    Two places it can go:

    - in_page=False (the sign-in page): inside a `with ui.header():`
      block, as the first child. That header has nothing else in it.
    - in_page=True (page_init): in the page's own content, right above the
      announcement banners and so below the header's logo/menu row, drawn
      the way they are (full width, flush under the header). It scrolls
      with the page like they do.
    """

    if is_cookie_notice_acknowledged():
        return

    # Same visual language, and the same 20px side padding, as an "info" announcement banner below
    # so the icons and close buttons line up between the two
    # (severity_styles["info"], utils/styles.py) -- same background,
    # border and icon colour, same icon + text layout -- so this reads
    # as the same kind of thing, not an unrelated strip of UI. Not
    # built on _show_announcement_banners itself, for the reasons in
    # this function's own docstring above.
    #
    # The background bleeds edge-to-edge (left/right) inside whatever
    # header surrounds it, via a negative margin that exactly cancels
    # that header's own horizontal padding -- not a hardcoded value,
    # because this function renders inside three differently-padded
    # headers (page_init's two, both "padding: 4px 16px", and
    # main.py's bare `with ui.header():` for the sign-in page, which
    # Quasar leaves at zero padding by default). Each header that has
    # horizontal padding declares it once, as the CSS custom property
    # --cookie-notice-inset-x, alongside its own padding (see
    # page_init below); a header with no such declaration -- like
    # main.py's -- falls back to 0px, i.e. no shift, because it is
    # already edge-to-edge and needs none. This only pulls the row
    # past its header's own left/right padding. No border: the fill is
    # the edge.
    if in_page:
        # The same box an announcement banner has (see
        # _show_announcement_banners): the content area's own padding is
        # cancelled so the fill reaches the edges. A line under it
        # separates it from the announcements below.
        placement = (
            "width: calc(100% + 2 * var(--content-pad-x, 2rem));"
            " margin: calc(-1 * var(--content-pad-top, 1rem))"
            " calc(-1 * var(--content-pad-x, 2rem)) 0"
            " calc(-1 * var(--content-pad-x, 2rem));"
            " border-bottom: 1px solid var(--color-severity-info-border);"
        )
    else:
        placement = (
            "width: calc(100% + 2 * var(--cookie-notice-inset-x, 0px));"
            " margin: 0 calc(-1 * var(--cookie-notice-inset-x, 0px));"
        )

    with ui.row().classes("cookie-notice-row").style(
        f"{placement}"
        " align-items: center; justify-content: space-between;"
        " flex-wrap: nowrap; gap: 16px; padding: 8px 20px;"
        " background-color: var(--color-severity-info-bg);"
    ) as notice_row:
        # One line of controls at any width: the sentence is what gives way
        # (it may wrap inside its own cell), never the link or the close
        # button dropping onto a row of their own.
        with ui.row().style(
            "align-items: center; gap: 10px; flex-wrap: nowrap;"
            " flex: 1 1 0; min-width: 0;"
        ):
            ui.icon("cookie", size="sm").style(
                "color: var(--color-severity-info-icon);"
            )
            ui.label("We use necessary cookies to provide the service.").style(
                "color: var(--color-text-primary); font-size: 0.95rem;"
            )

        with ui.row().style(
            "align-items: center; gap: 4px; flex-wrap: nowrap; flex: 0 0 auto;"
        ):
            # A real link, not a button: it navigates, it does not act in
            # place. Same reasoning as the main menu entries elsewhere in
            # this file.
            ui.link("Cookie information", "/cookies").classes(
                "cookie-notice-link"
            ).style(
                "font-size: 0.9rem; color: var(--color-severity-info-link);"
                " white-space: nowrap;"
            )

            def close_notice() -> None:
                acknowledge_cookie_notice()
                # set_visibility(False), not delete(): the row's own
                # close handler is still on the call stack when this
                # runs, so the element needs to still exist a moment
                # longer. The "hidden" class NiceGUI applies is
                # display:none, which (unlike visibility:hidden) drops
                # out of layout, so the header's ResizeObserver still
                # sees the shrink and the rest of the page moves up.
                notice_row.set_visibility(False)

            # An icon-only close control, same as
            # _show_announcement_banners' own dismiss button below --
            # "OK" read as a label to activate rather than a notice to
            # close, which was both an odd fit for a plain FYI (there is
            # nothing to agree to) and awkward to describe precisely in
            # prose (see acknowledge_cookie_notice's docstring). aria-label
            # is required, not optional: an icon-only button's accessible
            # name would otherwise just be the icon ligature's name,
            # which is aria-hidden.
            ui.button(icon="close", on_click=close_notice).props(
                "flat round dense size=sm color=grey-7"
                ' aria-label="Close cookie banner"'
            ).classes("cookie-notice-close")


def _show_announcement_banners(user_data: dict | None) -> None:
    """Show active announcement banners below the header."""

    if not user_data:
        return

    announcements = user_data.get("announcements", [])
    if not announcements:
        return

    dismissed = app.storage.user.get("dismissed_announcements", [])

    visible_count = 0
    for a in announcements:
        sev = a.get("severity", "info")
        style = severity_styles.get(sev, severity_styles["info"])
        if style["dismissible"] and a.get("id") in dismissed:
            continue
        visible_count += 1

    if visible_count > 0:
        ui.add_head_html(
            f"<style>:root {{ --banner-offset: {visible_count * 40}px; }}</style>"
        )

    # JS to fix link attributes (target, rel) for all banner links
    ui.add_head_html(
        "<script>"
        "document.addEventListener('DOMContentLoaded', function() {"
        "  new MutationObserver(function() {"
        "    document.querySelectorAll('.announcement-banner a').forEach(function(a) {"
        "      if (!a.getAttribute('target')) a.setAttribute('target', '_top');"
        "      try { var u = new URL(a.href, location.origin);"
        "        if (u.origin !== location.origin)"
        "          a.setAttribute('rel', 'noopener noreferrer');"
        "      } catch(e) {}"
        "    });"
        "  }).observe(document.body, {childList: true, subtree: true});"
        "});"
        "</script>"
    )

    for announcement in announcements:
        ann_id = announcement.get("id")
        sev = announcement.get("severity", "info")
        style = severity_styles.get(sev, severity_styles["info"])

        if style["dismissible"] and ann_id in dismissed:
            continue

        banner_container = (
            ui.element("div")
            .classes(f"announcement-banner {style['css_class']}")
            .style(
                "padding: 8px 20px; display: flex; align-items: center;"
                " justify-content: space-between;"
                " margin-left: calc(-1 * var(--content-pad-x, 2rem));"
                " margin-right: calc(-1 * var(--content-pad-x, 2rem));"
                " margin-top: calc(-1 * var(--content-pad-top, 1rem));"
                " width: calc(100% + 2 * var(--content-pad-x, 2rem));"
            )
        )

        with banner_container:
            with ui.element("div").style(
                "display: flex; align-items: center; gap: 10px; flex: 1;"
            ):
                ui.icon(style["icon"], size="sm").style(
                    f"color: {style['icon_color']};"
                )
                ui.html(announcement.get("message", ""), sanitize=False).style(
                    "color: var(--color-text-primary); font-size: 0.95rem;"
                )

            if style["dismissible"]:

                def dismiss(a_id=ann_id, container=banner_container):
                    current = app.storage.user.get("dismissed_announcements", [])
                    if a_id not in current:
                        current.append(a_id)
                        app.storage.user["dismissed_announcements"] = current
                    container.set_visibility(False)

                ui.button(icon="close", on_click=dismiss).props(
                    "flat round dense size=sm color=grey-7 aria-label='Dismiss announcement'"
                )


def reload_on_theme_change() -> None:
    """
    Reload when the OS switches between light and dark.

    Only for pages holding Plotly charts, which are drawn server-side in one
    theme's colours and cannot restyle themselves. Everything else follows
    the OS through CSS custom properties and needs no reload -- and a reload
    is never harmless: on the editor page it throws away every unsaved
    caption, which is exactly what a reader is doing at sunset.

    Calling this is also what _cycle_dark_mode (below) uses to decide
    whether ITS OWN reload, from clicking the header's theme button, is
    worth doing on this page. Measured: before this flag existed, that
    button reloaded on every page except /srt, whether or not the page had
    anything that needed it -- and a full reload always drops keyboard
    focus to the document body, so a page with nothing to redraw paid for
    the redraw anyway, in a focus loss the reload never bought back.
    """

    app.storage.client["scribe_theme_reload_needed"] = True

    ui.add_head_html(
        """
    <script>
    if (!window._scribeThemeListener) {
        window._scribeThemeListener = true;
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function() {
            location.reload();
        });
    }
    </script>
    """
    )


def _anonymous_header(header_text: str, cycle_dark_mode: Callable) -> None:
    """
    The header of a public page seen without being signed in: the logo and
    name, and the theme and help buttons. No menu and no cookie banner --
    there is nothing to navigate to, and the page itself is where the
    cookies are explained.
    """

    with (
        ui.header()
        .style(
            "justify-content: space-between; background-color:"
            " var(--color-header-bg); min-height: 50px; padding: 4px 16px;"
        )
        .classes("drop-shadow-md")
    ):
        with ui.element("div").style(
            "display: flex; gap: 0px; align-items: center;"
        ).classes("header-brand"):
            ui.image(f"static/{settings.LOGO_TOPBAR_LIGHT}").props(
                'alt="" aria-hidden="true"'
            ).classes("q-mr-sm logo-light").style("height: 30px; width: 30px;")
            ui.image(f"static/{settings.LOGO_TOPBAR_DARK}").props(
                'alt="" aria-hidden="true"'
            ).classes("q-mr-sm logo-dark").style("height: 30px; width: 30px;")
            ui.label(settings.TOPBAR_TEXT + header_text).classes(
                "text-h6 text-theme-primary topbar-text"
            )

        with ui.element("div").style("display: flex; gap: 0px;").classes(
            "header-actions"
        ):
            dark_val = app.storage.user.get("dark_mode", None)
            dark_icon = (
                "dark_mode"
                if dark_val
                else ("brightness_auto" if dark_val is None else "light_mode")
            )
            dark_btn = (
                ui.button(
                    icon=dark_icon,
                    on_click=lambda: cycle_dark_mode(dark_btn),
                )
                .props('flat aria-label="Toggle theme"')
                .classes("header-btn")
            )
            with dark_btn:
                ui.tooltip("Toggle theme")
            with ui.button(
                icon="help", on_click=lambda: show_help_dialog()
            ).props('flat aria-label="Help and documentation"').classes(
                "header-btn"
            ):
                ui.tooltip("Help")


async def page_init(
    header_text: Optional[str] = "",
    use_drawer: bool = False,
    title: str = "",
    on_session_end: Optional[Callable[[], None]] = None,
    public: bool = False,
) -> dict | None:
    """
    Initialize the page with a header and background color.

    Returns the signed-in user's data (GET /me), asked once per page load
    and without blocking the event loop -- it used to be asked three or four
    times, synchronously, stalling every connected user each time.  Pages
    gate on it (``(user_data or {}).get("admin")``) rather than asking
    again; it is as fresh as the page itself, exactly as the separate calls
    were.  None when it could not be had, which every gate treats as "no".

    :param on_session_end: called instead of navigating to the logout route
        when the sign-in is refused. For a page where leaving would destroy
        work in progress that is kept somewhere the sign-in does not matter
        -- the recorder, whose audio is on the device -- and which should
        say so rather than be taken away mid-recording.

    :param public: the page is also meant for a browser that is not signed
        in (the cookie information page). Signed in, it gets the page it
        always did. Signed out, it gets the same header and menu but with
        nothing that needs a session: no redirect to "/", no user data, no
        token refresh, no account entries, and a theme button that only
        remembers the choice in this browser.

    :param title: name of this page, appended to the service name and set
        as the document title. Every page shared the single title set in
        ui.run() before this, so a tab strip and a screen reader's page
        announcement could not tell /home, /user and the admin pages
        apart. WCAG 2.4.2 Page Titled (level A).
    """

    # Set before the storage guard below, so a page that redirects does
    # not leave the previous page's title in the tab.
    if title:
        ui.page_title(f"{settings.TAB_TITLE} - {title}")

    anonymous = public and not (
        app.storage.user.get("token") and app.storage.user.get("refresh_token")
    )

    if "_scribe_bk" not in app.storage.browser and not anonymous:
        ui.navigate.to("/")
        return None

    # The one await, and it has to come before anything that starts a timer
    # (the token refresh below).  A timer waits for the browser to connect,
    # and NiceGUI sends the page the moment anything does -- so a timer
    # already running during this await sent the page half-built, and
    # whatever the page added after page_init reached the browser over the
    # socket instead.  A <script> in the head arriving that way is never
    # run: the recorder engine was one ("The recorder did not load").
    user_data = None if anonymous else await get_user_data_async()

    # How many refreshes in a row have failed to reach the provider. A blip,
    # a suspended laptop or a provider restart is not a session that has
    # ended, and treating it as one logs the reader out mid-edit -- which on
    # the editor page takes every unsaved caption with it. See
    # token_refresh_or_wait.
    unreachable = {"count": 0, "ended": False}

    async def refresh():
        if unreachable["ended"]:
            return

        keep = await token_refresh_or_wait(unreachable["count"])

        if keep is True:
            unreachable["count"] = 0
            return

        # Kept, but only because the provider could not be asked: count it,
        # so a provider that stays unreachable does eventually end.
        if keep:
            unreachable["count"] += 1
            return

        app.storage.user["token"] = None
        app.storage.user["refresh_token"] = None
        app.storage.user["encryption_password"] = None

        if on_session_end is not None:
            unreachable["ended"] = True
            on_session_end()
            return

        ui.navigate.to(settings.OIDC_APP_LOGOUT_ROUTE)

    if not anonymous:
        ui.timer(0.1, refresh, once=True)

    # Apply dark mode preference
    ui.add_head_html(default_styles)
    dark_pref = app.storage.user.get("dark_mode", None)
    dark_mode_el = ui.dark_mode(dark_pref)

    # Store resolved dark mode state for components like Plotly
    if dark_pref is not None:
        app.storage.user["_resolved_dark"] = bool(dark_pref)

    is_admin = bool((user_data or {}).get("admin"))
    is_bofh = bool((user_data or {}).get("bofh"))
    if not anonymous:
        ui.timer(30, refresh)

    try:
        client = ui.context.client
        current_path = client.page.path if client and client.page else ""
    except Exception:
        current_path = ""

    if header_text:
        header_text = f" - {header_text}"

    if is_admin:
        header_text += " (Administrator)"

    async def _cycle_dark_mode(btn=None):
        current = app.storage.user.get("dark_mode", None)

        if current is None:
            new_val = True
        elif current:
            new_val = False
        else:
            new_val = None

        app.storage.user["dark_mode"] = new_val
        dark_mode_el.value = new_val
        if not anonymous:
            dark_mode_save(new_val)

        # Resolve the actual dark state (needed for Plotly chart templates)
        if new_val is not None:
            app.storage.user["_resolved_dark"] = bool(new_val)
        else:
            # Auto mode: detect OS preference
            try:
                prefers_dark = await ui.run_javascript(
                    "window.matchMedia('(prefers-color-scheme: dark)').matches",
                    timeout=5.0,
                )
                app.storage.user["_resolved_dark"] = bool(prefers_dark)
            except (TimeoutError, Exception):
                pass
        if btn:
            new_icon = (
                "dark_mode"
                if new_val
                else ("brightness_auto" if new_val is None else "light_mode")
            )
            btn._props["icon"] = new_icon
            btn.update()
        # Reload to update Plotly charts, on the pages that have them and
        # said so via reload_on_theme_change() -- see its docstring. Every
        # other page, /srt included, now skips the reload rather than being
        # named as a one-off exception: it never had anything a reload
        # would redraw, only state a reload would lose (editor captions) or
        # keyboard focus a reload would drop for no reason at all.
        if app.storage.client.get("scribe_theme_reload_needed"):
            # location.reload() always drops focus to the document body, so
            # a second Enter/Space on this same button -- to keep cycling
            # through the three theme states -- lands on nothing and does
            # nothing. Remembered here, in storage that survives the
            # reload, and consumed once the reloaded page has built its own
            # new theme button (see page_init, near _show_announcement_banners).
            app.storage.user["_scribe_restore_theme_focus"] = True
            ui.run_javascript("location.reload()")

    if anonymous:
        _anonymous_header(header_text, _cycle_dark_mode)
    elif use_drawer:
        drawer_open = app.storage.user.get("drawer_open", False)
        drawer = ui.left_drawer(value=True, elevated=True).style(
            "background-color: var(--color-bg-surface-alt); padding: 0;"
        )

        drawer.props(':mini-width="56" :width="250" :breakpoint="0"')

        if not drawer_open:
            drawer.props(add="mini")

        menu_tooltips = []
        menu_btn = None

        def toggle_drawer():
            is_open = app.storage.user.get("drawer_open", False)
            if is_open:
                drawer.props(add="mini")
                for t in menu_tooltips:
                    t.set_visibility(True)
                if menu_btn:
                    menu_btn._props["icon"] = "menu"
                    menu_btn.update()
                if menu_btn_tooltip_ref:
                    menu_btn_tooltip_ref.text = "Expand menu"
                    menu_btn_tooltip_ref.update()
            else:
                drawer.props(remove="mini")
                for t in menu_tooltips:
                    t.set_visibility(False)
                if menu_btn:
                    menu_btn._props["icon"] = "close"
                    menu_btn.update()
                if menu_btn_tooltip_ref:
                    menu_btn_tooltip_ref.text = "Close menu"
                    menu_btn_tooltip_ref.update()
            app.storage.user["drawer_open"] = not is_open

        menu_btn_tooltip_ref = None

        def navigate_closing_menu(path: str) -> None:
            # Only remembered, not drawn: collapsing this page's menu first
            # showed Quasar's mini rail of icons for a moment before the next
            # page, drawn closed, replaced it.
            app.storage.user["drawer_open"] = False
            ui.navigate.to(path)

        # menu_item_style, menu_active_style imported from utils.styles

        def menu_style(path: str) -> str:
            active = current_path == path
            return menu_item_style + (menu_active_style if active else "")

        def menu_link(path: str, icon: str, label: str) -> None:
            """
            A menu entry rendered as a real link.

            Each entry used to be a ui.element("div") with a click handler. Such
            elements are not focusable, have no role and cannot be activated
            from the keyboard, which left the entire main navigation outside the
            tab order (WCAG 2.1.1, 4.1.2). ui.link renders <a href>, which gives
            focusability, role=link, activation with Enter and support for
            open-in-new-tab. Note that Space does not activate links: that is
            correct behaviour for the link role, not a defect.
            """
            link = ui.link(target=path).style(menu_style(path)).classes("menu-item")
            if current_path == path:
                link.props('aria-current=page')
            # On a phone the opened menu is drawn over the page, and it would
            # be drawn open again on the page the link leads to, since whether
            # it is open is remembered per user.  A plain click there closes
            # it first and navigates from the server, so the new page is only
            # asked for once the menu is marked closed.  The width is only
            # known in the browser; 700px is the phone breakpoint the
            # stylesheet and the jobs table use.  A modified or middle click
            # (new tab) is left to the link.
            link.on(
                "click",
                lambda _, path=path: navigate_closing_menu(path),
                js_handler=(
                    "(e) => { if (window.innerWidth < 700 && e.button === 0"
                    " && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey)"
                    " { e.preventDefault(); emit(); } }"
                ),
            )
            with link:
                ui.icon(icon).style("font-size: 20px;").props("aria-hidden=true")
                ui.label(label).classes("menu-label")
                # The tooltip is a visual aid in mini mode, where the label is
                # clipped for the eye but still present for screen readers. It is
                # not the link's accessible name; the label is.
                t = ui.tooltip(label)
                t.set_visibility(not app.storage.user.get("drawer_open", False))
                menu_tooltips.append(t)

        def menu_group(title: Optional[str], items, group_id: str) -> None:
            """
            A group of menu entries as its own labelled nav landmark.

            Separate labelled landmarks (Main menu, Administration, System,
            Account) let a screen reader user jump straight to the right group
            with their landmark command instead of tabbing through every entry.
            The section headings used to be visual ui.label only (WCAG 1.3.1);
            they are now real h2 elements inside their landmark.
            """
            with ui.element("nav").props(
                f'aria-label="{title or "Main menu"}" id={group_id}'
            ).classes("w-full"):
                if title:
                    with ui.element("h2").classes("menu-header").style(
                        "padding: 10px 16px 4px; font-weight: bold;"
                        " font-size: 0.85rem; margin: 0;"
                        " color: var(--color-text-tertiary);"
                    ):
                        ui.label(title)
                with ui.element("ul").style(
                    "list-style: none; margin: 0; padding: 0; width: 100%;"
                ):
                    for path, icon, label in items:
                        with ui.element("li").style("width: 100%;"):
                            menu_link(path, icon, label)

        # Menu items: (path, icon, label)
        menu_items = [
            ("/home", "folder", "My files"),
            ("/record", "mic", "Recorder"),
            ("/user", "person", "User settings"),
        ]

        admin_items = [
            ("/admin/users", "people", "Users"),
            ("/admin", "group_work", "Groups"),
            ("/admin/rules", "rule", "User provisioning"),
            ("/admin/customers", "business", "Customers" if is_bofh else "Account"),
        ]

        system_items = [
            ("/health", "health_and_safety", "System status"),
            ("/admin/analytics", "analytics", "Activity overview"),
            ("/admin/announcements", "campaign", "Announcements"),
        ]

        with drawer:
            with ui.column().classes("w-full").style("gap: 0;"):
                ui.separator()

                menu_group(None, menu_items, "nav-main")

                if is_admin:
                    ui.separator().classes("menu-separator")
                    menu_group("Administration", admin_items, "nav-administration")

                    # The API documentation opens in a new tab. A real link with
                    # new_tab=True instead of a div calling window.open(): gives
                    # focusability, a role, and lets the user decide how to open it.
                    with ui.element("nav").props('aria-label="Documentation"').classes("w-full"):
                        with ui.element("ul").style(
                            "list-style: none; margin: 0; padding: 0; width: 100%;"
                        ):
                            with ui.element("li").style("width: 100%;"):
                                with ui.link(
                                    target=f"{settings.API_URL}/api/docs", new_tab=True
                                ).style(menu_item_style).classes("menu-item"):
                                    ui.icon("description").style(
                                        "font-size: 20px;"
                                    ).props("aria-hidden=true")
                                    ui.label("API documentation").classes("menu-label")
                                    # Tell the user the link opens in a new tab
                                    # (WCAG 2.4.4 / good practice 3.2.5)
                                    with ui.element("span").classes("sr-only"):
                                        ui.label(" (opens in a new tab)")
                                    t = ui.tooltip("API documentation")
                                    t.set_visibility(
                                        not app.storage.user.get("drawer_open", False)
                                    )
                                    menu_tooltips.append(t)

                if is_bofh:
                    ui.separator().classes("menu-separator")
                    menu_group("System", system_items, "nav-system")

                ui.separator()

                menu_group("Account", [("/logout", "logout", "Logout")], "nav-account")

        with (
            ui.header()
            .style(
                "justify-content: space-between; background-color: var(--color-header-bg); min-height: 50px; padding: 4px 16px;"
                ""
            )
            .classes("drop-shadow-md")
        ):
            with ui.element("div").style(
                "display: flex; gap: 0px; align-items: center; margin-left: -12px;"
            ).classes("header-brand"):
                # Skip to content. The first focusable element on the page.
                # Without it the main menu entries would precede the page content
                # in the tab order on every page load (WCAG 2.4.1).
                ui.link("Skip to content", "#main-content").classes("skip-link")

                with ui.button(
                    icon="close" if drawer_open else "menu",
                    on_click=lambda: toggle_drawer(),
                ).props("flat").classes("header-btn") as menu_btn:
                    # A tooltip does NOT provide an accessible name in Quasar: it
                    # becomes a child element. The name must be set with aria-label.
                    # aria-expanded mirrors the drawer state (disclosure pattern).
                    menu_btn.props(
                        'aria-label="Main menu" aria-controls=nav-main '
                        f'aria-expanded={"true" if drawer_open else "false"}'
                    )
                    menu_btn_tooltip = ui.tooltip(
                        "Close menu" if drawer_open else "Expand menu"
                    )
                    menu_btn_tooltip_ref = menu_btn_tooltip
                # Decorative, on both this header and the drawer-less one
                # below: the service name sits right next to the logo as
                # real text (settings.TOPBAR_TEXT), so the logo carries no
                # information a screen reader user would otherwise lose.
                # Only one of the pair is ever visible -- CSS swaps them by
                # theme -- but both get alt="" rather than relying on that.
                # aria-hidden is needed too: NiceGUI wraps the real <img>
                # in its own div carrying role="img", and an empty alt on
                # the inner element does not by itself mark the outer one
                # decorative -- axe's role-img-alt rule still flagged the
                # wrapper as an unnamed image without it.
                ui.image(f"static/{settings.LOGO_TOPBAR_LIGHT}").props(
                    'alt="" aria-hidden="true"'
                ).classes("q-mr-sm logo-light").style(
                    "height: 30px; width: 30px;"
                )
                ui.image(f"static/{settings.LOGO_TOPBAR_DARK}").props(
                    'alt="" aria-hidden="true"'
                ).classes("q-mr-sm logo-dark").style(
                    "height: 30px; width: 30px;"
                )
                ui.label(settings.TOPBAR_TEXT + header_text).classes(
                    "text-h6 text-theme-primary topbar-text"
                )

            with ui.element("div").style("display: flex; gap: 0px;").classes(
                "header-actions"
            ):
                dark_val = app.storage.user.get("dark_mode", None)
                dark_icon = (
                    "dark_mode"
                    if dark_val
                    else ("brightness_auto" if dark_val is None else "light_mode")
                )
                dark_btn = (
                    ui.button(
                        icon=dark_icon,
                        on_click=lambda: _cycle_dark_mode(dark_btn),
                    )
                    # Icon-only buttons take their name from the icon ligature
                    # ("brightness_auto"), which is aria-hidden, leaving the button
                    # nameless. aria-label is required; a tooltip is not enough.
                    .props('flat aria-label="Toggle theme"')
                    .classes("header-btn")
                )
                with dark_btn:
                    ui.tooltip("Toggle theme")
                with ui.button(
                    icon="help",
                    on_click=lambda: show_help_dialog(),
                ).props(
                    'flat aria-label="Help and documentation"'
                ).classes("header-btn"):
                    ui.tooltip("Help")

            # body background and .nicegui-content padding are in theme_styles
    else:
        with (
            ui.header()
            .style(
                "justify-content: space-between; background-color: var(--color-header-bg); min-height: 50px; padding: 4px 16px;"
                ""
            )
            .classes("drop-shadow-md")
        ):
            with ui.element("div").style("display: flex; gap: 0px;"):
                ui.image(f"static/{settings.LOGO_TOPBAR_LIGHT}").props(
                    'alt="" aria-hidden="true"'
                ).classes("q-mr-sm logo-light").style(
                    "height: 30px; width: 30px;"
                )
                ui.image(f"static/{settings.LOGO_TOPBAR_DARK}").props(
                    'alt="" aria-hidden="true"'
                ).classes("q-mr-sm logo-dark").style(
                    "height: 30px; width: 30px;"
                )
                ui.label(settings.TOPBAR_TEXT + header_text).classes(
                    "text-h6 text-theme-primary topbar-text"
                )

            with ui.element("div").style("display: flex; gap: 0px;"):
                if is_admin:
                    with ui.button(
                        icon="settings",
                        on_click=lambda: ui.navigate.to("/admin"),
                    ).props("flat color=red aria-label='Admin settings'"):
                        ui.tooltip("Admin settings")

                if is_bofh:
                    with ui.button(
                        icon="health_and_safety",
                        on_click=lambda: ui.navigate.to("/health"),
                    ).props("flat color=red aria-label='System status'"):
                        ui.tooltip("System status")
                    with ui.button(
                        icon="analytics",
                        on_click=lambda: ui.navigate.to("/admin/analytics"),
                    ).props("flat color=red aria-label='Page view statistics'"):
                        ui.tooltip("Page view statistics")
                with ui.button(
                    icon="home",
                    on_click=lambda: ui.navigate.to("/home"),
                ).props("flat aria-label='Home'").classes("header-btn"):
                    ui.tooltip("Home")
                with ui.button(
                    icon="person",
                    on_click=lambda: ui.navigate.to("/user"),
                ).props("flat aria-label='User settings'").classes("header-btn"):
                    ui.tooltip("User settings")
                dark_val2 = app.storage.user.get("dark_mode", None)
                dark_icon2 = (
                    "dark_mode"
                    if dark_val2
                    else ("brightness_auto" if dark_val2 is None else "light_mode")
                )
                dark_btn2 = (
                    ui.button(
                        icon=dark_icon2,
                        on_click=lambda: _cycle_dark_mode(dark_btn2),
                    )
                    .props("flat aria-label='Toggle theme'")
                    .classes("header-btn")
                )
                with dark_btn2:
                    ui.tooltip("Toggle theme")
                with ui.button(
                    icon="help",
                    on_click=lambda: show_help_dialog(),
                ).props(
                    "flat aria-label='Help and documentation'"
                ).classes("header-btn"):
                    ui.tooltip("Help")
                with ui.button(
                    icon="logout",
                    on_click=lambda: ui.navigate.to("/logout"),
                ).props("flat aria-label='Log out'").classes("header-btn"):
                    ui.tooltip("Logout")

    # Target for the skip link, and the first element in the page content.
    #
    # NiceGUI already gives <main class="q-page"> an id of its own (c2, c7, ...)
    # and uses it to address the element when patching the DOM, so that id must
    # not be overwritten. A dedicated element is used instead. tabindex=-1
    # lets it receive focus from the fragment jump without being a tab stop of
    # its own; the next Tab continues from here into the page content.
    #
    # It is placed before the announcement banners on purpose, so that skipping
    # the navigation does not also skip a service message.
    #
    # aria-label was added after review feedback pointed out that landing on
    # an empty, unlabelled element reads as an "unexplained empty box" once
    # focus is visible. It now carries the page name, so arriving here reads
    # as something rather than silence. The visible box the same feedback
    # flagged is fixed on the CSS side too: the global focus ring in
    # styles.py now excludes tabindex="-1" from its selector, so our own ring
    # never draws here. outline: none below is needed in addition to that --
    # measured after the styles.py fix, the browser's own default focus
    # outline still showed on arrival (outline: auto), since excluding this
    # element from our rule only stops our ring, not the browser's.
    ui.element("div").props(
        f'id=main-content tabindex=-1 aria-label="Main content{header_text}"'
    ).style(
        "position: absolute; width: 0; height: 0; overflow: hidden;"
        " outline: none;"
    )

    # Consumed once, whether or not this page ended up with a theme
    # button at all: a page that reaches here without one (use_drawer
    # branches always create one today, but nothing guarantees that stays
    # true) must not leave the flag set for whatever page loads next.
    if app.storage.user.pop("_scribe_restore_theme_focus", False):
        ui.add_head_html(
            """
            <script>
            (function () {
                function focusThemeButton() {
                    var btn = document.querySelector('[aria-label="Toggle theme"]');
                    if (btn) { btn.focus(); return true; }
                    return false;
                }
                if (!focusThemeButton()) {
                    var tries = setInterval(function () {
                        if (focusThemeButton()) clearInterval(tries);
                    }, 50);
                    setTimeout(function () { clearInterval(tries); }, 3000);
                }
            })();
            </script>
            """
        )

    # Above the announcements, below the header.
    if not anonymous:
        render_cookie_notice_row(in_page=True)

    _show_announcement_banners(user_data)

    return user_data


def add_timezone_to_timestamp(timestamp: str) -> str:
    """
    Convert a UTC timestamp to the user's local timezone.
    """
    user_timezone = app.storage.user.get("timezone", "UTC")
    utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
    utc_time = pytz.utc.localize(utc_time)
    local_tz = pytz.timezone(user_timezone)
    local_time = utc_time.astimezone(local_tz)

    return local_time.strftime("%Y-%m-%d %H:%M")


async def jobs_get() -> list | None:
    """
    Get the list of transcription jobs from the API.
    """
    jobs = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                "GET",
                f"{settings.API_URL}/api/v1/transcriber",
                headers=get_auth_header(),
                json={
                    "encryption_password": storage_decrypt(
                        app.storage.user.get("encryption_password"),
                    )
                },
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    # Get current time in user's timezone
    user_timezone = app.storage.user.get("timezone", "UTC")
    local_tz = pytz.timezone(user_timezone)
    current_time = datetime.now(local_tz)

    for idx, job in enumerate(response.json()["result"]["jobs"]):
        if job["status"] == "in_progress":
            job["status"] = "transcribing"

        deletion_date = add_timezone_to_timestamp(job["deletion_date"])
        created_at = add_timezone_to_timestamp(job["created_at"])
        updated_at = add_timezone_to_timestamp(job["updated_at"])

        # Check if deletion is approaching (within 24 hours)
        deletion_approaching = False
        if deletion_date:
            try:
                deletion_dt = datetime.strptime(deletion_date, "%Y-%m-%d %H:%M")
                deletion_dt = local_tz.localize(deletion_dt)
                time_until_deletion = deletion_dt - current_time
                # Default threshold: 24 hours
                deletion_approaching = time_until_deletion <= timedelta(hours=24)
            except (ValueError, AttributeError):
                pass

            deletion_date_display = deletion_date.split(" ")[0]
        else:
            deletion_date_display = "N/A"

        if job["status"] != "completed":
            job_type = ""
        elif job["output_format"] == "txt":
            job_type = "Transcript"
        elif job["output_format"] == "srt":
            job_type = "Subtitles"
        else:
            job_type = "Transcript"

        job_data = {
            "id": idx,
            "uuid": job["uuid"],
            "filename": job["filename"],
            "created_at": created_at,
            "updated_at": updated_at,
            "deletion_date": deletion_date_display,
            "deletion_approaching": deletion_approaching,
            "language": job["language"].capitalize(),
            "status": job["status"].capitalize(),
            "model_type": job["model_type"].capitalize(),
            "output_format": job["output_format"].upper(),
            "job_type": job_type,
            # Made by the recorder: the backend keeps its original, which
            # My files marks and offers for download.
            "is_recording": bool(job.get("has_original")),
        }

        jobs.append(job_data)

    # Sort jobs by created_at in descending order
    jobs.sort(key=lambda x: x["created_at"], reverse=True)

    return jobs


async def job_has_original(uuid: str) -> bool:
    """
    Whether the backend kept an original for this job, i.e. whether it was
    made in the recorder.  False whenever it cannot be asked: the editor
    then simply does not offer the original.
    """

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.API_URL}/api/v1/transcriber",
                params={"job_id": uuid},
                headers=get_auth_header(),
            )
            response.raise_for_status()
            return bool((response.json().get("result") or {}).get("has_original"))
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


def open_result(event, page: str) -> None:
    """
    Open a completed job on one of the two pages that can show it.

    The editor and the read-only view take the same job in the same query
    and differ in nothing else, so which of them a row opens is the
    caller's decision -- the phone's card asks for the view, the desktop
    table for the editor -- rather than something worked out again here
    from the width of the screen.
    """

    status = event.args["status"].lower()
    uuid = event.args["uuid"]
    filename = event.args["filename"]
    model_type = event.args["model_type"]
    language = event.args["language"]
    output_format = event.args.get("output_format")

    if status != "completed":
        return

    data_format = "txt" if output_format == "TXT" else "srt"

    ui.navigate.to(
        f"{page}?uuid={uuid}&filename={filename}&model={model_type}"
        f"&language={language}&data_format={data_format}"
    )


def table_click(event) -> None:
    """
    Handle the click event on the table rows.
    """

    open_result(event, "/srt")


def table_view(event) -> None:
    """
    Open a completed job read-only, which is what a phone offers.
    """

    open_result(event, "/view")


async def post_file(
    file_upload,
    filename: str,
    on_progress: callable = None,
) -> bool:
    """
    Post a file to the API with optional progress callback.

    Parameters:
        file_upload: A NiceGUI FileUpload (held in memory up to spool_max_size,
            4 GB -- the most one upload can be, see UPLOAD_MAX_TOTAL_BYTES).
        filename: The filename.
        on_progress: Optional callback(percent: int) called during upload.
    """
    total_size = file_upload.size()

    class ProgressReader:
        """Read bytes with progress tracking; releases buffer ref after consumption."""

        def __init__(self, src):
            self._src = src
            self._pos = 0
            self._bytes_sent = 0

        def read(self, size: int = -1) -> bytes:
            buf = self._src
            if buf is None:
                return b""

            if size is None or size < 0:
                chunk = buf[self._pos :]
                self._pos = len(buf)
            else:
                end = min(self._pos + size, len(buf))
                chunk = buf[self._pos : end]
                self._pos = end

            self._bytes_sent += len(chunk)

            if on_progress and total_size > 0:
                on_progress(min(int(self._bytes_sent * 100 / total_size), 100))

            if self._pos >= len(buf):
                self._src = None

            return chunk

    reader = ProgressReader(await file_upload.read())
    files_json = {"file": (filename, reader)}

    try:
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(
                f"{settings.API_URL}/api/v1/transcriber",
                files=files_json,
                headers=get_auth_header(),
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"Upload failed, status code: {response.status_code}",
                    request=response.request,
                    response=response,
                )
    except httpx.HTTPStatusError as e:
        ui.notify(
            f"Error when uploading file: {str(e)}",
            type="negative",
            position="top",
            timeout=None,
            close_button="Close",
        )
        return False
    finally:
        reader._src = None

    return True


def format_size(bytes_val) -> str:
    """
    Format bytes into a human-readable string.
    """
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.1f} GB"


def toggle_upload_status(upload_column, status_column, dialog, abort_button=None):
    # Hiding upload_column also hides the Cancel button, which lives inside it,
    # and dialog.props("persistent") disables Esc and backdrop dismissal at the
    # same moment. Together that left a modal with no focusable element and no
    # way out for the duration of the upload - up to 4 GB in all, per the dialog's own
    # text. That is a keyboard trap, WCAG 2.1.2 (level A).
    #
    # persistent is kept on purpose: a stray backdrop click should not abandon a
    # large upload. The way out is an explicit, focusable Cancel button that
    # status_column now carries.
    upload_column.visible = False
    status_column.visible = True
    dialog.props("persistent")

    # The element that had focus is being hidden underneath the user, which
    # drops focus to the document body: the keyboard user is left with nothing
    # selected and no indication that the dialog changed. Move focus to the one
    # control that is now visible. WCAG 2.4.3.
    if abort_button is not None:
        ui.run_javascript(
            f"const b = getElement({abort_button.id});"
            "const el = b && (b.$el || b);"
            "if (el && el.focus) el.focus();"
        )


# What the upload dialog accepts, and so what it says it accepts: the
# picker's `accept` and the list printed under the drop zone both come from
# here. .aif and .mpeg are the same formats as .aiff and .mpg, so they are
# accepted without being listed twice.
UPLOAD_EXTENSIONS = (
    ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".wma", ".aiff", ".aif",
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpg", ".mpeg",
)
UPLOAD_FORMATS_SHOWN = ", ".join(
    ext[1:].upper() for ext in UPLOAD_EXTENSIONS if ext not in (".aif", ".mpeg")
)
UPLOAD_MAX_FILES = 5
# The selected files are sent in one request (ui.upload's `batch`, which
# on_multi_upload turns on), so the proxy's body limit -- nginx
# client_max_body_size 4g in production -- caps them *together*, not each.
# Checked in the dialog too, so a selection that is too big is refused with
# a reason before it is sent rather than failing against the proxy. The
# megabyte of headroom is for the multipart framing nginx counts as well.
UPLOAD_MAX_TOTAL_BYTES = 4 * 1024**3 - 1024**2


def focus_element(element) -> None:
    """
    Move the browser's focus onto the given NiceGUI element.

    A click (or a Quasar-internal keyboard activation) on a switch,
    toggle or button can leave the DOM's real focus on a small
    presentational wrapper around the control -- SPAN.no-outline after
    a switch, SPAN.q-focus-helper after a button -- rather than on the
    control itself. That wrapper, unlike the control, does not consume
    a later Space keypress (no stopPropagation), so the keystroke
    falls through to the browser's own default action, such as toggling
    video playback via its native Space shortcut (see F-74). Re-focusing
    the control right after it is activated, or moving focus into a
    dialog right after it opens, closes that gap. Same idea as
    toggle_upload_status above, generalised for reuse.
    """
    # Retried for a moment: an element in a dialog that has only just been
    # opened is not in the page yet (Quasar mounts and shows it a frame or
    # two later), and a single attempt right away finds nothing to focus.
    ui.run_javascript(
        "(function () {"
        " let tries = 0;"
        " const timer = setInterval(function () {"
        f"  const b = getElement({element.id});"
        "  const el = b && (b.$el || b);"
        "  if (el && el.focus && el.offsetParent !== null) {"
        "   el.focus();"
        "   if (el === document.activeElement || el.contains(document.activeElement)) {"
        "    clearInterval(timer); return;"
        "   }"
        "  }"
        "  if (++tries > 20) clearInterval(timer);"
        " }, 50);"
        "})();"
    )


def table_upload(table) -> None:
    """
    Handle the click event on the Upload button with improved UX.

    Design A of the four drawn for it: a titled dialog, a drop zone that
    says what to drop and shows how to choose instead, and the limits and
    formats spelled out under it rather than left to be discovered.
    """

    ui.add_head_html(default_styles)

    with ui.dialog().props('aria-label="Upload files"') as dialog:
        # 400px is wider than a phone. It stays the width this wants to be
        # wherever there is room for it, and gives way where there is not.
        with ui.card().style(
            "width: 100%; max-width: 560px; min-width: min(400px, 100%);"
            " padding: 28px 32px;"
        ):
            with ui.column().classes("w-full items-center") as status_column:
                ui.label("Uploading files").classes("text-h6 q-mb-sm")
                # role=status so the byte counter is announced as it changes
                # instead of updating silently. WCAG 4.1.3.
                status_label = (
                    ui.label("Please wait...")
                    .classes("text-body1 q-mb-lg text-theme-muted")
                    .props('role=status aria-live=polite')
                )
                # The spinner is decorative; the text above carries the state.
                ui.spinner(size="50px").props("aria-hidden=true")
                # The keyboard way out of the upload. See toggle_upload_status.
                abort_button = ui.button("Cancel upload", icon="cancel").props(
                    'color=black flat aria-label="Cancel upload"'
                )
                abort_button.classes("cancel-style")
                status_column.visible = False

            with ui.column().classes("w-full gap-4") as upload_column:
                ui.label("Upload files").classes("text-h6")
                upload = (
                    ui.upload(
                        # The label is rendered into the uploader header, which
                        # sits inside the opacity:0 wrapper below. The literal
                        # string "hidden" was therefore exposed to screen
                        # readers as the uploader's text.
                        label="",
                        on_multi_upload=lambda e: handle_upload_with_feedback(
                            e, dialog, table
                        ),
                        auto_upload=True,
                        multiple=True,
                        max_files=UPLOAD_MAX_FILES,
                        max_total_size=UPLOAD_MAX_TOTAL_BYTES,
                        on_rejected=lambda: ui.notify(
                            f"Those files were not uploaded: at most "
                            f"{UPLOAD_MAX_FILES} files, 4 GB in total.",
                            type="warning",
                            position="top",
                            timeout=None,
                            close_button="Close",
                        ),
                    )
                    .props(f"accept={','.join(UPLOAD_EXTENSIONS)}")
                    .style(
                        "position: absolute; width: 0; height: 0; overflow: hidden; opacity: 0"
                    )
                )

                upload.on(
                    "start",
                    lambda _: toggle_upload_status(
                        upload_column, status_column, dialog, abort_button
                    ),
                )

                def _cleanup_dialog():
                    ui.run_javascript(
                        f"const upl = getElement({upload.id});"
                        f"if (upl && upl._cleanup) upl._cleanup();"
                    )
                    try:
                        upload.reset()
                    except Exception:
                        pass
                    dialog.close()
                    dialog.delete()

                upload.on("finish", lambda _: _cleanup_dialog())
                # _cleanup_dialog clears the progress interval, resets the
                # uploader and closes the dialog, so it is a real abort.
                abort_button.on_click(lambda: _cleanup_dialog())

                def on_byte_progress(e):
                    uploaded = e.args.get("uploaded", 0)
                    total = e.args.get("total", 0)
                    if total > 0:
                        status_label.set_text(
                            f"{format_size(uploaded)} / {format_size(total)}"
                        )

                upload.on("byte_progress", on_byte_progress)

                # The dropzone is the only thing that looks clickable, and the
                # instruction text points at it, but it used to be a plain div
                # with its click handler bound in JavaScript: not focusable, no
                # role, no accessible name. The file picker was reachable only
                # through a 34x34 anchor inside the opacity:0 uploader below,
                # which is invisible - focus went somewhere the user cannot see.
                #
                # role=button plus tabindex=0 makes the visible affordance the
                # focusable control, and the keydown handler further down gives
                # it Enter and Space. WCAG 2.1.1, 4.1.2 (level A).
                #
                # "Choose files" inside it is drawn as a button but is not
                # one: the whole zone already is, and a button inside a
                # button is not allowed. It is there to show the way in for
                # anyone who does not drag. Static markup, nothing from a user.
                dropzone = ui.html(
                    """
                    <div class="dropzone-area upload-dropzone"
                         role="button" tabindex="0"
                         aria-label="Choose audio or video files to upload, or drop them here">
                        <svg width="44" height="44" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" stroke-width="1.6"
                             aria-hidden="true">
                            <path d="M12 16V4M7 9l5-5 5 5"/>
                            <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>
                        </svg>
                        <span class="upload-dropzone-title">Drag audio or video files here</span>
                        <span class="upload-dropzone-or">or</span>
                        <span class="upload-dropzone-choose" aria-hidden="true">Choose files</span>
                    </div>
                    """,
                    sanitize=False,
                ).classes("w-full")

                with ui.column().classes("gap-1 upload-limits"):
                    ui.label(
                        f"Up to {UPLOAD_MAX_FILES} files at a time, 4 GB in total."
                    )
                    ui.label(UPLOAD_FORMATS_SHOWN)

                upload_id = upload.id
                dropzone_id = dropzone.id
                ui.timer(
                    0.1,
                    lambda: ui.run_javascript(
                        "const dz = getHtmlElement(" + str(dropzone_id) + ");"
                        "const upl = getElement(" + str(upload_id) + ");"
                        "if (!dz || !upl) return;"
                        "dz.addEventListener('click', () => upl.$refs.qRef.pickFiles());"
                        # Enter and Space activate the dropzone, the way any
                        # role=button must. preventDefault stops Space from
                        # scrolling the page instead.
                        "dz.addEventListener('keydown', e => {"
                        "  if (e.key === 'Enter' || e.key === ' ' || e.code === 'Space') {"
                        "    e.preventDefault();"
                        "    upl.$refs.qRef.pickFiles();"
                        "  }"
                        "});"
                        "dz.addEventListener('dragover', e => {"
                        "  e.preventDefault();"
                        "  dz.querySelector('div').classList.add('dropzone-drag');"
                        "});"
                        "dz.addEventListener('dragleave', () => {"
                        "  dz.querySelector('div').classList.remove('dropzone-drag');"
                        "});"
                        "dz.addEventListener('drop', e => {"
                        "  e.preventDefault();"
                        "  dz.querySelector('div').classList.remove('dropzone-drag');"
                        "  upl.$refs.qRef.addFiles(Array.from(e.dataTransfer.files));"
                        "});"
                        "const progressInterval = setInterval(() => {"
                        "  const qRef = upl.$refs.qRef;"
                        "  if (!qRef || !qRef.files || qRef.files.length === 0) return;"
                        "  let totalSize = 0, uploaded = 0, currentFile = '';"
                        "  qRef.files.forEach(f => {"
                        "    totalSize += f.size || 0;"
                        "    uploaded += f.__uploaded || 0;"
                        "    if (f.__status === 'uploading') currentFile = f.name;"
                        "  });"
                        "  if (currentFile) {"
                        "    getElement("
                        + str(upload_id)
                        + ").$emit('byte_progress', {"
                        "      uploaded: uploaded, total: totalSize, current_file: currentFile"
                        "    });"
                        "  }"
                        "}, 500);"
                        "upl._cleanup = () => {"
                        "  clearInterval(progressInterval);"
                        "  const qRef = upl.$refs.qRef;"
                        "  if (qRef) { try { qRef.reset(); } catch (e) {} }"
                        "};"
                        # The uploader is hidden with opacity: 0, but its own
                        # pick-files anchor stayed in the tab order - an
                        # invisible focus stop on the primary upload path
                        # (finding F-49). Take its focusable descendants out of
                        # the tab order; the dropzone above is the control now.
                        #
                        # getElement() returns the Vue component, not a DOM
                        # node, so the element has to be reached through $el.
                        # This runs last and is guarded: if it ever fails it
                        # must not take the drag-and-drop listeners or the
                        # progress interval above down with it.
                        "try {"
                        "  const uplEl = upl.$el ||"
                        "    (upl.$refs && upl.$refs.qRef && upl.$refs.qRef.$el);"
                        "  if (uplEl && uplEl.querySelectorAll) {"
                        "    uplEl.querySelectorAll('a, button, input, [tabindex]')"
                        "      .forEach(el => el.setAttribute('tabindex', '-1'));"
                        "  }"
                        "} catch (e) {}"
                    ),
                    once=True,
                )
                with ui.row().classes("w-full").style(
                    "justify-content: flex-end; gap: 12px;"
                ):
                    with ui.button(
                        "Cancel",
                        on_click=lambda: _cleanup_dialog(),
                    ) as cancel:
                        cancel.props("color=black flat")
                        cancel.classes("cancel-style")

        dialog.open()


async def handle_upload_with_feedback(files, dialog, table):
    """
    Handle file uploads with user feedback and validation.
    """

    client = ui.context.client

    dialog.close()

    file_items = []
    for file in files.files:
        file_name = sanitize_filename(file.name)
        file_items.append((file_name, file))
    files.files.clear()

    # Add temporary "Uploading" rows to the table
    existing_rows = list(table.rows or [])
    upload_row_ids = []
    for i, (file_name, _) in enumerate(file_items):
        row_id = f"_uploading_{i}"
        upload_row_ids.append(row_id)
        existing_rows.insert(
            0,
            {
                "id": row_id,
                "filename": file_name,
                "job_type": "",
                "created_at": "",
                "updated_at": "",
                "deletion_date": "",
                "deletion_approaching": False,
                "status": "Processing (0%)",
            },
        )
    table.update_rows(existing_rows, clear_selection=True)

    async def _swap_in_real_rows(pending_row_ids: list) -> None:
        """
        Replace the finished placeholder rows with the backend's own.

        The placeholders of files not uploaded yet are kept, ids and all, so
        their progress goes on being written to them.  Placeholder ids are
        strings (`_uploading_0`) and the backend's are ints, so the two can
        never collide.
        """

        if client._deleted:
            return

        fresh_rows = await jobs_get()
        if fresh_rows is None or client._deleted:
            return

        pending = [row for row in table.rows if row["id"] in pending_row_ids]
        table.update_rows(pending + fresh_rows, clear_selection=False)

    # Upload to backend in a background task so the UI stays responsive
    async def _upload():
        for idx in range(len(file_items)):
            file_name, file_upload = file_items[idx]
            row_id = upload_row_ids[idx]

            def update_progress(percent, _row_id=row_id):
                if not client._deleted:
                    for row in table.rows:
                        if row["id"] == _row_id:
                            row["status"] = f"Processing ({percent}%)"
                            break
                    table.update()

            try:
                # post_file reports a refusal by returning False (having
                # already said why), not by raising -- a refused upload was
                # otherwise marked "Uploaded" and announced as a success.
                if not await post_file(
                    file_upload, file_name, on_progress=update_progress
                ):
                    raise RuntimeError("the server refused the file")

                if not client._deleted:
                    for row in table.rows:
                        if row["id"] == row_id:
                            row["status"] = "Uploaded"
                            break
                    table.update()
                    with table:
                        ui.notify(
                            f"Successfully uploaded {file_name}",
                            type="positive",
                            timeout=3000,
                        )
                    # Swap this file's placeholder for the row the backend
                    # now holds, rather than waiting for the whole batch.
                    # The placeholder carries no uuid, and the status it
                    # has just been given is exactly what draws the
                    # Transcribe button and what bulk transcribe selects
                    # on -- so between here and the end of the batch a
                    # reader could start a transcription of a row with
                    # nothing to start (KeyError: 'uuid').
                    await _swap_in_real_rows(upload_row_ids[idx + 1 :])
            except Exception as e:
                if not client._deleted:
                    for row in table.rows:
                        if row["id"] == row_id:
                            row["status"] = "Processing failed"
                            break
                    table.update()
                    with table:
                        ui.notify(
                            f"Error uploading {file_name}: {str(e)}",
                            type="negative",
                            timeout=None,
                            close_button="Close")
            finally:
                if hasattr(file_upload, "_data"):
                    file_upload._data = b""
                file_items[idx] = (file_name, None)
                file_upload = None

        # Refresh with real data from backend.  Nothing is pending by here,
        # so every placeholder left (a failed upload) goes with it.
        await _swap_in_real_rows([])

    # Not asyncio.create_task: the loop keeps only a weak reference, so an
    # upload could be collected part way through and its errors would never
    # surface. NiceGUI holds onto the task and reports what it raises.
    background_tasks.create(_upload(), name=f"upload of {len(file_items)} file(s)")


def table_transcribe(selected_row, on_complete=None) -> None:
    """
    Handle the click event on the Transcribe button.
    """
    with ui.dialog().props('aria-label="Transcription settings"') as dialog:
        with (
            ui.card()
            .style(
                "background-color: var(--color-bg-surface); align-self: center;"
                " border: 0; width: 80%; min-width: min(320px, 100%);"
            )
            .classes("w-full no-shadow no-border")
        ):
            with ui.row().classes("w-full"):
                ui.label("Transcription settings").style("width: 100%;").classes(
                    "text-h6 q-mb-xl"
                )

                # Hidden until start_transcription has something to report;
                # role=alert means a screen reader hears it the moment
                # set_text/set_visibility make it appear, without moving
                # focus or rebuilding the dialog around it. See that
                # function's own comment for what this replaced.
                error_display = (
                    ui.label("")
                    .classes("text-h6 q-mb-md w-full")
                    .style("color: var(--color-text-danger);")
                )
                error_display.props("role=alert")
                error_display.set_visibility(False)

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Filename:").classes("text-subtitle2 q-mb-sm")
                    ui.label(f"{selected_row['filename']}")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        value=settings.WHISPER_LANGUAGES[0],
                    ).classes("w-full")

                with ui.column().classes("col-12 col-sm-24") as verbatim_container:
                    verbatim = ui.checkbox(
                        "Verbatim (include filler words, repetitions and unfinished sentences)"
                    ).classes("q-mt-sm")
                    verbatim_container.set_visibility(
                        language.value.lower() == "swedish"
                    )
                    # Untick as well as hide: set_visibility leaves the
                    # value alone, so a box ticked under Swedish survived
                    # unseen behind a language with no verbatim model and
                    # the dialog sent "<language> (verbatim)" -- a key the
                    # worker cannot look up, which kills its job thread
                    # (seen in production as KeyError: 'Ukrainian
                    # (verbatim)').
                    language.on_value_change(
                        lambda e: (
                            verbatim.set_value(False),
                            verbatim_container.set_visibility(
                                e.value.lower() == "swedish"
                                or e.value.lower() == "norwegian"
                            ),
                        )
                    )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers, automatic if not chosen").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0", min=0).classes("w-full")

            with ui.row().classes("justify-between w-full"):
                ui.label("Output format").classes("text-subtitle2 q-mb-sm")
                output_format = (
                    ui.radio(
                        ["Transcript", "Subtitles"],
                        value="Transcript",
                    )
                    .classes("w-full")
                    .props("inline")
                )

            with ui.row().classes("justify-between w-full"):
                with ui.button(
                    "Cancel",
                    icon="cancel",
                ) as cancel:
                    cancel.on("click", lambda: dialog.close())
                    cancel.props("color=black flat")
                    cancel.classes("cancel-style")

                with ui.button(
                    "Start transcribing",
                    on_click=lambda: start_transcription(
                        [selected_row],
                        f"{language.value} (verbatim)"
                        if verbatim.value
                        else language.value,
                        speakers.value,
                        output_format.value,
                        dialog,
                        on_complete=on_complete,
                        error_display=error_display,
                    ),
                ) as start:
                    start.props("color=black flat")
                    start.classes("default-style")

            dialog.open()


def table_bulk_transcribe(table: ui.table, on_complete=None) -> None:
    """
    Handle bulk transcription of selected uploaded jobs.
    Shows the same transcription settings dialog but applies to all selected rows.
    """
    selected = table.selected
    uploadable = [r for r in selected if r.get("status") == "Uploaded"]
    already_done = [r for r in selected if r.get("status") == "Completed"]
    if not uploadable:
        ui.notify("No uploaded files selected", type="warning", position="top", timeout=None, close_button="Close")
        return

    with ui.dialog().props('aria-label="Bulk transcription settings"') as dialog:
        with (
            ui.card()
            .style(
                "background-color: var(--color-bg-surface); align-self: center;"
                " border: 0; width: 80%; min-width: min(320px, 100%);"
            )
            .classes("w-full no-shadow no-border")
        ):
            with ui.row().classes("w-full"):
                ui.label("Transcription settings").style("width: 100%;").classes(
                    "text-h6 q-mb-xl"
                )

                # See table_transcribe's own copy of this element for why.
                error_display = (
                    ui.label("")
                    .classes("text-h6 q-mb-md w-full")
                    .style("color: var(--color-text-danger);")
                )
                error_display.props("role=alert")
                error_display.set_visibility(False)

                with ui.column().classes("w-full q-mb-sm").style(
                    "background-color: var(--color-severity-maint-bg); padding: 8px 12px; border-radius: 4px;"
                ):
                    with ui.row().classes("items-center"):
                        ui.icon("rtt").classes("text-body1")
                        ui.label(
                            f"{len(uploadable)} file(s) will be transcribed."
                        ).classes("text-body2")
                    if already_done:
                        with ui.row().classes("items-center"):
                            ui.icon("block").classes("text-body1")
                            ui.label(
                                f"{len(already_done)} completed file(s) will be skipped."
                            ).classes("text-body2")

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Language").classes("text-subtitle2 q-mb-sm")
                    language = ui.select(
                        settings.WHISPER_LANGUAGES,
                        value=settings.WHISPER_LANGUAGES[0],
                    ).classes("w-full")

                with ui.column().classes("col-12 col-sm-24") as verbatim_container:
                    verbatim = ui.checkbox(
                        "Verbatim (include filler words, repetitions and unfinished sentences)"
                    ).classes("q-mt-sm")
                    verbatim_container.set_visibility(
                        language.value.lower() == "swedish"
                    )
                    # Untick as well as hide -- see the same handler in
                    # the re-transcribe dialog above.
                    language.on_value_change(
                        lambda e: (
                            verbatim.set_value(False),
                            verbatim_container.set_visibility(
                                e.value.lower() == "swedish"
                            ),
                        )
                    )

                with ui.column().classes("col-12 col-sm-24"):
                    ui.label("Number of speakers, automatic if not chosen").classes(
                        "text-subtitle2 q-mb-sm"
                    )
                    speakers = ui.number(value="0", min=0).classes("w-full")

            with ui.row().classes("justify-between w-full"):
                ui.label("Output format").classes("text-subtitle2 q-mb-sm")
                output_format = (
                    ui.radio(
                        ["Transcript", "Subtitles"],
                        value="Transcript",
                    )
                    .classes("w-full")
                    .props("inline")
                )

            with ui.row().classes("justify-between w-full"):
                with ui.button(
                    "Cancel",
                    icon="cancel",
                ) as cancel:
                    cancel.on("click", lambda: dialog.close())
                    cancel.props("color=black flat")
                    cancel.classes("cancel-style")

                with ui.button(
                    "Start transcribing",
                    on_click=lambda: (
                        start_transcription(
                            uploadable,
                            f"{language.value} (verbatim)"
                            if verbatim.value
                            else language.value,
                            speakers.value,
                            output_format.value,
                            dialog,
                            table,
                            on_complete=on_complete,
                            error_display=error_display,
                        ),
                    ),
                ) as start:
                    start.props("color=black flat")
                    start.classes("default-style")

            dialog.open()


def table_delete(table: ui.table) -> None:
    """
    Handle the click event on the Delete button.
    """

    count = len(table.selected)

    with ui.dialog().props('aria-label="Delete files"') as dialog:
        with ui.card():
            ui.label("Delete files").classes("text-h6")
            ui.label(
                f"{str(count)} files will be permanently deleted. This action cannot be undone."
            ).classes("text-subtitle2").style("margin-bottom: 10px;")

            with ui.row().classes("justify-between w-full"):
                ui.button("Cancel", on_click=lambda: dialog.close()).props(
                    "color=black"
                )
                ui.button(
                    "Delete",
                    on_click=lambda: __delete_files(table, dialog),
                ).props("color=red")

        dialog.open()


async def __delete_files(table: ui.table, dialog: ui.dialog) -> None:
    selected = list(table.selected)
    total = len(selected)
    dialog.close()

    deleted = 0
    failed = 0

    for row in selected:
        uuid = row["uuid"]
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.delete(
                    f"{settings.API_URL}/api/v1/transcriber/{uuid}",
                    headers=get_auth_header(),
                )
                response.raise_for_status()
            deleted += 1
        except (httpx.HTTPStatusError, httpx.RequestError):
            failed += 1

    table.selected = []
    fresh_rows = await jobs_get()
    if fresh_rows is not None:
        table.update_rows(fresh_rows, clear_selection=True)

    if failed == 0:
        ui.notify(
            f"Successfully deleted {deleted} file{'s' if deleted != 1 else ''}",
            type="positive",
            position="top",
        )
    else:
        ui.notify(
            f"Deleted {deleted} of {total} files ({failed} failed)",
            type="warning",
            position="top",
            timeout=None, close_button="Close")


def table_bulk_export(table: ui.table) -> None:
    """
    Handle bulk export of selected completed jobs as a zip file.
    Either every selected job is transcribed, all of the same type
    (output_format), or none is; the two are never exported together.
    Recordings offer their original too; with nothing transcribed, the
    originals are the whole export.
    """

    selected = table.selected
    if not selected:
        ui.notify("No files selected", type="warning", position="top", timeout=None, close_button="Close")
        return

    # Recordings offer their original whether they are transcribed or not.
    originals = [
        (r["filename"], r["uuid"])
        for r in selected
        if r.get("is_recording") and r.get("uuid")
    ]

    completed = [r for r in selected if r.get("status") == "Completed"]
    if completed and len(completed) < len(selected):
        ui.notify(
            "Transcribed and untranscribed files can't be exported together",
            type="warning",
            position="top",
            timeout=None, close_button="Close")
        return

    if not completed:
        if originals:
            from utils.srt_export import show_originals_dialog

            show_originals_dialog(originals)
            return

        ui.notify("No already completed files selected", type="warning", position="top", timeout=None, close_button="Close")
        return

    formats = set(r.get("output_format", "") for r in completed)
    if len(formats) > 1:
        ui.notify(
            "All selected files must be of the same type",
            type="warning",
            position="top",
            timeout=None, close_button="Close")
        return

    source_format = formats.pop()
    data_format = "srt" if source_format == "SRT" else "txt"

    # Show progress dialog while fetching
    with ui.dialog().props('aria-label="Preparing export"') as progress_dialog:
        with ui.card().classes("p-6 items-center").style(
            "min-width: 400px; background-color: var(--color-bg-surface);"
        ):
            ui.label("Preparing export...").classes("text-h6 mb-2")
            progress_label = ui.label(f"Fetching file 0 of {len(completed)}").classes(
                "text-body2 mb-2"
            )
            progress = ui.linear_progress(value=0, show_value=False).classes("w-full")

    progress_dialog.open()

    async def fetch_and_show():
        # Imported here rather than at module scope: utils.srt imports back
        # into this module, and importing utils.srt first would otherwise hit
        # a half-initialised utils.common.
        from utils.srt import SRTEditor

        editors = []
        for i, row in enumerate(completed):
            uuid = row["uuid"]
            filename = row["filename"]
            progress_label.set_text(
                f"Fetching file {i + 1} of {len(completed)}: {filename}"
            )
            progress.set_value((i + 1) / len(completed))
            try:
                fmt = "srt" if data_format == "srt" else "txt"
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        "GET",
                        f"{settings.API_URL}/api/v1/transcriber/{uuid}/result/{fmt}",
                        headers=get_auth_header(),
                        json={
                            "encryption_password": storage_decrypt(
                                app.storage.user.get("encryption_password"),
                            )
                        },
                    )
                    response.raise_for_status()
                data = response.json()

                editor = SRTEditor(uuid, data_format, filename)
                if data_format == "srt":
                    editor.parse_srt(data["result"])
                else:
                    editor.parse_txt(data["result"])
                editors.append((filename, editor))
            except httpx.HTTPError as e:
                progress_dialog.close()
                ui.notify(
                    f"Error fetching {filename}: {str(e)}",
                    type="negative",
                    position="top",
                    timeout=None, close_button="Close")
                return

        progress_dialog.close()
        # Use the first editor to show the export dialog with all editors
        first_filename, first_editor = editors[0]
        first_editor.show_export_dialog(
            first_filename, bulk_editors=editors, originals=originals
        )

    ui.timer(0.1, fetch_and_show, once=True)


def start_transcription(
    rows: list,
    language: str,
    speakers: str,
    output_format: str,
    dialog: ui.dialog,
    table: ui.table = None,
    on_complete=None,
    error_display: ui.label = None,
) -> None:
    selected_language = language
    error = ""

    # A row the backend has not answered for yet carries no uuid: the table
    # draws a placeholder row of its own while a file uploads, and that row
    # is marked "Uploaded" the moment the upload finishes -- a moment before
    # the real row replaces it.  There is nothing to transcribe until then.
    rows = [row for row in rows if row.get("uuid")]

    if not rows:
        ui.notify(
            "That upload is still being registered. Try again in a moment.",
            type="warning",
            position="top",
        )
        dialog.close()
        return

    if output_format == "Subtitles":
        output_format = "SRT"
    elif output_format in ("Transcript", "Transcribed text"):
        output_format = "TXT"
    else:
        output_format = "TXT"

    for row in rows:
        uuid = row["uuid"]

        try:
            response = httpx.put(
                f"{settings.API_URL}/api/v1/transcriber/{uuid}",
                json={
                    "language": f"{selected_language}",
                    "speakers": int(speakers),
                    "output_format": output_format,
                    "encryption_password": storage_decrypt(
                        app.storage.user.get("encryption_password"),
                    ),
                },
                headers=get_auth_header(),
            )
            response.raise_for_status()
        except httpx.HTTPError:
            if response.status_code == 403:
                error = response.json()["result"]["error"]
            else:
                error = "Error: Failed to start transcription."
            break

    if error:
        # Used to be dialog.clear() + a bare replacement card: language,
        # speaker count and format the user had just chosen were thrown
        # away, and the error label had no role, so nothing announced that
        # anything had changed at all. Writing into error_display instead
        # keeps the form exactly as filled in -- nothing to redo -- and
        # role="alert" (set where error_display is created) means a screen
        # reader announces it the moment the text is set, with no dialog
        # rebuild needed for that. (3.3.1)
        if error_display is not None:
            error_display.set_text(error)
            error_display.set_visibility(True)
    else:
        if table is not None:
            table.selected = []
        dialog.close()
        if on_complete is not None:
            on_complete()

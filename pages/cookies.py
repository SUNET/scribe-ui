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

from nicegui import app, ui
from utils.common import page_init
from utils.cookies import COOKIES
from utils.settings import get_settings
from utils.styles import default_styles

settings = get_settings()


def create() -> None:
    @ui.page("/cookies")
    def cookies_page() -> None:
        """
        Public cookie information page. See issue #140.

        One URL, two headers, picked by whether this browser is signed
        in -- not two separate pages, so the cookie notice's link and
        anything else that points here never has to choose between them,
        and the cookie list itself (the only part that actually differs
        by content) is identical either way:

        - Signed in: page_init() gives this page the exact same header,
          drawer navigation, theme toggle, help button and announcement
          banners as every other page in the app (pages/user.py,
          pages/admin/announcements.py, ...). There is nothing special
          about this page once someone is already inside the service,
          so it asks for nothing special.
        - Not signed in: page_init()'s very first real line redirects an
          unrecognised browser to "/" (utils/common.py), which is wrong
          here -- this page has to work for exactly that browser, since
          it is where the cookie notice's "Cookie information" link
          points before anyone has signed in. That visitor gets a
          lighter header instead (the same theme CSS and dark-mode
          handling page_init applies, without the parts that assume a
          signed-in session), plus a link back to "/" of its own, since
          there is no drawer here to provide one.
        """

        is_signed_in = bool(
            app.storage.user.get("token") and app.storage.user.get("refresh_token")
        )

        if is_signed_in:
            page_init(use_drawer=True, title="Cookie information")
        else:
            ui.page_title(f"{settings.TAB_TITLE} - Cookie information")
            ui.add_head_html(default_styles)
            ui.dark_mode(app.storage.user.get("dark_mode", None))

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
                ):
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
                    ui.label(settings.TOPBAR_TEXT).classes(
                        "text-h6 text-theme-primary topbar-text"
                    )

        with ui.column().classes("w-full").style(
            "max-width: 900px; margin: 0 auto; padding: 24px 16px; gap: 16px;"
        ):
            if not is_signed_in:
                # The only way back to the service on this branch: there
                # is no drawer here, and page_init -- which would redirect
                # this exact visitor away -- is deliberately not called.
                ui.link("← Back to Sunet Scribe", "/").classes(
                    "text-theme-primary"
                )

            # Same component, same classes as every other page title in
            # this app (pages/user.py "User settings",
            # pages/admin/announcements.py "Announcements") -- not a raw
            # <h1> with its own styling, which read as a different,
            # unfamiliar typeface at an unfamiliar size next to the rest
            # of the site. role/aria-level give it the heading semantics
            # a real page title is missing everywhere else (a gap tracked
            # elsewhere in the accessibility audit) without changing how
            # it looks.
            ui.label("Cookie information").classes(
                "text-3xl font-bold"
            ).props("role=heading aria-level=1")

            ui.label(
                "Sunet Scribe uses cookies only where necessary to provide "
                "the service -- for example to keep you signed in, "
                "remember your preferences, and protect your uploaded "
                "recordings. It does not use cookies for analytics, "
                "advertising, or tracking your behaviour, and none of the "
                "cookies below require your consent, since none of them "
                "are optional."
            ).classes("text-theme-primary").style("max-width: 70ch;")

            # A table (ui.table, as pages/admin/announcements.py uses for
            # its list of announcements) put six columns of metadata next
            # to a full-sentence "Purpose" cell -- either the sentence ran
            # off the table's edge with no way to read the rest, or
            # (once given a width) every other column was squeezed down
            # to a sliver and the one cell became a tall, narrow strip of
            # text a few words wide. A table is the wrong shape for this
            # content regardless of column widths: there is one cookie
            # today and a handful at most ever (see utils/cookies.py), so
            # each one gets a labelled card instead, in the same
            # icon + label + value row pattern pages/user.py already uses
            # for its own short fields (Username, User id, Timezone).
            for cookie in COOKIES:
                with ui.column().classes("w-full gap-1").style(
                    "border: 1px solid var(--color-border); border-radius: 8px;"
                    " padding: 16px 20px;"
                ):
                    ui.label(cookie.name).classes("text-lg font-semibold mb-1")
                    ui.separator()

                    with ui.column().classes("gap-1 mt-2 mb-3"):
                        ui.label("Purpose").classes(
                            "font-medium text-theme-secondary"
                        )
                        ui.label(cookie.purpose).classes(
                            "text-theme-primary"
                        ).style("max-width: 70ch;")

                    with ui.column().classes("gap-2"):
                        with ui.row().classes("items-center gap-3"):
                            ui.icon("schedule").style("font-size: 20px;")
                            ui.label("Duration").classes(
                                "font-medium text-theme-secondary"
                            ).style("min-width: 160px;")
                            ui.label(cookie.duration).classes("text-theme-primary")

                        with ui.row().classes("items-center gap-3"):
                            ui.icon("category").style("font-size: 20px;")
                            ui.label("Type").classes(
                                "font-medium text-theme-secondary"
                            ).style("min-width: 160px;")
                            ui.label(cookie.cookie_type).classes(
                                "text-theme-primary"
                            )

                        with ui.row().classes("items-center gap-3"):
                            ui.icon("lock").style("font-size: 20px;")
                            ui.label("Security attributes").classes(
                                "font-medium text-theme-secondary"
                            ).style("min-width: 160px;")
                            ui.label(cookie.security).classes("text-theme-primary")

                        with ui.row().classes("items-center gap-3"):
                            ui.icon("language").style("font-size: 20px;")
                            ui.label("Source").classes(
                                "font-medium text-theme-secondary"
                            ).style("min-width: 160px;")
                            ui.label(cookie.source).classes("text-theme-primary")

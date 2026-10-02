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
from utils.cookies import COOKIES
from utils.settings import get_settings
from utils.styles import default_styles

settings = get_settings()


def create() -> None:
    @ui.page("/cookies")
    def cookies_page() -> None:
        """
        Public cookie information page. See issue #140.

        Deliberately does not call page_init: that function's very first
        line redirects to "/" for a browser that has not visited yet
        (utils/common.py), and this page has to work for exactly that
        browser -- someone who has not signed in, reading what the
        cookie notice's "Cookie information" button pointed them to.

        It does, however, load the same theme CSS and respect the same
        dark-mode preference page_init does (utils/common.py), and copies
        page_init's own header markup/measurements rather than a
        hand-rolled approximation -- without this, the page renders with
        none of the app's CSS custom properties (every var(--color-*) and
        var(--font-sans) reference in this module resolves to nothing)
        and reads as a generic, unstyled page instead of Sunet Scribe.
        """

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
            with ui.element("div").style("display: flex; gap: 0px; align-items: center;"):
                ui.image(f"static/{settings.LOGO_TOPBAR_LIGHT}").props(
                    'alt="" aria-hidden="true"'
                ).classes("q-mr-sm logo-light").style("height: 30px; width: 30px;")
                ui.image(f"static/{settings.LOGO_TOPBAR_DARK}").props(
                    'alt="" aria-hidden="true"'
                ).classes("q-mr-sm logo-dark").style("height: 30px; width: 30px;")
                ui.label(settings.TOPBAR_TEXT).classes(
                    "text-h6 text-theme-primary topbar-text"
                )

        with ui.column().classes("w-full").style(
            "max-width: 900px; margin: 0 auto; padding: 24px 16px; gap: 16px;"
        ):
            # A real <h1>: every other page title in this app is a styled
            # <div> (ui.label with a text-h* class only changes the font,
            # not the tag), which is an existing gap tracked elsewhere in
            # the accessibility audit -- not something to repeat on a new,
            # public page where it costs nothing extra to do properly.
            # Styled to match the "text-3xl font-bold" convention every
            # other real page title in this app uses (pages/user.py,
            # pages/admin/announcements.py) instead of Quasar's unrelated
            # text-h4 scale, with the browser's own large default <h1>
            # margin reset so it reads as a page title, not a banner.
            ui.html(
                '<h1 class="text-3xl font-bold" style="margin: 0 0 4px 0;'
                ' color: var(--color-text-primary); font-family:'
                ' var(--font-sans);">Cookie information</h1>'
            )

            ui.label(
                "Sunet Scribe uses cookies only where necessary to provide "
                "the service -- for example to keep you signed in, "
                "remember your preferences, and protect your uploaded "
                "recordings. It does not use cookies for analytics, "
                "advertising, or tracking your behaviour, and none of the "
                "cookies below require your consent, since none of them "
                "are optional."
            ).classes("text-theme-primary").style("max-width: 70ch;")

            columns = [
                {
                    "name": "name",
                    "label": "Name",
                    "field": "name",
                    "align": "left",
                    "style": "width: 110px;",
                },
                {
                    "name": "purpose",
                    "label": "Purpose",
                    "field": "purpose",
                    "align": "left",
                },
                {
                    "name": "duration",
                    "label": "Duration",
                    "field": "duration",
                    "align": "left",
                    "style": "width: 220px;",
                },
                {
                    "name": "cookie_type",
                    "label": "Type",
                    "field": "cookie_type",
                    "align": "left",
                    "style": "width: 140px;",
                },
                {
                    "name": "security",
                    "label": "Security attributes",
                    "field": "security",
                    "align": "left",
                    "style": "width: 160px;",
                },
                {
                    "name": "source",
                    "label": "Source",
                    "field": "source",
                    "align": "left",
                    "style": "width: 180px;",
                },
            ]
            rows = [
                {
                    "name": cookie.name,
                    "purpose": cookie.purpose,
                    "duration": cookie.duration,
                    "cookie_type": cookie.cookie_type,
                    "security": cookie.security,
                    "source": cookie.source,
                }
                for cookie in COOKIES
            ]

            # wrap-cells: Quasar's own prop for letting cell text wrap
            # onto multiple lines instead of being clipped at the column
            # edge. The "Purpose" column's text is a full sentence, and
            # without this it overflowed the table's right edge with no
            # visual indication there was more -- reported directly
            # against this page.
            ui.table(columns=columns, rows=rows, row_key="name").classes(
                "w-full"
            ).props('aria-label="Cookies used by Sunet Scribe" flat bordered wrap-cells')

            ui.label(
                "If a cookie that is not strictly necessary is ever added "
                "to the service, it will be listed here separately and "
                "will ask for your consent on its own -- acknowledging "
                "the notice on other pages is never treated as consent "
                "for a cookie like that."
            ).classes("text-theme-muted").style("max-width: 70ch;")

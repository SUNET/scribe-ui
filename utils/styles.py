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
Centralized styles, CSS variables, and presentation constants.

All theme-sensitive colors are defined as CSS custom properties under
`.body--light` so that a future `.body--dark` block is the only change
needed to enable dark mode.
"""

theme_styles = """
<style>
    /* ── Theme variables (light mode) ── */
    :root,
    .body--light {
        color-scheme: light;
        /* One stack for the interface, one for figures that are read as
           data -- timestamps, mostly. System faces throughout: nothing is
           fetched, so nothing is left to a network the app does not
           control, and the editor is legible before any font arrives. */
        --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter",
            Roboto, "Helvetica Neue", Arial, sans-serif;
        /* Monospaced, and with a plain zero. Every other mono this machine
           ships -- SF Mono (what ui-monospace resolves to), Menlo, Monaco,
           Andale Mono, PT Mono -- strikes its zero through, which reads as
           a marking on a timestamp rather than as a digit. Courier is the
           one that does not. */
        --font-mono: "Courier New", Courier, "Liberation Mono", monospace;

        --color-bg-page: #ffffff;
        --color-bg-surface: #ffffff;
        --color-bg-surface-alt: #f3f4f6;
        --color-bg-surface-hover: #e8eaed;

        --color-brand-primary: #082954;
        --color-brand-accent: #d3ecbe;

        /* Near black rather than pure black: long stretches of transcription
           are read here, and #000 on white glares at that length. */
        --color-text-primary: #111827;
        --color-text-secondary: #374151;
        --color-text-tertiary: #626b7a;
        --color-text-muted: #6b7280;
        --color-text-on-brand: #ffffff;

        /* A grey rule, not a black one. Pure black borders drew every button
           and table cell as hard as the text inside it. */
        --color-border: #d0d5dd;
        --color-border-subtle: #e5e7eb;
        --color-border-disabled: #bdbdbd;

        --color-bg-disabled: #e0e0e0;

        --color-status-ok-bg: #e8f5e9;
        --color-status-ok-border: #4caf50;
        --color-status-error-bg: #ffebee;
        --color-status-error-border: #f44336;

        --color-text-danger: #d32f2f;
        --color-text-delete: #721c24;

        --color-severity-info-bg: #e3f2fd;
        --color-severity-info-border: #90caf9;
        --color-severity-info-icon: #1565c0;
        --color-severity-info-link: #1565c0;

        --color-severity-maint-bg: #fff3e0;
        --color-severity-maint-border: #ffb74d;
        --color-severity-maint-icon: #e65100;
        --color-severity-maint-link: #bf360c;

        --color-severity-incident-bg: #fce4ec;
        --color-severity-incident-border: #ef9a9a;
        --color-severity-incident-icon: #c62828;
        --color-severity-incident-link: #b71c1c;

        --color-warning-bg: #fff3cd;
        --color-warning-border: #ffc107;
        --color-warning-icon: #ff9800;

        /* Words flagged for review. A violet used nowhere else in the app, so
           it cannot be mistaken for a status colour. Not red: the word is not
           wrong, it is worth a look. */
        --color-review-bg: #ede9fb;
        --color-review-accent: #6d51c9;
        --color-review-text: #2f1c66;
        --color-review-on-accent: #ffffff;

        /* Words the reader has changed. A teal, far enough from the review
           violet to be told apart at a glance, and used nowhere else. Not red
           either: an edit is a correction, not a fault. */
        --color-edit-bg: #dcf2ee;
        --color-edit-accent: #12796a;
        --color-edit-text: #10453d;

        /* The word currently being spoken. A pale tint of the brand
           navy, so it reads as "you are here" rather than as a status. */
        --color-playing-bg: #dbe4f0;

        --color-header-bg: #ffffff;

        --color-help-bg-start: #ffffff;
        --color-help-bg-end: #f8f9fa;
        --color-help-accent-border: #082954;

        --color-shadow-light: rgba(0, 0, 0, 0.05);
        --color-shadow-medium: rgba(0, 0, 0, 0.1);

        --color-stats-heading: #111827;
        --color-stats-text: #374151;

        --color-help-about-bg: #eff6ff;
        --color-help-about-icon: #1d4ed8;
        --color-help-privacy-bg: #fffbeb;
        --color-help-privacy-icon: #92400e;
        --color-help-support-bg: #f0fdf4;
        --color-help-support-icon: #166534;

        --color-btn-primary-bg: #082954;
        --color-btn-primary-text: #ffffff;
        --color-btn-primary-border: #082954;
        --color-btn-edit-bg: #082954;
        --color-btn-edit-text: #ffffff;
        --color-btn-edit-border: #082954;
        --color-btn-delete-bg: transparent;
        --color-btn-delete-text: #721c24;
        --color-btn-delete-border: #d0d5dd;

        --color-chart-bar-current: #4F46E5;
        --color-chart-bar-previous: #10B981;
        --color-chart-bar-primary: #082954;
        --color-chart-bar-secondary: #4caf50;
        --color-chart-line-cpu: #3b82f6;
        --color-chart-line-memory: #10b981;
        --color-chart-line-gpu: #8b5cf6;
        --color-chart-line-gpu-mem: #f59e0b;
        --color-chart-wow-positive: #2e7d32;
        --color-chart-wow-negative: #c62828;
        --color-chart-wow-neutral: #757575;
    }

    /* ── Theme variables (dark mode) ── */
    .body--dark {
        color-scheme: dark;
        --color-bg-page: #000000;
        --color-bg-surface: #16181d;
        --color-bg-surface-alt: #1e2128;
        --color-bg-surface-hover: #2a2e36;

        --color-brand-primary: #5b9bd5;
        --color-brand-accent: #3d7a2e;

        /* Off white, and three genuinely different weights of it: muted was
           #e0e0e0, all but indistinguishable from primary, so the character
           counts and the gutter read as loudly as the text they annotate. */
        --color-text-primary: #e6e8eb;
        --color-text-secondary: #c7ccd3;
        --color-text-tertiary: #a7aeb8;
        --color-text-muted: #9aa1ab;
        --color-text-on-brand: #ffffff;

        --color-border: #3a3f47;
        --color-border-subtle: #2c3038;
        --color-border-disabled: #444444;

        --color-bg-disabled: #2a2e36;

        --color-status-ok-bg: #1b3a1b;
        --color-status-ok-border: #4caf50;
        --color-status-error-bg: #3a1b1b;
        --color-status-error-border: #f44336;

        --color-text-danger: #ef5350;
        --color-text-delete: #ef9a9a;

        --color-severity-info-bg: #1a2a3a;
        --color-severity-info-border: #42a5f5;
        --color-severity-info-icon: #64b5f6;
        --color-severity-info-link: #64b5f6;

        --color-severity-maint-bg: #3a2a1a;
        --color-severity-maint-border: #ffb74d;
        --color-severity-maint-icon: #ffcc80;
        --color-severity-maint-link: #ffcc80;

        --color-severity-incident-bg: #3a1a1a;
        --color-severity-incident-border: #ef9a9a;
        --color-severity-incident-icon: #ef9a9a;
        --color-severity-incident-link: #ef9a9a;

        --color-warning-bg: #3a3020;
        --color-warning-border: #ffc107;
        --color-warning-icon: #ffb300;

        --color-review-bg: #2f2748;
        --color-review-accent: #b3a1f0;
        --color-review-text: #ece7ff;
        --color-review-on-accent: #241a45;

        --color-edit-bg: #1d3b37;
        --color-edit-accent: #6fd3c1;
        --color-edit-text: #dff5f0;

        --color-playing-bg: #1c3252;

        --color-header-bg: #16181d;

        --color-help-bg-start: #16181d;
        --color-help-bg-end: #1e2128;
        --color-help-accent-border: #5b9bd5;

        --color-shadow-light: rgba(0, 0, 0, 0.3);
        --color-shadow-medium: rgba(0, 0, 0, 0.5);

        --color-stats-heading: #e0e0e0;
        --color-stats-text: #b0b0b0;

        --color-help-about-bg: #1a2a3a;
        --color-help-about-icon: #64b5f6;
        --color-help-privacy-bg: #3a3020;
        --color-help-privacy-icon: #ffcc80;
        --color-help-support-bg: #1b3a1b;
        --color-help-support-icon: #66bb6a;

        --color-btn-primary-bg: #1a4a7a;
        --color-btn-primary-text: #ffffff;
        --color-btn-primary-border: #5b9bd5;
        --color-btn-edit-bg: #1a4a7a;
        --color-btn-edit-text: #ffffff;
        --color-btn-edit-border: #5b9bd5;
        --color-btn-delete-bg: transparent;
        --color-btn-delete-text: #ef9a9a;
        --color-btn-delete-border: #555555;

        --color-chart-bar-current: #818cf8;
        --color-chart-bar-previous: #34d399;
        --color-chart-bar-primary: #5b9bd5;
        --color-chart-bar-secondary: #66bb6a;
        --color-chart-line-cpu: #60a5fa;
        --color-chart-line-memory: #34d399;
        --color-chart-line-gpu: #a78bfa;
        --color-chart-line-gpu-mem: #fbbf24;
        --color-chart-wow-positive: #66bb6a;
        --color-chart-wow-negative: #ef5350;
        --color-chart-wow-neutral: #b0b0b0;
    }

    /* ── Dark mode overrides for Quasar components ── */
    .body--dark .q-table,
    .body--dark .q-table__top,
    .body--dark .q-table__middle,
    .body--dark .q-table__bottom,
    .body--dark .q-table__card,
    .body--dark .q-table__container,
    .body--dark .q-table thead,
    .body--dark .q-table thead tr,
    .body--dark .q-table thead th,
    .body--dark .q-table tbody,
    .body--dark .q-table tbody tr,
    .body--dark .q-table tbody td,
    .body--dark .q-table .q-td,
    .body--dark .q-table .q-tr,
    .body--dark .q-table .q-table__bottom .q-table__control,
    .body--dark .q-table .q-table__bottom .q-table__separator {
        background-color: var(--color-bg-page) !important;
        color: var(--color-text-primary) !important;
    }
    .body--dark .q-card {
        background-color: var(--color-bg-surface);
        box-shadow: none !important;
        border: none !important;
    }
    .body--dark .q-header {
        background-color: var(--color-header-bg);
    }
    .body--dark .q-drawer {
        background-color: var(--color-bg-surface-alt);
    }
    .body--dark .table-style,
    .body--dark .table-style .q-table__top,
    .body--dark .table-style .q-table__middle,
    .body--dark .table-style .q-table__bottom,
    .body--dark .table-style .q-table__card,
    .body--dark .table-style .q-table__container,
    .body--dark .table-style thead,
    .body--dark .table-style thead tr,
    .body--dark .table-style thead th,
    .body--dark .table-style tbody,
    .body--dark .table-style tbody tr,
    .body--dark .table-style tbody td,
    .body--dark .table-style .q-td,
    .body--dark .table-style .q-tr,
    .body--dark .table-style .q-table__bottom .q-table__control,
    .body--dark .table-style .q-table__bottom .q-table__separator {
        background-color: var(--color-bg-page) !important;
        color: var(--color-text-primary) !important;
    }
    .body--dark .table-style p,
    .body--dark .table-style span,
    .body--dark .table-style label,
    .body--dark .table-style .q-field__native,
    .body--dark .table-style .text-3xl {
        color: var(--color-text-primary) !important;
    }
    .body--dark .table-style .q-btn.button-close,
    .body--dark .table-style .q-btn.delete-style,
    .body--dark .table-style .q-btn.default-style {
        border-color: var(--color-border) !important;
    }
    .body--dark .table-style th,
    .body--dark .table-style td {
        border-color: var(--color-border-subtle);
    }
    .body--dark .q-dialog .q-card {
        background-color: var(--color-bg-surface-alt) !important;
        color: var(--color-text-primary) !important;
    }
    .body--dark .q-dialog .q-card *:not(.q-checkbox):not(.q-checkbox *) {
        color: var(--color-text-primary) !important;
    }
    .body--dark .q-field--outlined .q-field__control:before {
        border-color: var(--color-border-subtle) !important;
    }
    .body--dark .q-separator {
        background-color: var(--color-border-subtle);
    }
    .body--dark .drop-shadow-md {
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
    }

    /* ── Header logo auto-mode toggle ── */
    .body--dark .logo-light {
        display: none !important;
    }
    .body--light .logo-dark {
        display: none !important;
    }

    /* ── Header buttons ── */
    .header-btn,
    .header-btn .q-icon,
    .header-btn .q-btn__content {
        color: var(--color-text-primary) !important;
    }
    .q-btn.header-btn.q-btn--flat {
        border: none !important;
    }

    /* ── Page background and type ── */
    body {
        background-color: var(--color-bg-page);
        /* Quasar states Roboto on the body and again on several of its own
           controls, so both have to be answered or the interface ends up
           in two faces at once. */
        font-family: var(--font-sans);
    }
    .q-btn,
    .q-field,
    .q-item,
    .q-table,
    .q-tooltip,
    input,
    button,
    select,
    textarea {
        font-family: var(--font-sans);
    }

    /* ── Quasar chip ── */
    .q-chip {
        background-color: var(--color-brand-accent) !important;
        color: var(--color-text-primary) !important;
    }

    /* ── Button / action styles ── */
    .default-style {
        background-color: var(--color-brand-accent);
        border: 1px solid var(--color-border);
    }
    .default-style.disabled {
        background-color: var(--color-bg-disabled) !important;
        border: 1px solid var(--color-border-disabled) !important;
        opacity: 0.7;
    }
    .delete-style {
        background-color: var(--color-btn-delete-bg);
        color: var(--color-btn-delete-text) !important;
        border: 1px solid var(--color-btn-delete-border);
        width: 150px;
    }
    .delete-style.disabled {
        background-color: var(--color-bg-disabled) !important;
        border: 1px solid var(--color-border-disabled) !important;
        opacity: 0.7;
    }
    .cancel-style {
        background-color: var(--color-bg-surface);
        color: var(--color-text-primary) !important;
        border: 1px solid var(--color-border);
        width: 150px;
    }
    .button-default-style {
        background-color: var(--color-btn-primary-bg) !important;
        color: var(--color-btn-primary-text) !important;
        border: 1px solid var(--color-btn-primary-border) !important;
        width: 150px;
    }
    .button-replace {
        background-color: var(--color-bg-surface);
        color: var(--color-brand-primary) !important;
        border: 1px solid var(--color-brand-primary);
        width: 150px;
    }
    .button-replace-current {
        background-color: var(--color-brand-accent);
        color: var(--color-text-primary) !important;
        width: 150px;
    }
    .button-replace-prev-next {
        background-color: var(--color-bg-surface);
        color: var(--color-brand-primary) !important;
    }
    .button-close {
        background-color: var(--color-bg-surface);
        color: var(--color-text-primary) !important;
        width: 150px;
        border: 1px solid var(--color-border);
    }
    .button-user-status {
        background-color: var(--color-bg-surface);
        width: 150px;
        border: 1px solid var(--color-border);
    }
    .button-edit {
        background-color: var(--color-btn-edit-bg) !important;
        color: var(--color-btn-edit-text) !important;
        border: 1px solid var(--color-btn-edit-border) !important;
        width: 150px;
    }

    /* ── Upload dropzone ── */
    .dropzone-area {
        background-color: var(--color-bg-surface-alt);
        border-color: var(--color-border-subtle);
        color: var(--color-text-muted);
    }
    .dropzone-area:hover {
        background-color: var(--color-bg-surface-hover);
    }
    .dropzone-drag {
        background-color: var(--color-bg-surface-hover) !important;
    }

    /* ── Global dark mode button override ── */
    .body--dark .q-btn--flat {
        color: var(--color-text-primary) !important;
        border: 1px solid var(--color-border) !important;
    }
    .body--dark .q-btn--flat .q-icon,
    .body--dark .q-btn--flat .q-btn__content {
        color: var(--color-text-primary) !important;
    }

    /* ── Editor toolbar ── */
    /* Stays put while the caption list scrolls under it: every one of its
       actions applies to the document as a whole, so scrolling away from
       them meant scrolling back up to save. */
    .editor-toolbar {
        position: sticky;
        top: 0;
        z-index: 20;
        background-color: var(--color-bg-surface);
        border-bottom: 1px solid var(--color-border-subtle);
        padding: 0.5rem 0.25rem;
    }
    /* On the page's own black, with nothing dividing it from the editor
       below -- the same as the panels themselves. */
    .body--dark .editor-toolbar {
        background-color: var(--color-bg-page);
        border-bottom: none;
    }
    /* Actions that belong together sit together, divided by a rule rather
       than by spacing alone -- undo/redo, then the document's own actions,
       then the ones that only look at it. */
    .editor-toolbar-group {
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    .editor-toolbar .q-separator--vertical {
        height: 1.5rem;
        align-self: center;
        margin: 0 0.25rem;
    }

    /* The document's own name, at the head of the toolbar: it says what is
       being edited, which is a title, not a detail to be looked up at the
       bottom of a panel. Capped and ellipsised -- a filename can be long
       enough to push everything else off the row. */
    /* ── Video information dialog ── */
    /* What is open and what is in it. Read when a reader wonders rather than
       while they work, so it lives behind a button instead of taking a strip
       of the toolbar -- which also leaves room to say what each figure
       means, which a row of bare numbers never had. */
    .editor-info-card {
        min-width: 26rem;
        max-width: 32rem;
    }
    .editor-info-rows {
        gap: 0.85rem;
        width: 100%;
    }
    .editor-info-row {
        display: flex;
        align-items: baseline;
        gap: 1rem;
        width: 100%;
    }
    .editor-info-label {
        flex: 0 0 8rem;
        color: var(--color-text-muted);
    }
    .editor-info-value {
        flex: 1 1 auto;
        min-width: 0;
        gap: 0.1rem;
    }
    .editor-info-figure {
        font-weight: 600;
        color: var(--color-text-primary);
        font-variant-numeric: tabular-nums;
        /* A filename has no spaces to break at and is often long. */
        overflow-wrap: anywhere;
    }
    .editor-info-explanation {
        font-size: 0.8125rem;
        color: var(--color-text-secondary);
    }

    /* ── Editor toolbar buttons (flat, no border, subtle bg in dark mode) ── */
    .editor-btn {
        border: none !important;
    }
    /* Sized to their own label rather than to a shared floor. A fixed
       130px made six different actions read as one undifferentiated wall
       of boxes, and left Save no way to stand out from Shortcuts. */
    .editor-toolbar-btn {
        min-width: 0 !important;
        padding: 0 0.75rem !important;
    }
    .body--light .q-btn.editor-btn {
        background-color: var(--color-bg-surface) !important;
        border: 1px solid var(--color-border-subtle) !important;
        color: var(--color-text-primary) !important;
    }
    .body--light .q-btn.editor-btn:hover {
        background-color: var(--color-bg-surface-alt) !important;
    }
    .body--light .q-btn.editor-btn .q-icon,
    .body--light .q-btn.editor-btn .q-btn__content {
        color: var(--color-text-primary) !important;
    }
    .body--light .q-btn.editor-btn[disabled] {
        background-color: var(--color-bg-surface) !important;
        border: 1px solid var(--color-border-subtle) !important;
        opacity: 0.4;
    }
    /* Dark mode: the same black the editor panels sit on, drawn white, and
       nothing framing it -- the global .q-btn--flat rule gives every flat
       button a border, so it is turned off here explicitly. */
    .body--dark .q-btn.editor-btn {
        background-color: var(--color-bg-page) !important;
        border: none !important;
        color: #ffffff !important;
    }
    .body--dark .q-btn.editor-btn:hover {
        background-color: var(--color-bg-surface-alt) !important;
    }
    .body--dark .q-btn.editor-btn .q-icon,
    .body--dark .q-btn.editor-btn .q-btn__content {
        color: #ffffff !important;
    }
    .body--dark .q-btn.editor-btn[disabled] {
        background-color: var(--color-bg-page) !important;
        border: none !important;
        opacity: 0.4;
    }

    /* ── Dark mode primary button contrast ── */
    .body--dark .q-btn.bg-primary {
        background-color: var(--color-btn-primary-bg) !important;
        border: 1px solid var(--color-btn-primary-border) !important;
    }

    /* ── Table action buttons ── */
    .table-btn-edit {
        background-color: var(--color-bg-surface) !important;
        color: var(--color-text-primary) !important;
        border: 1px solid var(--color-border) !important;
    }
    .table-btn-transcribe {
        background-color: var(--color-btn-primary-bg) !important;
        color: var(--color-btn-primary-text) !important;
        border: 1px solid var(--color-btn-primary-border) !important;
    }

    /* ── Table ── */
    .table-style th {
        font-size: 14px;
    }
    .table-style tr {
        font-size: 14px;
    }

    /* ── Upload area ── */
    .upload-style {
        width: 100%;
        height: 200px;
    }

    /* ── Deletion warning ── */
    .deletion-warning {
        color: var(--color-text-danger);
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 4px;
    }
    .deletion-warning-icon {
        font-size: 18px;
    }
    .body--dark .deletion-warning {
        color: #ff8a80;
        font-weight: 700;
    }
    .body--dark .deletion-warning-icon {
        color: #ff8a80;
    }

    /* ── Tooltip ── */
    .q-tooltip {
        font-size: 14px;
        white-space: nowrap;
    }

    /* ── Status page cards ── */
    .status-card {
        padding: 24px;
        border-radius: 8px;
        margin-bottom: 16px;
    }
    .status-ok {
        background-color: var(--color-status-ok-bg);
        border-left: 4px solid var(--color-status-ok-border);
    }
    .status-error {
        background-color: var(--color-status-error-bg);
        border-left: 4px solid var(--color-status-error-border);
    }
    .status-icon {
        font-size: 24px;
        margin-right: 12px;
    }

    /* ── Drawer / menu ── */
    .menu-item:hover {
        background-color: var(--color-bg-surface-hover);
    }
    .q-drawer--mini .menu-header {
        display: none;
    }
    .q-drawer--mini .menu-separator {
        margin: 4px 0;
    }
    .q-drawer--mini .menu-item {
        justify-content: center;
        padding: 10px 0;
        gap: 0;
    }
    .q-drawer--mini .menu-item .q-icon {
        margin: 0;
    }
    .q-drawer--mini .menu-label {
        display: none;
    }

    /* ── Announcement banners ── */
    .announcement-banner a {
        color: var(--color-severity-info-link);
        text-decoration: underline;
        font-weight: 500;
    }
    .announcement-banner a:hover {
        text-decoration: underline;
        opacity: 0.8;
    }
    .announcement-banner.severity-maintenance a {
        color: var(--color-severity-maint-link);
    }
    .announcement-banner.severity-major_incident a {
        color: var(--color-severity-incident-link);
    }

    .severity-info {
        background-color: var(--color-severity-info-bg);
        border-bottom: 1px solid var(--color-severity-info-border);
    }
    .severity-maintenance {
        background-color: var(--color-severity-maint-bg);
        border-bottom: 1px solid var(--color-severity-maint-border);
    }
    .severity-major_incident {
        background-color: var(--color-severity-incident-bg);
        border-bottom: 1px solid var(--color-severity-incident-border);
    }

    /* ── Admin: group/customer cards ── */
    .body--dark .admin-card {
        background-color: var(--color-bg-surface-alt) !important;
    }

    /* ── Admin: stats page ── */
    .stats-container {
        max-width: 1500px;
        margin: 0 auto;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 2rem;
        padding: 2rem 1rem;
    }
    .stats-card {
        width: 100%;
        background-color: var(--color-bg-surface);
        box-shadow: 0 2px 10px var(--color-shadow-light);
        border-radius: 1rem;
        padding: 1.5rem 2rem;
        text-align: center;
    }
    .stats-card h1 {
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 1rem;
        color: var(--color-stats-heading);
    }
    .stats-card p {
        margin: 0.25rem 0;
        font-size: 1.1rem;
        color: var(--color-stats-text);
    }
    .chart-container {
        width: 100%;
        background-color: var(--color-bg-surface);
        border-radius: 1rem;
        box-shadow: 0 2px 10px var(--color-shadow-light);
        padding: 1.5rem 2rem;
    }
    .table-container {
        width: 100%;
        background-color: var(--color-bg-surface);
        border-radius: 1rem;
        box-shadow: 0 2px 10px var(--color-shadow-light);
        padding: 1.5rem 2rem;
    }

    /* ── Admin: health page ── */
    .health-card {
        background-color: var(--color-bg-surface);
        border-radius: 1rem;
        box-shadow: 0 2px 8px var(--color-shadow-medium);
        padding: 1.25rem;
        width: 100%;
        max-width: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .status-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
    }
    .status-dot-online {
        background-color: var(--color-status-ok-border);
    }
    .status-dot-offline {
        background-color: var(--color-status-error-border);
    }
    .health-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
        gap: 1.25rem;
        width: 100%;
    }
    @media (max-width: 768px) {
        .health-grid {
            grid-template-columns: 1fr;
        }
    }

    /* ── NiceGUI content padding ── */
    .nicegui-content {
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 100%;
    }

    /* ── Editor panels ── */
    /* The two halves of the editor -- the caption list and the video --
       are the page's own content, not something floating over it, so they
       carry neither a drop shadow nor a rule around them. Just a radius,
       and the splitter's own handle between them. */
    .editor-panel {
        background-color: var(--color-bg-surface);
        border: none !important;
        border-radius: 12px;
        box-shadow: none !important;
    }
    /* Dark mode puts the editor on the page's own black, not on the
       lifted surface the rest of the app uses -- nothing framing it, so
       the text is all there is to look at. */
    .body--dark .q-card.editor-panel {
        background-color: var(--color-bg-page) !important;
        border: none !important;
    }

    /* The handle between them: a hairline at rest, the brand colour while
       it is being dragged or pointed at, so it reads as something that can
       be moved rather than as a gap between two cards. */
    .q-splitter__separator {
        background-color: var(--color-border-subtle) !important;
        transition: background-color 0.12s ease-in-out;
    }
    .q-splitter__separator:hover,
    .q-splitter--active .q-splitter__separator {
        background-color: var(--color-brand-primary) !important;
    }

    /* ── Editor: selected caption styling ── */
    .body--dark .q-card.shadow-lg {
        box-shadow: 0 4px 16px rgba(255, 255, 255, 0.08) !important;
    }

    /* ── Editor: textarea/input visibility ── */
    .body--dark .q-field--outlined .q-field__control {
        background-color: var(--color-bg-surface);
    }

    /* ── Marked words: flagged for review, or changed by the reader ── */
    /* One marking for every flagged word, whatever its score. Deliberately
       not red and not a wavy underline: red reads as broken and wavy reads as
       a spellchecker, and neither is what this means. It is an invitation to
       look, so it is a calm highlight in a colour used for nothing else.

       Edited words follow the same shape in a second colour. A word is never
       both: one is a word the model was unsure of, the other a word the model
       never produced. */

    .review-word,
    .edit-word {
        position: relative;
        padding: 1px 3px;
        border-radius: 3px;
        /* Keep the highlight intact if a word wraps across lines. */
        box-decoration-break: clone;
        -webkit-box-decoration-break: clone;
    }
    .review-word {
        color: var(--color-review-text);
        background-color: var(--color-review-bg);
        box-shadow: inset 0 -2px 0 var(--color-review-accent);
    }
    .edit-word {
        color: var(--color-edit-text);
        background-color: var(--color-edit-bg);
        box-shadow: inset 0 -2px 0 var(--color-edit-accent);
    }

    /* Shared hover message. A CSS box rather than title=, which the browser
       draws itself and stylesheets cannot reach. */
    .review-word::after,
    .edit-word::after,
    .transcript-show-edits [data-changed]::after {
        position: absolute;
        bottom: calc(100% + 6px);
        /* Anchored to the word's left edge rather than centred on it. Centred,
           the tooltip reaches roughly half its width to the left of the word,
           which puts it outside the scrolling caption list for any word at the
           start of a line -- the first word of a caption came out half cut. */
        left: 0;
        z-index: 9000;
        padding: 4px 8px;
        border-radius: 4px;
        background-color: var(--color-bg-surface);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
        font-size: 12px;
        font-weight: 600;
        line-height: 1.3;
        /* Wraps rather than running off the right for a word near the end of
           a line. The message fits on one line at this width in practice. */
        max-width: 14rem;
        width: max-content;
        white-space: normal;
        text-decoration: none;
        pointer-events: none;
        opacity: 0;
        visibility: hidden;
        transition: opacity 0.12s ease-in-out;
    }
    .review-word::after {
        content: attr(data-review);
        border: 1px solid var(--color-review-accent);
        color: var(--color-review-text);
    }
    .edit-word::after {
        content: attr(data-edit);
        border: 1px solid var(--color-edit-accent);
        color: var(--color-edit-text);
    }
    .review-word:hover::after,
    .review-word:focus-visible::after,
    .edit-word:hover::after,
    .edit-word:focus-visible::after,
    .transcript-show-edits [data-changed]:hover::after,
    .transcript-show-edits [data-changed]:focus-visible::after {
        opacity: 1;
        visibility: visible;
    }

    /* A word being typed into, marked by the browser because the server cannot
       re-render the block the caret is in without moving it. The word no longer
       matches what was transcribed, so it is no longer a word the model was
       unsure of -- and it becomes one of the reader's own. An attribute rather
       than a class, so Vue does not take it away on the next patch, and so
       undoing the change restores the marking rather than leaving it bare. */
    .review-word[data-changed] {
        color: inherit;
        background-color: transparent;
        box-shadow: none;
    }
    .review-word[data-changed]::after {
        content: none;
    }
    .transcript-show-edits [data-changed] {
        /* Stated here as well as on .edit-word: a word that was not flagged
           carries neither class, so it has none of the shared geometry. Not
           positioned -- see the rule further down. */
        padding: 1px 3px;
        border-radius: 3px;
        color: var(--color-edit-text);
        background-color: var(--color-edit-bg);
        box-shadow: inset 0 -2px 0 var(--color-edit-accent);
        box-decoration-break: clone;
        -webkit-box-decoration-break: clone;
    }
    /* After the rule above that silences the review message, and at the same
       specificity, so a word that was flagged and has since been changed
       carries the edit message rather than none at all. */
    .transcript-show-edits [data-changed]::after {
        content: attr(data-edit);
        border: 1px solid var(--color-edit-accent);
        color: var(--color-edit-text);
    }

    /* Quasar resolves a control's colour from a class name, so naming a colour
       here is all it takes to hand one of ours to a Quasar control -- no
       guessing at which child element ends up selected, and no fighting the
       !important on its own palette classes. Used by the review sensitivity
       selector, so it matches the switch that reveals it. */
    .bg-review-accent {
        background: var(--color-review-accent) !important;
    }
    .text-review-accent-fg {
        color: var(--color-review-on-accent) !important;
    }

    /* No marking in the transcription is ever positioned.

       position: relative promotes an inline element to paint above the in-flow
       text, and WebKit draws the caret along with the block's own content -- so
       a positioned marking paints its background over the caret and hides it.
       The playing-word highlight has a background too and was never affected,
       which is what gave this away: it was never positioned.

       It was there only to anchor the hover message, and the message goes with
       it: anchoring it per word is the only thing that ever needed a positioned
       word, and in text being edited the caret matters more than an explanation
       of a marking -- the same call the layer behind a caption text area makes.
       The markings themselves are unchanged, and the switches that turn them on
       say what each one means.

       Doing it here for every marking, rather than for the word the caret
       happens to be in, also means nothing changes an element's position while
       it is being clicked. Doing that mid-click left Safari selecting the word
       before the one that was clicked. */
    .transcript-text .review-word,
    .transcript-text .edit-word,
    .transcript-show-edits [data-changed] {
        position: static;
    }
    .transcript-text .review-word::after,
    .transcript-text .edit-word::after,
    .transcript-show-edits [data-changed]::after {
        content: none;
    }

    /* The controls under the video are settings, not content: smaller than
       the text they act on, and all in one colour rather than each in
       whatever Quasar's defaults happened to give it -- three switches in
       three different colours read as three unrelated things. The one
       exception is below: a switch that turns on a marking wears that
       marking's own colour, because the colour is what it is about. */
    .q-toggle.editor-switch .q-toggle__label {
        font-size: 0.875rem;
    }
    .q-toggle.editor-switch .q-toggle__inner--truthy {
        color: var(--color-brand-primary);
    }

    /* "Off" is a state of the review control, not the review marking, so it
       is drawn as plainly as any other unselected thing. Painting it in the
       review violet -- which is what naming one toggle-color for every
       segment did -- made the loudest thing in the panel the setting that
       means nothing is being marked at all. */
    .bg-toggle-off {
        background: var(--color-bg-surface-hover) !important;
    }
    .text-toggle-off-fg {
        color: var(--color-text-primary) !important;
    }

    /* Each switch wears the colour of the marking it turns on, so the control
       and the words it affects read as one thing. Quasar draws both the track
       and the thumb of a switch that is on in currentColor, so setting the
       colour is all it takes. The class goes on the switch itself, which puts
       it ahead of Quasar's own light and dark rules for the same element. */
    .q-toggle.edits-switch .q-toggle__inner--truthy {
        color: var(--color-edit-accent);
    }

    /* Review controls under the video. */
    .review-count {
        font-variant-numeric: tabular-nums;
    }

    /* ── Video subtitle overlay ── */
    /* The caption playing right now, drawn over the video the same way a
       real subtitle would be -- a preview of what a viewer sees, not the
       editor's own review marking. .video-frame gives the video a
       positioning context of its own to sit inside, since neither
       ui.video nor the card wrapping it establishes one. */
    .video-frame {
        position: relative;
        /* The frame sits inside a rounded panel now, so the picture is
           rounded to match rather than filling square corners inside it. */
        border-radius: 8px;
        overflow: hidden;
        /* The overlay's type is sized against this frame's own width (cqi
           below), so a caption's longest allowed line still fits on one
           line however narrow the splitter leaves the video. */
        container-type: inline-size;
    }
    .video-subtitle-overlay {
        position: absolute;
        left: 50%;
        /* Where a viewer would see it: at the bottom of the frame. It only
           moves up when the player's own control bar is up (see below), so
           the rest of the time the preview is where the real thing is. */
        bottom: 1rem;
        transition: bottom 0.15s ease-in-out;
        transform: translateX(-50%);
        max-width: 90%;
        padding: 0.35rem 0.75rem;
        background-color: rgba(0, 0, 0, 0.7);
        color: #fff;
        /* A line the editor accepts (up to CHARACTER_LIMIT characters,
           handed down as --subtitle-char-limit by pages/srt.py) has to fit
           the frame without wrapping, or the overlay stops being a preview
           of what a viewer sees -- the reader breaks a caption at the
           guideline and the overlay breaks it again somewhere else. So the
           type is sized against the frame rather than fixed: roughly 0.55em
           per character for the sans in use, inside the ~85% of the frame
           the box and its padding get, capped at 1rem so a wide video keeps
           an ordinary subtitle rather than a blown-up one. */
        font-size: min(1rem, calc(85cqi / (var(--subtitle-char-limit, 42) * 0.55)));
        line-height: 1.4;
        text-align: center;
        /* One child per line of the caption (see draw_overlay), so the
           overlay breaks exactly where the caption does rather than
           wherever the width happens to run out. pre-line stays as a
           backstop for a line that still arrives carrying its own "\n". */
        white-space: pre-line;
        border-radius: 4px;
        /* Belt and suspenders alongside the fixed offset above: never in
           the way of the seek bar or a click-to-pause anywhere else on the
           frame, even if the two ever end up overlapping regardless. */
        pointer-events: none;
    }
    /* Clear of the control bar while that bar is up. A fixed offset, not a
       percentage of the frame's own height -- the bar's height is fixed too,
       so a percentage shrinks below it on a short or wide video and the
       overlay ends up drawn over the seek bar, hiding it rather than sitting
       above it. The class is put on the frame by pages/srt.py, which follows
       the same rules the browser draws the bar by: up while paused, and
       while the pointer has moved over the frame in the last few seconds. */
    .video-controls-visible .video-subtitle-overlay {
        bottom: 4.25rem;
    }

    .video-subtitle-line {
        /* Never break a line the editor did not break: draw_overlay gives
           each of the caption's own lines an element, and a wrap inside one
           of them would show a viewer a break the subtitle file does not
           have. The font-size above is what keeps this from overflowing. */
        white-space: nowrap;
    }

    /* ── Document editor (transcriptions and subtitles alike) ── */
    /* One contenteditable holds every block. A two column grid puts the
       margin beside the text, so the margin cells are real elements that can
       be clicked without the text ever leaving a single editable surface.
       They are contenteditable=false, so the caret cannot enter them. A
       transcription puts the speaker there; a subtitle has no speaker, so
       its margin carries a length guideline instead -- see
       .transcript-subtitle-mode throughout this section. The timing itself
       (.transcript-time / .transcript-subtitle-time) is in the cell in both
       modes, as a pair of plain inputs, over the text it belongs to. */
    .transcript-editor {
        /* The speaker menu is placed against this box. */
        position: relative;
        width: 100%;
        padding: 0.5rem 0 4rem;
    }
    .transcript-body {
        /* Stated rather than left to currentColor, which a marked word
           overrides -- the caret would take the marking's text colour and go
           faint against the marking's own background. */
        caret-color: var(--color-text-primary);
        display: grid;
        grid-template-columns: 8rem minmax(0, 1fr);
        column-gap: 1rem;
        row-gap: 1rem;
        outline: none;
        /* Wide enough to use the pane it is in. A subtitle line is capped
           at CHARACTER_LIMIT characters by the guideline itself, so a
           narrow column buys no readability here -- it only left the right
           half of the editor empty. */
        max-width: 72rem;
        margin: 0 auto;
    }
    /* The margin holds only the caption's index and its per-line character
       counts now -- the timing moved into the cell, over the text it times,
       rather than the margin tuned for a speaker name. Column width and gap
       are left at the base rule's own values, not just an equal sum of
       them, so the divider itself -- not only the text past it -- lines up
       with a transcription's. Only row-gap differs: more room between
       captions than the base rule's, which reads dense at a transcription's
       own smaller, denser scale. */
    .transcript-subtitle-mode .transcript-body {
        row-gap: 1.25rem;
    }

    .transcript-gutter {
        justify-self: end;
        display: flex;
        gap: 0.25rem;
        /* Line the speaker up with the first line of its text, which sits
           below the timestamp. */
        padding-top: 1.9rem;
        color: var(--color-text-muted);
        font-size: 0.9rem;
        user-select: none;
        white-space: nowrap;
    }
    /* A subtitle's margin is a column instead of the base rule's row: the
       index on its own top line, the per-line counts stacked below it. No
       padding-top skipping down to the text the way the base rule does for
       a speaker -- the index takes that row instead, so there is something
       in the margin to line up with the timing row after all, just not the
       counts. */
    .transcript-subtitle-mode .transcript-gutter {
        flex-direction: column;
        align-items: flex-end;
        /* The base rule's own padding-top is what skips a speaker past the
           timestamp -- the index sits there instead here, so it has to be
           reset back to 0 rather than inherited unchanged. */
        padding-top: 0;
        /* Matches .transcript-subtitle-time's own margin-bottom, so the
           counts below land aligned with the text below in the cell. */
        gap: 0.6rem;
    }
    .transcript-speaker {
        cursor: pointer;
        border-radius: 3px;
        padding: 0 2px;
    }
    .transcript-speaker:hover {
        color: var(--color-text-primary);
        background-color: var(--color-bg-surface-alt);
    }
    .transcript-colon {
        color: var(--color-border-disabled);
    }

    /* A left rule per block marks its state -- active (being played), invalid
       (failed "Validate", subtitles only) or highlighted (a search match).
       Invalid and highlighted are mutually exclusive in practice, since
       Validate and search are two different actions, but if both were ever
       true at once the later rule -- highlighted -- would win, which is the
       more immediate thing to have drawn the reader's attention here. */
    .transcript-cell {
        position: relative;
        border-left: 1px solid var(--color-border-subtle);
        padding-left: 1rem;
        /* Room on the right, and rounded away from the rule, so a tinted
           state below reads as a band around the caption rather than a
           stripe running off the edge of the column. The left corners stay
           square: that edge is the state rule itself. No vertical padding
           -- the margin's character counts are lined up with the text
           lines by line-height alone, and padding here would slide the
           text down out from under them. */
        padding-right: 0.75rem;
        border-radius: 0 6px 6px 0;
        min-width: 0;
        transition: border-color 0.15s ease-in-out, background-color 0.15s ease-in-out;
    }
    /* Subtitles are read as separate cues, not a continuous document, so
       hovering one draws a line under it -- in the middle of the row gap --
       to show where it ends and its neighbour begins. Quiet until then, or a
       long list of captions would read as a table. Hovering the margin
       (its timing) counts too, via the adjacent-sibling match below, since
       that margin belongs to the same caption as the cell right before it. */
    .transcript-subtitle-mode .transcript-cell::before {
        content: "";
        position: absolute;
        bottom: -0.625rem;
        left: -1rem;
        right: 0;
        border-bottom: 1px solid var(--color-border-subtle);
        opacity: 0;
        transition: opacity 0.12s ease-in-out;
        pointer-events: none;
    }
    .transcript-subtitle-mode .transcript-cell:hover::before,
    .transcript-subtitle-mode .transcript-gutter:hover + .transcript-cell::before {
        opacity: 1;
    }
    .transcript-cell-active {
        border-left-color: var(--color-brand-primary);
        border-left-width: 2px;
        padding-left: calc(1rem - 1px);
        background-color: color-mix(
            in srgb, var(--color-brand-primary) 7%, transparent
        );
    }
    /* A tint the same way, rather than the status colour at full strength:
       these sit behind body text that has to stay the easiest thing in the
       cell to read. The rule on the left is what names the state; the wash
       only says which caption it belongs to. */
    /* The caption the caret is in. After .transcript-cell-active, so the
       caption being edited wins when the recording happens to be playing
       the same one -- what the reader is doing beats what the player is
       doing. A quieter fill than the active tint, and the same 2px rule:
       the point is to say where the caret is without pulling the eye away
       from the text itself. */
    .transcript-cell-editing {
        border-left-color: var(--color-brand-primary);
        border-left-width: 2px;
        padding-left: calc(1rem - 1px);
        background-color: var(--color-bg-surface-alt);
    }
    .body--dark .transcript-cell-editing {
        background-color: var(--color-bg-surface);
    }
    .transcript-cell-invalid {
        border-left-color: var(--color-status-error-border);
        background-color: color-mix(
            in srgb, var(--color-status-error-border) 10%, transparent
        );
    }
    .transcript-cell-highlighted {
        border-left-color: var(--color-warning-border);
        background-color: color-mix(
            in srgb, var(--color-warning-border) 14%, transparent
        );
    }
    /* The same mixes over a dark page land far fainter than over a light
       one -- the tint is being mixed into the page behind it, and there is
       much less of it there to lift. */
    .body--dark .transcript-cell-active {
        background-color: color-mix(
            in srgb, var(--color-brand-primary) 14%, transparent
        );
    }
    .body--dark .transcript-cell-invalid {
        background-color: color-mix(
            in srgb, var(--color-status-error-border) 18%, transparent
        );
    }
    .body--dark .transcript-cell-highlighted {
        background-color: color-mix(
            in srgb, var(--color-warning-border) 22%, transparent
        );
    }

    .transcript-time {
        display: flex;
        align-items: baseline;
        margin-bottom: 0.35rem;
    }
    .transcript-dash {
        padding: 0 0.5rem;
        color: var(--color-text-muted);
    }

    /* The caption's index -- in the same column the character counts are
       in, but its own row above them, level with the timing rather than
       the text: it names the caption itself, the same as the timing does,
       not any one line of it.

       A box exactly one .transcript-action tall, with the figure centred
       in it the same way the timing row centres its own contents -- that
       height is what .transcript-subtitle-time actually renders at, since
       .transcript-cell-actions reserves it even hidden. Centring rather
       than a 1.5rem line-height on a 0.8rem figure: half-leading puts a
       short figure at the top of a line box that tall, which read as the
       index sitting a few pixels above the timestamp beside it. The two
       rows still have to agree in height, or the counts below drift out of
       line with the text. */
    .transcript-subtitle-index {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        height: 1.5rem;
        /* 0.8rem plus a pixel, the same as the timestamp it sits level
           with -- the two are read together and stay the same size. */
        font-size: 0.8625rem;
        line-height: 1;
        color: var(--color-text-muted);
        opacity: 0.7;
        /* Renumbering runs through this column as captions are split and
           merged, so the figures keep one width rather than shifting the
           margin as they change. */
        font-variant-numeric: tabular-nums;
    }

    /* One row per line, each carrying that line's character count and
       lined up with the text line it belongs to. */
    .transcript-subtitle-counts {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
    }
    .transcript-count-row {
        display: flex;
        align-items: baseline;
        gap: 0.35rem;
        /* Has to equal .transcript-text's own line-height (1.6 times its
           font-size, 1.0625rem) in absolute terms, or a row drifts away
           from the text line it belongs to. */
        line-height: 1.7rem;
    }
    /* A plain figure in the margin -- no box around it. Tabular figures so
       a count keeps one width as the number changes under the reader's
       typing. */
    .transcript-count {
        color: var(--color-text-muted);
        font-size: 0.7rem;
        font-variant-numeric: tabular-nums;
    }
    .transcript-count-exceeded {
        color: var(--color-text-danger);
    }

    /* padding-left is left at the base rule's own 1rem (and
       .transcript-cell-active's calc(1rem - 1px) needs no override to
       match), so the divider sits the same distance from the text a
       transcription's does -- the timing row and text are the cell's only
       content and need nothing beyond the plain block layout the base
       rule already gives it. */
    /* The timing sits over the caption it belongs to, not over the margin's
       character counts, so it is a heading inside the cell rather than
       something the margin carries -- the margin has no heading of its own
       to match against, the same as the base rule's speaker. */
    .transcript-subtitle-content {
        display: flex;
        flex-direction: column;
    }
    /* The timing and the four caption actions sit on one row -- both act
       on this specific caption, not the block of text below it.

       A grid rather than a flex row so the actions land on the row's true
       centre: the timing takes the first column, the actions the middle
       one, and the third is left empty purely to balance the first. Equal
       auto margins on a flex item would only centre them in whatever space
       the timing left over, which put them noticeably right of centre. */
    .transcript-subtitle-time {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        margin-bottom: 0.6rem;
    }
    .transcript-subtitle-timing {
        display: flex;
        align-items: baseline;
    }
    /* Edited directly, in place, rather than through a dialog: a plain
       input styled to read as the same clickable-looking label it replaces,
       text selection and a caret instead of the pointer cursor a label
       would have. Sized to its own value rather than a fixed character
       count -- ch is the width of "0", not of the punctuation in a
       timestamp, and a fixed width wide enough for the digits left slack
       after the narrower characters that made the space either side of the
       dash uneven. */
    .transcript-time-input {
        field-sizing: content;
        border: none;
        outline: none;
        padding: 0;
        background: transparent;
        font: inherit;
        /* A timestamp is read digit by digit against the one above it, so
           it is set in figures of one width in a face meant for them.
           "zero" 0 turns off a slashed zero wherever the face offers one
           as a feature rather than as its only glyph -- the stack itself
           is what rules the rest out. Semibold because Courier is a light
           face and a timestamp is set small. */
        font-family: var(--font-mono);
        font-feature-settings: "zero" 0;
        font-weight: 600;
        font-size: 0.8625rem;
        line-height: 1.2;
        font-variant-numeric: tabular-nums;
        color: var(--color-brand-primary);
        cursor: text;
    }
    /* An underline read as a link -- this is a field. Hovering gives it the
       box it will be edited in, and focus states it outright, which is also
       the only visible sign a reader tabbing through the captions has of
       where they are. Padding is compensated by an equal negative margin so
       neither state moves the timing along the row. */
    .transcript-time-input:hover,
    .transcript-time-input:focus {
        padding: 1px 4px;
        margin: -1px -4px;
        border-radius: 4px;
        background-color: var(--color-bg-surface-alt);
    }
    .transcript-time-input:focus {
        box-shadow: 0 0 0 2px var(--color-brand-primary);
    }

    /* Split this caption at the caret, add one after it, merge it with the
       next, or delete it outright -- subtitles only. Quiet until the
       caption is hovered or a reader tabs into one of the icons, so a long
       list of captions is not lined with icons -- an ordinary flex item on
       the timing row rather than a floating overlay, so hidden still
       reserves its own width instead of the row reflowing under it as it
       fades in and out. Sits in the middle column of the timing row's own
       grid (see .transcript-subtitle-time), which is what puts it on the
       row's true centre rather than the centre of whatever space the
       timing left over. */
    .transcript-cell-actions {
        display: flex;
        gap: 2px;
        /* A tray of its own -- surface, hairline, fully rounded -- rather
           than four loose icons fading in over the caption behind them.
           Reserved even while hidden, the same as before: it is an
           ordinary item on the timing row's grid, so the row does not
           reflow as it appears. Deliberately not positioned; see the
           timing row's own note. */
        padding: 2px;
        border: 1px solid var(--color-border-subtle);
        border-radius: 999px;
        background-color: var(--color-bg-surface);
        /* Cancels exactly what the tray's own padding and border add (2px
           + 1px each side), so the timing row still stands one
           .transcript-action tall. The row's height is what the margin's
           index is lined up against, and the counts below it follow from
           that -- letting the tray grow the row by 6px would slide every
           count out of line with the text line it belongs to. */
        margin: -3px 0;
        opacity: 0;
        transition: opacity 0.12s ease-in-out;
    }
    .transcript-cell:hover .transcript-cell-actions,
    .transcript-gutter:hover + .transcript-cell .transcript-cell-actions,
    .transcript-cell-actions:focus-within {
        opacity: 1;
    }
    .transcript-action {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 1.5rem;
        height: 1.5rem;
        border-radius: 50%;
        color: var(--color-text-muted);
        cursor: pointer;
        transition: color 0.12s ease-in-out, background-color 0.12s ease-in-out;
    }
    /* Each a distinct colour for its own kind of action, rather than the
       four sharing one -- split in the same blue as the clickable timestamp
       it acts relative to, merge in the amber a caption losing its own
       identity into a neighbour warrants, creation (add) in the green
       already used for success, destructive (delete) in the same red as
       every other danger state. */
    .transcript-action-split:hover {
        color: var(--color-brand-primary);
        background-color: var(--color-bg-surface-alt);
    }
    .transcript-action-merge:hover {
        color: var(--color-severity-maint-icon);
        background-color: var(--color-severity-maint-bg);
    }
    .transcript-action-add:hover {
        color: var(--color-status-ok-border);
        background-color: var(--color-status-ok-bg);
    }
    .transcript-action-delete:hover {
        color: var(--color-text-danger);
        background-color: var(--color-status-error-bg);
    }

    /* The reading surface. Generous leading, because this is read in long
       stretches rather than scanned line by line. */
    .transcript-text {
        /* A shade over the interface's own size. This is read in long
           stretches and corrected word by word, so it is the one place in
           the app that is not set at the size of a form label. Anything
           tied to it moves with it -- .transcript-count-row's line-height
           in the margin above all. */
        font-size: 1.0625rem;
        /* Read in long stretches, but corrected line by line -- 1.85 was
           book leading and pushed a third of the captions off the screen.
           .transcript-count-row's own line-height has to move with this;
           see its note. */
        line-height: 1.6;
        /* An empty block still has to be a line the caret can sit on. */
        min-height: 1.6em;
        white-space: pre-wrap;
        overflow-wrap: break-word;
        outline: none;
        /* This is editable text, and the pointer is the first thing that
           says so -- it stayed an arrow over the whole editor before. */
        cursor: text;
    }

    /* The word under the playhead. Marked with an attribute rather than a
       class, because the spans carry a bound :class for the review marking and
       Vue rewrites that list whenever it patches them.

       Background only: padding or a border would shift the text as the
       highlight travels along the line. */
    .transcript-text [data-current] {
        background-color: var(--color-playing-bg);
        border-radius: 2px;
        box-shadow: 0 0 0 1px var(--color-playing-bg);
    }

    /* Speaker menu, anchored under the label it belongs to. Fixed, so it is
       positioned from the label's own screen position and is not clipped by
       the scrolling transcription. */
    .speaker-menu {
        position: absolute;
        z-index: 9500;
        min-width: 11rem;
        padding: 0.25rem 0;
        border-radius: 4px;
        background-color: var(--color-bg-surface);
        border: 1px solid var(--color-border-subtle);
        box-shadow: 0 4px 14px var(--color-shadow-medium);
        font-size: 0.95rem;
    }
    .speaker-menu-add,
    .speaker-menu-row {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.45rem 0.75rem;
        cursor: pointer;
    }
    .speaker-menu-add {
        border-bottom: 1px solid var(--color-border-subtle);
        justify-content: space-between;
    }
    .speaker-menu-add:hover,
    .speaker-menu-row:hover {
        background-color: var(--color-bg-surface-alt);
    }
    /* The speaker this block already has. */
    .speaker-menu-row-current {
        background-color: var(--color-bg-surface-alt);
        font-weight: 600;
    }
    .speaker-menu-name {
        flex: 1 1 auto;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .speaker-menu-icon {
        flex: 0 0 auto;
        color: var(--color-text-muted);
        opacity: 0.55;
    }
    .speaker-menu-icon:hover {
        opacity: 1;
        color: var(--color-text-primary);
    }
    .speaker-menu-remove:hover {
        color: var(--color-text-danger);
    }

    .transcript-dialog {
        min-width: 22rem;
    }

    /* ── Validation report ── */
    /* Every caption in the report is a row that jumps to it, so it says as
       much before it is clicked. */
    .validation-issue {
        cursor: pointer;
        padding: 0.35rem 0.5rem;
        border-radius: 6px;
        transition: background-color 0.12s ease-in-out;
    }
    .validation-issue:hover {
        background-color: var(--color-bg-surface-alt);
    }

    /* ── Speech strip ── */
    /* Where someone is talking, under the video. The colours are stated as
       custom properties because the canvas cannot read a stylesheet: the
       component asks for these by name at draw time, which is also what
       lets dark mode change them without the component knowing. */
    .speech-timeline {
        /* Speech along the top in the brand blue; the captions below it as
           grey brackets, with the one being played or edited in the same
           blue. The two are never in the same row and a bracket is not a
           bar, so sharing a colour does not blur them together. */
        /* Silence: a shade darker than a hairline border, or the stretches
           between speech read as nothing being drawn there at all. */
        --timeline-ground: var(--color-border);
        --timeline-speech: var(--color-brand-primary);
        --timeline-caption: var(--color-text-tertiary);
        --timeline-caption-playing: var(--color-brand-primary);
        --timeline-caption-current: var(--color-brand-primary);
        /* The caption numbers. The text colour, not the bracket's own: in a
           bracket grey they were on the strip without being readable. */
        --timeline-label: var(--color-text-primary);
        --timeline-void: var(--color-bg-surface-hover);
        --timeline-playhead: var(--color-text-danger);
        position: relative;
        width: 100%;
        height: 4.5rem;
        margin-top: 0.5rem;
        border-radius: 6px;
        background-color: var(--color-bg-surface-alt);
        cursor: pointer;
    }
    .speech-timeline canvas {
        display: block;
        width: 100%;
        height: 100%;
    }
    .body--dark .speech-timeline {
        background-color: var(--color-bg-surface-alt);
    }

    /* What is under the pointer -- the time, whether anyone is talking
       there, and which caption covers it. A canvas has no elements to hang
       a tooltip on, so the strip works this out itself and draws it here.
       Anchored to the pointer and never taking one: it would otherwise sit
       between the reader and the strip they are trying to click. */
    .speech-timeline-readout {
        position: absolute;
        bottom: calc(100% + 0.25rem);
        transform: translateX(-50%);
        z-index: 10;
        padding: 2px 6px;
        border-radius: 4px;
        background-color: var(--color-bg-surface);
        border: 1px solid var(--color-border-subtle);
        box-shadow: 0 2px 6px var(--color-shadow-medium);
        font-size: 0.75rem;
        color: var(--color-text-primary);
        white-space: nowrap;
        pointer-events: none;
        font-variant-numeric: tabular-nums;
    }

    /* The strip draws four things and names none of them, so the key does.
       Small, muted, and directly under what it describes. */
    .speech-timeline-legend {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.75rem;
        margin-top: 0.35rem;
        font-size: 0.75rem;
        color: var(--color-text-secondary);
    }
    .speech-timeline-key {
        display: inline-flex;
        align-items: center;
        gap: 0.3rem;
    }
    /* Reads as part of the key -- what the strip is and what can be done to
       it -- so it stays with it on the left. */
    .speech-timeline-hint {
        color: var(--color-text-muted);
    }

    /* Which minute of the recording is on the strip. A different question
       from the key's, so it sits at the far end of the row rather than in
       the queue behind it. */
    .speech-timeline-range {
        margin-left: auto;
        color: var(--color-text-secondary);
        font-variant-numeric: tabular-nums;
    }

    /* While a caption is being dragged the pointer owns it wherever it
       goes, and nothing on the way should look selectable. */
    .speech-timeline-dragging {
        user-select: none;
        cursor: grabbing !important;
    }
    .speech-timeline-swatch {
        display: inline-block;
        border-radius: 1px;
    }
    /* Each swatch is the shape the strip draws, not a uniform square: a
       caption break is a thin full-height line there, and so is the
       playhead, and reading the key should not need a second translation. */
    .speech-timeline-swatch-speech {
        width: 0.85rem;
        height: 0.4rem;
        border-radius: 2px;
        background-color: var(--color-brand-primary);
    }
    .speech-timeline-swatch-silence {
        width: 0.85rem;
        height: 2px;
        background-color: var(--color-border);
    }
    /* Drawn as the bracket it is on the strip, not as a block: which end
       of a caption a boundary belongs to is the whole point of the shape. */
    .speech-timeline-swatch-caption {
        width: 0.7rem;
        height: 0.7rem;
        border: 2px solid var(--color-brand-primary);
        border-left-width: 3px;
        border-right-width: 3px;
        border-top: 2px solid var(--color-brand-primary);
        border-bottom: 2px solid var(--color-brand-primary);
        background: transparent;
        border-radius: 1px;
    }
    .speech-timeline-swatch-playhead {
        width: 2px;
        height: 0.75rem;
        background-color: var(--color-text-danger);
    }

    /* ── SRT editor controls under the video ── */
    /* The switches on one row, what they mark under it -- grouped by what
       each control affects, without a heading naming each group. */
    .editor-settings {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        padding: 0.75rem 0 0.25rem;
    }
    /* ── Theme-aware text utilities ── */
    .text-theme-primary {
        color: var(--color-text-primary);
    }
    .text-theme-secondary {
        color: var(--color-text-secondary);
    }
    .text-theme-muted {
        color: var(--color-text-muted);
    }

    /* ── Help dialog sections ── */
    .help-dialog-card {
        background: linear-gradient(to bottom, var(--color-help-bg-start) 0%, var(--color-help-bg-end) 100%);
    }
    .help-about-card {
        background-color: var(--color-help-about-bg);
        border-left: 4px solid var(--color-help-accent-border);
    }
    .help-about-icon {
        color: var(--color-help-about-icon);
    }
    .help-privacy-card {
        background-color: var(--color-help-privacy-bg);
    }
    .help-privacy-icon {
        color: var(--color-help-privacy-icon);
    }
    .help-support-card {
        background-color: var(--color-help-support-bg);
    }
    .help-support-icon {
        color: var(--color-help-support-icon);
    }
</style>
"""

# Keep backward-compatible alias so existing `from utils.common import default_styles`
# and `from utils.styles import default_styles` both work during migration.
default_styles = theme_styles

# ---------------------------------------------------------------------------
# Chart color tokens for Plotly (keyed by light / dark)
# ---------------------------------------------------------------------------

chart_colors = {
    "light": {
        "bar_current": "#4F46E5",
        "bar_previous": "#10B981",
        "bar_primary": "#082954",
        "bar_secondary": "#4caf50",
        "line_cpu": "#3b82f6",
        "line_memory": "#10b981",
        "line_gpu": "#8b5cf6",
        "line_gpu_mem": "#f59e0b",
        "fill_cpu": "rgba(59, 130, 246, 0.1)",
        "fill_memory": "rgba(16, 185, 129, 0.1)",
        "fill_gpu": "rgba(139, 92, 246, 0.1)",
        "fill_gpu_mem": "rgba(245, 158, 11, 0.1)",
        "wow_positive": "#2e7d32",
        "wow_negative": "#c62828",
        "wow_neutral": "#757575",
        "hourly_bar": "#1565c0",
        "heatmap_zero": "#f5f5f5",
        "heatmap_low": "#bbdefb",
    },
    "dark": {
        "bar_current": "#818cf8",
        "bar_previous": "#34d399",
        "bar_primary": "#5b9bd5",
        "bar_secondary": "#66bb6a",
        "line_cpu": "#60a5fa",
        "line_memory": "#34d399",
        "line_gpu": "#a78bfa",
        "line_gpu_mem": "#fbbf24",
        "fill_cpu": "rgba(96, 165, 250, 0.15)",
        "fill_memory": "rgba(52, 211, 153, 0.15)",
        "fill_gpu": "rgba(167, 139, 250, 0.15)",
        "fill_gpu_mem": "rgba(251, 191, 36, 0.15)",
        "wow_positive": "#66bb6a",
        "wow_negative": "#ef5350",
        "wow_neutral": "#b0b0b0",
        "hourly_bar": "#42a5f5",
        "heatmap_zero": "#1e1e1e",
        "heatmap_low": "#1a3a5c",
    },
}

# ---------------------------------------------------------------------------
# Severity styles (used by announcement banners)
# ---------------------------------------------------------------------------

severity_styles = {
    "info": {
        "css_class": "severity-info",
        "icon": "campaign",
        "icon_color": "var(--color-severity-info-icon)",
        "dismissible": True,
    },
    "maintenance": {
        "css_class": "severity-maintenance",
        "icon": "construction",
        "icon_color": "var(--color-severity-maint-icon)",
        "dismissible": True,
    },
    "major_incident": {
        "css_class": "severity-major_incident",
        "icon": "crisis_alert",
        "icon_color": "var(--color-severity-incident-icon)",
        "dismissible": False,
    },
}

# ---------------------------------------------------------------------------
# Menu style constants (used by page_init drawer)
# ---------------------------------------------------------------------------

menu_item_style = (
    "display: flex; align-items: center; gap: 12px; padding: 10px 16px;"
    " cursor: pointer; font-size: 1.05rem;"
    " transition: background-color 0.15s; width: 100%;"
    " white-space: nowrap; overflow: hidden;"
)

menu_active_style = (
    " background-color: var(--color-bg-surface-hover); font-weight: 600;"
)

# ---------------------------------------------------------------------------
# Table column definitions
# ---------------------------------------------------------------------------

jobs_columns = [
    {
        "name": "filename",
        "label": "Filename",
        "field": "filename",
        "align": "left",
        "classes": "text-weight-medium",
    },
    {
        "name": "job_type",
        "label": "Type",
        "field": "job_type",
        "align": "left",
        "classes": "text-weight-medium",
    },
    {
        "name": "created_at",
        "label": "Created",
        "field": "created_at",
        "align": "left",
    },
    {
        "name": "update_at",
        "label": "Modified",
        "field": "updated_at",
        "align": "left",
    },
    {
        "name": "deletion_date",
        "label": "Scheduled deletion",
        "field": "deletion_date",
        "align": "left",
    },
    {
        "name": "status",
        "label": "Status",
        "field": "status",
        "align": "left",
    },
    {"name": "action", "label": "Action", "field": "action", "align": "center"},
]

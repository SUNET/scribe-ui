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
        --color-bg-page: #ffffff;
        --color-bg-surface: #ffffff;
        --color-bg-surface-alt: #f5f5f5;
        --color-bg-surface-hover: #e0e0e0;

        --color-brand-primary: #082954;
        --color-brand-accent: #d3ecbe;

        --color-text-primary: #000000;
        --color-text-secondary: #374151;
        --color-text-tertiary: #666666;
        --color-text-muted: #757575;
        --color-text-on-brand: #ffffff;

        --color-border: #000000;
        --color-border-subtle: #e0e0e0;
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
        --color-btn-delete-border: #000000;

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
        --color-bg-surface: #000000;
        --color-bg-surface-alt: #1a1a1a;
        --color-bg-surface-hover: #3a3a3a;

        --color-brand-primary: #5b9bd5;
        --color-brand-accent: #3d7a2e;

        --color-text-primary: #ffffff;
        --color-text-secondary: #ffffff;
        --color-text-tertiary: #e0e0e0;
        --color-text-muted: #e0e0e0;
        --color-text-on-brand: #ffffff;

        --color-border: #555555;
        --color-border-subtle: #3a3a3a;
        --color-border-disabled: #444444;

        --color-bg-disabled: #333333;

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

        --color-header-bg: #1e1e1e;

        --color-help-bg-start: #1e1e1e;
        --color-help-bg-end: #252525;
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

    /* ── Page background ── */
    body {
        background-color: var(--color-bg-page);
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

    /* ── Editor toolbar buttons (flat, no border, subtle bg in dark mode) ── */
    .editor-btn {
        border: none !important;
    }
    .editor-toolbar-btn {
        min-width: 130px !important;
    }
    .body--light .q-btn.editor-btn {
        background-color: #ffffff !important;
        border: 1px solid var(--color-border-subtle) !important;
        color: #000000 !important;
    }
    .body--light .q-btn.editor-btn:hover {
        background-color: var(--color-bg-surface-alt) !important;
    }
    .body--light .q-btn.editor-btn .q-icon,
    .body--light .q-btn.editor-btn .q-btn__content {
        color: #000000 !important;
    }
    .body--light .q-btn.editor-btn[disabled] {
        background-color: #ffffff !important;
        border: 1px solid var(--color-border-subtle) !important;
        opacity: 0.4;
    }
    .body--dark .q-btn.editor-btn {
        background-color: var(--color-bg-page) !important;
        border: 1px solid var(--color-border-subtle) !important;
        color: var(--color-text-primary) !important;
    }
    .body--dark .q-btn.editor-btn:hover {
        background-color: var(--color-bg-surface-alt) !important;
    }
    .body--dark .q-btn.editor-btn .q-icon,
    .body--dark .q-btn.editor-btn .q-btn__content {
        color: var(--color-text-primary) !important;
    }
    .body--dark .q-btn.editor-btn[disabled] {
        background-color: var(--color-bg-page) !important;
        border: 1px solid var(--color-border-subtle) !important;
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

    /* ── Editor: splitter cards use page background ── */
    .body--dark .q-splitter .q-card {
        background-color: var(--color-bg-page) !important;
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

    /* Each switch wears the colour of the marking it turns on, so the control
       and the words it affects read as one thing. Quasar draws both the track
       and the thumb of a switch that is on in currentColor, so setting the
       colour is all it takes. The class goes on the switch itself, which puts
       it ahead of Quasar's own light and dark rules for the same element. */
    .q-toggle.review-switch .q-toggle__inner--truthy {
        color: var(--color-review-accent);
    }
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
    }
    .video-subtitle-overlay {
        position: absolute;
        left: 50%;
        /* A fixed offset, not a percentage of the frame's own height --
           the native control bar's own height is fixed too, so a percentage
           shrinks below it on a short or wide video and the overlay ends up
           drawn over the seek bar, hiding it rather than sitting above it. */
        bottom: 3rem;
        transform: translateX(-50%);
        max-width: 90%;
        padding: 0.35rem 0.75rem;
        background-color: rgba(0, 0, 0, 0.7);
        color: #fff;
        font-size: 1rem;
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
        row-gap: 1.25rem;
        outline: none;
        max-width: 60rem;
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
        row-gap: 1.75rem;
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
    }
    .transcript-cell-invalid {
        border-left-color: var(--color-status-error-border);
        background-color: var(--color-status-error-bg);
    }
    .transcript-cell-highlighted {
        border-left-color: var(--color-warning-border);
        background-color: var(--color-warning-bg);
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
       not any one line of it. line-height matches .transcript-action's own
       height (1.5rem) rather than the plain text's, since that is what
       actually decides .transcript-subtitle-time's rendered height --
       .transcript-cell-actions reserves that height even hidden -- and the
       two rows have to agree, or the counts below drift out of line with
       the text below. */
    .transcript-subtitle-index {
        font-size: 0.8rem;
        line-height: 1.5rem;
        color: var(--color-text-muted);
        opacity: 0.7;
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
        /* Has to equal .transcript-text's own line-height (1.85 times its
           font-size, 1rem -- the same size a transcription's own text
           is) in absolute terms, or a row drifts away from the text line
           it belongs to. */
        line-height: 1.85rem;
    }
    .transcript-count {
        color: var(--color-text-muted);
        font-size: 0.7rem;
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
        font-size: 0.8rem;
        line-height: 1.2;
        font-variant-numeric: tabular-nums;
        color: var(--color-brand-primary);
        cursor: text;
    }
    .transcript-time-input:hover,
    .transcript-time-input:focus {
        text-decoration: underline;
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
        font-size: 1rem;
        line-height: 1.85;
        /* An empty block still has to be a line the caret can sit on. */
        min-height: 1.85em;
        white-space: pre-wrap;
        overflow-wrap: break-word;
        outline: none;
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

    /* ── SRT editor info panel ── */
    .srt-info-panel {
        background-color: var(--color-bg-surface-alt);
    }
    .body--dark .srt-info-panel {
        background-color: var(--color-bg-page);
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

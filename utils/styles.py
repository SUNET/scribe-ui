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

# ---------------------------------------------------------------------------
# CSS custom properties + class definitions
# ---------------------------------------------------------------------------

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
    .editor-caption-btn {
        min-width: 100px !important;
        flex: 1 1 0;
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

    /* ── SRT editor caption card states ── */
    .caption-card-invalid {
        border-color: var(--color-status-error-border) !important;
        background-color: var(--color-status-error-bg) !important;
    }
    .caption-card-invalid:hover {
        border-color: var(--color-text-danger) !important;
    }
    .caption-card-highlighted {
        border-color: var(--color-warning-border) !important;
        background-color: var(--color-warning-bg) !important;
    }
    .caption-card-highlighted:hover {
        border-color: var(--color-warning-icon) !important;
    }
    .caption-card-selected-highlighted {
        border-color: var(--color-warning-border) !important;
        background-color: var(--color-warning-bg) !important;
    }
    .caption-card-selected-highlighted:hover {
        border-color: var(--color-warning-icon) !important;
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

menu_active_style = " background-color: var(--color-bg-surface-hover); font-weight: 600;"

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

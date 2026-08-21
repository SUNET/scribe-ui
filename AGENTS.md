# Agent Guidelines — transcribe-ui

## Project overview

NiceGUI-based web frontend for Sunet Scribe (transcription service). Requires Python ≥ 3.13. Package manager: `uv` (see `uv.lock`).

## Architecture

- **Framework**: NiceGUI (Python-based web UI built on Quasar/Vue)
- **Entry point**: `main.py` — registers `@ui.page("/")` and `/logout`, handles OIDC auth callback and encryption-password bootstrap
- **Pages**: `pages/` — `home.py`, `admin/` (package, one module per admin page: `analytics.py`, `announcements.py`, `customers.py`, `groups.py`, `health.py`, `rules.py`, `shared.py`, `users.py`), `srt.py`, `user.py`, `status.py`. Each top-level page module exports a `create()` function called from `main.py`; `pages/admin/__init__.py` imports the admin submodules for their `@ui.page` side effects and re-exports `create` from `groups.py` for `/admin` itself.
- **Utilities**: `utils/` — split by concern:
  - `helpers.py` — `storage_encrypt`/`storage_decrypt` (AES-256-GCM), filename sanitisation, encryption-password set/verify/reset, customer/realm CRUD
  - `token.py` — `get_auth_header`, `token_refresh`, `get_user_info`, `get_admin_status`, `get_bofh_status`
  - `common.py` — `page_init()` and shared UI scaffolding
  - `settings.py` — pydantic `BaseSettings` loaded from `.env` via `get_settings()` (lru-cached)
  - `caption.py` (`SRTCaption`), `video.py`, `undo_redo.py`, `customer.py`, `group.py`, `crypto.py`, `styles.py`
  - The SRT/transcript editor is split across several files rather than one monolith — see "Editor split" below.
- **DB / analytics**: `db/analytics.py` — async `httpx` calls to backend API
- **Static assets**: `static/` — logos, favicon
- **Tests**: `tests/` — pytest with `nicegui.testing.user_plugin`; run with `uv run pytest` (or `.venv/bin/python -m pytest`)
- **Container**: `Dockerfile` at repo root

### Editor split (`utils/srt*.py`, `utils/transcript_editor.*`)

`pages/srt.py` opens one editor regardless of `data_format` — `TranscriptEditor` (`utils/transcript_editor.py`), a single `contenteditable` (Vue component `transcript_editor.js`) — backed by one `SRTEditor` (`utils/srt.py`) so saving, exporting, and word/review data work identically for both a transcription and a set of subtitles. `SRTEditor.render_override` points at `TranscriptEditor.refresh`, which is what `refresh_display()` calls; `SRTEditor.on_select` points at `TranscriptEditor.scroll_to`, which is what `select_caption()` (search, autoscroll) calls to bring a caption into view. The component takes a `subtitleMode` prop (`self.editor.data_format == "srt"`, set once in `TranscriptEditor.build()`) that swaps the speaker margin for a character-count guideline, one row per line (`caption_line_counts()`), each row lined up with its text line the same way the base rule lines the speaker up with the text. Those counts are redrawn as the caption is typed into, from the DOM text itself (`computeLineCounts()`, mirroring `caption_line_counts()` — same guideline, same tooltip wording, `characterLimit`/`maxSubtitleLines` sent down as props rather than duplicated as constants) into a `liveCounts` map keyed by block id, since `set_text()` deliberately does not re-render the block being typed into (it would move the caret) and so nothing else would keep the counts current; a real render (split/merge/undo) clears the map so the server's own answer takes back over — the margin is a column (`.transcript-subtitle-mode .transcript-gutter`, `flex-direction: column`) rather than the base rule's row, the caption's index heading it at the same height as the cell's timing row (`.transcript-subtitle-index`, `line-height: 1.5rem` to match `.transcript-action`'s own height — see below — rather than the shorter plain text beside it, since that is what actually decides the timing row's rendered height) with the per-line counts stacked below (`.transcript-subtitle-counts`), a `gap` matching `.transcript-subtitle-time`'s own `margin-bottom` keeping the first count aligned with the text's first line the same way the index lines up with the timing above it. The index names the caption itself, in the same column the counts are in but its own row, not folded into the first count row the way it once was. The timing itself sits in the cell, over the text it times rather than over the margin's counts, as two plain `<input>`s (`.transcript-time-input`) edited directly — no dialog, in either mode; a typed value is read back by `parse_time_label()` and applied via `retime()`/`apply_time()`, and a value that does not parse (or an end before the start) is refused and the input reverted, forced by marking the block dirty the same way a text edit does so Vue's own diff cannot skip a prop that ends up unchanged. A transcription's own `.transcript-time` uses the same input pair, just outside `.transcript-subtitle-content`'s flex wrapper (stacking the timing above the text, which only subtitleMode needs — a transcription's own `.transcript-time` and `.transcript-text` sit as plain siblings instead). subtitleMode also turns on per-caption split/merge/add/delete actions (`.transcript-cell-actions`), riding the same timing row rather than sitting beside the text below — quiet (opacity 0) until the caption is hovered or a reader tabs into one, an ordinary flex item so hidden still reserves its own width and the row does not reflow as they fade in and out; centred in the row's own leftover space with `margin: 0 auto` — equal auto margins on a flex item split whatever room its siblings (the timing) left, rather than pushing it against either edge (`splitAt()`, mouse equivalent of Ctrl/Cmd+Enter — prefers the caret when it is already in that caption, otherwise the middle of its text; merge reuses the existing `mergeblock`/`direction: "next"` event Delete-at-the-end already emits, no new server-side method) — a transcription has speakers and no length limit; a subtitle has the opposite. Structural edits (split/merge/add/delete/speaker/timing) are reported to the server rather than left to the browser, which owns the block structure and sends a fresh set back. `delete()` refocuses a neighbouring caption afterward (the one that took its place, or the new last one) the same way `add_after()` already focuses the caption it starts — refresh() removes the deleted caption's own DOM node, and a caret that was inside it does not survive that: left alone, the browser collapses the invalidated selection to the very start of the contenteditable, which reads as the cursor jumping to the top of the page. The same collapse hits a block that was typed into and never got a real render before one finally arrived (undo, most of all — see the revision watcher's own comment): changing that block's key so Vue rebuilds it rather than patches it, needed so undo's own text actually shows, throws away whatever element the caret was anchored to. The revision watcher reads the caret before that happens and, if it was in the block about to be rebuilt, restores it afterward with `placeCaretAt()` — the inverse of `caret()`'s own offset, walking the fresh (server-authoritative, so never carrying `plainText`'s placeholder) text nodes directly, falling back to the block's end if the caption shrank out from under it, and carrying the block's own change in length along with the offset before that — undo (most of all) changes the very text the offset was measured against, and restoring it unchanged into a block that shrank landed past the word the caret was actually at, into whatever now sat where the old, larger offset pointed. `merge()` refocuses the surviving caption at the seam between the two texts for the same reason `delete()` does — merging previous removes the very block the caret was in, and merging next is more useful landing exactly where the two met than wherever the caret already was — `focus()`/`focus_block()`/`focusBlock()` all now take an optional character offset (default 0, unchanged for `add_after()`'s own use) rather than always collapsing to a block's start, `focusBlock()` itself just handing that off to `placeCaretAt()`. `merge_with_previous()`/`merge_with_next()` only actually join the two texts with `"\n"` when both have something to separate — "Add caption after" followed straight away by Backspace merges the empty caption it just started back into its neighbour, and an unconditional join left that neighbour with a trailing blank line it was never typed into. `split()`'s own mid-text branch likewise refocuses the start of the new second block afterward, same as pressing Enter mid-sentence anywhere else — unlike a merge's removal the first block keeps its own DOM node here, so this is about landing where the reader expects rather than avoiding a broken caret; skipped when split_caption refuses the split (nothing on one side of the caret) since no second block exists to focus then. Enter means the same thing in both modes: a bare Enter inserts a literal line break (`insertLineBreak()`, spliced in by hand — `document.execCommand("insertText", ..., "\n")` looked right but corrupted surrounding content in testing); a break landing at the true end of the caption's text also gets a trailing zero-width space, since a browser reserves no line box, and so no navigable caret, for a forced break with nothing real after it — `plainText()` strips that character back out wherever a block's text is read for anything other than drawing it (`caret()`, the edit reported to the server), so it never reaches the saved caption. Splitting the caption (or block) moves to Ctrl/Cmd+Enter in both — a transcription used to keep plain Enter for splitting, but a speaker's own paragraph breaks need somewhere to go too, so it now matches subtitleMode instead of the caption/block distinction deciding this.

- `srt.py` — `SRTEditor` core: state, caption CRUD, undo/redo wiring (delegates to `undo_redo.py`), `parse_srt`/`parse_txt`.
- `srt_render.py` — validation (`validate_captions`, subtitle-only: line length and line count against `CHARACTER_LIMIT`/`MAX_SUBTITLE_LINES`) and the keyboard-shortcuts dialog. No longer draws anything itself — see above.
- `srt_review.py` — word-level review/edit marking shared by both formats (`retag_edits`, `review_runs`, confidence flagging).
- `srt_search.py`, `srt_export.py` — search panel and export dialog, shared by both formats.
- `transcript_editor.py` / `transcript_editor.js` — the editor itself, described above.

**Gotcha with `transcript_editor.js`:** NiceGUI registers a custom Vue component (`component="…js"`) once, at class-definition/import time, keyed by file content — a running server keeps serving the old JS until the *process* restarts, not just the browser. `ui.run(reload=True)` is on by default, but uvicorn's reload watcher only globs `*.py` by default, so an edit to this file was silently invisible to a running dev server. `main.py` now passes `uvicorn_reload_includes="*.py, *.js, *.vue"` so edits here trigger the same auto-reload `.py` changes do — if a JS fix still doesn't seem to apply, restart the server by hand and confirm that setting is intact.

## Key conventions

- All authenticated page handlers must call `page_init()` before accessing secret storage keys. `page_init` redirects to `/` when `_scribe_bk` missing in browser storage and refreshes the OIDC token.
- All API calls MUST be async — use `httpx.AsyncClient` (see `db/analytics.py`). Do not introduce blocking `requests` or sync `httpx` calls in new code; legacy sync calls in `utils/helpers.py` should be migrated when touched.
- API calls use `get_auth_header()` from `utils/token.py` for bearer-token auth.
- NiceGUI `ui.table` uses Quasar slot templates with `$parent.$emit('event_name', props.row)` for per-row actions.
- Dialog close on validation failure uses short-circuit pattern: `result and (dialog.close(), navigate)`.
- Use `match/case` statements (Python 3.13+).

## Security

This app holds session tokens, user PII, and an encryption password that gates backend-side data encryption. Treat security as a first-class concern in every change.

### Authentication & session

- Authentication is OIDC. The flow lives in `main.py` (`@ui.page("/")` and `/logout`).
- Every authenticated page handler MUST call `utils.common.page_init()` first. It:
  - redirects to `/` if `app.storage.browser["_scribe_bk"]` (browser key) is missing,
  - schedules `token_refresh()` on each page load and logs out on refresh failure by clearing `token`, `refresh_token`, and `encryption_password` from `app.storage.user`, then navigating to `OIDC_APP_LOGOUT_ROUTE`.
- Never read `app.storage.user["token"]` / `["encryption_password"]` without going through `page_init()` first.
- Authorization checks: `get_admin_status()`, `get_bofh_status()`, `get_user_status()` in `utils/token.py`. Admin pages must gate on these — do not infer privilege from UI state.

### Secret handling

- Browser-bound encryption: `storage_encrypt` / `storage_decrypt` in `utils/helpers.py` wrap `utils/crypto.py` (`AESGCM` + `HKDF` from `cryptography.hazmat`, base64-encoded ciphertext, random 12-byte nonce, AAD `b"scribe-secret"`).
- Key material = `app.storage.browser["_scribe_bk"]` ++ `settings.STORAGE_SECRET`. Salt = `get_browser_id()`. Never log, print, or echo any of these into UI text, error messages, or exceptions.
- Decryption failure intentionally clears `encryption_password` and redirects to `/` — preserve this fail-closed behavior; do not catch and continue.
- Any new value stored in `app.storage.user` that contains tokens, passwords, keys, or PII MUST go through `storage_encrypt`.
- `STORAGE_SECRET` default in `utils/settings.py` is a placeholder. Production deployments must override via `.env`. Never commit a real secret.

### Input handling

- Filenames coming from users or the API: pass through `sanitize_filename()` (strips `/ \ \x00 < > : " | ? *` and control chars, trims `. ` ).
- Any text rendered into NiceGUI: prefer `ui.label`/`ui.markdown` — avoid `ui.html` with untrusted input. If raw HTML is unavoidable, sanitise with a library like Bleach (`bleach.clean`) rather than ad-hoc regex.
- Validate at boundaries: API responses and form input. Internal helpers can trust their callers.
- Logs must use `user_id`, never usernames, email addresses, or other PII.

### Crypto rules

- Use the existing `utils/crypto.py` helpers. Do not roll new AES/HKDF code; do not switch to ECB, CBC-without-MAC, or PyCryptodome.
- Prefer the secure-by-default `cryptography` package (already a dep). For new crypto needs, evaluate Google Tink before bespoke code.
- Never hard-code keys, IVs, or salts. Nonces must be `os.urandom(12)` per encrypt call (already done by `encrypt_string`).

### Transport & external calls

- All outbound HTTP MUST use `httpx.AsyncClient` (see `db/analytics.py`). Set explicit timeouts. Do not disable TLS verification.
- Backend base URL comes from `settings.API_URL`. Do not concatenate user input into URLs; pass via `params=` so `httpx` quotes them.
- SSRF: if a feature ever fetches a user-supplied URL, block private/loopback ranges before connecting (e.g., an SSRF filter library) — there is no such code path today; flag any addition for review.

### Container & deps

- `Dockerfile` should not run as root in production; pin base image and pip-installed versions.
- Dependencies are tracked in `pyproject.toml` / `uv.lock`. Run `uv lock --upgrade` deliberately, review the diff, and prefer libraries from the "secure-by-default" list (Bleach, defusedxml, Tink) over hand-rolled equivalents.

## Word timings (`utils/srt_review.py`)

`SRTEditor` is `ReviewMixin, SearchMixin, ExportMixin, RenderMixin` composed onto the core defined in `utils/srt.py` (see "Editor split" above). `ReviewMixin.load_words()` takes the optional payload from `GET /api/v1/transcriber/{uuid}/words`:

```json
{"version": 1, "words": [{"t": "Hej", "s": 0.12, "e": 0.34, "c": 0.98}]}
```

- Anything with a different `version`, or an unparseable payload, is discarded — the editor must open normally without word data. Jobs transcribed before word timings existed have none.
- Words are flat and time-ordered, not tied to segments. `caption_words()` maps them onto a caption by time range (bisect on precomputed midpoints), so they survive splits, merges and renumbering. Never key word data by caption index.
- `split_caption(caption, cursor_position=..., text=...)` cuts at the caret and picks the timestamp from the silence between the two adjacent words. Without word data a caret split falls back to proportional; **a split with no caret must keep halving the caption**, which is what results predating this feature rely on.
- `c` is absent when the worker ran with `WORD_CONFIDENCE=false`. Gate the review controls on `editor.has_confidence`, not on the presence of `words`.
- The editor renders review/edit marking as structured runs (`review_runs()`, one dict per run: `t`/`flag`/`edit`/`s`/`e`), consumed directly by `transcript_editor.js`'s Vue template rather than as an HTML string — never build caption markup inline. `get_review_html()`/`review_backdrop_html()` produce the same marking as escaped HTML for callers outside the live editor (e.g. tests asserting on the marking itself); nothing in the UI renders them today.
- Live edit marking (the `[data-changed]` attribute `onInput` sets, styled green only under `.transcript-show-edits` — see `TranscriptBody.set_show_edits`, and `build()` syncing it from `editor.show_my_edits` before the first render, since that toggle is a saved preference and can already be on when the page loads) is a client-side stand-in for `review_runs()`'s own `edit` flag, needed because `set_text()` deliberately never re-renders the block being typed into. `spaceAtTail()` stops a space typed at a word's own tail from marking that word — the browser extends the same span for it, "nowhere else for it to go" — but the next *real* character removes that trailing whitespace, so `effectiveSpan()` remembers the crossing as `newWordBoundary` (a span+offset pair, forgotten if the caret ever dips back below it — editing the original word again) and, the moment real content exists past it, calls `splitNewWord()` to move that content into a new sibling span of its own before marking it — marking the original (shared) span would mark the old word too. A second space typed right after the first extends the boundary instead of splitting: there is still nothing but whitespace past it, so nothing to give a span of its own. The one place this reaches into the DOM directly rather than only reading it; safe because `dirty` already guarantees whatever shape it leaves gets discarded and rebuilt at the next real render regardless. `markChanged()` itself refuses to mark a span of pure whitespace no matter which path hands it one — `wordAt`/`effectiveSpan` both work at DOM element boundaries, not word boundaries, so a caret can legitimately land inside a separator's own span, and there is no word there to highlight. The mirror case — typing a new word in *before* an existing one, caret at the boundary between a separator and the word right after it — resolves into the separator's own tail too, the same way `spaceAtTail` exploits for the word-before-a-space case, but nothing here remembers a boundary across keystrokes the way `newWordBoundary` does, since the whitespace prefix never changes: `effectiveSpan()`'s `headMatch` branch (`/^(\s+)(\S+)$/` against the span, caret at its tail) fires and calls `splitNewWord()` on the very first real character, isolating the new word immediately rather than waiting for a second keystroke to cross anything. Splitting alone still leaves the new word flush against the one after it with nothing between them in the DOM — fine while the reader keeps typing, since nothing has been sent yet, but the debounced `flush()` 400ms out does not know that, and a natural pause mid-word sends the two run together (`"thereworld"`) as an undo-able state, with `retag_edits()` then correctly, if unhelpfully, marking that merged token as edited once undo lands on it. A synthetic space (a bare `Text` node, `this.syntheticSpace`) is appended right after the new word's span the same moment it is split off, so every flush from there on stays properly spaced even before the reader finishes typing a separator of their own; `spaceAtTail()` firing against that same span — the reader's own trailing space — retires it, so a real one and the synthetic one already standing in for it never both persist.

### Words flagged for review

The "Uncertain words" switch highlights words the model was least sure of; "Review sensitivity" (low/medium/high, default low) picks how far up the confidence range to flag, via `REVIEW_SENSITIVITY_*` in settings. Raising sensitivity must only ever flag more.

- **Every flagged word is marked identically** — one class, one shared tooltip. The score is not a calibrated probability, so it cannot support grading flagged words against each other, and the raw number is never shown anywhere.
- **The marking must not read as an error.** No red, and no wavy underline (that means spellcheck). It uses `--color-review-*`, a violet reserved for this and used nowhere else.
- The flagged counter comes from `flagged_word_count()` over the whole word list, and reports 0 while the switch is off. Anything that changes the switch or the sensitivity must call `update_flagged_count()`.

## Following the video (`TranscriptEditor.follow_video`, `pages/srt.py`)

`video.on("timeupdate", transcript.follow_video)` (`pages/srt.py`) drives two separate things from one server round trip, a linear scan of `editor.captions` for the one whose `[get_start_seconds(), get_end_seconds())` window contains the player's current time (`ui.run_javascript` reads `document.querySelector("video").currentTime` — timeupdate itself carries no position):

- The editor's own active-block highlight (`TranscriptBody.set_active` → `activeId` → `.transcript-cell-active`, and the scroll that follows it) — gated on `editor.autoscroll`, the "Follow audio"/"Autoscroll" switch.
- The subtitle overlay drawn over the video itself (`TranscriptEditor.set_overlay_label`/`_set_overlay_text`, subtitles only — `pages/srt.py` only creates and wires the label when `data_format == "srt"`, since a transcription's own blocks are a speaker's whole turn, not a short timed cue, and would cover half the frame) — **not** gated on `autoscroll`: it is a preview of what a viewer sees, wanted whether or not the reader also has the editor scrolling to follow along. Hidden (`set_visibility(False)`) between two captions or past the last one, the same as a real subtitle track would be. A plain `ui.label`, not `ui.html` — a caption's text is user content, not markup to trust — styled with `white-space: pre-line` (`.video-subtitle-overlay` in `utils/styles.py`) so a caption's own `"\n"` line breaks still render as separate lines. `.video-frame` gives the video's wrapping `div` a `position: relative` neither `ui.video` nor the card around it otherwise has, for the overlay's `position: absolute` to anchor against; `pointer-events: none` on the overlay keeps it from swallowing clicks meant for the native controls or a click-to-pause anywhere else on the frame. `bottom` is a fixed `3rem`, not a percentage of the frame's own height -- a percentage once put the overlay on top of the native control bar (a fixed height itself) on a short or wide video, hiding the seek bar underneath its own opaque background rather than sitting above it.

There is no bisect index over caption time windows the way `caption_words()` has one over word midpoints (`utils/srt_review.py`) — `follow_video` re-scans the full caption list on every tick, which is fine at typical caption-list sizes and timeupdate frequency.

## Settings

`utils/settings.py` `Settings` (pydantic `BaseSettings`, loaded from `.env`):

- `API_URL`, `OIDC_APP_LOGIN_ROUTE`, `OIDC_APP_LOGOUT_ROUTE`, `OIDC_APP_REFRESH_ROUTE`
- `STORAGE_SECRET` — keys AES-256-GCM encryption for browser storage
- Branding: `LOGO_*`, `FAVICON`, `TAB_TITLE`, `TOPBAR_TEXT`, `LANDING_TEXT`, `MANUAL_URL`
- `WHISPER_MODELS`, `WHISPER_LANGUAGES` (includes "Northern Sámi (Experimental)")
- Editor: `CHARACTER_LIMIT` (must match `SUBTITLE_LINE_LENGTH` in transcribe-worker — the worker wraps at it, the editor flags lines that exceed it), `CHARACTER_LIMIT_EXCEEDED_COLOR`, `CONFIDENCE_LOW`, `CONFIDENCE_MEDIUM`

Tunables belong here; wire-format constants do not. `WORDS_FORMAT_VERSION` in `utils/srt.py` stays in code — a deployment claiming a version the code does not implement would only mis-parse silently.

Access via `get_settings()` (cached).

## Admin hierarchy

- **BOFH** (`bofh=True`): sees everything, manages all realms and onboarding attributes
- **Realm Admin** (`admin=True`): scoped to own realm + `admin_domains`. Can manage rules for their realms
- **Regular User**: no admin access

## Onboarding rules (pages/admin/rules.py)

- Rules page at `/admin/rules` — table with create/edit/delete dialogs and per-row test/delete actions
- Realm field is a multi-select dropdown filtered to real domains (containing a dot/TLD)
- Rules scoped by realm — admins within the same organisation see the same rules
- BOFH users see all rules across all realms
- Onboarding attributes section hidden for non-BOFH users
- Help dialog explains rule matching, actions, scoping, and manual override
- "Attributes" terminology used throughout (not "JWT claims")

## Testing

```bash
# All tests
uv run pytest
```

A `pytest.ini` (gitignored, not committed) normally configures `asyncio_mode = auto`, `main_file = main.py`, and loads `nicegui.testing.user_plugin` — check it exists locally if async tests misbehave; the suite currently collects and passes without one too. Current test files: `tests/test_srt.py`, `tests/test_storage.py`, `tests/test_transcript_editor.py`, `tests/test_my_edits.py`, `tests/test_words.py`, `tests/test_word_moves.py`, `tests/test_parse_txt.py`, `tests/test_caption_editor_styles.py`, `tests/test_billing_export.py`, `tests/test_event_loop_hygiene.py`, `tests/conftest.py`.

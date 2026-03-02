# TODO — Fantastical CLI + MCP Server

> **This file is for issues, problems, and action plans only.** Do not add development notes, workflow tips, reference material, or general documentation here — those belong in `AGENTS.md` or `docs/`.


## LAYER-SETUP — `cli.setup` bypasses `api.py` and imports backend directly

**Priority:** P2

`AGENTS.md` layer rules require `cli.py` to call only `api.py`, but `cli.setup` currently imports `generate_shortcut_file` and `import_shortcut` from `backend/shortcut_gen.py` directly.

This duplicates backend orchestration in two places (`api.setup_shortcuts()` and `cli.setup`) and weakens the API as the single source of truth.

**Fix plan:**
1. Add API-level setup primitives that keep backend calls inside `api.py` while still allowing per-shortcut progress UX in CLI.
2. Refactor `cli.setup` to call those API functions only (no backend imports in `cli.py`).
3. Add/adjust tests to enforce the layer boundary for setup flow.


## CLI-SETUP-CMD — `setup` success message prints invalid `events` command

**Priority:** P3

The setup completion message suggests:
`fantastical events --from 2026-01-01 --to 2026-01-31`

But `--from/--to` are options on `events list`, not on the `events` group. The correct command is:
`fantastical events list --from 2026-01-01 --to 2026-01-31`

**Fix plan:**
1. Update the printed command in `cli.setup` to include `list`.
2. Add/adjust a CLI output test to prevent this regression.


## CLI-DETAILS — Add CLI command for event details + attendees

**Priority:** P2

`get_event_details` (with lazy attendee fetching) only exists as an MCP tool in `server.py`. Terminal users can list events and see attendee counts, but there's no way to drill into a single event to see full details and attendee names/emails.

**Fix plan:**
1. Add `api.get_event_details()` that takes a date range + title filter, finds the event, fetches attendees, and returns the enriched dict.
2. Add `fantastical events details` CLI command (or similar) that displays full event info including attendees.
3. Reuse `get_event_attendees()` for the attendee fetch — the plumbing already exists.
4. Add `--json` support for machine-readable output.
5. Add tests for the new API function and CLI command.


## DOCS-NAME — README still uses old `fantastical-mcp` name/paths

**Priority:** P3

The canonical project name is `fantastical-cli` (package + repo), but README still contains stale `fantastical-mcp` references in title, clone/cd commands, and MCP config path examples.

This creates onboarding errors (wrong clone URL / directory names) and contradicts the resolved package rename.

**Fix plan:**
1. Replace remaining `fantastical-mcp` references in `README.md` with `fantastical-cli`.
2. Verify quick-start and MCP config snippets are copy-paste correct.
3. Add a small docs sanity check test/lint (or review checklist) to catch future rename drift.



## INPUT-PIPE — Forbid `|` in title query inputs to shortcut transport

**Priority:** P3

Shortcut input uses `start|end|titleQuery` framing. A literal pipe inside the title query collides with the delimiter and gets split into extra fields, silently truncating/mangling the query.

Pragmatic resolution: explicitly reject `|` in title query inputs for both event search and attendee lookup, with a clear user-facing error.

**Fix plan:**
1. Add validation before building shortcut input payloads (`get_events` / `get_attendees` path).
2. Raise a clear API error message instructing users to remove/replace `|`.
3. Add tests for rejection behavior.


## LOCALE-DATES — Add non-English Shortcuts date parsing support

**Priority:** P4

Current event date parsing is English-only (`"%d %b %Y %H:%M"` style), so localized month names from non-English macOS/Shortcuts locales may fail to parse.

**Fix plan:**
1. Add locale-aware date parsing strategy (or normalize date output in shortcuts to locale-neutral format).
2. Add tests with non-English month names/locales.
3. Keep current English parsing as a fast path.



## EDIT — Edit existing events

**Priority:** P2

No edit/update capability exists yet. Fantastical's 16 App Intents are all read-only or create — there is no `FKREditEventIntent` or similar.

**Research needed — possible approaches (untested):**
1. **Fantastical URL scheme** — We have `fantasticalURL` (`x-fantastical://show?item=...`) per event. The URL scheme may support edit parameters (e.g., `x-fantastical3://edit?item=...&title=...`). Undocumented, needs experimentation.
2. **JXA property setting** — Fantastical's JXA dictionary might allow `item.title = "new"` on calendar items. Most JXA access throws `-1700`, but property *setting* hasn't been tested.
3. **CalDAV/Exchange direct access** — Bypass Fantastical, talk to the calendar server directly using the event UID (extractable from `fantasticalURL`). Requires account credentials or OAuth.
4. **Delete + recreate** — Find event → delete (if possible) → create new one with modified fields. Crude but may be the only option.
5. **UI scripting** — Open event via deep link → use Accessibility API to modify fields. Fragile, last resort.

**First step:** Research approaches 1 and 2 (URL scheme docs, JXA set properties). If both fail, evaluate CalDAV feasibility.


## CREATE — `create_event` is fire-and-forget

**Priority:** P2

`create_event` uses `x-fantastical3://parse` URL scheme which returns nothing. `FKRCreateFromInputIntent` App Intent returns the created event with details.

**Fix:** Create a shortcut wrapping `FKRCreateFromInputIntent`, output created event properties.













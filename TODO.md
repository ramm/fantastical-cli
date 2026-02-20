# TODO — Fantastical CLI + MCP Server

> **This file is for issues, problems, and action plans only.** Do not add development notes, workflow tips, reference material, or general documentation here — those belong in `AGENTS.md` or `docs/`.

## ~~CALFIELD — Rename misleading `calendar` field to `calendarIdentifier`~~ ✓ RESOLVED

Renamed `EVENT_FIELDS[3]` from `"calendar"` to `"calendarIdentifier"` in `shortcuts.py`. Updated all references in `api.py`, `cli.py`, `server.py`, and all tests.


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


## DOCS-NAME — README still uses old `fantastical-mcp` name/paths

**Priority:** P3

The canonical project name is `fantastical-cli` (package + repo), but README still contains stale `fantastical-mcp` references in title, clone/cd commands, and MCP config path examples.

This creates onboarding errors (wrong clone URL / directory names) and contradicts the resolved package rename.

**Fix plan:**
1. Replace remaining `fantastical-mcp` references in `README.md` with `fantastical-cli`.
2. Verify quick-start and MCP config snippets are copy-paste correct.
3. Add a small docs sanity check test/lint (or review checklist) to catch future rename drift.


## MCP-CONTRACT — Docs still describe a thin JSON wrapper, but server now optimizes for compact text + caches

**Priority:** P2

The original "thin JSON wrapper" description is stale. `server.py` now intentionally includes context-shrink output formatting and in-memory caches (event IDs + attendee cache), and most tools return compact/plain text rather than JSON.

Current docs still imply all MCP tools return `json.dumps()` and that the server is a thin pass-through, which no longer matches reality.

**Fix plan:**
1. Update `AGENTS.md` architecture/layer notes to describe the current MCP server role (tool-facing formatting + cache lifecycle).
2. Update README MCP section with the actual tool list and response format expectations.
3. Decide and document a stable response contract per tool (text vs JSON), including rationale and parsing guidance.


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


## ATTENDEES — Enrich event data with attendees and emails

**Priority:** P1

Currently `EVENT_PROPS` has 5 fields (title, startDate, endDate, calendarIdentifier, fantasticalURL). Attendee data is missing.

**Why not just add `attendees` to `EVENT_PROPS`:** Accessing `Repeat Item.attendees` via property aggrandizement (`if_map:` / `WFContentItemPropertyName`) crashes BackgroundShortcutRunner — `IntentAttendee` entities don't support text coercion. This is a Shortcuts runtime limitation, not a Fantastical bug.

**Approach:** Use `FKRGetAttendeesFromEventIntent` ("Get Invitees from Event") — a dedicated intent that takes an event and returns attendees. Chain: Find Events → Repeat Each → Get Invitees → format. This also requires solving the If/Otherwise/End If action format on macOS 15+ (to guard nil values), which hasn't worked yet. Both problems will be addressed together during implementation. Note: `_if_has_value_start()`, `_if_otherwise()`, and `_if_end()` helpers already exist in `shortcut_gen.py` (lines 206-256) — untested, may need adjustment.

See `docs/shortcuts-format.md` for crash details and the reverse-engineering approach for If actions.


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


## ~~SEARCH — Search performance~~ ✓ RESOLVED

Title filter added to CalendarItemQuery (Operator 99, `title contains`). Both `list_events` and `search_events` now use one shortcut with server-side filtering. Input format: `start|end|titleQuery` (empty title = no-op). Python-side title filtering removed from `search_events()`.


## ~~PKGNAME — Package name `fantastical-mcp` doesn't match the project~~ ✓ RESOLVED

Renamed package from `fantastical-mcp` to `fantastical-cli` in pyproject.toml.


## ~~LAYER — Backend constants `SHORTCUTS`/`LEGACY_SHORTCUTS` leak through API to CLI~~ ✓ RESOLVED

Replaced re-exported dicts with `api.get_shortcut_names()` and `api.check_legacy_shortcuts()`. cli.py no longer imports backend constants.


## ~~ADD-OUTPUT — `add` command doesn't use `_output()` helper~~ ✓ RESOLVED

Refactored `add` command to use `_output()` like every other command.


## ~~CALMAP-EXCEPT — Fix redundant exception handling in `_get_calendar_map`~~ ✓ RESOLVED

Narrowed `except (JXAError, Exception)` to `except (JXAError, KeyError)` — catches JXA timeouts and dict issues, surfaces real bugs.


## ~~SHOWSCHEDULE — Remove redundant `show_schedule()` function~~ ✓ RESOLVED

Replaced `api.show_schedule("today")` with `api.list_events(from_date="today", to_date="today")` in cli.py setup test. Deleted `show_schedule()` from api.py.


## ~~MCP — MCP server testing~~ ✓ RESOLVED

pytest suite in `tests/test_server.py` covering tool registration, argument passing, JSON serialization, and error propagation. Uses `FastMCP.call_tool()` with mocked `api.*` — no macOS dependencies.


## ~~TESTS — Unit tests~~ ✓ RESOLVED

pytest suite in `tests/` covering parsing, API logic, shortcut generation, and shortcut runner integration. All tests use pure Python or `unittest.mock` — no macOS dependencies.


## ~~IMPORTS — Move inline stdlib imports to top of `cli.py`~~ ✓ RESOLVED

Moved `subprocess` and `time` to top-level imports in cli.py.


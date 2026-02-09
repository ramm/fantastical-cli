# TODO — Fantastical CLI + MCP Server

> **This file is for issues, problems, and action plans only.** Do not add development notes, workflow tips, reference material, or general documentation here — those belong in `AGENTS.md` or `docs/`.

## CALFIELD — Rename misleading `calendar` field to `calendarIdentifier`

**Priority:** P1

`shortcut_gen.py:309` outputs the Fantastical property `calendarIdentifier` (an opaque ID), but `shortcuts.py:129` parses it into a dict key named `calendar`:

```
EVENT_PROPS  = [..., "calendarIdentifier", ...]   # shortcut_gen.py — actual property
EVENT_FIELDS = [..., "calendar",           ...]   # shortcuts.py   — parsed dict key
```

Anyone reading `ev["calendar"]` would expect a human-readable name, not a UUID. The API then does `cal_map.get(ev.get("calendar"))` which only works because `calendar` secretly holds an identifier. The `--calendar` CLI filter (`api.py:179-182`) accidentally matches on the raw identifier too.

**Fix:** Rename `EVENT_FIELDS[3]` from `"calendar"` to `"calendarIdentifier"` in `shortcuts.py:129`, then update all references:
- `api.py:152` — `ev.get("calendar")` → `ev.get("calendarIdentifier")`
- `api.py:181-182` — calendar filter to match on `calendarName` and `calendarIdentifier`
- `cli.py:54` — `ev.get("calendar", "")` → `ev.get("calendarIdentifier", "")`


## PIPE — Fix pipe delimiter collision

**Priority:** P0

Event titles containing `|` (e.g., "Miro Engineering Council | Virtual Advisory Session") break the pipe-delimited parser. Need a different delimiter or escaping. See `shortcuts.py:parse_pipe_delimited()` and `shortcut_gen.py:_pipe_delimited_text()`.


## ATTENDEES — Enrich event data with attendees and emails

**Priority:** P1

Currently `EVENT_PROPS` has 5 fields (title, startDate, endDate, calendarIdentifier, fantasticalURL). Attendee data is missing — accessing `Repeat Item.attendees` via property aggrandizement crashes BackgroundShortcutRunner (`IntentAttendee` doesn't support text coercion).

**Approach:** Use `FKRGetAttendeesFromEventIntent` ("Get Invitees from Event") — a dedicated intent that takes an event and returns attendees. Chain: Find Events → Repeat Each → Get Invitees → format. This also requires solving the If/Otherwise/End If action format on macOS 15+ (to guard nil values), which hasn't worked yet. Both problems will be addressed together during implementation. Note: `_if_has_value_start()`, `_if_otherwise()`, and `_if_end()` helpers already exist in `shortcut_gen.py` (lines 206-256) — untested, may need adjustment.

See `AGENTS.md` and `docs/shortcuts-format.md` for crash details and the reverse-engineering approach for If actions.


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


## SEARCH — Search performance

**Priority:** P2

`search_events` uses a single CalendarItemQuery call with ±30 day range, then filters by title in Python. Could add a `title contains` filter directly in the CalendarItemQuery `WFContentItemFilter` to push filtering to Fantastical.


## PKGNAME — Package name `fantastical-mcp` doesn't match the project

**Priority:** P3

`pyproject.toml` names the package `fantastical-mcp`, suggesting a standalone MCP server. But the project is CLI-first: `cli.py` is 404 lines with interactive setup, `server.py` is a 43-line wrapper, README leads with CLI usage, entry point is `fantastical.cli:cli`. Consider renaming to `fantastical-cli` or just `fantastical` if available.


## LAYER — Backend constants `SHORTCUTS`/`LEGACY_SHORTCUTS` leak through API to CLI

**Priority:** P3

`api.py:13-14` re-exports `SHORTCUTS` and `LEGACY_SHORTCUTS` dicts from `shortcuts.py`, and `cli.py:12` imports them directly. This means `cli.py` knows the backend's internal dict structure (keys like `"find_events"`, values like `"Fantastical - Find Events"`), violating the layer rule that cli.py should only depend on api.py's public interface.

**Fix:** Replace the re-exported dicts with proper API functions, e.g. `api.get_shortcut_status()` returning `[{"key": "find_events", "name": "Fantastical - Find Events", "installed": True}]`. Remove `SHORTCUTS`/`LEGACY_SHORTCUTS` from api.py's public surface. Update `setup()` and `uninstall()` in cli.py to use the new API.


## ADD-OUTPUT — `add` command doesn't use `_output()` helper

**Priority:** P3

`cli.py:176-179` rolls its own JSON output instead of using `_output()` like every other command. Missing `default=str` kwarg. Refactor to use `_output()` with a small format function for the human-readable "Event sent to Fantastical: ..." message.


## CALMAP-EXCEPT — Fix redundant exception handling in `_get_calendar_map`

**Priority:** P3

`api.py:128` catches `(JXAError, Exception)` — `Exception` is a superclass of `JXAError`, making `JXAError` redundant. Decide the right scope: `except Exception` if the intent is "never crash on enrichment", or narrow to `except (JXAError, KeyError)` if the intent was to catch JXA failures and dict comprehension issues specifically. The broad `except Exception` silently swallows unexpected bugs — narrowing it would surface real problems while still tolerating JXA timeouts.


## SHOWSCHEDULE — Remove redundant `show_schedule()` function

**Priority:** P3

`api.show_schedule(date_str)` is identical to `api.list_events(from_date=date_str, to_date=date_str)` — it just calls `_get_events_for_range(resolved, resolved)`. It's a vestige of the old `FKRShowScheduleIntent` shortcut (now in `LEGACY_SHORTCUTS`). No CLI command or MCP tool exposes it. Only caller is `cli.py:322` during setup's test step.

**Fix:** Replace `api.show_schedule("today")` in `cli.py:322` with `api.list_events(from_date="today", to_date="today")`, then delete `show_schedule()` from `api.py`.


## MCP — MCP server testing

**Priority:** P3

The MCP server (`server.py`) wraps `api.py` but hasn't been tested end-to-end.


## TESTS — Unit tests

**Priority:** P3

No test suite. Testable pure-Python functions:
- `api._resolve_date` — date resolution, validation
- `shortcuts.parse_pipe_delimited` — field parsing, null handling, booleans
- `api._get_events_for_range` — date filtering, calendar enrichment
- `api.list_events` — date range cap, calendar name filtering


## IMPORTS — Move inline stdlib imports to top of `cli.py`

**Priority:** P3

`cli.py:382` imports `subprocess` and `cli.py:389` imports `time` inline in the `uninstall` command. These are standard library modules with no reason to defer — unlike the `shortcut_gen` imports in `setup()` which are intentionally lazy to avoid loading heavy modules. Move `subprocess` and `time` to the top-level imports for consistency.


## CLEANUP — Clean up test shortcuts

**Priority:** P3

Delete from Shortcuts.app after development:
- "Fantastical - Tomorrow Test"
- "Test Find"
- "Test Minimal", "Test No Attendees" (if still present)
- "claude-test-v2" (latest working test shortcut)
- Any other `claude-test-*` shortcuts

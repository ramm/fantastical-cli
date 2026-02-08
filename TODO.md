# TODO — Fantastical CLI + MCP Server

> **This file is for issues, problems, and action plans only.** Do not add development notes, workflow tips, reference material, or general documentation here — those belong in `AGENTS.md` or `docs/`.

## P0: Migrate from FKRShowScheduleIntent to CalendarItemQuery

**Status:** Code written, shortcut NOT working yet (2026-02-09)

### What's done

- `shortcut_gen.py`: `build_find_events()` generates a CalendarItemQuery shortcut with static date range, Repeat Each → pipe-delimited output. Uses native `datetime` objects for filter dates (string dates showed as empty "Date" placeholders — key discovery).
- `shortcuts.py`: Updated to `find_events` key, `get_events()` function, legacy shortcut detection.
- `api.py`: Rewritten `_get_events_for_range()` — single shortcut call, Python-side date filtering, `fantasticalURL` dedup.
- `cli.py`: Setup detects legacy shortcuts, updated prompts.
- `AGENTS.md`, `docs/cherri.md`: Updated.

### What's NOT working

The generated shortcut fails at runtime with "There was a problem running the shortcut". The shortcut renders correctly in Shortcuts.app (dates show properly with native `datetime` plist values), but execution fails. A minimal CalendarItemQuery-only shortcut (no Repeat Each / Output) ran without error but produced no output — unclear if it actually queried anything.

### Next steps (can be done in parallel)

**Route A: Cherri rawAction()** — Write a Cherri script using `rawAction("com.flexibits.fantastical2.mac.IntentCalendarItem", {...})` with the full nested filter dict. Compile with `--debug`, inspect the plist, import, test. If Cherri's plist serialization differs from our `plistlib.dump()` (key ordering, type coercion, internal wrapping), that's our bug. Fully automatable, no manual Shortcuts.app work needed.

**Route B: Manual shortcut extraction** — Create a working "Find Fantastical Calendar Item" shortcut manually in Shortcuts.app with a date filter + Repeat Each + output. Export, extract plist via AEA decryption, diff against our generated plist.

**Fallback:** The old `FKRShowScheduleIntent` approach still works — consider reverting to it temporarily while debugging.


## P1: CalendarItemQuery dynamic date range

**Status:** Needs research

### Problem

CalendarItemQuery currently uses a hardcoded ±2.5 year static date range. This means:
- Events beyond that range are invisible
- The shortcut must be regenerated (re-run `fantastical setup`) to re-center the window
- Unnecessary events are returned for narrow queries, increasing Shortcuts runtime

### What we tried

Investigated via Cherri compiler source analysis. Entity query filters use `Property`/`Operator`/`Values` (not `WFCondition`/`WFInput` like If conditions). The extracted plist had plain date strings in `Values.Date`/`Values.AnotherDate`. Whether these accept `WFTextTokenString` variable references is unknown.

### How to fix

1. Create a shortcut manually in Shortcuts.app where CalendarItemQuery's date filter is bound to a variable (Shortcut Input → Detect Dates → use in Find filter)
2. Export and extract the plist to see if `Values.Date` becomes a WFTextTokenString
3. If yes: update `_calendar_item_query_action()` to accept dynamic date variable references
4. If no: explore workarounds (separate "Format Date" actions, relative date filters with `WFContentPredicateBoundedDate: true`, etc.)


## P1: Attendee email addresses

**Status:** Partially investigated, likely a Fantastical limitation

### Problem

The user wants attendee email addresses, not just display names.

### What we tried

1. **Nested Repeat Each** over `Repeat Item.attendees` → `displayString` and `email` were BOTH empty on the one event with attendees. Crashes on events without attendees (Repeat Each over nil).
2. **If guard** (condition 100 "has any value") → format doesn't work on macOS 15+ (see P1 below)
3. **Simple property access** (`Repeat Item.attendees`) → gives names only, no emails

### Current state

The shortcut currently omits the `attendees` field entirely to avoid crashes. `EVENT_PROPS` in `shortcut_gen.py` does NOT include `attendees`.

### Possible next steps

- Try `FKRGetAttendeesFromEventIntent` — dedicated intent, might return richer data
- Test with events from different calendar types (Google vs iCloud) — emails may only be populated for some
- Accept limitation: names only, no emails


## P1: If/Otherwise/End If action format on macOS 15+

**Status:** Not working, needs reverse engineering

### Problem

Conditional logic is needed to guard against nil values (e.g., attendees). The If action format has changed on macOS 15+ and our attempts don't work.

### What we tried

- Flat format (`WFCondition: 100`, `WFInput`): "Please choose a value for each parameter" error
- `WFContentPredicateTableTemplate` format: still crashed

### How to fix

Same reverse-engineering approach as CalendarItemQuery:
1. User creates a shortcut with If action ("has any value" condition) in Shortcuts.app
2. Export `.shortcut` file
3. Extract plist via AEA decryption
4. Compare against our generated format


## P2: Event deduplication key is fragile

`api._get_events_for_range` deduplicates multi-day events using `(title, startDate, endDate, calendar)`. Recurring events with identical fields are incorrectly collapsed.

**Plan:** `fantasticalURL` is now included in `EVENT_PROPS` and `EVENT_FIELDS`, and `_get_events_for_range()` uses it as the dedup key — but this depends on the CalendarItemQuery shortcut working (P0). Untested.


## P2: `create_event` is fire-and-forget

`create_event` uses `x-fantastical3://parse` URL scheme which returns nothing. `FKRCreateFromInputIntent` App Intent returns the created event with details.

**Fix:** Create a shortcut wrapping `FKRCreateFromInputIntent`, output created event properties.


## P2: Search performance

Current `search_events` calls the schedule shortcut once per day across ±14 days (29 invocations). Code has been rewritten to use CalendarItemQuery with a single call and ±30 day range — but depends on CalendarItemQuery shortcut working (P0). Untested.

Further optimization: could add a `title contains` filter directly in the CalendarItemQuery `WFContentItemFilter` to push filtering to Fantastical.


## P3: MCP server testing

The MCP server (`server.py`) wraps `api.py` but hasn't been tested end-to-end.


## P3: Unit tests

No test suite. Testable pure-Python functions:
- `api._resolve_date` — date resolution, validation
- `shortcuts.parse_pipe_delimited` — field parsing, null handling, booleans
- `api._get_events_for_range` — deduplication logic
- `api.list_events` — date range cap, calendar filtering


## P3: Clean up test shortcuts

Delete from Shortcuts.app after development:
- "Fantastical - Tomorrow Test"
- "Test Find"
- "Test Minimal", "Test No Attendees" (if still present)

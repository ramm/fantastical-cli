# TODO — Fantastical CLI + MCP Server

> **This file is for issues, problems, and action plans only.** Do not add development notes, workflow tips, reference material, or general documentation here — those belong in `AGENTS.md` or `docs/`.

## P0: CalendarItemQuery end-to-end pipeline

**Status:** WORKING (2026-02-09)

### What works

Full pipeline verified: `fantastical events today`, `fantastical --json events today`, `fantastical events list --from ... --to ...` all produce correct output.

- `shortcut_gen.py`: `build_find_events()` generates CalendarItemQuery with dynamic ±14 day range (Current Date → Adjust Date actions), Repeat Each → pipe-delimited text (title|start|end|cal|fantasticalURL), Text wrap → Output.
- `shortcuts.py`: `get_events()`, `EVENT_FIELDS` = 5 fields: title, startDate, endDate, calendar, fantasticalURL.
- `api.py`: `_get_events_for_range()` — single shortcut call, Python-side date filtering, calendar name enrichment via JXA. `_parse_event_date()` handles Shortcuts localized format ("12 Feb 2026 at 12:00"). `_get_calendar_map()` builds calendarIdentifier→name lookup. `--calendar` filter matches by name or ID.

### Key discoveries (2026-02-09)

1. **Dynamic dates in CalendarItemQuery filters ARE possible.** The shortcut uses Current Date → Adjust Date actions to compute ±14 days at runtime. Two critical discoveries: (a) `WFDuration` must use **string** values (`Magnitude: "14"`, `Unit: "days"`), not integers — integers silently break the output; (b) `WFWorkflowClientVersion: "4046.0.2.2"` must be in the top-level plist — without it, freshly-generated shortcuts with variable dates return 0 items. Found by extracting a working plist from Shortcuts.app (`_experiments/anything.shortcut`). Previous attempts A/B/F/G/H crashed or returned 0 items due to wrong WFDuration encoding or missing client version.

2. **Output action taint tracking.** Data from third-party apps (Fantastical) is "tainted" — the Output action refuses to emit it directly with `WFActionErrorDomain Code=4` and log message "produces private output and is not exempt from taint tracking, but is missing an appIdentifier". **Fix:** wrap Repeat Results in a Text action before Output. The intermediate Text action "launders" the data through a built-in action.

3. **±90 days was too slow** (~700+ events, timed out). **±14 days** works well for typical calendars.

4. **Date format from Shortcuts** is localized: "12 Feb 2026 at 12:00", NOT ISO. Parser handles this.

5. **Pipe delimiter collision:** Event titles containing `|` (e.g., "Miro Engineering Council | Virtual Advisory Session") break the pipe-delimited parser. This is a known issue to fix later.

6. **Shortcut never goes stale.** Since dates are computed at runtime, `fantastical setup` only needs to run once. No periodic regeneration needed.

### What still needs doing

1. **Fix pipe delimiter collision** — titles with `|` break parsing. Use a different delimiter or escape it.


## P1: Attendee data

**Status:** Root cause identified — `attendees` property crashes BackgroundShortcutRunner

### Root cause (2026-02-09)

Accessing `Repeat Item.attendees` via `WFPropertyVariableAggrandizement` in a Text action crashes BackgroundShortcutRunner:
```
NSInvalidArgumentException: -[WFLinkEntityContentItem_com.flexibits.fantastical2.mac_IntentAttendee if_map:]: unrecognized selector
```
Stack trace: `WFPropertyVariableAggrandizement applyToContentCollection:` → `WFContentProperty getValuesForObject:`. The `IntentAttendee` entity objects don't support text coercion. This crash killed the entire shortcut run including all events that came before.

### Current state

`EVENT_PROPS` in `shortcut_gen.py` does NOT include `attendees`. The 8 safe properties work fine.

### Possible next steps

- **`FKRGetAttendeesFromEventIntent`** ("Get Invitees from Event" in Shortcuts.app UI) — dedicated intent that takes an event and returns attendees. Could be chained: Find Events → Repeat Each → Get Invitees → format. Needs its own plist structure discovery.
- Test with events from different calendar types (Google vs iCloud) — emails may only be populated for some
- Accept limitation: skip attendees entirely for now


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


## P2: Event deduplication

**Status:** Not needed — "duplicates" are from a personal calendar + delegated room calendar, both legitimate.

`fantasticalURL` was added to `EVENT_PROPS` as a permalink. It includes `calendarIdentifier` in the URL, so it's unique per calendar copy (not usable as a cross-calendar dedup key). Dedup on `(title, startDate, endDate)` was implemented and reverted — it would eat legitimate events from delegated calendars.


## P2: `create_event` is fire-and-forget

`create_event` uses `x-fantastical3://parse` URL scheme which returns nothing. `FKRCreateFromInputIntent` App Intent returns the created event with details.

**Fix:** Create a shortcut wrapping `FKRCreateFromInputIntent`, output created event properties.


## P2: Search performance

`search_events` uses a single CalendarItemQuery call with ±30 day range, then filters by title in Python. Further optimization: could add a `title contains` filter directly in the CalendarItemQuery `WFContentItemFilter` to push filtering to Fantastical.


## P3: MCP server testing

The MCP server (`server.py`) wraps `api.py` but hasn't been tested end-to-end.


## P3: Unit tests

No test suite. Testable pure-Python functions:
- `api._resolve_date` — date resolution, validation
- `shortcuts.parse_pipe_delimited` — field parsing, null handling, booleans
- `api._get_events_for_range` — date filtering, calendar enrichment
- `api.list_events` — date range cap, calendar name filtering


## P3: Clean up test shortcuts

Delete from Shortcuts.app after development:
- "Fantastical - Tomorrow Test"
- "Test Find"
- "Test Minimal", "Test No Attendees" (if still present)
- "claude-test-v2" (latest working test shortcut)
- Any other `claude-test-*` shortcuts

# TODO — Fantastical CLI + MCP Server

> **This file is for issues, problems, and action plans only.** Do not add development notes, workflow tips, reference material, or general documentation here — those belong in `AGENTS.md` or `docs/`.

## PIPE — Fix pipe delimiter collision

**Priority:** P0

Event titles containing `|` (e.g., "Miro Engineering Council | Virtual Advisory Session") break the pipe-delimited parser. Need a different delimiter or escaping. See `shortcuts.py:parse_pipe_delimited()` and `shortcut_gen.py:_pipe_delimited_text()`.


## ATTENDEES — Enrich event data with attendees and emails

**Priority:** P1

Currently `EVENT_PROPS` has 5 fields (title, startDate, endDate, calendarIdentifier, fantasticalURL). Attendee data is missing — accessing `Repeat Item.attendees` via property aggrandizement crashes BackgroundShortcutRunner (`IntentAttendee` doesn't support text coercion).

**Approach:** Use `FKRGetAttendeesFromEventIntent` ("Get Invitees from Event") — a dedicated intent that takes an event and returns attendees. Chain: Find Events → Repeat Each → Get Invitees → format. This also requires solving the If/Otherwise/End If action format on macOS 15+ (to guard nil values), which hasn't worked yet. Both problems will be addressed together during implementation.

See `AGENTS.md` and `docs/shortcuts-format.md` for crash details and the reverse-engineering approach for If actions.


## CREATE — `create_event` is fire-and-forget

**Priority:** P2

`create_event` uses `x-fantastical3://parse` URL scheme which returns nothing. `FKRCreateFromInputIntent` App Intent returns the created event with details.

**Fix:** Create a shortcut wrapping `FKRCreateFromInputIntent`, output created event properties.


## SEARCH — Search performance

**Priority:** P2

`search_events` uses a single CalendarItemQuery call with ±30 day range, then filters by title in Python. Could add a `title contains` filter directly in the CalendarItemQuery `WFContentItemFilter` to push filtering to Fantastical.


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


## CLEANUP — Clean up test shortcuts

**Priority:** P3

Delete from Shortcuts.app after development:
- "Fantastical - Tomorrow Test"
- "Test Find"
- "Test Minimal", "Test No Attendees" (if still present)
- "claude-test-v2" (latest working test shortcut)
- Any other `claude-test-*` shortcuts

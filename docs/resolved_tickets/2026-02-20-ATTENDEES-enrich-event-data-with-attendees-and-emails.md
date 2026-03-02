# ATTENDEES — Enrich event data with attendees and emails

Resolved: 2026-02-20
Commits: 630badb, 7cd9e89

## Original ticket

**Priority:** P1

Currently `EVENT_PROPS` has 5 fields (title, startDate, endDate, calendarIdentifier, fantasticalURL). Attendee data is missing.

**Why not just add `attendees` to `EVENT_PROPS`:** Accessing `Repeat Item.attendees` via property aggrandizement (`if_map:` / `WFContentItemPropertyName`) crashes BackgroundShortcutRunner — `IntentAttendee` entities don't support text coercion. This is a Shortcuts runtime limitation, not a Fantastical bug.

**Approach:** Use `FKRGetAttendeesFromEventIntent` ("Get Invitees from Event") — a dedicated intent that takes an event and returns attendees. Chain: Find Events → Repeat Each → Get Invitees → format. This also requires solving the If/Otherwise/End If action format on macOS 15+ (to guard nil values), which hasn't worked yet. Both problems will be addressed together during implementation. Note: `_if_has_value_start()`, `_if_otherwise()`, and `_if_end()` helpers already exist in `shortcut_gen.py` (lines 206-256) — untested, may need adjustment.

See `docs/shortcuts-format.md` for crash details and the reverse-engineering approach for If actions.

## Changes

### 630badb — Add attendee count to event listings and lazy attendee detail fetching

**Shortcut generation (`shortcut_gen.py`):**
- Modified `build_find_events()` to chain `FKRGetAttendeesFromEventIntent` → Count inside the Repeat Each loop, appending `attendeeCount` to each event's delimited output.
- Added `build_find_attendees()` — new shortcut that takes a date range + title filter, finds the first matching event, calls `FKRGetAttendeesFromEventIntent`, and iterates attendees with a single-level Repeat Each to extract `displayString` and `email`. Uses "Level 4" pattern (single-level Repeat Each) because nested Repeat Each fails for inner property access (discovered in experiment 22).
- Added `ATTENDEE_PROPS`, `ATTENDEE_INTENT_ID`, `ATTENDEE_OUTPUT_NAME` constants.

**Shortcuts runner (`shortcuts.py`):**
- Added `ATTENDEE_FIELDS = ["displayString", "email"]` and `get_attendees()` function.
- Extended `EVENT_FIELDS` with `attendeeCount` (6th field, appended by Count action, not part of `EVENT_PROPS`).
- Registered `"find_attendees"` in `SHORTCUTS` dict.

**API (`api.py`):**
- Added `get_event_attendees()` — resolves dates, delegates to `shortcuts.get_attendees()`.

**MCP server (`server.py`):**
- Added `_attendee_cache` (event_id → attendee list) with thread-safe access.
- `get_event_details` lazily fetches attendees via `_fetch_attendees()` on first access, caches for the session.
- `clear_cache` clears both event and attendee caches.
- Compact output from `list_events`/`search_events` includes `attendeeCount` column.

**CLI (`cli.py`):**
- `_format_events()` displays `[N attendees]` when count > 0.

### 7cd9e89 — Fix "Select an event" modal bugs in Shortcuts integration

Two bugs caused `FKRGetAttendeesFromEventIntent` to show a blocking "Select an event" modal dialog:

1. **Find Attendees — nil calendarItem:** When CalendarItemQuery returned no results, the intent received nil and prompted the user. Fixed by wrapping the intent call in an If "has any value" guard in `build_find_attendees()`.

2. **Find Events — runtime iteration bug:** After ~260 iterations of the intent inside a Repeat Each loop, the macOS Shortcuts runtime creates a duplicate action instance whose `calendarItem` parameter can't be resolved. Fixed by auto-batching `get_events()` into 4-day chunks (`_CHUNK_DAYS`) on the Python side.

Also added warmup of both shortcuts during `fantastical setup` to trigger privacy grants upfront.

## Reasoning

The straightforward approach (adding `attendees` to `EVENT_PROPS` and accessing via property aggrandizement) crashes the Shortcuts runtime — `IntentAttendee` entities don't support text coercion. The workaround uses a dedicated Fantastical intent (`FKRGetAttendeesFromEventIntent`) that returns attendee entities, then iterates them with a single-level Repeat Each to extract the two usable properties (`displayString`, `email`).

Attendee counts are cheap (Count action in the existing Find Events loop) so they're included inline. Full attendee details are expensive (separate shortcut call per event) so they're fetched lazily in the MCP server and cached per session.

The 4-day chunking for Find Events is a pragmatic workaround for an apparent macOS Shortcuts runtime bug — the exact threshold (~260 iterations) was determined empirically.

## Remaining gap

CLI has no command for full event details + attendees (only MCP `get_event_details` exposes this). Tracked in CLI-DETAILS.

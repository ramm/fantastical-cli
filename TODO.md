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



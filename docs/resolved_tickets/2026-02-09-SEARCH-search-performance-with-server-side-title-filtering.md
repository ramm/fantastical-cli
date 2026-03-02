# SEARCH — Search performance

Resolved: 2026-02-09
Commits: 8749281

## Original ticket

`search_events()` fetched all events in a date range via the shortcut, then filtered by title in Python. For busy calendars this meant transferring hundreds of events just to match a few. The shortcut needed server-side title filtering.

## Changes

**Shortcut generation (`shortcut_gen.py`):**
- Added a title contains filter (Operator 99) to CalendarItemQuery. The filter is conditional — empty title query is a no-op (matches all events).

**Shortcuts runner (`shortcuts.py`):**
- Input format changed from `"start|end"` to `"start|end|titleQuery"`. Empty title = match all.
- Switched field delimiter from pipe (`|`) to ASCII Unit Separator (`\x1F`) to avoid collision with pipes in event titles. Records still end with Record Separator (`\x1E`).

**API (`api.py`):**
- Both `list_events` and `search_events` now call the same `_get_events_for_range()` with an optional `title_query` parameter. Python-side title filtering removed from `search_events()`.

## Reasoning

Server-side filtering via CalendarItemQuery is dramatically faster — Fantastical filters internally before serializing results, so the shortcut returns only matching events. This also unified the two code paths (list and search) into one shortcut with one input format, reducing maintenance surface. The delimiter change from pipe to `\x1F` was done opportunistically to prevent a known collision risk with event titles containing literal pipes.

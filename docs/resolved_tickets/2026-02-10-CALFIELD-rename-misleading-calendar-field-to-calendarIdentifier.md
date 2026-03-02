# CALFIELD — Rename misleading `calendar` field to `calendarIdentifier`

Resolved: 2026-02-10
Commits: 735fa6f

## Original ticket

`EVENT_FIELDS[3]` was named `"calendar"`, suggesting a human-readable calendar name. The actual value is an opaque Fantastical identifier (e.g., `"F81A..."`) — not something a user would recognize. This caused confusion in downstream code where `calendar` was used interchangeably to mean the name or the ID.

## Changes

Renamed `EVENT_FIELDS[3]` from `"calendar"` to `"calendarIdentifier"` in `shortcuts.py`. Updated all references across `api.py` (calendar map lookup, filter matching), `cli.py` (display fallback), `server.py` (hash key, compact output), and all tests.

## Reasoning

The parsed dict key now matches the actual Fantastical property name, making it immediately clear that the value is an opaque ID, not a human-readable calendar name. This prevents bugs where code assumes it can display the raw value to users. The human-readable name is provided separately via `calendarName` (enriched from JXA calendar map).

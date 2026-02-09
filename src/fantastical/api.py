"""Core API — all business logic. Both CLI and MCP server call this layer."""

from __future__ import annotations

import subprocess
from datetime import date, datetime, timedelta

from fantastical.backend import fantastical as fan_backend
from fantastical.backend import shortcuts
from fantastical.backend.jxa import JXAError



class FantasticalError(Exception):
    """General Fantastical API error."""


class ShortcutsNotConfigured(FantasticalError):
    """Shortcuts are not set up yet."""

    def __init__(self, shortcut_key: str | None = None):
        self.shortcut_key = shortcut_key
        name = shortcuts.SHORTCUTS.get(shortcut_key, shortcut_key) if shortcut_key else "helper shortcuts"
        super().__init__(
            f'Required shortcut "{name}" is not installed. '
            f"Run `fantastical setup` to create the required shortcuts."
        )


def _resolve_date(value: str) -> str:
    """Resolve a date string to YYYY-MM-DD format.

    Accepts: 'today', 'tomorrow', 'yesterday', or YYYY-MM-DD.
    """
    lower = value.lower().strip()
    today = date.today()

    if lower == "today":
        return today.isoformat()
    elif lower == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    elif lower == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    else:
        # Validate it's a real date
        try:
            datetime.strptime(lower, "%Y-%m-%d")
        except ValueError:
            raise FantasticalError(f"Invalid date format: {value!r}. Use YYYY-MM-DD, 'today', 'tomorrow', or 'yesterday'.")
        return lower


def _run_shortcut_or_raise(shortcut_key: str, fn, *args, **kwargs):
    """Call a shortcuts backend function, converting ShortcutNotFoundError."""
    from fantastical.backend.shortcuts import ShortcutNotFoundError

    try:
        return fn(*args, **kwargs)
    except ShortcutNotFoundError as e:
        raise ShortcutsNotConfigured(shortcut_key) from e


# --- Public API ---


def list_calendars() -> list[dict]:
    """List all Fantastical calendars.

    No shortcuts required — uses JXA directly.
    """
    try:
        return fan_backend.list_calendars()
    except JXAError as e:
        raise FantasticalError(f"Failed to list calendars: {e}") from e



def create_event(sentence: str, calendar: str | None = None, notes: str | None = None) -> dict:
    """Create an event using natural language parsing.

    No shortcuts required — uses URL scheme directly.
    """
    try:
        return fan_backend.create_event(sentence, calendar, notes)
    except (subprocess.SubprocessError, OSError) as e:
        raise FantasticalError(f"Failed to create event: {e}") from e


def _parse_event_date(date_str: str | None) -> date | None:
    """Parse an event date string to a date object for filtering.

    Handles multiple formats from Shortcuts output:
    - "12 Feb 2026 at 12:00" (macOS Shortcuts localized format)
    - "2026-02-09T10:00:00+00:00" (ISO format)
    - "2026-02-09" (date-only ISO)
    """
    if not date_str:
        return None
    try:
        # Try Shortcuts localized format: "12 Feb 2026 at 12:00"
        cleaned = date_str.replace(" at ", " ")
        return datetime.strptime(cleaned, "%d %b %Y %H:%M").date()
    except (ValueError, AttributeError):
        pass
    try:
        # Try ISO format (2026-02-09T10:00:00+00:00 or 2026-02-09 10:00:00)
        return datetime.fromisoformat(date_str.replace(" ", "T")).date()
    except (ValueError, AttributeError):
        pass
    try:
        # Try date-only
        return date.fromisoformat(date_str[:10])
    except (ValueError, AttributeError):
        return None


def _get_calendar_map() -> dict[str, str]:
    """Build calendarIdentifier → calendar name map via JXA.

    Returns empty dict if JXA fails (e.g., Fantastical not responding).
    """
    try:
        cals = fan_backend.list_calendars()
        return {c["id"]: c["title"] for c in cals if "id" in c and "title" in c}
    except (JXAError, KeyError):
        return {}


def _get_events_for_range(from_iso: str, to_iso: str, title_query: str = "") -> list[dict]:
    """Get events across a date range using CalendarItemQuery.

    Passes the date range and optional title filter to the shortcut as input
    so CalendarItemQuery fetches the exact range with server-side filtering.
    Python-side date filtering is kept as a safety net.
    Events are enriched with calendarName from JXA when available.
    """
    start = date.fromisoformat(from_iso)
    end = date.fromisoformat(to_iso)

    all_events = _run_shortcut_or_raise(
        "find_events", shortcuts.get_events, from_iso, to_iso, title_query,
    )
    cal_map = _get_calendar_map()

    # Safety-net filter + calendar name enrichment
    filtered: list[dict] = []
    for ev in all_events:
        ev_start = _parse_event_date(ev.get("startDate"))
        if ev_start is not None and (ev_start < start or ev_start > end):
            continue
        if cal_map:
            ev["calendarName"] = cal_map.get(ev.get("calendar"), None)
        filtered.append(ev)

    return filtered


def list_events(
    from_date: str = "today",
    to_date: str | None = None,
    calendar: str | None = None,
) -> list[dict]:
    """List events in a date range.

    Requires shortcuts. Dates accept 'today', 'tomorrow', 'yesterday', or YYYY-MM-DD.
    Uses CalendarItemQuery — single shortcut call, capped at 365 days.
    """
    resolved_from = _resolve_date(from_date)
    resolved_to = _resolve_date(to_date) if to_date else resolved_from

    start = date.fromisoformat(resolved_from)
    end = date.fromisoformat(resolved_to)
    if (end - start).days > 365:
        raise FantasticalError("Date range too large (max 365 days). Use a narrower range.")

    events = _get_events_for_range(resolved_from, resolved_to)

    if calendar:
        cal_lower = calendar.lower()
        events = [e for e in events
                  if cal_lower in ((e.get("calendarName") or "").lower(),
                                   (e.get("calendar") or "").lower())]

    return events


def search_events(
    query: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[dict]:
    """Search events by title.

    Requires shortcuts. Passes date range and title query to the shortcut
    for server-side filtering via CalendarItemQuery's title contains filter.
    Default range is ±30 days; overridable with from_date/to_date.
    Capped at 365 days like list_events.
    """
    today_date = date.today()
    from_iso = _resolve_date(from_date) if from_date else (today_date - timedelta(days=30)).isoformat()
    to_iso = _resolve_date(to_date) if to_date else (today_date + timedelta(days=30)).isoformat()

    start = date.fromisoformat(from_iso)
    end = date.fromisoformat(to_iso)
    if (end - start).days > 365:
        raise FantasticalError("Date range too large (max 365 days). Use a narrower range.")

    return _get_events_for_range(from_iso, to_iso, title_query=query)



def get_shortcut_names() -> dict[str, str]:
    """Get shortcut key → display name mapping.

    Returns dict like {"find_events": "Fantastical - Find Events"}.
    """
    return dict(shortcuts.SHORTCUTS)


def check_legacy_shortcuts() -> list[str]:
    """Check for legacy shortcuts that are still installed.

    Returns list of display names that should be removed.
    """
    return shortcuts.check_legacy_shortcuts()


def check_setup() -> dict[str, bool]:
    """Check which helper shortcuts are installed.

    Returns dict mapping shortcut key to installed status.
    """
    return shortcuts.check_all_shortcuts()


def setup_shortcuts() -> dict[str, str]:
    """Generate, sign, and import all required helper shortcuts.

    Returns dict mapping shortcut key to the signed file path.

    Raises RuntimeError if signing fails (e.g., no internet).
    """
    from fantastical.backend.shortcut_gen import generate_shortcut_file, import_shortcut, SHORTCUT_BUILDERS

    results = {}
    for key in SHORTCUT_BUILDERS:
        path = generate_shortcut_file(key)
        import_shortcut(path)
        results[key] = str(path)
    return results


def get_installed_shortcut_ids() -> dict[str, str]:
    """Get UUIDs of installed Fantastical helper shortcuts.

    Returns dict mapping shortcut name to UUID (only for those that exist).
    """
    status = shortcuts.check_all_shortcuts()
    installed_names = [shortcuts.SHORTCUTS[key] for key, ok in status.items() if ok]
    if not installed_names:
        return {}
    return shortcuts.get_shortcut_ids_by_name(installed_names)


def open_shortcut(shortcut_id: str) -> None:
    """Open a shortcut in Shortcuts.app by UUID."""
    shortcuts.open_shortcut_in_app(shortcut_id)

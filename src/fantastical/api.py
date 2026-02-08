"""Core API — all business logic. Both CLI and MCP server call this layer."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fantastical.backend import fantastical as fan_backend
from fantastical.backend import shortcuts
from fantastical.backend.jxa import JXAError
from fantastical.backend.shortcuts import ShortcutNotFoundError


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


def _run_shortcut_or_raise(fn, *args, **kwargs):
    """Call a shortcuts backend function, converting ShortcutNotFoundError."""
    try:
        return fn(*args, **kwargs)
    except ShortcutNotFoundError as e:
        raise ShortcutsNotConfigured() from e


# --- Public API ---


def list_calendars() -> list[dict]:
    """List all Fantastical calendars.

    No shortcuts required — uses JXA directly.
    """
    try:
        return fan_backend.list_calendars()
    except JXAError as e:
        raise FantasticalError(f"Failed to list calendars: {e}") from e


def get_selected() -> list[dict]:
    """Get currently selected calendar items in Fantastical.

    No shortcuts required — uses JXA directly.
    """
    try:
        return fan_backend.get_selected_items()
    except JXAError as e:
        raise FantasticalError(f"Failed to get selected items: {e}") from e


def create_event(sentence: str, calendar: str | None = None, notes: str | None = None) -> dict:
    """Create an event using natural language parsing.

    No shortcuts required — uses URL scheme directly.
    """
    return fan_backend.create_event(sentence, calendar, notes)


def list_events(
    from_date: str = "today",
    to_date: str | None = None,
    calendar: str | None = None,
) -> list[dict]:
    """List events in a date range.

    Requires shortcuts. Dates accept 'today', 'tomorrow', 'yesterday', or YYYY-MM-DD.
    """
    resolved_from = _resolve_date(from_date)
    resolved_to = _resolve_date(to_date) if to_date else resolved_from

    events = _run_shortcut_or_raise(shortcuts.get_events, resolved_from, resolved_to)

    if calendar:
        cal_lower = calendar.lower()
        events = [e for e in events if e.get("calendar", "").lower() == cal_lower]

    return events


def show_schedule(date_str: str = "today") -> list[dict]:
    """Show the schedule for a given date.

    Requires shortcuts.
    """
    resolved = _resolve_date(date_str)
    return _run_shortcut_or_raise(shortcuts.get_schedule, resolved)


def list_tasks(list_name: str | None = None, overdue: bool = False) -> list[dict]:
    """List tasks, optionally filtered by list or overdue status.

    Requires shortcuts.
    """
    if overdue:
        return _run_shortcut_or_raise(shortcuts.get_overdue_tasks)
    return _run_shortcut_or_raise(shortcuts.get_tasks, list_name)


def search_events(query: str) -> list[dict]:
    """Search events by title.

    Requires shortcuts.
    """
    return _run_shortcut_or_raise(shortcuts.search_events, query)


def check_setup() -> dict[str, bool]:
    """Check which helper shortcuts are installed.

    Returns dict mapping shortcut key to installed status.
    """
    return shortcuts.check_all_shortcuts()


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

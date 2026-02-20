"""Apple Shortcuts integration for Fantastical App Intents."""

from __future__ import annotations

import subprocess
import threading

# Shortcut names used by this tool
SHORTCUT_PREFIX = "Fantastical - "
SHORTCUTS = {
    "find_events": f"{SHORTCUT_PREFIX}Find Events",
    "find_attendees": f"{SHORTCUT_PREFIX}Find Attendees",
}

# Legacy shortcut names (for migration detection)
LEGACY_SHORTCUTS = {
    "schedule": f"{SHORTCUT_PREFIX}Show Schedule",
}


class ShortcutNotFoundError(Exception):
    """A required shortcut is not installed."""


def list_installed_shortcuts() -> list[str]:
    """List all installed shortcut names.

    Called multiple times during setup (status check, legacy check, verification).
    No caching — consistency is worth a little latency.
    """
    result = subprocess.run(
        ["shortcuts", "list"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]


def check_shortcut_exists(key: str) -> bool:
    """Check if a specific Fantastical helper shortcut is installed."""
    name = SHORTCUTS[key]
    installed = list_installed_shortcuts()
    return name in installed


def check_all_shortcuts() -> dict[str, bool]:
    """Check which helper shortcuts are installed.

    Returns dict mapping shortcut key to installed status.
    """
    installed = set(list_installed_shortcuts())
    return {key: name in installed for key, name in SHORTCUTS.items()}


def get_shortcut_ids_by_name(names: list[str]) -> dict[str, str]:
    """Look up shortcut UUIDs by name via JXA.

    Returns dict mapping shortcut name to its UUID (for those that exist).
    """
    from fantastical.backend.jxa import run_jxa_json

    def _js_escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    names_js = "[" + ",".join(f'"{_js_escape(n)}"' for n in names) + "]"
    script = f"""
    var app = Application("Shortcuts");
    var targetNames = {names_js};
    var result = {{}};
    var all = app.shortcuts();
    for (var i = 0; i < all.length; i++) {{
        var name = all[i].name();
        if (targetNames.indexOf(name) !== -1) {{
            result[name] = all[i].id();
        }}
    }}
    JSON.stringify(result);
    """
    return run_jxa_json(script)


def open_shortcut_in_app(shortcut_id: str) -> None:
    """Open a shortcut in Shortcuts.app by its UUID."""
    subprocess.run(
        ["open", f"shortcuts://open-shortcut?id={shortcut_id}"],
        check=True,
        timeout=10,
    )


def run_shortcut(key: str, input_text: str | None = None) -> str:
    """Run a Fantastical helper shortcut and return its text output.

    Args:
        key: Shortcut key (e.g. 'schedule')
        input_text: Optional text input to pass to the shortcut

    Returns:
        Raw text output from the shortcut.

    Raises:
        ShortcutNotFoundError: If the shortcut is not installed.
    """
    name = SHORTCUTS.get(key)
    if not name:
        raise ValueError(f"Unknown shortcut key: {key}")

    cmd = ["shortcuts", "run", name]
    if input_text:  # intentionally falsy — empty string means "no input"
        cmd.extend(["-i", input_text])

    with _shortcut_lock:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not found" in stderr.lower() or "find shortcut" in stderr.lower() or "couldn\u2019t find" in stderr.lower():
            raise ShortcutNotFoundError(
                f'Shortcut "{name}" is not installed. '
                f"Run `fantastical setup` to create the required shortcuts."
            )
        raise RuntimeError(f'Shortcut "{name}" failed: {stderr}')

    return result.stdout.strip()


# Field names matching EVENT_PROPS order in shortcut_gen.py
# attendeeCount is appended after EVENT_PROPS by the Count action in the shortcut.
EVENT_FIELDS = ["title", "startDate", "endDate", "calendarIdentifier", "fantasticalURL", "attendeeCount"]

ATTENDEE_FIELDS = ["displayString", "email"]


_shortcut_lock = threading.Lock()

RECORD_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"


def _parse_fields(parts: list[str], field_names: list[str] = EVENT_FIELDS) -> dict:
    """Parse a list of field values into a dict using the given field names."""
    item: dict = {}
    for i, name in enumerate(field_names):
        if i < len(parts):
            val = parts[i].strip()
            if val in ("", "nil", "null", "(null)"):
                item[name] = None
            else:
                item[name] = val
        else:
            item[name] = None
    return item


def parse_shortcut_output(output: str, field_names: list[str] | None = None) -> list[dict]:
    """Parse shortcut output into list of dicts.

    Fields are separated by ASCII Unit Separator (0x1F) — safe even when
    event titles contain pipes.  Records are separated by ASCII Record
    Separator (0x1E), so fields can safely contain newlines (e.g.,
    multi-line locations, attendee lists).

    Args:
        output: Raw shortcut output text.
        field_names: Field names to parse. Defaults to EVENT_FIELDS.

    Expected format per record (matching EVENT_PROPS in shortcut_gen.py):
    TITLE\x1fSTART\x1fEND\x1fCALENDAR\x1fURL\x1fATTENDEE_COUNT\x1e
    """
    if field_names is None:
        field_names = EVENT_FIELDS

    if not output:
        return []

    results = []
    num_fields = len(field_names)

    for record in output.split(RECORD_SEPARATOR):
        record = record.strip()
        if not record:
            continue

        parts = record.split(FIELD_SEPARATOR, num_fields - 1)
        results.append(_parse_fields(parts, field_names))

    return results


# Maximum days per shortcut run for event queries.
# FKRGetAttendeesFromEventIntent inside the Find Events shortcut's Repeat Each
# loop triggers a macOS Shortcuts runtime bug after ~260 iterations: the runtime
# creates a duplicate action instance whose calendarItem parameter can't be
# resolved, showing a blocking "Select an event" modal.  Batching into smaller
# date ranges keeps each run well under that threshold.
_CHUNK_DAYS = 4


def get_events(from_date: str, to_date: str, title_query: str = "") -> list[dict]:
    """Get events in a date range via CalendarItemQuery.

    Args:
        from_date: Start date as YYYY-MM-DD (inclusive).
        to_date: End date as YYYY-MM-DD (inclusive).
        title_query: Optional title substring filter (server-side).
            Empty string matches all events.

    Returns all events across ALL calendars within the requested range.
    The shortcut receives the dates and title query as input and queries
    Fantastical directly with server-side filtering.

    Large date ranges are automatically split into _CHUNK_DAYS-day windows
    to work around a macOS Shortcuts runtime bug (see _CHUNK_DAYS).

    Note: CalendarItemQuery's "between" operator excludes the end date,
    so we add 1 day to make to_date inclusive from the caller's perspective.
    """
    from datetime import date, timedelta

    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)

    all_events: list[dict] = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=_CHUNK_DAYS - 1), end)
        end_exclusive = (chunk_end + timedelta(days=1)).isoformat()
        input_text = f"{chunk_start.isoformat()}|{end_exclusive}|{title_query}"
        output = run_shortcut("find_events", input_text=input_text)
        all_events.extend(parse_shortcut_output(output))
        chunk_start = chunk_end + timedelta(days=1)

    return all_events


def get_attendees(from_date: str, to_date: str, title_query: str = "") -> list[dict]:
    """Get attendees for a specific event via the Find Attendees shortcut.

    Args:
        from_date: Start date as YYYY-MM-DD (inclusive).
        to_date: End date as YYYY-MM-DD (inclusive).
        title_query: Title substring filter to identify the event.

    Returns list of attendee dicts with displayString and email fields.

    Note: CalendarItemQuery's "between" operator excludes the end date,
    so we add 1 day to make to_date inclusive from the caller's perspective.
    """
    from datetime import date, timedelta

    end_exclusive = (date.fromisoformat(to_date) + timedelta(days=1)).isoformat()
    input_text = f"{from_date}|{end_exclusive}|{title_query}"
    output = run_shortcut("find_attendees", input_text=input_text)
    return parse_shortcut_output(output, field_names=ATTENDEE_FIELDS)


def check_legacy_shortcuts() -> list[str]:
    """Check for legacy shortcuts that can be removed.

    Returns list of legacy shortcut names that are still installed.
    """
    installed = set(list_installed_shortcuts())
    return [name for name in LEGACY_SHORTCUTS.values() if name in installed]

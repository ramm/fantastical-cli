"""Apple Shortcuts integration for Fantastical App Intents."""

from __future__ import annotations

import subprocess

# Shortcut names used by this tool
SHORTCUT_PREFIX = "Fantastical - "
SHORTCUTS = {
    "find_events": f"{SHORTCUT_PREFIX}Find Events",
}

# Legacy shortcut names (for migration detection)
LEGACY_SHORTCUTS = {
    "schedule": f"{SHORTCUT_PREFIX}Show Schedule",
}


class ShortcutNotFoundError(Exception):
    """A required shortcut is not installed."""


def list_installed_shortcuts() -> list[str]:
    """List all installed shortcut names."""
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

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
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
EVENT_FIELDS = ["title", "startDate", "endDate", "calendar", "isAllDay", "location", "notes", "fantasticalURL"]


RECORD_SEPARATOR = "\x1e"


def _parse_fields(parts: list[str]) -> dict:
    """Parse a list of field values into an event dict."""
    item: dict = {}
    for i, name in enumerate(EVENT_FIELDS):
        if i < len(parts):
            val = parts[i].strip()
            if name == "isAllDay":
                item[name] = val.lower() in ("true", "yes", "1")
            elif val in ("", "nil", "null", "(null)"):
                item[name] = None
            else:
                item[name] = val
        else:
            item[name] = None
    return item


def parse_pipe_delimited(output: str) -> list[dict]:
    """Parse pipe-delimited shortcut output into list of event dicts.

    Each record ends with ASCII Record Separator (0x1E), so fields can
    safely contain newlines (e.g., multi-line locations, attendee lists).
    Records are split on 0x1E first, then each record is split on pipe.

    Expected format per record (matching EVENT_PROPS in shortcut_gen.py):
    TITLE | START | END | CALENDAR | ALL_DAY | LOCATION | NOTES | URL\x1e
    """
    if not output:
        return []

    results = []
    num_fields = len(EVENT_FIELDS)

    for record in output.split(RECORD_SEPARATOR):
        record = record.strip()
        if not record:
            continue

        parts = record.split("|", num_fields - 1)
        results.append(_parse_fields(parts))

    return results


def get_events() -> list[dict]:
    """Get all events in the shortcut's static date range via CalendarItemQuery.

    Returns all events across ALL calendars. The caller is responsible
    for filtering to the desired date range.
    """
    output = run_shortcut("find_events")
    return parse_pipe_delimited(output)


def check_legacy_shortcuts() -> list[str]:
    """Check for legacy shortcuts that can be removed.

    Returns list of legacy shortcut names that are still installed.
    """
    installed = set(list_installed_shortcuts())
    return [name for name in LEGACY_SHORTCUTS.values() if name in installed]

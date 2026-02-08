"""Apple Shortcuts integration for Fantastical App Intents."""

from __future__ import annotations

import subprocess

# Shortcut names used by this tool
SHORTCUT_PREFIX = "Fantastical - "
SHORTCUTS = {
    "schedule": f"{SHORTCUT_PREFIX}Show Schedule",
    "overdue": f"{SHORTCUT_PREFIX}Overdue Tasks",
}

# Instructions for creating each shortcut manually
SHORTCUT_INSTRUCTIONS = {
    "schedule": {
        "name": SHORTCUTS["schedule"],
        "steps": [
            'Add action: "Show Schedule" (Fantastical)',
            "Set date to Shortcut Input",
            'Add action: Repeat with each item, format as text',
        ],
        "input": "A date (YYYY-MM-DD)",
        "output": "One event per line: TITLE | START | END | CALENDAR | ALL_DAY | LOCATION | NOTES",
    },
    "overdue": {
        "name": SHORTCUTS["overdue"],
        "steps": [
            'Add action: "Overdue Tasks" (Fantastical)',
            'Add action: Repeat with each item, format as text',
        ],
        "input": "None",
        "output": "One task per line: TITLE | DUE_DATE | LIST | NOTES",
    },
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

    names_js = "[" + ",".join(f'"{n}"' for n in names) + "]"
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
        key: Shortcut key (e.g. 'schedule', 'overdue')
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
    stdin_data = None
    if input_text:
        cmd.extend(["-i", input_text])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=stdin_data,
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


def parse_pipe_delimited(output: str) -> list[dict]:
    """Parse pipe-delimited shortcut output into list of dicts.

    Expected format per line:
    TITLE | START | END | CALENDAR | ALL_DAY | LOCATION | NOTES

    Handles varying numbers of fields gracefully.
    """
    if not output:
        return []

    results = []
    field_names = ["title", "startDate", "endDate", "calendar", "isAllDay", "location", "notes"]

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]
        item: dict = {}
        for i, name in enumerate(field_names):
            if i < len(parts):
                val = parts[i]
                if name == "isAllDay":
                    item[name] = val.lower() in ("true", "yes", "1")
                elif val in ("", "nil", "null", "(null)"):
                    item[name] = None
                else:
                    item[name] = val
            else:
                item[name] = None
        results.append(item)

    return results


def parse_task_output(output: str) -> list[dict]:
    """Parse pipe-delimited task output into list of dicts.

    Expected format per line:
    TITLE | DUE_DATE | LIST | NOTES
    """
    if not output:
        return []

    results = []
    field_names = ["title", "dueDate", "list", "notes"]

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split("|")]
        item: dict = {}
        for i, name in enumerate(field_names):
            if i < len(parts):
                val = parts[i]
                if val in ("", "nil", "null", "(null)"):
                    item[name] = None
                else:
                    item[name] = val
            else:
                item[name] = None
        results.append(item)

    return results


def get_schedule(date: str) -> list[dict]:
    """Get schedule for a date via shortcuts."""
    output = run_shortcut("schedule", date)
    return parse_pipe_delimited(output)


def get_overdue_tasks() -> list[dict]:
    """Get overdue tasks via shortcuts."""
    output = run_shortcut("overdue")
    return parse_task_output(output)



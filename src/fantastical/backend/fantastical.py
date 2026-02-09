"""Fantastical integration via JXA and URL schemes."""

from __future__ import annotations

import subprocess
from urllib.parse import quote

from fantastical.backend.jxa import run_jxa_json


def list_calendars() -> list[dict]:
    """List all Fantastical calendars via JXA.

    Returns list of dicts with 'title' and 'id' keys.
    """
    script = """
    const app = Application("Fantastical");
    const cals = app.calendars();
    const result = cals.map(c => ({
        title: c.title(),
        id: c.id()
    }));
    JSON.stringify(result);
    """
    return run_jxa_json(script)



def create_event(sentence: str, calendar: str | None = None, notes: str | None = None) -> dict:
    """Create an event using Fantastical's natural language parsing.

    Uses the x-fantastical3://parse URL scheme. The URL scheme is fire-and-forget:
    there is no way to confirm Fantastical actually created the event.
    Returns dict with 'sent' status and the request parameters.
    """
    url = f"x-fantastical3://parse?s={quote(sentence)}"
    if calendar:
        url += f"&calendarName={quote(calendar)}"
    if notes:
        url += f"&n={quote(notes)}"
    # Add &add=1 to add directly without showing the UI
    url += "&add=1"

    subprocess.run(["open", url], check=True, timeout=10)
    return {"sent": True, "sentence": sentence, "calendar": calendar}

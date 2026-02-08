"""JXA (JavaScript for Automation) runner via osascript."""

from __future__ import annotations

import json
import subprocess


class JXAError(Exception):
    """Error running JXA script."""


def run_jxa(script: str) -> str:
    """Run a JXA script via osascript and return raw stdout.

    The script should use JSON.stringify() for structured output.
    """
    result = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise JXAError(f"JXA script failed: {stderr}")
    return result.stdout.strip()


def run_jxa_json(script: str) -> list | dict:
    """Run a JXA script and parse the JSON output."""
    raw = run_jxa(script)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise JXAError(f"Failed to parse JXA output as JSON: {e}\nOutput: {raw}")

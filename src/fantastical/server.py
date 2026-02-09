"""MCP server for Fantastical — thin wrapper over api.py."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading

from mcp.server.fastmcp import FastMCP

from fantastical import api

mcp = FastMCP("fantastical")

# --- Event cache ---

_event_cache: dict[str, dict] = {}  # event_id → full event dict
_cache_lock = threading.Lock()       # thread-safe for parallel tool calls


def _hash_event(event: dict) -> str:
    """Short stable ID. Includes calendar to distinguish cross-calendar duplicates."""
    cal = event.get("calendar") or ""
    url = event.get("fantasticalURL") or ""
    if url:
        key = f"{url}|{cal}"
    else:
        key = f"{event.get('title')}|{event.get('startDate')}|{event.get('endDate')}|{cal}"
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def _cache_and_compact(events: list[dict]) -> str:
    """Cache full events, return compact tab-separated output. Thread-safe."""
    lines = []
    with _cache_lock:
        for ev in events:
            eid = _hash_event(ev)
            ev["id"] = eid
            _event_cache[eid] = ev  # store/update ALL fields
            lines.append(f"{eid}\t{ev.get('title')}\t{ev.get('startDate')}\t{ev.get('endDate')}")
    header = f"count: {len(events)}"
    return header + "\n" + "\n".join(lines)


# --- Tools ---


@mcp.tool()
async def list_calendars() -> str:
    """List all Fantastical calendars.

    Fast and lightweight — no shortcuts required, uses JXA directly.
    Returns plain text: one calendar per line as "name (id)".
    """
    data = await asyncio.to_thread(api.list_calendars)
    return "\n".join(f"{c.get('title')} ({c.get('id')})" for c in data)


@mcp.tool()
async def list_events(from_date: str = "today", to_date: str | None = None, calendar: str | None = None) -> str:
    """List calendar events in a date range (YYYY-MM-DD).

    Accepts 'today', 'tomorrow', 'yesterday', or YYYY-MM-DD. Defaults to today only.
    Max 365 days. Ranges >1 month may be slow — recommend 2-week chunks.

    Returns compact tab-separated output: id, title, startDate, endDate.
    All events are cached — use get_event_details for full data (calendar, URL, etc.).
    Can be called in parallel for different date ranges.
    """
    data = await asyncio.to_thread(api.list_events, from_date, to_date, calendar)
    return _cache_and_compact(data)


@mcp.tool()
async def create_event(sentence: str, calendar: str | None = None, notes: str | None = None) -> str:
    """Create event using natural language (e.g. 'Meeting tomorrow at 3pm')."""
    data = await asyncio.to_thread(api.create_event, sentence, calendar, notes)
    return json.dumps(data)


@mcp.tool()
async def search_events(
    query: str,
    from_date: str | None = None,
    to_date: str | None = None,
) -> str:
    """Search events by title.

    Default search window is ±30 days. Override with from_date/to_date (YYYY-MM-DD).
    Max 365 days. Same compact tab-separated output as list_events with caching.
    Can be called in parallel for different queries.
    """
    data = await asyncio.to_thread(api.search_events, query, from_date, to_date)
    return _cache_and_compact(data)


@mcp.tool()
async def get_event_details(event_id: str) -> str:
    """Get full details of a cached event by ID.

    Returns all fields: title, startDate, endDate, calendar, fantasticalURL, calendarName.
    Events are cached from previous list_events/search_events calls.
    """
    with _cache_lock:
        ev = _event_cache.get(event_id)
    if ev is None:
        return f"Event {event_id} not found in cache. Run list_events or search_events first."
    return "\n".join(f"{k}: {v}" for k, v in ev.items())


@mcp.tool()
async def clear_cache() -> str:
    """Clear the in-memory event cache.

    Use when starting a fresh analysis session.
    """
    with _cache_lock:
        count = len(_event_cache)
        _event_cache.clear()
    return f"Cache cleared ({count} events removed)."

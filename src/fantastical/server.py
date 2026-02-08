"""MCP server for Fantastical — thin wrapper over api.py."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from fantastical import api

mcp = FastMCP("fantastical")


@mcp.tool()
def list_calendars() -> str:
    """List all Fantastical calendars."""
    return json.dumps(api.list_calendars())


@mcp.tool()
def list_events(from_date: str = "today", to_date: str = "today", calendar: str | None = None) -> str:
    """List calendar events in a date range (YYYY-MM-DD). Accepts 'today', 'tomorrow', 'yesterday'."""
    return json.dumps(api.list_events(from_date, to_date, calendar))


@mcp.tool()
def create_event(sentence: str, calendar: str | None = None, notes: str | None = None) -> str:
    """Create event using natural language (e.g. 'Meeting tomorrow at 3pm')."""
    return json.dumps(api.create_event(sentence, calendar, notes))


@mcp.tool()
def show_schedule(date: str = "today") -> str:
    """Show the schedule for a given date (YYYY-MM-DD, 'today', 'tomorrow')."""
    return json.dumps(api.show_schedule(date))


@mcp.tool()
def list_tasks(list_name: str | None = None, overdue: bool = False) -> str:
    """List tasks, optionally filtered by list name or overdue status."""
    return json.dumps(api.list_tasks(list_name, overdue))


@mcp.tool()
def search_events(query: str) -> str:
    """Search events by title."""
    return json.dumps(api.search_events(query))


@mcp.tool()
def get_selected() -> str:
    """Get currently selected calendar items in Fantastical."""
    return json.dumps(api.get_selected())

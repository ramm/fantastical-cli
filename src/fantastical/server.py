"""MCP server for Fantastical — thin wrapper over api.py."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from fantastical import api

mcp = FastMCP("fantastical")


@mcp.tool()
async def list_calendars() -> str:
    """List all Fantastical calendars."""
    data = await asyncio.to_thread(api.list_calendars)
    return json.dumps(data)


@mcp.tool()
async def list_events(from_date: str = "today", to_date: str | None = None, calendar: str | None = None) -> str:
    """List calendar events in a date range (YYYY-MM-DD). Accepts 'today', 'tomorrow', 'yesterday'. Defaults to today only."""
    data = await asyncio.to_thread(api.list_events, from_date, to_date, calendar)
    return json.dumps(data)


@mcp.tool()
async def create_event(sentence: str, calendar: str | None = None, notes: str | None = None) -> str:
    """Create event using natural language (e.g. 'Meeting tomorrow at 3pm')."""
    data = await asyncio.to_thread(api.create_event, sentence, calendar, notes)
    return json.dumps(data)


@mcp.tool()
async def search_events(query: str) -> str:
    """Search events by title."""
    data = await asyncio.to_thread(api.search_events, query)
    return json.dumps(data)



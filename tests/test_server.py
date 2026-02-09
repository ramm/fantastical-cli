"""Tests for MCP server — tool registration, argument passing, JSON serialization, error propagation."""

import json
from unittest.mock import patch

import pytest

from mcp.server.fastmcp.exceptions import ToolError

from fantastical.api import FantasticalError
from fantastical.server import mcp


def _text(result: tuple) -> str:
    """Extract text from call_tool return value (content_list, extras)."""
    return result[0][0].text


# --- Tool registration ---


@pytest.mark.anyio
async def test_all_tools_registered():
    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    assert names == ["create_event", "list_calendars", "list_events", "search_events"]


# --- list_calendars ---


@pytest.mark.anyio
@patch("fantastical.server.api.list_calendars")
async def test_list_calendars(mock_lc):
    cals = [{"id": "1", "title": "Work"}, {"id": "2", "title": "Home"}]
    mock_lc.return_value = cals
    result = await mcp.call_tool("list_calendars", {})
    assert json.loads(_text(result)) == cals


@pytest.mark.anyio
@patch("fantastical.server.api.list_calendars")
async def test_list_calendars_error(mock_lc):
    mock_lc.side_effect = FantasticalError("JXA timeout")
    with pytest.raises(ToolError, match="JXA timeout"):
        await mcp.call_tool("list_calendars", {})


# --- list_events ---


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_list_events_defaults(mock_le):
    mock_le.return_value = []
    await mcp.call_tool("list_events", {})
    mock_le.assert_called_once_with("today", None, None)


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_list_events_all_args(mock_le):
    mock_le.return_value = []
    await mcp.call_tool("list_events", {
        "from_date": "2026-01-01",
        "to_date": "2026-01-31",
        "calendar": "Work",
    })
    mock_le.assert_called_once_with("2026-01-01", "2026-01-31", "Work")


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_list_events_returns_json(mock_le):
    events = [{"title": "Standup", "startDate": "2026-02-09"}]
    mock_le.return_value = events
    result = await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    assert json.loads(_text(result)) == events


# --- create_event ---


@pytest.mark.anyio
@patch("fantastical.server.api.create_event")
async def test_create_event_required_arg(mock_ce):
    mock_ce.return_value = {"title": "Lunch", "ok": True}
    result = await mcp.call_tool("create_event", {"sentence": "Lunch tomorrow at noon"})
    mock_ce.assert_called_once_with("Lunch tomorrow at noon", None, None)
    assert json.loads(_text(result)) == {"title": "Lunch", "ok": True}


@pytest.mark.anyio
@patch("fantastical.server.api.create_event")
async def test_create_event_optional_args(mock_ce):
    mock_ce.return_value = {"title": "Lunch"}
    await mcp.call_tool("create_event", {
        "sentence": "Lunch tomorrow",
        "calendar": "Work",
        "notes": "Bring laptop",
    })
    mock_ce.assert_called_once_with("Lunch tomorrow", "Work", "Bring laptop")


# --- search_events ---


@pytest.mark.anyio
@patch("fantastical.server.api.search_events")
async def test_search_events(mock_se):
    events = [{"title": "Team sync"}]
    mock_se.return_value = events
    result = await mcp.call_tool("search_events", {"query": "sync"})
    mock_se.assert_called_once_with("sync")
    assert json.loads(_text(result)) == events

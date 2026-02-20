"""Tests for MCP server — tool registration, compact output, caching, new tools."""

import asyncio
import threading
from unittest.mock import patch

import pytest

from mcp.server.fastmcp.exceptions import ToolError

from fantastical.api import FantasticalError
from fantastical.server import _event_cache, _attendee_cache, _cache_lock, _hash_event, _cache_and_compact, mcp


def _text(result: tuple) -> str:
    """Extract text from call_tool return value (content_list, extras)."""
    return result[0][0].text


def _clear_cache():
    """Helper to reset cache between tests."""
    with _cache_lock:
        _event_cache.clear()
        _attendee_cache.clear()


@pytest.fixture(autouse=True)
def clean_cache():
    """Ensure each test starts with a clean cache."""
    _clear_cache()
    yield
    _clear_cache()


# --- Tool registration ---


@pytest.mark.anyio
async def test_all_tools_registered():
    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    assert names == [
        "clear_cache",
        "create_event",
        "get_event_details",
        "list_calendars",
        "list_events",
        "search_events",
    ]


# --- list_calendars ---


@pytest.mark.anyio
@patch("fantastical.server.api.list_calendars")
async def test_list_calendars_plain_text(mock_lc):
    cals = [{"id": "abc123", "title": "Work"}, {"id": "def456", "title": "Home"}]
    mock_lc.return_value = cals
    result = await mcp.call_tool("list_calendars", {})
    text = _text(result)
    assert "Work (abc123)" in text
    assert "Home (def456)" in text


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
async def test_list_events_compact_output(mock_le):
    events = [
        {"title": "Standup", "startDate": "9 Feb 2026 at 10:00", "endDate": "9 Feb 2026 at 10:30",
         "calendarIdentifier": "cal1", "fantasticalURL": "x-fantastical3://show/1",
         "attendeeCount": "3"},
    ]
    mock_le.return_value = events
    result = await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    text = _text(result)
    lines = text.strip().split("\n")
    assert lines[0] == "count: 1"
    parts = lines[1].split("\t")
    assert len(parts) == 5  # id, title, startDate, endDate, attendeeCount
    assert len(parts[0]) == 8  # 8-char hash
    assert parts[1] == "Standup"
    assert parts[2] == "9 Feb 2026 at 10:00"
    assert parts[3] == "9 Feb 2026 at 10:30"
    assert parts[4] == "3"


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_list_events_caches_events(mock_le):
    events = [
        {"title": "Standup", "startDate": "9 Feb 2026 at 10:00", "endDate": "9 Feb 2026 at 10:30",
         "calendarIdentifier": "cal1", "fantasticalURL": "x-fantastical3://show/1"},
    ]
    mock_le.return_value = events
    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    assert len(_event_cache) == 1
    cached = list(_event_cache.values())[0]
    assert cached["title"] == "Standup"
    assert cached["calendarIdentifier"] == "cal1"
    assert cached["fantasticalURL"] == "x-fantastical3://show/1"
    assert "id" in cached


# --- Hashing ---


def test_hash_event_uses_url_when_present():
    ev = {"title": "A", "startDate": "s", "endDate": "e", "calendarIdentifier": "c1",
          "fantasticalURL": "x-fantastical3://show/1"}
    h = _hash_event(ev)
    assert len(h) == 8
    # Same URL + calendar → same hash
    ev2 = dict(ev)
    assert _hash_event(ev2) == h


def test_hash_event_falls_back_to_title_dates():
    ev = {"title": "A", "startDate": "s", "endDate": "e", "calendarIdentifier": "c1",
          "fantasticalURL": None}
    h = _hash_event(ev)
    assert len(h) == 8


def test_hash_event_different_calendars():
    ev1 = {"title": "A", "startDate": "s", "endDate": "e", "calendarIdentifier": "c1",
           "fantasticalURL": None}
    ev2 = {"title": "A", "startDate": "s", "endDate": "e", "calendarIdentifier": "c2",
           "fantasticalURL": None}
    assert _hash_event(ev1) != _hash_event(ev2)


# --- _cache_and_compact ---


def test_cache_and_compact_format():
    events = [
        {"title": "Ev1", "startDate": "s1", "endDate": "e1", "calendarIdentifier": "c", "fantasticalURL": "url1"},
        {"title": "Ev2", "startDate": "s2", "endDate": "e2", "calendarIdentifier": "c", "fantasticalURL": "url2"},
    ]
    output = _cache_and_compact(events)
    lines = output.strip().split("\n")
    assert lines[0] == "count: 2"
    assert len(lines) == 3  # header + 2 events
    assert len(_event_cache) == 2


def test_cache_and_compact_merges():
    ev = {"title": "Ev1", "startDate": "s1", "endDate": "e1", "calendarIdentifier": "c", "fantasticalURL": "url1"}
    _cache_and_compact([ev])
    assert len(_event_cache) == 1
    # Call again with same event — no duplicate
    ev2 = {"title": "Ev1", "startDate": "s1", "endDate": "e1", "calendarIdentifier": "c",
            "fantasticalURL": "url1", "calendarName": "Work"}
    _cache_and_compact([ev2])
    assert len(_event_cache) == 1
    # But calendarName should be updated
    cached = list(_event_cache.values())[0]
    assert cached["calendarName"] == "Work"


# --- create_event (unchanged — still JSON) ---


@pytest.mark.anyio
@patch("fantastical.server.api.create_event")
async def test_create_event_required_arg(mock_ce):
    mock_ce.return_value = {"title": "Lunch", "ok": True}
    result = await mcp.call_tool("create_event", {"sentence": "Lunch tomorrow at noon"})
    mock_ce.assert_called_once_with("Lunch tomorrow at noon", None, None)
    import json
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
async def test_search_events_compact_output(mock_se):
    events = [{"title": "Team sync", "startDate": "s", "endDate": "e",
               "calendarIdentifier": "c", "fantasticalURL": "url"}]
    mock_se.return_value = events
    result = await mcp.call_tool("search_events", {"query": "sync"})
    mock_se.assert_called_once_with("sync", None, None)
    text = _text(result)
    assert text.startswith("count: 1")
    assert "Team sync" in text


@pytest.mark.anyio
@patch("fantastical.server.api.search_events")
async def test_search_events_with_dates(mock_se):
    mock_se.return_value = []
    await mcp.call_tool("search_events", {
        "query": "sync",
        "from_date": "2026-01-01",
        "to_date": "2026-06-01",
    })
    mock_se.assert_called_once_with("sync", "2026-01-01", "2026-06-01")


# --- get_event_details ---


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_get_event_details_found(mock_le):
    events = [{"title": "Standup", "startDate": "s", "endDate": "e",
               "calendarIdentifier": "cal1", "fantasticalURL": "url1", "calendarName": "Work"}]
    mock_le.return_value = events
    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    eid = list(_event_cache.keys())[0]
    result = await mcp.call_tool("get_event_details", {"event_id": eid})
    text = _text(result)
    assert "title: Standup" in text
    assert "calendarIdentifier: cal1" in text
    assert "calendarName: Work" in text


@pytest.mark.anyio
async def test_get_event_details_not_found():
    result = await mcp.call_tool("get_event_details", {"event_id": "nonexist"})
    text = _text(result)
    assert "not found in cache" in text


# --- clear_cache ---


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_clear_cache(mock_le):
    events = [{"title": "A", "startDate": "s", "endDate": "e",
               "calendarIdentifier": "c", "fantasticalURL": "u"}]
    mock_le.return_value = events
    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    assert len(_event_cache) == 1
    result = await mcp.call_tool("clear_cache", {})
    text = _text(result)
    assert "1 events removed" in text
    assert len(_event_cache) == 0


@pytest.mark.anyio
async def test_clear_cache_empty():
    result = await mcp.call_tool("clear_cache", {})
    text = _text(result)
    assert "0 events removed" in text


# --- Parallel tool use and cache consistency ---


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_parallel_list_events_no_duplicates(mock_le):
    """Two concurrent list_events returning overlapping events — no duplicate cache entries."""
    shared_event = {"title": "Shared", "startDate": "s", "endDate": "e",
                    "calendarIdentifier": "c", "fantasticalURL": "shared-url"}
    week1_only = {"title": "Week1", "startDate": "s1", "endDate": "e1",
                  "calendarIdentifier": "c", "fantasticalURL": "url-w1"}
    week2_only = {"title": "Week2", "startDate": "s2", "endDate": "e2",
                  "calendarIdentifier": "c", "fantasticalURL": "url-w2"}

    def side_effect(from_date, to_date, calendar):
        if from_date == "2026-02-01":
            return [dict(shared_event), dict(week1_only)]
        return [dict(shared_event), dict(week2_only)]

    mock_le.side_effect = side_effect

    r1, r2 = await asyncio.gather(
        mcp.call_tool("list_events", {"from_date": "2026-02-01", "to_date": "2026-02-14"}),
        mcp.call_tool("list_events", {"from_date": "2026-02-15", "to_date": "2026-02-28"}),
    )

    # Both calls succeed
    assert "count: 2" in _text(r1)
    assert "count: 2" in _text(r2)

    # Cache has exactly 3 unique events (shared de-duped)
    assert len(_event_cache) == 3
    titles = {ev["title"] for ev in _event_cache.values()}
    assert titles == {"Shared", "Week1", "Week2"}


@pytest.mark.anyio
@patch("fantastical.server.api.search_events")
@patch("fantastical.server.api.list_events")
async def test_parallel_list_and_search_merge_cache(mock_le, mock_se):
    """Concurrent list_events + search_events both populate the same cache."""
    mock_le.return_value = [
        {"title": "Listed", "startDate": "s", "endDate": "e",
         "calendarIdentifier": "c", "fantasticalURL": "url-listed"},
    ]
    mock_se.return_value = [
        {"title": "Searched", "startDate": "s", "endDate": "e",
         "calendarIdentifier": "c", "fantasticalURL": "url-searched"},
    ]

    await asyncio.gather(
        mcp.call_tool("list_events", {"from_date": "2026-02-09"}),
        mcp.call_tool("search_events", {"query": "Searched"}),
    )

    assert len(_event_cache) == 2
    titles = {ev["title"] for ev in _event_cache.values()}
    assert titles == {"Listed", "Searched"}


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_parallel_list_events_enriches_on_overlap(mock_le):
    """Second call returning same event with extra field updates the cache."""
    bare = {"title": "Ev", "startDate": "s", "endDate": "e",
            "calendarIdentifier": "c", "fantasticalURL": "url-ev"}
    enriched = {"title": "Ev", "startDate": "s", "endDate": "e",
                "calendarIdentifier": "c", "fantasticalURL": "url-ev", "calendarName": "Work"}

    call_count = 0

    def side_effect(from_date, to_date, calendar):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [dict(bare)]
        return [dict(enriched)]

    mock_le.side_effect = side_effect

    await asyncio.gather(
        mcp.call_tool("list_events", {"from_date": "2026-02-01", "to_date": "2026-02-07"}),
        mcp.call_tool("list_events", {"from_date": "2026-02-01", "to_date": "2026-02-07"}),
    )

    # Still one entry — same event ID
    assert len(_event_cache) == 1
    cached = list(_event_cache.values())[0]
    # The second write wins, so calendarName should be present
    assert cached["calendarName"] == "Work"


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_get_event_details_consistent_after_parallel_writes(mock_le):
    """get_event_details returns coherent data even after parallel cache writes."""
    events_a = [{"title": f"A{i}", "startDate": f"s{i}", "endDate": f"e{i}",
                 "calendarIdentifier": "c", "fantasticalURL": f"url-a{i}"} for i in range(20)]
    events_b = [{"title": f"B{i}", "startDate": f"s{i}", "endDate": f"e{i}",
                 "calendarIdentifier": "c", "fantasticalURL": f"url-b{i}"} for i in range(20)]

    def side_effect(from_date, to_date, calendar):
        if from_date == "2026-01-01":
            return [dict(e) for e in events_a]
        return [dict(e) for e in events_b]

    mock_le.side_effect = side_effect

    await asyncio.gather(
        mcp.call_tool("list_events", {"from_date": "2026-01-01", "to_date": "2026-01-31"}),
        mcp.call_tool("list_events", {"from_date": "2026-02-01", "to_date": "2026-02-28"}),
    )

    assert len(_event_cache) == 40

    # Every cached event is retrievable and has consistent fields
    for eid, ev in _event_cache.items():
        result = await mcp.call_tool("get_event_details", {"event_id": eid})
        text = _text(result)
        assert f"id: {eid}" in text
        assert f"title: {ev['title']}" in text


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_clear_cache_during_reads(mock_le):
    """clear_cache between two list_events calls resets correctly."""
    mock_le.return_value = [
        {"title": "Ev", "startDate": "s", "endDate": "e",
         "calendarIdentifier": "c", "fantasticalURL": "url-ev"},
    ]

    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    assert len(_event_cache) == 1
    eid_before = list(_event_cache.keys())[0]

    await mcp.call_tool("clear_cache", {})
    assert len(_event_cache) == 0

    # Event is gone
    result = await mcp.call_tool("get_event_details", {"event_id": eid_before})
    assert "not found in cache" in _text(result)

    # Re-populate
    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    assert len(_event_cache) == 1
    # Same event gets same ID
    assert list(_event_cache.keys())[0] == eid_before


def test_cache_and_compact_threaded_consistency():
    """Hammer _cache_and_compact from multiple threads — cache stays consistent."""
    batches = [
        [{"title": f"T{t}E{i}", "startDate": f"s{i}", "endDate": f"e{i}",
          "calendarIdentifier": "c", "fantasticalURL": f"url-t{t}-e{i}"}
         for i in range(50)]
        for t in range(4)
    ]

    errors = []

    def worker(batch):
        try:
            output = _cache_and_compact(batch)
            lines = output.strip().split("\n")
            assert lines[0] == f"count: {len(batch)}"
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(b,)) for b in batches]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # 4 threads × 50 events, all unique URLs → 200 cache entries
    assert len(_event_cache) == 200
    # Every entry has an 8-char id
    for eid, ev in _event_cache.items():
        assert len(eid) == 8
        assert ev["id"] == eid


def test_threaded_same_event_150_writes():
    """3 threads each write the same event 50 times — exactly 1 cache entry."""
    event = {"title": "Daily", "startDate": "9 Feb 2026 at 09:00",
             "endDate": "9 Feb 2026 at 09:30", "calendarIdentifier": "c1",
             "fantasticalURL": "x-fantastical3://show/daily"}
    expected_id = _hash_event(event)

    errors = []

    def worker():
        try:
            for _ in range(50):
                _cache_and_compact([dict(event)])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(_event_cache) == 1
    assert expected_id in _event_cache
    cached = _event_cache[expected_id]
    assert cached["id"] == expected_id
    assert cached["title"] == "Daily"
    assert cached["fantasticalURL"] == "x-fantastical3://show/daily"


# --- get_event_details with attendees ---


@pytest.mark.anyio
@patch("fantastical.server.api.get_event_attendees")
@patch("fantastical.server.api.list_events")
async def test_get_event_details_includes_attendees(mock_le, mock_ga):
    """get_event_details lazily fetches and includes attendees."""
    events = [{"title": "Standup", "startDate": "9 Feb 2026 at 10:00", "endDate": "9 Feb 2026 at 10:30",
               "calendarIdentifier": "cal1", "fantasticalURL": "x-fantastical3://show/1",
               "attendeeCount": "2"}]
    mock_le.return_value = events
    mock_ga.return_value = [
        {"displayString": "Alice", "email": "alice@example.com"},
        {"displayString": "Bob", "email": "bob@example.com"},
    ]

    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    eid = list(_event_cache.keys())[0]

    result = await mcp.call_tool("get_event_details", {"event_id": eid})
    text = _text(result)
    assert "title: Standup" in text
    assert "attendees:" in text
    assert "Alice <alice@example.com>" in text
    assert "Bob <bob@example.com>" in text
    mock_ga.assert_called_once()

    # Attendees should now be cached
    assert eid in _attendee_cache
    assert len(_attendee_cache[eid]) == 2


@pytest.mark.anyio
@patch("fantastical.server.api.get_event_attendees")
@patch("fantastical.server.api.list_events")
async def test_get_event_details_attendee_cache_hit(mock_le, mock_ga):
    """Second get_event_details returns cached attendees without shortcut call."""
    events = [{"title": "Standup", "startDate": "9 Feb 2026 at 10:00", "endDate": "9 Feb 2026 at 10:30",
               "calendarIdentifier": "cal1", "fantasticalURL": "x-fantastical3://show/1",
               "attendeeCount": "1"}]
    mock_le.return_value = events
    mock_ga.return_value = [{"displayString": "Alice", "email": "alice@example.com"}]

    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    eid = list(_event_cache.keys())[0]

    # First call — cache miss
    await mcp.call_tool("get_event_details", {"event_id": eid})
    assert mock_ga.call_count == 1

    # Second call — cache hit
    result = await mcp.call_tool("get_event_details", {"event_id": eid})
    assert mock_ga.call_count == 1  # not called again
    text = _text(result)
    assert "Alice <alice@example.com>" in text


@pytest.mark.anyio
@patch("fantastical.server.api.get_event_attendees")
@patch("fantastical.server.api.list_events")
async def test_get_event_details_no_attendees(mock_le, mock_ga):
    """get_event_details omits attendees section when there are none."""
    events = [{"title": "Solo", "startDate": "9 Feb 2026 at 10:00", "endDate": "9 Feb 2026 at 10:30",
               "calendarIdentifier": "cal1", "fantasticalURL": "x-fantastical3://show/2",
               "attendeeCount": "0"}]
    mock_le.return_value = events
    mock_ga.return_value = []

    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    eid = list(_event_cache.keys())[0]

    result = await mcp.call_tool("get_event_details", {"event_id": eid})
    text = _text(result)
    assert "title: Solo" in text
    assert "attendees:" not in text


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_get_event_details_unparseable_date_skips_attendees(mock_le):
    """get_event_details skips attendees when the date can't be parsed."""
    events = [{"title": "NoDate", "startDate": "garbage", "endDate": "garbage",
               "calendarIdentifier": "c", "fantasticalURL": "url"}]
    mock_le.return_value = events
    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    eid = list(_event_cache.keys())[0]

    result = await mcp.call_tool("get_event_details", {"event_id": eid})
    text = _text(result)
    assert "title: NoDate" in text
    assert "attendees:" not in text


@pytest.mark.anyio
@patch("fantastical.server.api.list_events")
async def test_clear_cache_clears_attendees(mock_le):
    """clear_cache removes both event and attendee caches."""
    events = [{"title": "A", "startDate": "s", "endDate": "e",
               "calendarIdentifier": "c", "fantasticalURL": "u"}]
    mock_le.return_value = events
    await mcp.call_tool("list_events", {"from_date": "2026-02-09"})
    eid = list(_event_cache.keys())[0]

    # Manually populate attendee cache
    with _cache_lock:
        _attendee_cache[eid] = [{"displayString": "Alice", "email": "a@b.com"}]

    await mcp.call_tool("clear_cache", {})
    assert len(_event_cache) == 0
    assert len(_attendee_cache) == 0

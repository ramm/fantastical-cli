"""Tests for api._resolve_date, _parse_event_date, list_events, search_events, _get_events_for_range."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from fantastical.api import (
    FantasticalError,
    _get_events_for_range,
    _parse_event_date,
    _resolve_date,
    list_events,
    search_events,
)


# --- _resolve_date ---


def test_resolve_today():
    assert _resolve_date("today") == date.today().isoformat()


def test_resolve_tomorrow():
    assert _resolve_date("tomorrow") == (date.today() + timedelta(days=1)).isoformat()


def test_resolve_yesterday():
    assert _resolve_date("yesterday") == (date.today() - timedelta(days=1)).isoformat()


def test_resolve_case_insensitive():
    assert _resolve_date("TODAY") == date.today().isoformat()


def test_resolve_whitespace():
    assert _resolve_date(" today ") == date.today().isoformat()


def test_resolve_valid_iso():
    assert _resolve_date("2026-06-15") == "2026-06-15"


def test_resolve_invalid_format():
    with pytest.raises(FantasticalError):
        _resolve_date("not-a-date")


def test_resolve_invalid_month():
    with pytest.raises(FantasticalError):
        _resolve_date("2026-13-01")


def test_resolve_wrong_order():
    with pytest.raises(FantasticalError):
        _resolve_date("02-09-2026")


# --- _parse_event_date ---


def test_parse_shortcuts_format():
    assert _parse_event_date("12 Feb 2026 at 12:00") == date(2026, 2, 12)


def test_parse_iso_with_timezone():
    assert _parse_event_date("2026-02-09T10:00:00+00:00") == date(2026, 2, 9)


def test_parse_iso_date_only():
    assert _parse_event_date("2026-02-09") == date(2026, 2, 9)


def test_parse_iso_space_separator():
    assert _parse_event_date("2026-02-09 10:00:00") == date(2026, 2, 9)


def test_parse_none():
    assert _parse_event_date(None) is None


def test_parse_empty_string():
    assert _parse_event_date("") is None


def test_parse_garbage():
    assert _parse_event_date("not a date") is None


# --- list_events ---


@patch("fantastical.api._get_events_for_range")
def test_list_events_default_range(mock_get):
    mock_get.return_value = []
    list_events(from_date="today", to_date=None)
    args = mock_get.call_args
    # When to_date is None, resolved_to == resolved_from
    assert args[0][0] == args[0][1]


@patch("fantastical.api._get_events_for_range")
def test_list_events_range_cap_ok(mock_get):
    mock_get.return_value = []
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=365)).isoformat()
    list_events(from_date=start, to_date=end)
    mock_get.assert_called_once()


@patch("fantastical.api._get_events_for_range")
def test_list_events_range_cap_exceeded(mock_get):
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=366)).isoformat()
    with pytest.raises(FantasticalError, match="too large"):
        list_events(from_date=start, to_date=end)


@patch("fantastical.api._get_events_for_range")
def test_list_events_calendar_filter(mock_get):
    mock_get.return_value = [
        {"title": "A", "calendarName": "Work", "calendar": "id1"},
        {"title": "B", "calendarName": "Personal", "calendar": "id2"},
    ]
    result = list_events(from_date="today", calendar="Work")
    assert len(result) == 1
    assert result[0]["title"] == "A"


@patch("fantastical.api._get_events_for_range")
def test_list_events_calendar_filter_case_insensitive(mock_get):
    mock_get.return_value = [
        {"title": "A", "calendarName": "Work", "calendar": "id1"},
    ]
    result = list_events(from_date="today", calendar="work")
    assert len(result) == 1


@patch("fantastical.api._get_events_for_range")
def test_list_events_calendar_filter_id(mock_get):
    mock_get.return_value = [
        {"title": "A", "calendarName": None, "calendar": "abc123"},
    ]
    result = list_events(from_date="today", calendar="abc123")
    assert len(result) == 1


@patch("fantastical.api._get_events_for_range")
def test_list_events_no_calendar_match(mock_get):
    mock_get.return_value = [
        {"title": "A", "calendarName": "Work", "calendar": "id1"},
    ]
    result = list_events(from_date="today", calendar="Nonexistent")
    assert result == []


# --- search_events ---


@patch("fantastical.api._get_events_for_range")
def test_search_passes_title_query(mock_get):
    mock_get.return_value = []
    search_events(query="Meeting")
    _, kwargs = mock_get.call_args
    assert kwargs["title_query"] == "Meeting"


@patch("fantastical.api._get_events_for_range")
def test_search_default_date_range(mock_get):
    mock_get.return_value = []
    today = date.today()
    search_events(query="test")
    args = mock_get.call_args[0]
    assert args[0] == (today - timedelta(days=30)).isoformat()
    assert args[1] == (today + timedelta(days=30)).isoformat()


@patch("fantastical.api._get_events_for_range")
def test_search_custom_from_date(mock_get):
    mock_get.return_value = []
    today = date.today()
    search_events(query="test", from_date="2026-01-01")
    args = mock_get.call_args[0]
    assert args[0] == "2026-01-01"
    assert args[1] == (today + timedelta(days=30)).isoformat()


@patch("fantastical.api._get_events_for_range")
def test_search_custom_to_date(mock_get):
    mock_get.return_value = []
    today = date.today()
    search_events(query="test", to_date="2026-06-01")
    args = mock_get.call_args[0]
    assert args[0] == (today - timedelta(days=30)).isoformat()
    assert args[1] == "2026-06-01"


@patch("fantastical.api._get_events_for_range")
def test_search_custom_both_dates(mock_get):
    mock_get.return_value = []
    search_events(query="test", from_date="2026-01-01", to_date="2026-06-01")
    args = mock_get.call_args[0]
    assert args[0] == "2026-01-01"
    assert args[1] == "2026-06-01"


@patch("fantastical.api._get_events_for_range")
def test_search_accepts_today_keyword(mock_get):
    mock_get.return_value = []
    search_events(query="test", from_date="today")
    args = mock_get.call_args[0]
    assert args[0] == date.today().isoformat()


def test_search_range_cap_exceeded():
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=366)).isoformat()
    with pytest.raises(FantasticalError, match="too large"):
        search_events(query="test", from_date=start, to_date=end)


@patch("fantastical.api._get_events_for_range")
def test_search_range_cap_365_ok(mock_get):
    mock_get.return_value = []
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=365)).isoformat()
    search_events(query="test", from_date=start, to_date=end)
    mock_get.assert_called_once()


# --- _get_events_for_range ---


@patch("fantastical.api._get_calendar_map")
@patch("fantastical.api._run_shortcut_or_raise")
def test_get_events_enriches_calendar(mock_run, mock_cal_map):
    mock_run.return_value = [
        {"title": "Ev", "startDate": "2026-02-09 10:00:00", "calendar": "cal-id-1"},
    ]
    mock_cal_map.return_value = {"cal-id-1": "Work"}
    result = _get_events_for_range("2026-02-09", "2026-02-09")
    assert result[0]["calendarName"] == "Work"


@patch("fantastical.api._get_calendar_map")
@patch("fantastical.api._run_shortcut_or_raise")
def test_get_events_empty_cal_map(mock_run, mock_cal_map):
    mock_run.return_value = [
        {"title": "Ev", "startDate": "2026-02-09 10:00:00", "calendar": "cal-id-1"},
    ]
    mock_cal_map.return_value = {}
    result = _get_events_for_range("2026-02-09", "2026-02-09")
    assert "calendarName" not in result[0]


@patch("fantastical.api._get_calendar_map")
@patch("fantastical.api._run_shortcut_or_raise")
def test_get_events_filters_out_of_range(mock_run, mock_cal_map):
    mock_run.return_value = [
        {"title": "Before", "startDate": "2026-02-08 10:00:00", "calendar": "c"},
    ]
    mock_cal_map.return_value = {}
    result = _get_events_for_range("2026-02-09", "2026-02-10")
    assert result == []


@patch("fantastical.api._get_calendar_map")
@patch("fantastical.api._run_shortcut_or_raise")
def test_get_events_includes_boundary(mock_run, mock_cal_map):
    mock_run.return_value = [
        {"title": "OnStart", "startDate": "2026-02-09 08:00:00", "calendar": "c"},
    ]
    mock_cal_map.return_value = {}
    result = _get_events_for_range("2026-02-09", "2026-02-10")
    assert len(result) == 1
    assert result[0]["title"] == "OnStart"


@patch("fantastical.api._get_calendar_map")
@patch("fantastical.api._run_shortcut_or_raise")
def test_get_events_null_start_included(mock_run, mock_cal_map):
    mock_run.return_value = [
        {"title": "NoDate", "startDate": None, "calendar": "c"},
    ]
    mock_cal_map.return_value = {}
    result = _get_events_for_range("2026-02-09", "2026-02-10")
    assert len(result) == 1


@patch("fantastical.api._get_calendar_map")
@patch("fantastical.api._run_shortcut_or_raise")
def test_get_events_passes_title_query(mock_run, mock_cal_map):
    mock_run.return_value = []
    mock_cal_map.return_value = {}
    _get_events_for_range("2026-02-09", "2026-02-10", title_query="test")
    call_args = mock_run.call_args
    # _run_shortcut_or_raise("find_events", shortcuts.get_events, from_iso, to_iso, title_query)
    assert call_args[0][4] == "test"

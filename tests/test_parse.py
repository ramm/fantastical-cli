"""Tests for shortcuts.parse_shortcut_output and shortcuts._parse_fields."""

from fantastical.backend.shortcuts import parse_shortcut_output, _parse_fields


# --- parse_shortcut_output ---


def test_empty_output():
    assert parse_shortcut_output("") == []


def test_single_record():
    output = "Meeting\x1f9 Feb\x1f9 Feb\x1fID\x1fURL\x1e"
    result = parse_shortcut_output(output)
    assert len(result) == 1
    assert result[0] == {
        "title": "Meeting",
        "startDate": "9 Feb",
        "endDate": "9 Feb",
        "calendar": "ID",
        "fantasticalURL": "URL",
    }


def test_multiple_records():
    output = "A\x1fS1\x1fE1\x1fC1\x1fU1\x1eB\x1fS2\x1fE2\x1fC2\x1fU2\x1e"
    result = parse_shortcut_output(output)
    assert len(result) == 2
    assert result[0]["title"] == "A"
    assert result[1]["title"] == "B"


def test_nil_becomes_none():
    output = "Title\x1fnil\x1fnil\x1fnil\x1fnil\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None
    assert result[0]["endDate"] is None
    assert result[0]["calendar"] is None
    assert result[0]["fantasticalURL"] is None


def test_null_becomes_none():
    output = "Title\x1fnull\x1fnull\x1fnull\x1fnull\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None


def test_parenthetical_null_becomes_none():
    output = "Title\x1f(null)\x1f(null)\x1f(null)\x1f(null)\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None


def test_empty_field_becomes_none():
    output = "Title\x1f\x1f\x1f\x1f\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None
    assert result[0]["endDate"] is None
    assert result[0]["calendar"] is None
    assert result[0]["fantasticalURL"] is None


def test_whitespace_only_becomes_none():
    output = "Title\x1f  \x1f  \x1f  \x1f  \x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None
    assert result[0]["endDate"] is None


def test_fewer_fields_than_expected():
    output = "Title\x1fStart\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["title"] == "Title"
    assert result[0]["startDate"] == "Start"
    assert result[0]["endDate"] is None
    assert result[0]["calendar"] is None
    assert result[0]["fantasticalURL"] is None


def test_pipe_in_title_preserved():
    output = "A | B\x1fStart\x1fEnd\x1fCal\x1fURL\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["title"] == "A | B"


def test_newline_in_field():
    output = "Title\x1fStart\x1fEnd\x1fID\x1fline1\nline2\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["fantasticalURL"] == "line1\nline2"


def test_trailing_empty_records():
    output = "T\x1fS\x1fE\x1fC\x1fU\x1e\x1e\x1e"
    result = parse_shortcut_output(output)
    assert len(result) == 1


def test_whitespace_around_values():
    output = " Title \x1f Start \x1f End \x1f Cal \x1f URL \x1e"
    result = parse_shortcut_output(output)
    assert result[0]["title"] == "Title"
    assert result[0]["startDate"] == "Start"
    assert result[0]["endDate"] == "End"
    assert result[0]["calendar"] == "Cal"
    assert result[0]["fantasticalURL"] == "URL"


# --- _parse_fields ---


def test_parse_fields_empty_list():
    result = _parse_fields([])
    assert result == {
        "title": None,
        "startDate": None,
        "endDate": None,
        "calendar": None,
        "fantasticalURL": None,
    }


def test_parse_fields_partial():
    result = _parse_fields(["Title", "Start"])
    assert result["title"] == "Title"
    assert result["startDate"] == "Start"
    assert result["endDate"] is None
    assert result["calendar"] is None
    assert result["fantasticalURL"] is None


def test_parse_fields_full():
    result = _parse_fields(["T", "S", "E", "C", "U"])
    assert result == {
        "title": "T",
        "startDate": "S",
        "endDate": "E",
        "calendar": "C",
        "fantasticalURL": "U",
    }


def test_parse_fields_extra_ignored():
    result = _parse_fields(["T", "S", "E", "C", "U", "EXTRA"])
    assert len(result) == 5
    assert "EXTRA" not in result.values()

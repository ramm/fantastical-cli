"""Tests for shortcuts.parse_shortcut_output and shortcuts._parse_fields."""

from fantastical.backend.shortcuts import (
    ATTENDEE_FIELDS,
    EVENT_FIELDS,
    parse_shortcut_output,
    _parse_fields,
)


# --- parse_shortcut_output (default EVENT_FIELDS) ---


def test_empty_output():
    assert parse_shortcut_output("") == []


def test_single_record():
    output = "Meeting\x1f9 Feb\x1f9 Feb\x1fID\x1fURL\x1f3\x1e"
    result = parse_shortcut_output(output)
    assert len(result) == 1
    assert result[0] == {
        "title": "Meeting",
        "startDate": "9 Feb",
        "endDate": "9 Feb",
        "calendarIdentifier": "ID",
        "fantasticalURL": "URL",
        "attendeeCount": "3",
    }


def test_multiple_records():
    output = "A\x1fS1\x1fE1\x1fC1\x1fU1\x1f2\x1eB\x1fS2\x1fE2\x1fC2\x1fU2\x1f0\x1e"
    result = parse_shortcut_output(output)
    assert len(result) == 2
    assert result[0]["title"] == "A"
    assert result[0]["attendeeCount"] == "2"
    assert result[1]["title"] == "B"
    assert result[1]["attendeeCount"] == "0"


def test_nil_becomes_none():
    output = "Title\x1fnil\x1fnil\x1fnil\x1fnil\x1fnil\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None
    assert result[0]["endDate"] is None
    assert result[0]["calendarIdentifier"] is None
    assert result[0]["fantasticalURL"] is None
    assert result[0]["attendeeCount"] is None


def test_null_becomes_none():
    output = "Title\x1fnull\x1fnull\x1fnull\x1fnull\x1fnull\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None


def test_parenthetical_null_becomes_none():
    output = "Title\x1f(null)\x1f(null)\x1f(null)\x1f(null)\x1f(null)\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None


def test_empty_field_becomes_none():
    output = "Title\x1f\x1f\x1f\x1f\x1f\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None
    assert result[0]["endDate"] is None
    assert result[0]["calendarIdentifier"] is None
    assert result[0]["fantasticalURL"] is None
    assert result[0]["attendeeCount"] is None


def test_whitespace_only_becomes_none():
    output = "Title\x1f  \x1f  \x1f  \x1f  \x1f  \x1e"
    result = parse_shortcut_output(output)
    assert result[0]["startDate"] is None
    assert result[0]["endDate"] is None


def test_fewer_fields_than_expected():
    output = "Title\x1fStart\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["title"] == "Title"
    assert result[0]["startDate"] == "Start"
    assert result[0]["endDate"] is None
    assert result[0]["calendarIdentifier"] is None
    assert result[0]["fantasticalURL"] is None
    assert result[0]["attendeeCount"] is None


def test_five_field_output_gives_none_attendee_count():
    """Old shortcut output (5 fields) gracefully degrades — attendeeCount is None."""
    output = "Meeting\x1f9 Feb\x1f9 Feb\x1fID\x1fURL\x1e"
    result = parse_shortcut_output(output)
    assert len(result) == 1
    assert result[0]["title"] == "Meeting"
    assert result[0]["fantasticalURL"] == "URL"
    assert result[0]["attendeeCount"] is None


def test_pipe_in_title_preserved():
    output = "A | B\x1fStart\x1fEnd\x1fCal\x1fURL\x1f1\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["title"] == "A | B"


def test_newline_in_field():
    output = "Title\x1fStart\x1fEnd\x1fID\x1fline1\nline2\x1f2\x1e"
    result = parse_shortcut_output(output)
    assert result[0]["fantasticalURL"] == "line1\nline2"


def test_trailing_empty_records():
    output = "T\x1fS\x1fE\x1fC\x1fU\x1f0\x1e\x1e\x1e"
    result = parse_shortcut_output(output)
    assert len(result) == 1


def test_whitespace_around_values():
    output = " Title \x1f Start \x1f End \x1f Cal \x1f URL \x1f 5 \x1e"
    result = parse_shortcut_output(output)
    assert result[0]["title"] == "Title"
    assert result[0]["startDate"] == "Start"
    assert result[0]["endDate"] == "End"
    assert result[0]["calendarIdentifier"] == "Cal"
    assert result[0]["fantasticalURL"] == "URL"
    assert result[0]["attendeeCount"] == "5"


# --- parse_shortcut_output with ATTENDEE_FIELDS ---


def test_attendee_parse():
    output = "Alice\x1falice@example.com\x1eBob\x1fbob@example.com\x1e"
    result = parse_shortcut_output(output, field_names=ATTENDEE_FIELDS)
    assert len(result) == 2
    assert result[0] == {"displayString": "Alice", "email": "alice@example.com"}
    assert result[1] == {"displayString": "Bob", "email": "bob@example.com"}


def test_attendee_parse_empty():
    assert parse_shortcut_output("", field_names=ATTENDEE_FIELDS) == []


def test_attendee_parse_nil_email():
    output = "Alice\x1fnil\x1e"
    result = parse_shortcut_output(output, field_names=ATTENDEE_FIELDS)
    assert result[0]["displayString"] == "Alice"
    assert result[0]["email"] is None


# --- _parse_fields ---


def test_parse_fields_empty_list():
    result = _parse_fields([])
    assert result == {
        "title": None,
        "startDate": None,
        "endDate": None,
        "calendarIdentifier": None,
        "fantasticalURL": None,
        "attendeeCount": None,
    }


def test_parse_fields_partial():
    result = _parse_fields(["Title", "Start"])
    assert result["title"] == "Title"
    assert result["startDate"] == "Start"
    assert result["endDate"] is None
    assert result["calendarIdentifier"] is None
    assert result["fantasticalURL"] is None
    assert result["attendeeCount"] is None


def test_parse_fields_full():
    result = _parse_fields(["T", "S", "E", "C", "U", "3"])
    assert result == {
        "title": "T",
        "startDate": "S",
        "endDate": "E",
        "calendarIdentifier": "C",
        "fantasticalURL": "U",
        "attendeeCount": "3",
    }


def test_parse_fields_extra_ignored():
    result = _parse_fields(["T", "S", "E", "C", "U", "3", "EXTRA"])
    assert len(result) == 6
    assert "EXTRA" not in result.values()


def test_parse_fields_with_attendee_field_names():
    result = _parse_fields(["Alice", "alice@example.com"], field_names=ATTENDEE_FIELDS)
    assert result == {"displayString": "Alice", "email": "alice@example.com"}


def test_parse_fields_attendee_partial():
    result = _parse_fields(["Alice"], field_names=ATTENDEE_FIELDS)
    assert result == {"displayString": "Alice", "email": None}

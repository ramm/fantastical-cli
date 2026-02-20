"""Tests for shortcuts.get_events and shortcuts.get_attendees with mocked run_shortcut."""

from unittest.mock import patch

from fantastical.backend.shortcuts import _CHUNK_DAYS, get_attendees, get_events


# --- get_events ---


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_input_format(mock_run):
    mock_run.return_value = ""
    get_events("2026-02-09", "2026-02-10", "Meeting")
    # 2-day range fits in one chunk
    mock_run.assert_called_once_with(
        "find_events", input_text="2026-02-09|2026-02-11|Meeting"
    )


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_end_date_incremented(mock_run):
    mock_run.return_value = ""
    get_events("2026-02-09", "2026-02-10")
    call_kwargs = mock_run.call_args
    input_text = call_kwargs[1]["input_text"]
    # to_date="2026-02-10" → end_exclusive="2026-02-11"
    assert input_text.startswith("2026-02-09|2026-02-11|")


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_empty_title_query(mock_run):
    mock_run.return_value = ""
    get_events("2026-02-09", "2026-02-10")
    input_text = mock_run.call_args[1]["input_text"]
    assert input_text.endswith("|")


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_output_parsed(mock_run):
    mock_run.return_value = "Meeting\x1f9 Feb\x1f9 Feb\x1fCal\x1fURL\x1f3\x1e"
    result = get_events("2026-02-09", "2026-02-10")
    assert len(result) == 1
    assert result[0]["title"] == "Meeting"
    assert result[0]["calendarIdentifier"] == "Cal"
    assert result[0]["attendeeCount"] == "3"


# --- get_events: batching ---


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_large_range_batched(mock_run):
    """Ranges > _CHUNK_DAYS are split into multiple shortcut calls."""
    mock_run.return_value = ""
    get_events("2026-02-01", "2026-02-14")
    # 14 days with _CHUNK_DAYS=4 → 4 calls: Feb 1-4, 5-8, 9-12, 13-14
    assert mock_run.call_count == 4
    calls = [c[1]["input_text"] for c in mock_run.call_args_list]
    assert calls[0] == "2026-02-01|2026-02-05|"
    assert calls[1] == "2026-02-05|2026-02-09|"
    assert calls[2] == "2026-02-09|2026-02-13|"
    assert calls[3] == "2026-02-13|2026-02-15|"


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_batched_results_concatenated(mock_run):
    """Results from multiple chunks are combined into a single list."""
    mock_run.side_effect = [
        "A\x1fS1\x1fE1\x1fC1\x1fU1\x1f2\x1e",
        "B\x1fS2\x1fE2\x1fC2\x1fU2\x1f1\x1e",
    ]
    result = get_events("2026-02-01", "2026-02-08")
    # 8 days → 2 chunks
    assert mock_run.call_count == 2
    assert len(result) == 2
    assert result[0]["title"] == "A"
    assert result[1]["title"] == "B"


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_single_day_not_batched(mock_run):
    """A single-day range uses exactly one shortcut call."""
    mock_run.return_value = ""
    get_events("2026-02-09", "2026-02-09")
    mock_run.assert_called_once()


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_batching_passes_title_query(mock_run):
    """Title query is passed to every chunk."""
    mock_run.return_value = ""
    get_events("2026-02-01", "2026-02-10", "Standup")
    assert mock_run.call_count > 1
    for call in mock_run.call_args_list:
        assert call[1]["input_text"].endswith("|Standup")


# --- get_attendees ---


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_get_attendees_input_format(mock_run):
    mock_run.return_value = ""
    get_attendees("2026-02-20", "2026-02-20", "Standup")
    mock_run.assert_called_once_with(
        "find_attendees", input_text="2026-02-20|2026-02-21|Standup"
    )


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_get_attendees_end_date_incremented(mock_run):
    mock_run.return_value = ""
    get_attendees("2026-02-20", "2026-02-20")
    input_text = mock_run.call_args[1]["input_text"]
    # to_date="2026-02-20" → end_exclusive="2026-02-21"
    assert input_text.startswith("2026-02-20|2026-02-21|")


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_get_attendees_empty_title(mock_run):
    mock_run.return_value = ""
    get_attendees("2026-02-20", "2026-02-20")
    input_text = mock_run.call_args[1]["input_text"]
    assert input_text.endswith("|")


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_get_attendees_output_parsed(mock_run):
    mock_run.return_value = "Alice\x1falice@example.com\x1eBob\x1fbob@example.com\x1e"
    result = get_attendees("2026-02-20", "2026-02-20", "Meeting")
    assert len(result) == 2
    assert result[0] == {"displayString": "Alice", "email": "alice@example.com"}
    assert result[1] == {"displayString": "Bob", "email": "bob@example.com"}


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_get_attendees_empty_output(mock_run):
    mock_run.return_value = ""
    result = get_attendees("2026-02-20", "2026-02-20")
    assert result == []

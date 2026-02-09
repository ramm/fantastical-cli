"""Tests for shortcuts.get_events with mocked run_shortcut."""

from unittest.mock import patch

from fantastical.backend.shortcuts import get_events


@patch("fantastical.backend.shortcuts.run_shortcut")
def test_input_format(mock_run):
    mock_run.return_value = ""
    get_events("2026-02-09", "2026-02-10", "Meeting")
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
    mock_run.return_value = "Meeting\x1f9 Feb\x1f9 Feb\x1fCal\x1fURL\x1e"
    result = get_events("2026-02-09", "2026-02-10")
    assert len(result) == 1
    assert result[0]["title"] == "Meeting"
    assert result[0]["calendar"] == "Cal"

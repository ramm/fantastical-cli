"""Click CLI for Fantastical."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

import click

from fantastical import api
from fantastical.api import FantasticalError, ShortcutsNotConfigured
from fantastical.backend.shortcuts import SHORTCUT_INSTRUCTIONS, SHORTCUTS


def _output(data, as_json: bool, format_fn=None):
    """Output data as JSON or human-readable format."""
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    elif format_fn:
        format_fn(data)
    else:
        click.echo(json.dumps(data, indent=2, default=str))


def _handle_error(e: Exception):
    """Print error and exit."""
    if isinstance(e, ShortcutsNotConfigured):
        click.secho("Error: ", fg="red", nl=False)
        click.echo(str(e))
        click.echo()
        click.echo("Run `fantastical setup` to create the required helper shortcuts.")
        sys.exit(1)
    elif isinstance(e, FantasticalError):
        click.secho(f"Error: {e}", fg="red")
        sys.exit(1)
    else:
        raise e


def _format_calendars(calendars: list[dict]):
    if not calendars:
        click.echo("No calendars found.")
        return
    for cal in calendars:
        click.echo(f"  {cal['title']}")


def _format_events(events: list[dict]):
    if not events:
        click.echo("No events found.")
        return
    for ev in events:
        title = ev.get("title", "(no title)")
        start = ev.get("startDate", "")
        end = ev.get("endDate", "")
        cal = ev.get("calendar", "")
        all_day = ev.get("isAllDay", False)
        location = ev.get("location")

        if all_day:
            time_str = "all day"
        elif start and end:
            time_str = f"{start} - {end}"
        elif start:
            time_str = start
        else:
            time_str = ""

        line = f"  {title}"
        if time_str:
            line += f"  ({time_str})"
        if cal:
            line += f"  [{cal}]"
        if location:
            line += f"  @ {location}"
        click.echo(line)


def _format_tasks(tasks: list[dict]):
    if not tasks:
        click.echo("No tasks found.")
        return
    for task in tasks:
        title = task.get("title", "(no title)")
        due = task.get("dueDate")
        list_name = task.get("list")

        line = f"  {title}"
        if due:
            line += f"  (due: {due})"
        if list_name:
            line += f"  [{list_name}]"
        click.echo(line)


def _format_selected(items: list[dict]):
    if not items:
        click.echo("No items selected in Fantastical.")
        return
    for item in items:
        title = item.get("title", "(no title)")
        start = item.get("startDate", "")
        end = item.get("endDate", "")
        all_day = item.get("isAllDay", False)
        notes = item.get("notes")
        location = item.get("location")

        click.secho(f"  {title}", bold=True)
        if all_day:
            click.echo("    All day")
        elif start:
            time_line = f"    {start}"
            if end:
                time_line += f" - {end}"
            click.echo(time_line)
        if location:
            click.echo(f"    Location: {location}")
        if notes:
            click.echo(f"    Notes: {notes}")


@click.group()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def cli(ctx, as_json: bool):
    """Fantastical calendar CLI for macOS."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json


@cli.command()
@click.pass_context
def calendars(ctx):
    """List all Fantastical calendars."""
    try:
        data = api.list_calendars()
        _output(data, ctx.obj["json"], _format_calendars)
    except Exception as e:
        _handle_error(e)


@cli.command()
@click.pass_context
def selected(ctx):
    """Show currently selected items in Fantastical."""
    try:
        data = api.get_selected()
        _output(data, ctx.obj["json"], _format_selected)
    except Exception as e:
        _handle_error(e)


@cli.group(invoke_without_command=True)
@click.option("--from", "from_date", default=None, help="Start date (YYYY-MM-DD, 'today', 'tomorrow').")
@click.option("--to", "to_date", default=None, help="End date (YYYY-MM-DD, 'today', 'tomorrow').")
@click.option("--calendar", default=None, help="Filter by calendar name.")
@click.pass_context
def events(ctx, from_date, to_date, calendar):
    """List calendar events. Requires shortcuts setup."""
    ctx.ensure_object(dict)
    ctx.obj["from_date"] = from_date
    ctx.obj["to_date"] = to_date
    ctx.obj["calendar"] = calendar

    if ctx.invoked_subcommand is None:
        # No subcommand — list events with provided dates
        try:
            data = api.list_events(
                from_date=from_date or "today",
                to_date=to_date,
                calendar=calendar,
            )
            _output(data, ctx.obj["json"], _format_events)
        except Exception as e:
            _handle_error(e)


@events.command()
@click.option("--calendar", default=None, help="Filter by calendar name.")
@click.pass_context
def today(ctx, calendar):
    """Show today's events."""
    cal = calendar or ctx.obj.get("calendar")
    try:
        data = api.list_events(from_date="today", to_date="today", calendar=cal)
        _output(data, ctx.obj["json"], _format_events)
    except Exception as e:
        _handle_error(e)


@events.command()
@click.option("--days", default=7, help="Number of days to look ahead (default: 7).")
@click.option("--calendar", default=None, help="Filter by calendar name.")
@click.pass_context
def upcoming(ctx, days, calendar):
    """Show upcoming events for the next N days."""
    cal = calendar or ctx.obj.get("calendar")
    today_date = date.today()
    end_date = today_date + timedelta(days=days)
    try:
        data = api.list_events(
            from_date=today_date.isoformat(),
            to_date=end_date.isoformat(),
            calendar=cal,
        )
        _output(data, ctx.obj["json"], _format_events)
    except Exception as e:
        _handle_error(e)


@cli.command()
@click.argument("query")
@click.pass_context
def search(ctx, query):
    """Search events by title. Requires shortcuts setup."""
    try:
        data = api.search_events(query)
        _output(data, ctx.obj["json"], _format_events)
    except Exception as e:
        _handle_error(e)


@cli.command()
@click.argument("sentence")
@click.option("--calendar", default=None, help="Target calendar name.")
@click.option("--notes", default=None, help="Event notes.")
@click.pass_context
def add(ctx, sentence, calendar, notes):
    """Create event using natural language (e.g. 'Meeting tomorrow at 3pm')."""
    try:
        result = api.create_event(sentence, calendar, notes)
        if ctx.obj["json"]:
            click.echo(json.dumps(result, indent=2))
        else:
            click.secho("Event created: ", fg="green", nl=False)
            click.echo(sentence)
    except Exception as e:
        _handle_error(e)


@cli.command()
@click.option("--list", "list_name", default=None, help="Filter by task list name.")
@click.option("--overdue", is_flag=True, help="Show only overdue tasks.")
@click.pass_context
def tasks(ctx, list_name, overdue):
    """List tasks. Requires shortcuts setup."""
    try:
        data = api.list_tasks(list_name, overdue)
        _output(data, ctx.obj["json"], _format_tasks)
    except Exception as e:
        _handle_error(e)


@cli.command()
@click.argument("event_id")
def show(event_id):
    """Open an event in Fantastical by its URL/ID."""
    import subprocess
    url = event_id if event_id.startswith("x-fantastical") else f"x-fantastical3://show?id={event_id}"
    subprocess.run(["open", url], check=True)


@cli.command()
def setup():
    """Create or verify helper shortcuts for Fantastical integration."""
    click.secho("Fantastical CLI — Shortcut Setup", bold=True)
    click.echo()

    status = api.check_setup()
    all_ok = all(status.values())

    if all_ok:
        click.secho("All shortcuts are installed!", fg="green")
        click.echo()
        for key, name in SHORTCUTS.items():
            click.echo(f"  [ok] {name}")
        return

    missing = {k: v for k, v in status.items() if not v}
    installed = {k: v for k, v in status.items() if v}

    if installed:
        click.echo("Installed:")
        for key in installed:
            click.echo(f"  [ok] {SHORTCUTS[key]}")
        click.echo()

    click.echo(f"Missing {len(missing)} shortcut(s). Please create them in the Shortcuts app:")
    click.echo()

    for i, (key, _) in enumerate(missing.items(), 1):
        info = SHORTCUT_INSTRUCTIONS[key]
        click.secho(f"  {i}. {info['name']}", bold=True)
        for step in info["steps"]:
            click.echo(f"     - {step}")
        click.echo(f"     Input: {info['input']}")
        click.echo(f"     Output: {info['output']}")
        click.echo()

    click.echo("After creating the shortcuts, run `fantastical setup` again to verify.")


@cli.command()
def uninstall():
    """Remove helper shortcuts created by `fantastical setup`."""
    click.secho("Fantastical CLI — Uninstall Shortcuts", bold=True)
    click.echo()

    status = api.check_setup()
    installed = {k: v for k, v in status.items() if v}

    if not installed:
        click.echo("No Fantastical helper shortcuts are installed. Nothing to remove.")
        return

    click.echo(f"Found {len(installed)} helper shortcut(s) to remove:")
    for key in installed:
        click.echo(f"  - {SHORTCUTS[key]}")
    click.echo()

    # macOS Shortcuts has no programmatic delete — we open each shortcut
    # in Shortcuts.app for the user to delete manually.
    click.echo("Shortcuts.app does not support programmatic deletion.")
    click.echo("Each shortcut will be opened in Shortcuts.app — right-click and choose")
    click.secho('  "Delete Shortcut"', bold=True, nl=False)
    click.echo(" for each one.")
    click.echo()

    if not click.confirm("Open shortcuts in Shortcuts.app?"):
        return

    try:
        ids = api.get_installed_shortcut_ids()
    except Exception:
        # If JXA lookup fails, open Shortcuts.app generically
        import subprocess
        click.echo("Could not look up shortcut IDs. Opening Shortcuts.app...")
        subprocess.run(["open", "-a", "Shortcuts"], check=True)
        click.echo()
        click.echo("Please search for shortcuts prefixed with \"Fantastical - \" and delete them.")
        return

    import time
    for name, shortcut_id in ids.items():
        click.echo(f"  Opening: {name}")
        api.open_shortcut(shortcut_id)
        time.sleep(0.5)

    click.echo()
    click.echo("After deleting, run `fantastical setup` to verify they're removed.")


@cli.command()
def serve():
    """Start the MCP server (stdio transport)."""
    from fantastical.server import mcp
    mcp.run()

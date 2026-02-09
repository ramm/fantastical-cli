"""Click CLI for Fantastical."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, timedelta

import click

from fantastical import api
from fantastical.api import FantasticalError, ShortcutsNotConfigured, SHORTCUTS, LEGACY_SHORTCUTS


def _output(data, as_json: bool, format_fn):
    """Output data as JSON or human-readable format."""
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        format_fn(data)


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
        cal = ev.get("calendarName") or ev.get("calendar", "")
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



@cli.group()
@click.option("--calendar", default=None, help="Filter by calendar name.")
@click.pass_context
def events(ctx, calendar):
    """List calendar events. Requires shortcuts setup."""
    ctx.ensure_object(dict)
    ctx.obj["calendar"] = calendar


@events.command(name="list")
@click.option("--from", "from_date", default="today", help="Start date (YYYY-MM-DD, 'today', 'tomorrow').")
@click.option("--to", "to_date", default=None, help="End date (YYYY-MM-DD, 'today', 'tomorrow').")
@click.pass_context
def list_events(ctx, from_date, to_date):
    """List events in a date range."""
    try:
        data = api.list_events(
            from_date=from_date,
            to_date=to_date,
            calendar=ctx.obj.get("calendar"),
        )
        _output(data, ctx.obj["json"], _format_events)
    except Exception as e:
        _handle_error(e)


@events.command()
@click.pass_context
def today(ctx):
    """Show today's events."""
    try:
        data = api.list_events(from_date="today", to_date="today", calendar=ctx.obj.get("calendar"))
        _output(data, ctx.obj["json"], _format_events)
    except Exception as e:
        _handle_error(e)


@events.command()
@click.option("--days", default=7, help="Number of days to look ahead (default: 7).")
@click.pass_context
def upcoming(ctx, days):
    """Show upcoming events for the next N days."""
    today_date = date.today()
    end_date = today_date + timedelta(days=days)
    try:
        data = api.list_events(
            from_date=today_date.isoformat(),
            to_date=end_date.isoformat(),
            calendar=ctx.obj.get("calendar"),
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
    def _format_add(data):
        click.secho("Event sent to Fantastical: ", fg="green", nl=False)
        click.echo(sentence)

    try:
        result = api.create_event(sentence, calendar, notes)
        _output(result, ctx.obj["json"], _format_add)
    except Exception as e:
        _handle_error(e)



@cli.command()
@click.option("--force", is_flag=True, help="Regenerate shortcuts even if already installed.")
def setup(force):
    """Create or update helper shortcuts for Fantastical integration.

    Generates, signs, and imports Apple Shortcuts that bridge
    Fantastical's App Intents to the command line.

    Use --force to regenerate shortcuts after a CLI update (e.g., when
    new event fields are added to the shortcut output).
    """
    click.secho("Fantastical CLI — Shortcut Setup", bold=True)
    click.echo()

    # Check for legacy shortcuts that should be removed
    from fantastical.backend.shortcuts import check_legacy_shortcuts
    legacy = check_legacy_shortcuts()
    if legacy:
        click.secho("Legacy shortcuts detected:", fg="yellow")
        for name in legacy:
            click.echo(f"  - {name}")
        click.echo("  These are no longer used and can be removed from Shortcuts.app.")
        click.echo()

    # Check current status
    status = api.check_setup()
    all_ok = all(status.values())

    if all_ok and not force:
        click.secho("All shortcuts are already installed!", fg="green")
        click.echo()
        for key, name in SHORTCUTS.items():
            click.echo(f"  [ok] {name}")
        click.echo()
        click.echo("Use --force to regenerate shortcuts after a CLI update.")
        return

    if force:
        to_generate = list(SHORTCUTS.keys())
        click.echo(f"Will regenerate {len(to_generate)} shortcut(s):")
    else:
        to_generate = [k for k, ok in status.items() if not ok]
        installed = [k for k, ok in status.items() if ok]
        if installed:
            click.echo("Already installed:")
            for key in installed:
                click.echo(f"  [ok] {SHORTCUTS[key]}")
            click.echo()
        click.echo(f"Will create {len(to_generate)} shortcut(s):")

    for key in to_generate:
        click.echo(f"  - {SHORTCUTS[key]}")
    click.echo()

    # Explain what will happen
    click.secho("What to expect:", bold=True)
    click.echo("  1. Shortcut files will be generated and signed (requires internet)")
    click.echo("  2. Shortcuts.app will open an import dialog for each shortcut")
    if force:
        click.echo('     -> Click "Replace Shortcut" to update each one')
    else:
        click.echo('     -> Click "Add Shortcut" to accept each one')
    click.echo("  3. On first use, Fantastical will show a privacy prompt:")
    click.echo('     "Allow ... to share 1 text item with Fantastical?"')
    click.echo('     -> Click "Always Allow"')
    click.echo()

    if not click.confirm("Proceed?"):
        return

    click.echo()

    # Generate, sign, and import
    try:
        click.echo("Generating and signing shortcuts...")
        click.echo("  (contacting Apple servers for signing — requires internet)")
        click.echo()
        from fantastical.backend.shortcut_gen import generate_shortcut_file, import_shortcut

        for key in to_generate:
            name = SHORTCUTS[key]
            click.echo(f"  Signing {name}...", nl=False)
            path = generate_shortcut_file(key)
            click.secho(" done", fg="green")

            click.echo(f"  Importing {name}...")
            import_shortcut(path)
            click.echo()
            if force:
                click.secho(f'  -> Shortcuts.app: click "Replace Shortcut" to update.', bold=True)
            else:
                click.secho(f'  -> Shortcuts.app: click "Add Shortcut" to accept.', bold=True)

            # Wait for the user to confirm they accepted
            click.pause("  Press any key after accepting the shortcut...")
            click.echo()

    except RuntimeError as e:
        click.secho(f"Error: {e}", fg="red")
        click.echo()
        click.echo("Signing requires internet access. Check your connection and try again.")
        sys.exit(1)

    # Verify installation
    click.echo("Verifying installation...")
    status = api.check_setup()

    if not all(status.values()):
        click.echo()
        click.secho("Some shortcuts were not detected:", fg="yellow")
        for key, ok in status.items():
            icon = "[ok]" if ok else "[missing]"
            color = "green" if ok else "red"
            click.secho(f"  {icon} {SHORTCUTS[key]}", fg=color)
        click.echo()
        click.echo("Try running `fantastical setup` again.")
        return

    click.echo()
    for key, name in SHORTCUTS.items():
        click.echo(f"  [ok] {name}")
    click.echo()

    # Test the shortcut to trigger privacy grant
    click.secho("Testing shortcut with today's events...", bold=True)
    click.echo()
    if not force:
        click.echo("  macOS will show a privacy dialog:")
        click.echo('    "Allow ... to interact with Fantastical?"')
        click.echo()
        click.secho('  IMPORTANT: Click "Always Allow" (not "Allow Once")', bold=True)
        click.echo('  "Allow Once" will require approval on every single run.')
        click.echo()
        click.pause("  Press any key to run the test...")

    try:
        events = api.list_events(from_date="today", to_date="today")
        click.echo()
        if events:
            click.secho(f"  Got {len(events)} event(s) for today.", fg="green")
            for ev in events[:3]:
                click.echo(f"    - {ev.get('title', '(no title)')}")
            if len(events) > 3:
                click.echo(f"    ... and {len(events) - 3} more")
        else:
            click.secho("  No events for today (that's OK — shortcut is working).", fg="green")
    except Exception as e:
        click.echo()
        click.secho(f"  Test failed: {e}", fg="red")
        click.echo()
        click.echo("  If you dismissed the privacy dialog, run `fantastical setup` again.")
        click.echo('  Make sure to click "Always Allow" when prompted.')
        sys.exit(1)

    click.echo()
    click.secho("Setup complete!", fg="green", bold=True)
    click.echo()
    click.echo("You can now use:")
    click.echo("  fantastical events today")
    click.echo("  fantastical events --from 2026-01-01 --to 2026-01-31")
    click.echo('  fantastical search "meeting"')


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
        click.echo("Could not look up shortcut IDs. Opening Shortcuts.app...")
        subprocess.run(["open", "-a", "Shortcuts"], check=True)
        click.echo()
        click.echo("Please search for shortcuts prefixed with \"Fantastical - \" and delete them.")
        return

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

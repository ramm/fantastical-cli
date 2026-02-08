# fantastical-cli

A CLI and [MCP server](https://modelcontextprotocol.io/) for [Fantastical](https://flexibits.com/fantastical) on macOS.

Fantastical keeps its own calendar store that is invisible to Calendar.app and EventKit. This tool bridges the gap by talking to Fantastical directly — via JXA scripting, Apple Shortcuts, and URL schemes — so you can query and create events from the terminal or from any MCP-compatible AI assistant.

## Requirements

- macOS with Fantastical installed
- Python 3.10+
- [uv](https://github.com/astral-sh/uv)

## Install

```bash
git clone git@github.com:ramm/fantastical-cli.git
cd fantastical-cli
uv sync
```

## macOS permissions

On first run, macOS will prompt you to grant permissions. Click **Allow** when asked:

- **Automation**: your terminal app (Terminal, iTerm, etc.) needs permission to control Fantastical via Apple Events. Triggered by commands like `calendars` and `selected`.
- **Shortcuts**: running shortcuts from the terminal may prompt you to allow your terminal to run shortcuts. Triggered by commands like `events`, `tasks`, and `search`.

These prompts only appear once. If you accidentally deny a permission, you can re-enable it in **System Settings > Privacy & Security > Automation** (or **Shortcuts**).

When using the MCP server, the prompts will appear for the MCP host app (e.g. Claude Desktop) instead of your terminal.

## Quick start

```bash
# List your calendars (works immediately, no setup needed)
uv run fantastical calendars

# See what's selected in Fantastical
uv run fantastical selected

# Create an event using natural language
uv run fantastical add "Lunch with Alex tomorrow at noon"

# Set up helper shortcuts (one-time, needed for events/tasks/search)
uv run fantastical setup

# After setup — list today's events
uv run fantastical events today

# Upcoming events for the next 7 days
uv run fantastical events upcoming

# Search events by title
uv run fantastical search "standup"

# List tasks
uv run fantastical tasks
uv run fantastical tasks --overdue
```

All commands support `--json` for machine-readable output:

```bash
uv run fantastical --json events today
```

## Setup

Some features (events by date, search, tasks) use Fantastical's App Intents through Apple Shortcuts. Run the guided setup to create the required shortcuts:

```bash
uv run fantastical setup
```

This checks which helper shortcuts are installed and gives step-by-step instructions for any that are missing. You only need to do this once.

| Feature          | Needs setup? |
|------------------|:------------:|
| List calendars   | No           |
| Selected items   | No           |
| Create event     | No           |
| Events by date   | Yes          |
| Show schedule    | Yes          |
| Search events    | Yes          |
| List tasks       | Yes          |
| Overdue tasks    | Yes          |

## MCP server

To use fantastical-cli as an MCP server (e.g. with Claude Desktop), start it in stdio mode:

```bash
uv run fantastical serve
```

Or add it to your MCP client config:

```json
{
  "mcpServers": {
    "fantastical": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/fantastical-cli", "fantastical", "serve"]
    }
  }
}
```

The server exposes these tools: `list_calendars`, `list_events`, `create_event`, `show_schedule`, `list_tasks`, `search_events`, `get_selected`.

## CLI reference

| Command                  | Description                              |
|--------------------------|------------------------------------------|
| `calendars`              | List all Fantastical calendars           |
| `selected`               | Show currently selected items            |
| `add "..."`,             | Create event via natural language        |
| `events`                 | List events (default: today)             |
| `events today`           | Today's events                           |
| `events upcoming`        | Next 7 days (configurable with `--days`) |
| `search <query>`         | Search events by title                   |
| `tasks`                  | List tasks                               |
| `show <id>`              | Open an event in Fantastical             |
| `setup`                  | Create/verify helper shortcuts           |
| `uninstall`              | Remove helper shortcuts                  |
| `serve`                  | Start MCP server (stdio)                 |

## Uninstall shortcuts

macOS doesn't support programmatic shortcut deletion. The uninstall command opens each helper shortcut in Shortcuts.app for you to delete manually:

```bash
uv run fantastical uninstall
```

## License

MIT

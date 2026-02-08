# AGENTS.md — Fantastical CLI + MCP Server

## Project overview

A Python CLI tool (`fantastical`) providing composable access to Fantastical calendar data on macOS, with an MCP server as a thin wrapper. Installed via `uv sync`, run via `uv run fantastical <command>`.

**Critical constraint:** Fantastical does NOT sync to Calendar.app. Accounts added directly to Fantastical are invisible to Calendar.app and EventKit. All data access must go through Fantastical itself — JXA scripting or Apple Shortcuts with Fantastical's App Intents. Do NOT attempt EventKit, CalendarStore, or Calendar.app bridges.

## Architecture

```
src/fantastical/
├── backend/
│   ├── jxa.py            # osascript -l JavaScript subprocess runner
│   ├── fantastical.py     # JXA scripts (calendars, selected) + URL scheme (create)
│   └── shortcuts.py       # `shortcuts run` CLI wrapper (events, tasks, search)
├── api.py                 # Business logic — both CLI and MCP call this
├── cli.py                 # Click CLI — user-facing, formats output
└── server.py              # FastMCP server — thin JSON wrapper over api.py
```

### Layer rules

1. **`backend/`** touches macOS. Raw subprocess calls, JXA scripts, URL schemes. Returns parsed Python dicts. Never imported by server.py or cli.py directly — only through api.py.
2. **`api.py`** is the single source of truth. Combines backends, resolves dates ("today" -> ISO), handles "shortcuts not configured" gracefully. Returns clean dicts.
3. **`cli.py`** calls only `api.py`. Formats for humans (tables) or machines (`--json`). Never calls backends directly.
4. **`server.py`** calls only `api.py`. Returns `json.dumps()` strings for MCP tool responses.

When adding a new capability: add backend function -> add api.py function -> add CLI command + MCP tool.

## Two backend systems

### JXA (no setup required)
- Runs via `osascript -l JavaScript -e "..."` subprocess
- Can: list calendars, get selected items
- Cannot: query events by date, search, list tasks
- Gotcha: wrap every property access in try/catch — Fantastical's JXA bridge throws `-1700` type conversion errors on missing/null properties
- Gotcha: use `title` not `name` for calendars
- Gotcha: `startDate().toISOString()` can throw; the current code handles this

### Shortcuts (requires one-time `fantastical setup`)
- Runs via `shortcuts run "Name" -i "input"` subprocess
- Can: everything JXA can't — date-range queries, search, tasks, schedule
- 2 helper shortcuts must exist in user's Shortcuts app (see `SHORTCUTS` dict in `shortcuts.py`)
- Shortcuts output pipe-delimited text, parsed by `parse_pipe_delimited()` / `parse_task_output()`
- The `shortcuts` CLI uses Unicode smart quotes in errors — detection must handle `'` (U+2019) not just ASCII `'`

### Backend selection table

| Operation        | Backend        | Needs Shortcuts? |
|------------------|----------------|-----------------|
| List calendars   | JXA            | No              |
| Selected items   | JXA            | No              |
| Create event     | URL scheme     | No              |
| Events by date   | Shortcuts      | Yes             |
| Show schedule    | Shortcuts      | Yes             |
| Search events    | Shortcuts      | Yes             |
| List tasks       | Shortcuts      | Yes             |
| Overdue tasks    | Shortcuts      | Yes             |

## Key conventions

- All dates in the public API accept `"today"`, `"tomorrow"`, `"yesterday"`, or `YYYY-MM-DD` strings. Resolution happens in `api._resolve_date()`.
- The `--json` flag is a top-level Click option, stored in `ctx.obj["json"]`.
- When shortcuts are missing, raise `api.ShortcutsNotConfigured` — the CLI catches this and prints a helpful message pointing to `fantastical setup`.
- The MCP server (`server.py`) uses FastMCP. Each `@mcp.tool()` function calls the corresponding `api.*` function and returns `json.dumps()`.

## Common tasks

### Adding a new MCP tool / CLI command
1. If new macOS integration needed: add function to appropriate `backend/` module
2. Add function to `api.py` with docstring explaining shortcuts requirement
3. Add `@cli.command()` in `cli.py` with `--json` support
4. Add `@mcp.tool()` in `server.py`

### Adding a new shortcut
1. Add entry to `SHORTCUTS` dict in `shortcuts.py` (key + display name)
2. Add entry to `SHORTCUT_INSTRUCTIONS` dict with manual creation steps
3. Add wrapper function (e.g. `get_foo()`) that calls `run_shortcut()` + parser
4. Wire through `api.py` -> `cli.py` -> `server.py`

### Automatic shortcut generation (TODO)
The .shortcut plist format for third-party App Intent actions is not publicly documented. To enable `fantastical setup` to auto-create shortcuts:
1. Manually create a shortcut in Shortcuts.app that uses a Fantastical App Intent action
2. Export it, convert with `plutil -convert xml1`
3. Identify the WFWorkflowActionIdentifier format for Fantastical intents
4. Template the plist, sign with `shortcuts sign --mode anyone`, import with `shortcuts import`
See `docs/shortcuts-format.md` for current findings.

### Shortcut deletion (important limitation)
There is **no programmatic way to delete shortcuts** on macOS. The `shortcuts` CLI has no `delete` subcommand, and JXA's `delete()` method silently no-ops. The `fantastical uninstall` command works around this by looking up shortcut UUIDs via JXA and opening each one in Shortcuts.app via `shortcuts://open-shortcut?id=UUID` for the user to delete manually. See `docs/shortcuts-format.md` for full details of what was tested.

## Testing

No test suite yet. Manual verification:
```bash
uv run fantastical calendars              # JXA — should list calendars
uv run fantastical --json calendars       # JSON mode
uv run fantastical selected               # JXA — whatever's selected in Fantastical
uv run fantastical events today           # Shortcuts — will error if not set up
uv run fantastical setup                  # Shows which shortcuts are missing
uv run fantastical uninstall              # Opens shortcuts in Shortcuts.app for deletion
```

## Dependencies

- `click>=8.0` — CLI framework
- `mcp[cli]>=1.2.0` — MCP server (FastMCP)
- Python >= 3.10
- macOS with Fantastical installed
- `osascript` (system) for JXA
- `shortcuts` (system) for Apple Shortcuts
- `open` (system) for URL schemes

## Files you should read first

1. `docs/fantastical-app-intents.md` — Complete catalog of Fantastical's App Intents (16 actions, 3 queries, 5 entities)
2. `docs/jxa-findings.md` — What works and doesn't work with Fantastical's JXA dictionary
3. `docs/shortcuts-format.md` — What we know about .shortcut plist format
4. `api.py` — The core logic, small and readable

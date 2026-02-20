# AGENTS.md — Fantastical CLI + MCP Server

## Project overview

A Python CLI tool (`fantastical`) providing composable access to Fantastical calendar data on macOS, with an MCP server as a thin wrapper. Installed via `uv sync`, run via `uv run fantastical <command>`.

**Critical constraint:** Fantastical does NOT sync to Calendar.app. Accounts added directly to Fantastical are invisible to Calendar.app and EventKit. All data access must go through Fantastical itself — JXA scripting or Apple Shortcuts with Fantastical's App Intents. Do NOT attempt EventKit, CalendarStore, or Calendar.app bridges.

## Architecture

```
src/fantastical/
├── backend/
│   ├── jxa.py            # osascript -l JavaScript subprocess runner
│   ├── fantastical.py     # JXA scripts (calendars) + URL scheme (create)
│   ├── shortcuts.py       # `shortcuts run` CLI wrapper (schedule, overdue)
│   └── shortcut_gen.py    # Programmatic .shortcut file generation + signing
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
- Can: list calendars, provide calendar ID→name mapping for event enrichment
- Cannot: query events by date, search
- Gotcha: wrap every property access in try/catch — Fantastical's JXA bridge throws `-1700` type conversion errors on missing/null properties
- Gotcha: use `title` not `name` for calendars
- Gotcha: `startDate().toISOString()` can throw; the current code handles this

### Shortcuts (requires one-time `fantastical setup`)
- Runs via `shortcuts run "Name"` subprocess
- Can: everything JXA can't — date-range queries, schedule, search
- Helper shortcuts are **auto-generated** by `shortcut_gen.py`, signed, and imported during setup
- Shortcuts output delimited text (fields separated by `\x1f`, records by `\x1e`), parsed by `parse_shortcut_output()`
- The `shortcuts` CLI uses Unicode smart quotes in errors — detection must handle `'` (U+2019) not just ASCII `'`

### Backend selection table

| Operation        | Backend        | Needs Shortcuts? |
|------------------|----------------|-----------------|
| List calendars   | JXA            | No              |
| Create event     | URL scheme     | No              |
| Events by date   | Shortcuts      | Yes             |
| Show schedule    | Shortcuts      | Yes             |
| Search events    | Shortcuts      | Yes             |

## Shortcut generation (shortcut_gen.py)

Shortcuts are generated as binary plists, signed via `shortcuts sign --mode anyone`, and imported via `open`. The signing step contacts Apple servers and needs internet.

**Key format discovery:** App Intent parameters MUST use `WFTextTokenString` encoding (string + attachmentsByRange with U+FFFC placeholders), NOT `WFTextTokenAttachment`. Using the wrong encoding causes Fantastical to show interactive pickers instead of using the bound variable. See `docs/shortcuts-format.md` for the full technical deep-dive.

**Current shortcut:**

| Name | Intent / Query | Purpose | Status |
|------|---------------|---------|--------|
| `Fantastical - Find Events` | `CalendarItemQuery` (IntentCalendarItem) | Events across ALL calendars | **Working** — end-to-end verified |

The find events shortcut flow: Input "start|end|titleQuery" → Split Text → Get Item 1 → Detect Dates → Adjust Date +0d → Get Item 2 → Detect Dates → Adjust Date +0d → Get Item 3 (title query) → CalendarItemQuery(startDate between adj1..adj2 AND title contains item3) → Repeat Each → delimited text (title`\x1f`start`\x1f`end`\x1f`cal`\x1f`fantasticalURL) → Text wrap → Output. Fields use ASCII Unit Separator (0x1F); records end with Record Separator (0x1E). The caller passes the exact date range and optional title query as shortcut input; empty title = no-op (matches all events). Both `list_events` and `search_events` use this single shortcut — search passes the query string for server-side filtering.

**Key discoveries:**
- Dynamic dates in CalendarItemQuery `Values.Date`/`Values.AnotherDate` ARE possible using Adjust Date action outputs with `WFTextTokenAttachment` refs. The critical requirement is that `WFDuration` must use **string values** (`Magnitude: "14"`, `Unit: "days"`), NOT integers. Using integers silently breaks the Adjust Date output, causing the CalendarItemQuery to return 0 items without crashing. Discovered by extracting a working plist from a shortcut created in Shortcuts.app UI.
- **Output action taint tracking:** Data from third-party apps is "tainted" — Output action refuses to emit it directly (`WFActionErrorDomain Code=4`, "missing an appIdentifier"). **Fix:** wrap Repeat Results in a Text action before Output to "launder" the data through a built-in action.
- `EVENT_PROPS` = `["title", "startDate", "endDate", "calendarIdentifier", "fantasticalURL"]`. The `fantasticalURL` is a deep link back into Fantastical; it includes `calendarIdentifier` in the URL, so it's unique per calendar copy (not a cross-calendar dedup key).
- Date format from Shortcuts is currently parsed in **English-only** month format (e.g., "12 Feb 2026 at 12:00"). Non-English locale month names are not supported yet.
- Caller passes exact date range. No hard cap — MCP tool descriptions guide agents to start with 2-week chunks and widen if the calendar is sparse.
- **WFDuration gotcha:** The Adjust Date action's `WFDuration` must use **string** values for `Magnitude` and `Unit` (e.g., `"14"` and `"days"`). Using integers (e.g., `14` and `4`) silently produces broken output that causes CalendarItemQuery to return 0 items. This was the root cause of 7 failed dynamic date experiments before extracting a working plist from Shortcuts.app.
- **`WFWorkflowClientVersion` is required** for dynamic variable resolution in entity query filters. Without `"WFWorkflowClientVersion": "4046.0.2.2"` in the top-level plist, freshly-generated shortcuts with variable dates in CalendarItemQuery filters silently return 0 items. Shortcuts.app always includes this key; we must add it explicitly in `_build_shortcut_plist()`.

**Calendar name enrichment:** `api._get_events_for_range()` calls `_get_calendar_map()` (JXA) to build a `calendarIdentifier → calendarName` map, then enriches each event with `calendarName`. This is best-effort — if JXA times out, events still have the raw `calendarIdentifier`. The `--calendar` filter in `list_events()` matches on both `calendarName` and raw `calendarIdentifier`.

**Shortcut updates:** When `EVENT_PROPS` changes (new fields added), the shortcut must be regenerated. Use `fantastical setup --force` to regenerate and re-import even when shortcuts already exist.

### Privacy dialog on first run

The first run of a new shortcut triggers a **privacy dialog** ("Allow ... to access Fantastical?"). The user must accept it once; subsequent runs work without the dialog. If the dialog doesn't appear, try restarting Shortcuts.app (`killall Shortcuts && open -a Shortcuts`).

### Adding a new generated shortcut

1. Add a `build_*()` function in `shortcut_gen.py` following existing patterns
2. Add entry to `SHORTCUT_BUILDERS` dict
3. Add entry to `SHORTCUTS` dict in `shortcuts.py`
4. Add wrapper function in `shortcuts.py` that calls `run_shortcut()` + parser
5. Wire through `api.py` -> `cli.py` -> `server.py`

### Shortcut file locations

Shortcuts are stored in a system database, NOT as individual files on disk. There is no `shortcuts export` CLI command. The only way to get a `.shortcut` file is via the Shortcuts.app Share menu.

### Shortcut format gotchas

- App Intent parameters: use `_token_string_param()` (WFTextTokenString), NOT `_var_attachment()` (WFTextTokenAttachment)
- Enum parameters (e.g., `day: "specificDate"`): set as plain strings, no wrapping
- Boolean parameters (e.g., `skipTodayPastEvents: false`): set as plain booleans
- Signing timeout: 120s (Apple servers can be slow, occasionally 503/504)
- No programmatic shortcut deletion — `fantastical uninstall` opens each in Shortcuts.app for manual deletion

## Key conventions

- **NEVER create, modify, or delete calendar events without explicit user consent.** The `add` command and `create_event` API write to the user's real calendar. Always confirm before calling them — especially from MCP tools or automated workflows.
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

### Shortcut deletion (important limitation)
There is **no programmatic way to delete shortcuts** on macOS. The `shortcuts` CLI has no `delete` subcommand, and JXA's `delete()` method silently no-ops. The `fantastical uninstall` command works around this by looking up shortcut UUIDs via JXA and opening each one in Shortcuts.app via `shortcuts://open-shortcut?id=UUID` for the user to delete manually.

## Debugging shortcuts

See `docs/shortcuts-format.md` § "Debugging with macOS unified logs" for full details. Quick reference:

```bash
# View recent BackgroundShortcutRunner logs (after running a shortcut)
/usr/bin/log show --last 5m --predicate 'process == "BackgroundShortcutRunner"' --style compact

# Stream logs in real-time (start before running shortcut)
/usr/bin/log stream --predicate 'process == "BackgroundShortcutRunner" OR process CONTAINS "hortcut"' --style compact
```

**Must use `/usr/bin/log`** — zsh has a builtin `log` function that shadows it.

Key things to look for:
- `finished with output of N items` — action completed successfully
- `Terminating app due to uncaught exception` — crash (check which property/action)
- `smart prompt` — privacy dialog was shown
- `Disabling privacy prompts` — privacy already granted

## Testing

```bash
uv run pytest              # all tests
uv run pytest -v           # verbose
uv run pytest tests/test_parse.py  # single file
uv run pytest -k "test_resolve"    # by name pattern
```

All tests are pure-Python or use `unittest.mock` — no macOS/Fantastical dependencies needed.

### Manual verification
```bash
uv run fantastical calendars                      # JXA — should list calendars
uv run fantastical --json calendars               # JSON mode
uv run fantastical events today                   # Shortcuts — will error if not set up
uv run fantastical events --calendar "Cal" today  # Filter by calendar name
uv run fantastical --json events today            # JSON with calendarName enrichment
uv run fantastical setup                          # Generates, signs, and imports shortcuts
uv run fantastical setup --force                  # Regenerate shortcuts (after CLI update)
uv run fantastical uninstall                      # Opens shortcuts in Shortcuts.app for deletion
```

## Running Python

**Always use `uv run python` instead of bare `python`.** This project uses `uv` for dependency management. Bare `python` is not available in the project environment — use `uv run python script.py` or `uv run fantastical <command>`.

## Dependencies

- `click>=8.0` — CLI framework
- `mcp[cli]>=1.2.0` — MCP server (FastMCP)
- Python >= 3.10
- macOS with Fantastical installed
- `osascript` (system) for JXA
- `shortcuts` (system) for Apple Shortcuts CLI
- `open` (system) for URL schemes and shortcut import
- Internet access for `shortcuts sign` (one-time during setup)

## Live MCP testing prompt

When the Fantastical MCP tools are available in your session, use the following prompt to exercise the server thoroughly. Copy-paste it or adapt it to the current date.

> **Prompt:**
>
> Do a deep analysis of my calendar — 3 months back and 3 months forward from today. I want to understand:
>
> 1. **1-on-1 patterns**: who do I meet with most often? What's the cadence — weekly, biweekly, ad-hoc? Has it changed over the 6-month window (e.g., new 1-1s appearing, old ones dropped)?
> 2. **Trend changes**: compare the past 3 months to the upcoming 3 months. Am I trending toward more or fewer meetings? Any new recurring events showing up? Any that disappeared?
> 3. **Schedule optimization**: which days are overloaded? Are there back-to-back stretches with no breaks? Do I have focus time, or is it all fragmented? Give me concrete suggestions.
>
> Start by listing my calendars, then fetch events in 2-week chunks (in parallel when possible). After building up the data, search for a few specific recurring meeting titles to cross-check. For any interesting events, pull full details. When done with the analysis, clear the cache and re-fetch the current week to verify the cache lifecycle works.
>
> Do NOT create any events. Read-only analysis only.

**What this exercises and why:**

| Behavior | Why it matters |
|----------|---------------|
| `list_calendars` first | Lightweight JXA call, no shortcuts, confirms connectivity |
| `list_events` in 2-week chunks | ~13 calls across 6 months, each ~50–150 events; tests chunking guidance from tool description |
| Parallel `list_events` calls | Concurrent cache writes via `_cache_lock`; tests thread safety |
| Cache accumulation across calls | ~13 chunks = 6 months of events merged into one flat cache with dedup |
| `search_events` with `from_date`/`to_date` | Cross-checking specific titles across the full 6-month window — well beyond ±30d default |
| Past vs. future comparison | Forces agent to reason over two large slices of cached data, not just dump raw output |
| `get_event_details` on specific IDs | Cache reads; verifies full fields (calendar, URL, calendarName) are stored |
| `clear_cache` then re-fetch | Full cache lifecycle: populate → read → clear → verify gone → repopulate |
| Real analytical questions | Forces the agent to actually interpret results, not just dump them — catches format/parsing issues that synthetic tests miss |

**Expected volume:** ~500–1500 events for 6 months of a typical busy calendar. ~13 parallel 2-week chunks, each returning compact tab-separated output (~2–5KB instead of the 80–120KB JSON it would have been before).

**Failure modes to watch for:**
- Shortcuts timeout on ranges >1 month (should not happen with 2-week chunks)
- Duplicate cache entries for same event fetched in overlapping ranges
- `get_event_details` returning "not found" for an ID that was just listed
- `search_events` without `from_date`/`to_date` silently falling back to ±30 days when the analysis needs the full 6-month window
- Agent failing to parallelize the 2-week chunk calls (sequential = ~2 min vs parallel = ~15–20s)

## Files you should read first

1. `TODO.md` — Prioritized task list with current blockers and implementation plans
2. `docs/shortcuts-format.md` — Complete .shortcut plist format documentation, variable encoding, AEA extraction, CalendarItemQuery format, Fantastical-specific findings
3. `docs/fantastical-app-intents.md` — Complete catalog of Fantastical's App Intents (16 actions, 3 queries, 5 entities)
4. `docs/jxa-findings.md` — What works and doesn't work with Fantastical's JXA dictionary
5. `docs/why-not-eventkit.md` — Why EventKit/Calendar.app can't work
6. `docs/cherri.md` — Cherri Shortcuts compiler, useful as a plist format reference
7. `api.py` — The core logic, small and readable

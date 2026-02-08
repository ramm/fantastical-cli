# Apple Shortcuts Integration — Format & Findings

## Overview

Apple Shortcuts is the only way to access Fantastical's rich App Intent actions (date queries, search, tasks) from the command line. The `shortcuts` CLI tool can run user-created shortcuts and pipe output to stdout.

## The `shortcuts` CLI

```bash
# List all installed shortcuts
shortcuts list

# Run a shortcut with text input, capture stdout
shortcuts run "Shortcut Name" -i "input text"

# Sign a .shortcut file for sharing
shortcuts sign --mode anyone --input file.shortcut --output signed.shortcut

# Import a signed shortcut
shortcuts import signed.shortcut
```

### Error handling gotcha

The `shortcuts` CLI uses Unicode smart quotes in error messages:

```
Error: The operation couldn\u2019t be completed. Couldn\u2019t find shortcut
```

That's U+2019 RIGHT SINGLE QUOTATION MARK, not ASCII `'`. When detecting "shortcut not found" errors, match on `"find shortcut"` to avoid the apostrophe issue entirely.

### No programmatic deletion

The `shortcuts` CLI has **no `delete` subcommand** (only `run`, `list`, `view`, `sign`). We also tested:

- **JXA `app.delete()`** — `Application("Shortcuts")` exposes `shortcuts` elements and a `delete()` method, but calling it silently no-ops. Both `s.delete()` on an element and `app.delete(app.shortcuts.whose({name: "..."}))` return without error but do nothing.
- **AppleScript** — `tell application "Shortcuts" to delete (every shortcut whose name is "...")` also silently no-ops.
- **URL scheme** — `shortcuts://delete-shortcut?name=...` is not a real endpoint; it opens Shortcuts.app but does nothing.

The only way to delete shortcuts is **manually in Shortcuts.app** (right-click > Delete Shortcut). For `fantastical uninstall`, we look up shortcut UUIDs via JXA (`app.shortcuts[i].id()`) and open each one in Shortcuts.app via `shortcuts://open-shortcut?id=UUID` so the user can delete them.

**JXA can read shortcut metadata** even though it can't delete:
```javascript
var app = Application("Shortcuts");
app.shortcuts().map(s => s.properties());
// => [{name, id, actionCount, subtitle, folder, color, icon, pcls, acceptsInput}, ...]
```

## Current approach: Manual shortcut creation

The CLI requires 2 helper shortcuts that the user creates manually in Shortcuts.app. Each shortcut:
1. Takes text input from the CLI
2. Calls one Fantastical App Intent action
3. Formats the result as pipe-delimited text
4. Outputs to stdout

The `list_events` and `search_events` features reuse the "Show Schedule" shortcut internally — `list_events` calls it once per day in the requested range (max 31 days), and `search_events` calls it for ±14 days around today, then filters by title in Python. The `list_tasks` feature uses the "Overdue Tasks" shortcut with optional list-name filtering in Python.

### Required shortcuts

| Name | Fantastical Action | Input | Output Format |
|------|-------------------|-------|---------------|
| `Fantastical - Show Schedule` | Show Schedule (FKRShowScheduleIntent) | `DATE` | `TITLE \| START \| END \| CALENDAR \| ALL_DAY \| LOCATION \| NOTES` |
| `Fantastical - Overdue Tasks` | Overdue Tasks (FKROverdueRemindersIntent) | (none) | `TITLE \| DUE_DATE \| LIST \| NOTES` |

## TODO: Automatic shortcut generation

### What we know about .shortcut file format

- `.shortcut` files are binary plists (bplist)
- Convert to readable format: `plutil -convert xml1 -o output.xml input.shortcut`
- Convert to JSON: `plutil -convert json -o output.json input.shortcut`
- Must be signed before import: `shortcuts sign --mode anyone --input unsigned.shortcut --output signed.shortcut`

### Planned reverse-engineering process

1. **Create one test shortcut manually** in Shortcuts.app:
   - Add a "Show Schedule" Fantastical action
   - Set date to "Shortcut Input"
   - Add a "Repeat with Each" action
   - Add "Text" action formatting properties with `|` separator
   - End repeat, pass to output

2. **Export and inspect:**
   ```bash
   # Find the shortcut in the Shortcuts database
   # Shortcuts stores data in ~/Library/Shortcuts/
   # or export via Shortcuts.app share sheet

   plutil -convert json -o schedule.json "Fantastical - Show Schedule.shortcut"
   ```

3. **Key things to find in the plist:**
   - `WFWorkflowActionIdentifier` value for Fantastical's App Intent actions
   - How the intent ID (e.g., `FKRShowScheduleIntent`) maps to the Shortcuts action format
   - Parameter binding format (how Shortcut Input gets passed to intent params)
   - Entity reference format (how IntentCalendarItem properties are accessed in Text actions)

4. **Template and generate** the other 4 shortcuts from the discovered format.

### Known plist structure (from Apple's built-in actions)

Standard Shortcuts actions use this format:
```xml
<dict>
    <key>WFWorkflowActionIdentifier</key>
    <string>is.workflow.actions.ACTIONNAME</string>
    <key>WFWorkflowActionParameters</key>
    <dict>
        <!-- action-specific params -->
    </dict>
</dict>
```

For third-party App Intent actions, the identifier format is likely different — possibly using the bundle ID and intent class name. This is the key unknown.

### Alternative: Siri Shortcuts URL scheme

Another approach to explore: Shortcuts supports `shortcuts://` URL schemes that might allow programmatic shortcut creation. Not investigated yet.

### Fallback

If auto-generation proves impossible, the manual setup (2 shortcuts, ~30 seconds each) is acceptable. The `fantastical setup` command already walks users through it step by step.

## Output parsing

Shortcuts pipe output to stdout as plain text. Our shortcuts format output as pipe-delimited lines:

```
Meeting with Bob | 2026-02-08T10:00:00 | 2026-02-08T11:00:00 | Work | false | Conference Room | Discuss Q1 plans
Lunch | 2026-02-08T12:00:00 | 2026-02-08T13:00:00 | Personal | false | (null) | (null)
```

Parser handles:
- Varying number of fields (graceful degradation)
- Null values represented as `nil`, `null`, `(null)`, or empty string
- Boolean fields (`isAllDay`) normalized from `true`/`yes`/`1`
- Leading/trailing whitespace stripped from each field

See `shortcuts.py:parse_pipe_delimited()` and `parse_task_output()` for implementation.

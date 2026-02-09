# Apple Shortcuts Integration — Format & Findings

## Overview

Apple Shortcuts is the only way to access Fantastical's rich App Intent actions (date queries, schedule, tasks) from the command line. The `shortcuts` CLI tool can run user-created shortcuts and pipe output to stdout.

We generate `.shortcut` files programmatically (binary plist), sign them via `shortcuts sign`, and import them with `open`. This is fully automatic via `fantastical setup`.

## The `shortcuts` CLI

```bash
# List all installed shortcuts
shortcuts list

# Run a shortcut with text input, capture stdout
echo "2026-02-08" | shortcuts run "Fantastical - Show Schedule"

# Sign a .shortcut file for sharing (contacts Apple servers)
shortcuts sign --mode anyone --input unsigned.shortcut --output signed.shortcut

# Import a signed shortcut (opens Shortcuts.app add dialog)
open signed.shortcut
```

### Error handling gotcha

The `shortcuts` CLI uses Unicode smart quotes in error messages:

```
Error: The operation couldn\u2019t be completed. Couldn\u2019t find shortcut
```

That's U+2019 RIGHT SINGLE QUOTATION MARK, not ASCII `'`. When detecting "shortcut not found" errors, match on `"find shortcut"` to avoid the apostrophe issue entirely.

### Signing requirements

- Unsigned `.shortcut` files **will not import** on modern macOS (since iOS 15+/macOS 12+)
- `shortcuts sign --mode anyone` contacts Apple servers — needs internet, can take 5-30 seconds
- Timeout should be generous (120s) — Apple servers occasionally return 503/504
- The signed output is an AEA (Apple Encrypted Archive) container, not a plain plist

### No programmatic deletion

The `shortcuts` CLI has **no `delete` subcommand** (only `run`, `list`, `view`, `sign`). We also tested:

- **JXA `app.delete()`** — `Application("Shortcuts")` exposes `shortcuts` elements and a `delete()` method, but calling it silently no-ops.
- **AppleScript** — `tell application "Shortcuts" to delete (every shortcut whose name is "...")` also silently no-ops.
- **URL scheme** — `shortcuts://delete-shortcut?name=...` is not a real endpoint.

The only way to delete shortcuts is **manually in Shortcuts.app**. For `fantastical uninstall`, we look up shortcut UUIDs via JXA and open each in Shortcuts.app via `shortcuts://open-shortcut?id=UUID`.

**JXA can read shortcut metadata:**
```javascript
var app = Application("Shortcuts");
app.shortcuts().map(s => s.properties());
// => [{name, id, actionCount, subtitle, folder, color, icon, pcls, acceptsInput}, ...]
```

## .shortcut file format (binary plist)

### Top-level structure

A `.shortcut` file is a binary plist (`bplist00`) with these top-level keys:

```json
{
  "WFWorkflowMinimumClientVersionString": "900",
  "WFWorkflowMinimumClientVersion": 900,
  "WFWorkflowClientVersion": "4046.0.2.2",
  "WFWorkflowIcon": {
    "WFWorkflowIconStartColor": 4282601983,
    "WFWorkflowIconGlyphNumber": 59511
  },
  "WFWorkflowActions": [ ... ],
  "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
  "WFWorkflowOutputContentItemClasses": ["WFStringContentItem"],
  "WFWorkflowTypes": [],
  "WFWorkflowHasOutputFallback": false,
  "WFWorkflowImportQuestions": [],
  "WFQuickActionSurfaces": [],
  "WFWorkflowHasShortcutInputVariables": true
}
```

### Actions

Each action in `WFWorkflowActions` has:

```json
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
  "WFWorkflowActionParameters": { ... }
}
```

**Built-in actions** use identifiers like `is.workflow.actions.*`:
- `is.workflow.actions.detect.date` — Detect Dates
- `is.workflow.actions.repeat.each` — Repeat with Each
- `is.workflow.actions.gettext` — Text
- `is.workflow.actions.output` — Stop and Output

**Third-party App Intent actions** use `<BundleIdentifier>.<IntentIdentifier>`:
- `com.flexibits.fantastical2.mac.FKRShowScheduleIntent`
- `com.flexibits.fantastical2.mac.FKRShowCalendarIntent`
- `com.flexibits.fantastical2.mac.FKROverdueRemindersIntent`

### Variable references — Two encodings

This is the most important discovery. There are TWO ways to reference variables, and using the wrong one for App Intent parameters is the #1 pitfall.

#### 1. WFTextTokenAttachment (single variable reference)

Used for action inputs like Repeat Each's `WFInput`. References a single variable directly.

```json
{
  "WFSerializationType": "WFTextTokenAttachment",
  "Value": {
    "Type": "ActionOutput",
    "OutputUUID": "UUID-of-source-action"
  }
}
```

Or for Shortcut Input:

```json
{
  "WFSerializationType": "WFTextTokenAttachment",
  "Value": {
    "Type": "ExtensionInput"
  }
}
```

#### 2. WFTextTokenString (text with inline variable attachments)

Used for Text action content AND **App Intent parameters**. Wraps variables in a text string using U+FFFC (Object Replacement Character) as placeholders.

```json
{
  "WFSerializationType": "WFTextTokenString",
  "Value": {
    "string": "\ufffc",
    "attachmentsByRange": {
      "{0, 1}": {
        "OutputUUID": "UUID-of-source-action",
        "Type": "ActionOutput",
        "OutputName": "Dates"
      }
    }
  }
}
```

The `attachmentsByRange` keys are `{position, length}` where position is the UTF-16 offset of the `\ufffc` character. For a single variable at the start, it's always `{0, 1}`.

For multiple inline variables (pipe-delimited text):
```json
{
  "string": "\ufffc | \ufffc | \ufffc",
  "attachmentsByRange": {
    "{0, 1}": { "Type": "Variable", "VariableName": "Repeat Item", "Aggrandizements": [...] },
    "{4, 1}": { "Type": "Variable", "VariableName": "Repeat Item", "Aggrandizements": [...] },
    "{8, 1}": { "Type": "Variable", "VariableName": "Repeat Item", "Aggrandizements": [...] }
  }
}
```

### CRITICAL: App Intent parameters MUST use WFTextTokenString

This was the key blocker that took many iterations to solve. When passing a variable to a third-party App Intent parameter (e.g., passing a date to Fantastical's `date` parameter):

**WRONG — does NOT bind (shows interactive picker):**
```json
"date": {
  "WFSerializationType": "WFTextTokenAttachment",
  "Value": {
    "Type": "ActionOutput",
    "OutputUUID": "...",
    "Aggrandizements": [
      { "CoercionItemClass": "WFDateContentItem", "Type": "WFCoercionVariableAggrandizement" }
    ]
  }
}
```

**CORRECT — binds successfully:**
```json
"date": {
  "WFSerializationType": "WFTextTokenString",
  "Value": {
    "string": "\ufffc",
    "attachmentsByRange": {
      "{0, 1}": {
        "OutputUUID": "...",
        "Type": "ActionOutput",
        "OutputName": "Dates"
      }
    }
  }
}
```

Key differences:
1. Must use `WFTextTokenString`, not `WFTextTokenAttachment`
2. Must use `string` + `attachmentsByRange` wrapper
3. **No** coercion aggrandizements needed
4. Must include `OutputName` (e.g., `"Dates"` for Detect Dates action output)

Simple scalar parameters (booleans, strings, enums) are set directly:
```json
"skipTodayPastEvents": false,
"day": "specificDate",
"showUpcomingEventsOnly": false
```

### App Intent action structure

```json
{
  "WFWorkflowActionIdentifier": "com.flexibits.fantastical2.mac.FKRShowScheduleIntent",
  "WFWorkflowActionParameters": {
    "AppIntentDescriptor": {
      "TeamIdentifier": "85C27NK92C",
      "BundleIdentifier": "com.flexibits.fantastical2.mac",
      "Name": "Fantastical",
      "AppIntentIdentifier": "FKRShowScheduleIntent"
    },
    "ShowWhenRun": false,
    "UUID": "unique-uuid-for-this-action",
    "day": "specificDate",
    "date": { ... WFTextTokenString ... }
  }
}
```

The `AppIntentDescriptor` is required and contains:
- `TeamIdentifier` — from `codesign -d --verbose=2 /Applications/Fantastical.app` (85C27NK92C)
- `BundleIdentifier` — `com.flexibits.fantastical2.mac`
- `Name` — display name ("Fantastical")
- `AppIntentIdentifier` — the Swift intent class name (e.g., `FKRShowScheduleIntent`)

### Property access on entities (Aggrandizements)

To access a property of an entity variable (e.g., `Repeat Item.title`):

```json
{
  "Type": "Variable",
  "VariableName": "Repeat Item",
  "Aggrandizements": [
    {
      "Type": "WFPropertyVariableAggrandizement",
      "PropertyName": "title",
      "PropertyUserInfo": "title"
    }
  ]
}
```

Available properties on `IntentCalendarItem`: `title`, `startDate`, `endDate`, `dueDate`, `calendarIdentifier`, `isAllDay`, `location`, `notes`, `fantasticalURL`, `hexColorString`, `url`, `attendees`, `availability`, `conferences`.

### Repeat with Each

Uses a shared `GroupingIdentifier` UUID and `WFControlFlowMode`:
- Mode 0 = start of loop
- Mode 2 = end of loop

```json
// Start
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
  "WFWorkflowActionParameters": {
    "WFControlFlowMode": 0,
    "GroupingIdentifier": "shared-uuid",
    "WFInput": { ... WFTextTokenAttachment referencing source ... }
  }
}

// End
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
  "WFWorkflowActionParameters": {
    "WFControlFlowMode": 2,
    "GroupingIdentifier": "shared-uuid",
    "UUID": "output-uuid"
  }
}
```

The end action's `UUID` is what you reference as `OutputUUID` when using the repeat results downstream, with `OutputName: "Repeat Results"`.

### Stop and Output action

Explicitly outputs data from the shortcut (needed for `shortcuts run` to capture stdout):

```json
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.output",
  "WFWorkflowActionParameters": {
    "WFOutput": {
      "WFSerializationType": "WFTextTokenString",
      "Value": {
        "string": "\ufffc",
        "attachmentsByRange": {
          "{0, 1}": {
            "OutputUUID": "repeat-end-uuid",
            "Type": "ActionOutput",
            "OutputName": "Repeat Results"
          }
        }
      }
    }
  }
}
```

## Extracting plists from signed shortcuts

Signed `.shortcut` files are AEA (Apple Encrypted Archive) containers. To extract the actual plist:

```python
import plistlib, struct

data = open("signed.shortcut", "rb").read()

# AEA1 header: 4 bytes magic + 4 bytes padding + 4 bytes LE uint32 (header plist size)
header_size = struct.unpack("<I", data[8:12])[0]

# Header plist at offset 12 contains SigningCertificateChain
header = plistlib.loads(data[12:12 + header_size])
cert_der = header["SigningCertificateChain"][0]

# Write cert, extract public key
with open("/tmp/cert.der", "wb") as f:
    f.write(cert_der)
# openssl x509 -inform DER -in /tmp/cert.der -pubkey -noout > /tmp/pubkey.pem

# Decrypt AEA with extracted public key
# aea decrypt -i signed.shortcut -o decrypted.bin -sign-pub /tmp/pubkey.pem

# The decrypted output has an AA01 header; the actual bplist starts at offset 98
decrypted = open("decrypted.bin", "rb").read()
bplist_offset = decrypted.find(b"bplist00")
plist = plistlib.loads(decrypted[bplist_offset:])
```

This was essential for reverse-engineering the correct parameter format — we generated a shortcut, the user manually fixed the variable binding in Shortcuts.app, exported it, and we extracted the working plist to compare against our broken one.

## Fantastical-specific findings

### Intent selection: FKRShowScheduleIntent vs FKRShowCalendarIntent

Both return `IntentCalendarItem` arrays for a date, but behave differently:

| Intent | Params | Interactive prompts |
|--------|--------|-------------------|
| `FKRShowScheduleIntent` | `day` (enum: today/tomorrow/specificDate), `date`, `showUpcomingEventsOnly`, `hideAllDayItems` | Prompts for `day` enum if not set |
| `FKRShowCalendarIntent` | `calendar` (CalendarEntity), `date`, `skipTodayPastEvents` | Prompts for calendar selection if not set |

**We use `FKRShowScheduleIntent`** with `day: "specificDate"` — this avoids all interactive prompts. Setting the enum explicitly prevents Fantastical from asking "Which one? today / tomorrow / specific date".

### Enum parameter values

`IntentScheduleDay` enum (for `FKRShowScheduleIntent.day`):
- `"today"` — today's schedule
- `"tomorrow"` — tomorrow's schedule
- `"specificDate"` — use the `date` parameter

These are set as plain strings in `WFWorkflowActionParameters`, not wrapped in any serialization type.

### Fantastical identifiers

```
BundleIdentifier: com.flexibits.fantastical2.mac
TeamIdentifier:   85C27NK92C
```

Found via `codesign -d --verbose=2 /Applications/Fantastical.app`.

## Entity Query actions ("Find" actions)

Entity queries like `CalendarItemQuery` use a different plist format from App Intent actions. Discovered by having the user create a "Find Fantastical Calendar Item" shortcut manually in Shortcuts.app, then extracting the plist via AEA decryption (see "Extracting plists from signed shortcuts" above).

### CalendarItemQuery plist structure

**Action identifier:** `com.flexibits.fantastical2.mac.IntentCalendarItem`

Note: the identifier uses the **entity name** (`IntentCalendarItem`), not the query name (`CalendarItemQuery`).

```json
{
  "WFWorkflowActionIdentifier": "com.flexibits.fantastical2.mac.IntentCalendarItem",
  "WFWorkflowActionParameters": {
    "AppIntentDescriptor": {
      "TeamIdentifier": "85C27NK92C",
      "BundleIdentifier": "com.flexibits.fantastical2.mac",
      "Name": "Fantastical",
      "AppIntentIdentifier": "IntentCalendarItem",
      "ActionRequiresAppInstallation": true
    },
    "WFContentItemFilter": {
      "WFSerializationType": "WFContentPredicateTableTemplate",
      "Value": {
        "WFActionParameterFilterPrefix": 1,
        "WFContentPredicateBoundedDate": false,
        "WFActionParameterFilterTemplates": [
          {
            "Operator": 1003,
            "Property": "startDate",
            "Removable": true,
            "Values": {
              "Unit": 4,
              "Date": "2026-02-01 22:57:35.316589",
              "AnotherDate": "2026-02-15 22:57:19.881821"
            }
          }
        ]
      }
    },
    "UUID": "unique-uuid"
  }
}
```

### Filter format details

- **`WFContentItemFilter`** wraps the filter in `WFContentPredicateTableTemplate` serialization type
- **`WFActionParameterFilterTemplates`** is an array of filter conditions
- Each condition has:
  - `Property` — the entity property to filter on (e.g., `"startDate"`, `"title"`, `"type"`)
  - `Operator` — the comparison operator (see below)
  - `Values` — operator-specific values (dates, strings, etc.)
  - `Removable` — whether the user can remove the filter in the UI
- **`WFActionParameterFilterPrefix`** — `1` for AND, `0` for OR (combining multiple filters)
- **`WFContentPredicateBoundedDate`** — `false` for absolute dates, `true` for relative dates

### Filter operator values

From the CalendarItemQuery metadata and shortcut extraction:

| Operator | Meaning | Context |
|----------|---------|---------|
| `1003` | is between | Date range filter (uses `Date` + `AnotherDate` in `Values`) |
| `9` | is between | Alternate comparator value from metadata (may differ by context) |
| `6` | contains | String filter (used for title search) |
| `0` | equals | Exact match |

### Date values in filters

For the "is between" operator (`1003`), `Values` contains:
- `Unit: 4` — meaning unclear, possibly "day" granularity
- `Date` — start of range (WFTextTokenAttachment or static datetime)
- `AnotherDate` — end of range (same)

**Dynamic dates ARE possible** using Adjust Date action outputs referenced via `WFTextTokenAttachment`:
```json
"Date": {
  "WFSerializationType": "WFTextTokenAttachment",
  "Value": {
    "Type": "ActionOutput",
    "OutputUUID": "adjust-date-subtract-uuid",
    "OutputName": "Date"
  }
}
```

**Critical requirement:** The Adjust Date actions feeding these filter values must use **string** values for `WFDuration`:
```json
"WFDuration": {
  "WFSerializationType": "WFQuantityFieldValue",
  "Value": {
    "Magnitude": "14",
    "Unit": "days"
  }
}
```
Using integers (`Magnitude: 14`, `Unit: 4`) silently breaks the Adjust Date output, causing CalendarItemQuery to return 0 items without crashing.

Static `datetime` plist objects also work (the original approach), but dynamic dates are preferred since the shortcut never goes stale.

**`WFWorkflowClientVersion` is required for dynamic variables in entity query filters.** Without `"WFWorkflowClientVersion": "4046.0.2.2"` in the top-level plist, freshly-generated shortcuts with variable references in CalendarItemQuery `Values.Date`/`Values.AnotherDate` silently return 0 items — even when the encoding is structurally identical to a working shortcut. The Shortcuts engine apparently uses this key to decide whether to resolve variable references in filter predicates. Shortcuts exported from Shortcuts.app always include this key; programmatically-generated plists must add it explicitly.

**History:** Initial attempts crashed because they used Detect Dates output directly (not Adjust Date) in the CalendarItemQuery filter. Next attempts used Adjust Date but with integer WFDuration values, causing silent failures. Further iterations had correct encoding but returned 0 items due to missing `WFWorkflowClientVersion`. The correct encoding was discovered by extracting a working plist from a shortcut created in Shortcuts.app UI, then diffing against the programmatic output.

### Split Text action

**Action:** `is.workflow.actions.text.split`

The separator must be specified as `WFTextSeparator: "Custom"` with the actual character in `WFTextCustomSeparator`. Setting `WFTextSeparator` directly to the separator string (e.g., `"|"`) is silently ignored — the action returns the input unsplit.

```json
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.text.split",
  "WFWorkflowActionParameters": {
    "UUID": "...",
    "WFTextSeparator": "Custom",
    "WFTextCustomSeparator": "|",
    "text": {
      "WFSerializationType": "WFTextTokenAttachment",
      "Value": {"Type": "ExtensionInput"}
    }
  }
}
```

### Get Item from List action

**Action:** `is.workflow.actions.getitemfromlist`

**Critical:** The item type is controlled by `WFItemSpecifier` (string), NOT `WFGetItemType` (integer). Using `WFGetItemType` is silently ignored — the action always returns the first item regardless of the integer value.

Valid `WFItemSpecifier` values (confirmed via [Cherri source](https://github.com/electrikmilk/cherri/blob/main/actions/scripting.cherri)):

| WFItemSpecifier | Extra params | Notes |
|---|---|---|
| (absent/default) | — | First Item |
| `"First Item"` | — | Explicit first item |
| `"Last Item"` | — | Last item |
| `"Random Item"` | — | Random item |
| `"Item At Index"` | `WFItemIndex: N` | 1-based index. Note capital "A" in "At" |
| `"Items in Range"` | `WFItemRangeStart`, `WFItemRangeEnd` | 1-based range |

```json
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
  "WFWorkflowActionParameters": {
    "UUID": "...",
    "WFItemSpecifier": "Item At Index",
    "WFItemIndex": 2,
    "WFInput": {
      "WFSerializationType": "WFTextTokenAttachment",
      "Value": {
        "Type": "ActionOutput",
        "OutputUUID": "split-text-uuid",
        "OutputName": "Split Text"
      }
    }
  }
}
```

All specifiers confirmed working (including `"Item At Index"` with indices 1–3 on a 3-element split list). Index 0 gives an explicit error: "You asked for item 0, but the first item is at index 1."

**History:** Experiments with `WFGetItemType` (integer values 0–4) all returned the first item. The correct `WFItemSpecifier` (string) was discovered by testing parameter variants and confirmed against the Cherri compiler source. The production shortcut uses `"Item At Index"` with indices 1 and 2 for the 2-element date split.

### CalendarItemQuery "between" is end-exclusive

The `Operator: 1003` ("is between") date filter **excludes the end date**. A query for `startDate between Feb 9..Feb 9` returns zero results. To query a single day, the end date must be the next day (e.g., `Feb 9..Feb 10`).

The Python layer (`shortcuts.get_events()`) adds +1 day to the caller's `to_date` to make the API inclusive from the user's perspective.

### Input-driven date query pattern

The production Find Events shortcut receives the date range as input text (`"YYYY-MM-DD|YYYY-MM-DD"`) instead of hardcoding a fixed window. The full action chain:

```
Input "2026-03-01|2026-03-16" (via shortcuts run -i)
  → Split Text on "|" (Custom separator)
  → Get Item At Index 1 → Detect Dates → Adjust Date +0d  (start)
  → Get Item At Index 2 → Detect Dates → Adjust Date +0d  (end)
  → CalendarItemQuery(startDate between adj1..adj2)
  → Repeat Each → Text → Text wrap → Output
```

The Adjust Date +0d step is not a no-op — it "launders" the Detect Dates output into a format CalendarItemQuery's filter accepts. Without it, the filter silently returns 0 items. The exact reason is unknown but likely related to the internal type system: Detect Dates produces a `WFDateContentItem` array while Adjust Date produces a single `WFDateContentItem` that the predicate evaluator can compare.

### Output action taint tracking

Data from third-party App Intent actions (like Fantastical's CalendarItemQuery) is marked as "tainted" by macOS. The Output action refuses to emit tainted data directly:

```
Action <private> produces private output and is not exempt from taint tracking, but is missing an appIdentifier
Error Domain=WFActionErrorDomain Code=4
```

**Fix:** Insert a Text action between the Repeat Results and the Output action. The Text action wraps the data, and its output is owned by the Shortcuts engine (not the third-party app), bypassing the taint tracking:

```
Repeat Results → Text(Repeat Results) → Output(Text)
```

This is required for all shortcuts that output data from third-party App Intent actions via `shortcuts run`.

### Output name

The output of CalendarItemQuery is referenced with `OutputName: "Fantastical Calendar Item"` (singular, despite potentially returning multiple items).

### Why CalendarItemQuery instead of FKRShowScheduleIntent

**Critical discovery:** `FKRShowScheduleIntent` only returns events from ONE calendar set (likely the default/active one). During testing, it only returned events from the "Danya&Liza" calendar, completely missing events from "Calendar" and other calendars — even though Fantastical's UI shows them all.

`CalendarItemQuery` ("Find Fantastical Calendar Item") should query across ALL calendars, making it the correct choice for a CLI tool that needs complete event data.

### Retrieving shortcut UUIDs via JXA

To look up a shortcut's UUID (needed for opening in Shortcuts.app, or for future inspection):

```javascript
// Note: use "Shortcuts Events" not "Shortcuts" — the latter throws -1708
var app = Application("Shortcuts Events");
var shortcuts = app.shortcuts();
var result = [];
for (var i = 0; i < shortcuts.length; i++) {
    result.push({name: shortcuts[i].name(), id: shortcuts[i].id()});
}
JSON.stringify(result);
```

### Reverse engineering approach

To discover new plist formats for actions not yet supported by our generator:

1. Ask the user to create a shortcut manually in Shortcuts.app with the desired action
2. User shares/exports the `.shortcut` file (Share → File)
3. Extract the plist via AEA decryption (see "Extracting plists from signed shortcuts")
4. Inspect the action parameters and replicate programmatically in `shortcut_gen.py`

This approach was used to discover:
- The WFTextTokenString encoding for App Intent parameters (vs WFTextTokenAttachment)
- The WFContentPredicateTableTemplate format for CalendarItemQuery filters
- The WFDuration string encoding and WFWorkflowClientVersion requirement for dynamic dates

## Conditional actions (If/Otherwise/End If)

Uses `is.workflow.actions.conditional` with `WFControlFlowMode` 0/1/2 and shared `GroupingIdentifier`, similar to Repeat Each.

### Condition values (from Cherri compiler source)

| Value | Meaning |
|-------|---------|
| 0 | less than |
| 1 | less than or equal |
| 2 | greater than |
| 3 | greater than or equal |
| 4 | is |
| 5 | is not |
| 8 | begins with |
| 9 | ends with |
| 99 | contains |
| 100 | has any value |
| 101 | does not have any value |
| 999 | does not contain |
| 1003 | is between |

Source: [Cherri Shortcuts compiler](https://github.com/electrikmilk/cherri/blob/main/shortcut.go)

### macOS 15+ / iOS 18+ format

On modern macOS, the If action uses `WFConditions` with `WFContentPredicateTableTemplate` instead of flat `WFCondition` + `WFInput` parameters:

```json
{
  "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
  "WFWorkflowActionParameters": {
    "WFControlFlowMode": 0,
    "GroupingIdentifier": "if-group-uuid",
    "WFConditions": {
      "WFSerializationType": "WFContentPredicateTableTemplate",
      "Value": {
        "WFActionParameterFilterPrefix": 1,
        "WFActionParameterFilterTemplates": [
          {
            "WFCondition": 100,
            "WFInput": {
              "Type": "Variable",
              "Variable": {
                "WFSerializationType": "WFTextTokenAttachment",
                "Value": { ... variable reference ... }
              }
            }
          }
        ]
      }
    }
  }
}
```

**Status:** Not yet validated. Our attempt to use condition 100 ("has any value") to guard a nested Repeat Each over nil attendees produced "Please choose a value for each parameter" error with the flat format, and still crashed with the WFContentPredicateTableTemplate format. The exact working format may need to be discovered by having the user create an If shortcut manually (same reverse-engineering approach as CalendarItemQuery).

## Debugging with macOS unified logs

Shortcuts execute in the `BackgroundShortcutRunner` process. Use `/usr/bin/log` (full path required — zsh has a builtin `log` function that shadows it) to capture diagnostic output.

### Capturing logs during a shortcut run

```bash
# Start log capture in background BEFORE running the shortcut
/usr/bin/log stream --predicate 'process == "BackgroundShortcutRunner" OR process == "Fantastical" OR process CONTAINS "hortcut"' --style compact > /tmp/sc_log.txt 2>&1 &
LOG_PID=$!

# Run the shortcut
shortcuts run "My Shortcut" > /tmp/sc_output.txt 2>&1 &
SC_PID=$!

# Wait for completion (with timeout)
for i in $(seq 1 120); do
  kill -0 $SC_PID 2>/dev/null || break
  sleep 1
done

# Clean up
kill $LOG_PID 2>/dev/null
kill $SC_PID 2>/dev/null  # if still running (timeout)
```

### Viewing past logs (no streaming needed)

```bash
# Last 5 minutes of BackgroundShortcutRunner logs
/usr/bin/log show --last 5m --predicate 'process == "BackgroundShortcutRunner"' --style compact

# Include Fantastical and Shortcuts processes
/usr/bin/log show --last 5m --predicate 'process == "BackgroundShortcutRunner" OR process == "Fantastical" OR process CONTAINS "hortcut"' --style compact
```

### Key log subsystems

| Subsystem | What it shows |
|-----------|--------------|
| `com.apple.shortcuts:RunningLifecycle` | Action start/finish, output item counts |
| `com.apple.shortcuts:WorkflowExecution` | Parameter processing, action start/finish with details |
| `com.apple.shortcuts:Dialog` | Smart prompt / privacy dialog responses |
| `com.apple.shortcuts:Security` | Smart prompt presentation, privacy decisions |
| `com.apple.shortcuts:AppIntentsMetadata` | Metadata loading for third-party actions |
| `com.apple.shortcuts:Interchange` | App definition loading |
| `com.apple.appintents:Connection` | XPC connection to Fantastical for query execution |

### Common log patterns

**Successful query execution:**
```
Action <WFLinkContentItemFilterAction: ...IntentCalendarItem...> finished with output of 99 items
```

**Smart prompt shown (expected — user must accept):**
```
Action com.flexibits.fantastical2.mac.IntentCalendarItem is presenting a smart prompt, but it does not have a custom smart prompt string.
```

**Metadata warnings (benign — execution continues):**
```
Metadata not found for com.flexibits.fantastical2.mac:IntentCalendarItem
Failed to load a definition for com.flexibits.fantastical2.mac
```
These appear on every run but don't prevent the action from working.

**Property aggrandizement crash (attendees):**
```
*** Terminating app due to uncaught exception 'NSInvalidArgumentException',
reason: '-[WFLinkEntityContentItem_com.flexibits.fantastical2.mac_IntentAttendee if_map:]:
unrecognized selector sent to instance ...'
```
This crash occurs when accessing the `attendees` property via `WFPropertyVariableAggrandizement` in a Text action. The `IntentAttendee` entity objects cannot be coerced to text. Use "Get Invitees from Event" action instead.

### Known property safety

Properties tested via `WFPropertyVariableAggrandizement` on `IntentCalendarItem`:

| Property | Status | Notes |
|----------|--------|-------|
| `title` | Works | |
| `startDate` | Works | |
| `endDate` | Works | |
| `calendarIdentifier` | Works | |
| `isAllDay` | Works | |
| `location` | Works | |
| `notes` | Works | |
| `fantasticalURL` | Works | |
| `attendees` | **CRASHES** | `IntentAttendee` objects don't support `if_map:` for text coercion |
| `url` | Untested | |
| `hexColorString` | Untested | |
| `availability` | Untested | |
| `conferences` | Untested | |

## Output parsing

Shortcuts pipe output to stdout as plain text. Our shortcuts format output as pipe-delimited records separated by ASCII Record Separator (0x1E):

```
Meeting with Bob | 8 Feb 2026 at 10:00 | 8 Feb 2026 at 11:00 | f800940a... | x-fantastical://show?...␞
Lunch | 8 Feb 2026 at 12:00 | 8 Feb 2026 at 13:00 | 2aab12d3... | x-fantastical://show?...␞
```

Current fields (matching `EVENT_PROPS` in `shortcut_gen.py`):
1. `title`
2. `startDate` — localized format: "12 Feb 2026 at 12:00"
3. `endDate`
4. `calendarIdentifier` — hex hash, mapped to `calendarName` by `api._get_calendar_map()`
5. `fantasticalURL` — deep link back to event in Fantastical

Parser handles:
- Record separator (0x1E) splits records — allows fields to contain newlines
- Varying number of fields (graceful degradation)
- Null values represented as `nil`, `null`, `(null)`, or empty string
- Leading/trailing whitespace stripped from each field
- **Known issue:** pipe (`|`) in event titles (e.g., "Miro Council | Virtual Session") breaks field splitting

See `shortcuts.py:parse_pipe_delimited()` for implementation.

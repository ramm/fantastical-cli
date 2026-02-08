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
- `Date` — start of range, format `"YYYY-MM-DD HH:MM:SS.ffffff"`
- `AnotherDate` — end of range, same format

**TODO:** Test whether simpler date formats work (e.g., `"2026-02-09"` without time component), and whether the `Date`/`AnotherDate` values can be dynamic (WFTextTokenString with variable references) rather than static strings.

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
- Multiline fields (e.g., location with address) — pipe is the delimiter, newlines within fields are preserved

See `shortcuts.py:parse_pipe_delimited()` for implementation.

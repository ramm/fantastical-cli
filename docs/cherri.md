# Cherri — Shortcuts Programming Language

[Cherri](https://github.com/electrikmilk/cherri) is a Go-based language that compiles to `.shortcut` files. Its source code is useful as a reference for understanding Apple Shortcuts plist internals.

## Installation

```bash
brew tap electrikmilk/cherri && brew install electrikmilk/cherri/cherri
```

## Useful source files

- `shortcut.go` → `conditions` map — condition values (less than, contains, has any value, etc.)
- `shortcutgen.go` → `makeConditions()` — `WFContentPredicateTableTemplate` format
- `shortcutgen.go` → `makeConditionalAction()` — control flow encoding (If/Otherwise/End If)
- `shortcutgen.go` → `attachmentValues()` — how variable refs become `WFTextTokenString` with `attachmentsByRange`
- `shortcutgen.go` → `conditionalParameter()` → `conditionalParameterVariable()` — how variables are encoded inside If condition comparisons

## Usage

```bash
# Compile a .cherri script, output debug plist
cherri test.cherri -d --skip-sign --derive-uuids -o output.shortcut

# The -d flag writes a .plist file alongside the .shortcut for inspection
# --skip-sign avoids contacting Apple servers
# --derive-uuids produces deterministic UUIDs for reproducible output
```

## Key findings from source analysis

### If conditions (iOS 18+) use WFContentPredicateTableTemplate

Cherri's `makeConditions()` (shortcutgen.go:907) generates the iOS 18+ format:

```json
{
  "WFSerializationType": "WFContentPredicateTableTemplate",
  "Value": {
    "WFActionParameterFilterPrefix": -1,
    "WFActionParameterFilterTemplates": [
      {
        "WFCondition": 99,
        "WFConditionalActionString": "hello",
        "WFInput": {
          "Type": "Variable",
          "Variable": { "WFSerializationType": "WFTextTokenAttachment", "Value": {...} }
        }
      }
    ]
  }
}
```

### Variable references in If condition values

From `conditionalParameter()` (shortcutgen.go:939):
- **String comparisons** → `WFConditionalActionString` key, value via `paramValue()` → `attachmentValues()` → `WFTextTokenString`
- **Number comparisons** → `WFNumberValue` key, value via `paramValue()` → `variableValue()` → `WFTextTokenAttachment`
- **"is between" (condition 1003)** → second arg → `WFNumberValue`, third arg → `WFAnotherNumber`

### Entity query filters use a DIFFERENT structure

**Critical finding:** Cherri has NO support for entity query actions (like CalendarItemQuery). Its `rawAction()` can build basic actions but cannot express the nested `WFContentItemFilter` → `WFContentPredicateTableTemplate` → `WFActionParameterFilterTemplates` structure with `Property`/`Operator`/`Values`.

Entity query filters use:
- `Property` (e.g., `"startDate"`) — not `WFInput`
- `Operator` (e.g., `1003` for "is between") — not `WFCondition`
- `Values` dict (e.g., `{Unit: 4, Date: "...", AnotherDate: "..."}`) — not `WFConditionalActionString`/`WFNumberValue`

This means the Cherri source cannot tell us whether `Values.Date`/`Values.AnotherDate` accept dynamic `WFTextTokenString` variable references. The extracted CalendarItemQuery plist had plain date strings, and this remains an open question (see TODO.md P1).

### attachmentValues() encoding pipeline

`attachmentValues()` (shortcutgen.go:445) converts strings with `{variable}` references into `WFTextTokenString`:

1. Collects inline variables via regex `\{@?(.*?)(?:\['(.*?)'])?(?:\.(.*?))?\}`
2. Replaces them with U+FFFC (Object Replacement Character)
3. Maps each U+FFFC position to an attachment dict in `attachmentsByRange`
4. Handles UTF-16 surrogate pairs (emoji etc.) by doubling the position offset

This is the same encoding our `_text_token_string()` helper in `shortcut_gen.py` produces.

## General methodology: Cherri as a reference plist generator

Cherri is a known-good plist generator — its output is accepted by Shortcuts.app and the `shortcuts` CLI. When debugging shortcut generation issues in `shortcut_gen.py`, the most productive approach is:

1. Write a Cherri script that produces the same (or similar) action structure
2. Compile with `cherri script.cherri -d --skip-sign --derive-uuids`
3. Inspect the `.plist` debug output
4. Diff against our `plistlib.dump()` output to find encoding differences

This is faster and more reliable than manual Shortcuts.app → export → AEA decrypt, and catches subtle issues like type mismatches (e.g., string vs native datetime), key ordering, or missing wrapper structures.

For actions Cherri doesn't natively support (like entity queries), use `rawAction()` with a full parameter dict — Cherri will still serialize it through its plist pipeline.

## Cherri syntax notes

- Includes use single quotes: `#include 'actions/scripting'`
- Variables: `const myText = "hello"` or `myVar = "hello"`
- `number()` takes a variable, not a literal: `const myNum = number(someVar)`
- If conditions: `if myVar contains "text" { ... }`
- Basic actions are auto-included; others need explicit `#include`

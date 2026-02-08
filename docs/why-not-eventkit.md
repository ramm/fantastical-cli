# Why Not EventKit / Calendar.app?

## The fundamental problem

Fantastical maintains its own account system separate from macOS Calendar.app. When a user adds a Google, Exchange, or CalDAV account directly in Fantastical (which is the default and recommended setup), those accounts are **invisible** to Calendar.app and EventKit.

This is [confirmed by community reports](https://talk.macpowerusers.com/t/fantastical-3-macos-option-to-access-calendar-accounts-via-macos-internal-api-anymore/16916) — Fantastical 3 moved away from using the macOS internal calendar API (EventKit), requiring direct connections to calendar providers instead. Flexibits cited "poor performance" of macOS APIs as the reason. The [official Mac docs](https://flexibits.com/fantastical/help/getting-started) confirm accounts must be added manually in Fantastical's own settings.

Fantastical *can* optionally show "On My Mac" calendars from Calendar.app (Settings > Accounts > Apps > local Calendar sync), but this only covers local calendars — not cloud accounts.

This means:
- `EKEventStore` returns empty or incomplete data for Fantastical-only accounts
- The existing npm `mcp-fantastical` package is fundamentally flawed — it falls back to Calendar.app
- Any approach using Apple's EventKit framework will miss Fantastical-only accounts

## What we tried

### 1. EventKit via JXA ObjC bridge

```javascript
ObjC.import('EventKit');
var store = $.EKEventStore.alloc.init;
store.requestAccessToEntityTypeCompletion(0, function(granted, error) { ... });
```

**Result:** Returns empty arrays. `osascript` doesn't have the TCC (Transparency, Consent, and Control) entitlement required for calendar access. Even if it worked, it would only see Calendar.app accounts.

### 2. EventKit via compiled Swift CLI

A compiled Swift binary requesting EKEventStore access:

**Result:**
- First run: times out waiting for the macOS TCC permission dialog
- Subsequent runs: "Access denied: unknown"
- CLI tools lack proper entitlements for calendar TCC access
- Would need to be a proper .app bundle with Info.plist to get TCC prompts
- Even then, would only see Calendar.app accounts, not Fantastical's

### 3. Direct database access

Fantastical stores its data in a private SQLite database. This is:
- Undocumented and changes between versions
- Likely encrypted or obfuscated
- Not a stable interface
- Not investigated further

## The correct approach

All data access must go through Fantastical's own interfaces:

1. **JXA scripting** — Limited but works without setup (calendars, selected items, create events)
2. **Apple Shortcuts + App Intents** — Rich and powerful (date queries, search, tasks) but requires one-time shortcut creation
3. **URL schemes** — Good for event creation (`x-fantastical3://parse?s=...`)

These are the only interfaces that see ALL of Fantastical's data, including accounts not shared with Calendar.app.

# JXA (JavaScript for Automation) Findings

## How it works

Fantastical exposes a scripting dictionary accessible via JXA (or AppleScript). We use JXA because it returns data structures that are easy to JSON.stringify().

```bash
osascript -l JavaScript -e 'var app = Application("Fantastical"); ...'
```

## What works

### List calendars

```javascript
const app = Application("Fantastical");
const cals = app.calendars();
const result = cals.map(c => ({
    title: c.title(),
    id: c.id()
}));
JSON.stringify(result);
```

Returns all 12 calendars. Calendar properties available: `title`, `id`, `class`. No color, source, or account info exposed via JXA.

### Get selected calendar items

```javascript
const app = Application("Fantastical");
let items;
try {
    items = app.selectedCalendarItems();
} catch(e) {
    items = [];
}
// ... wrap every property access in try/catch
```

Selected item properties:
- `title` — string
- `startDate` — Date object (use `.toISOString()`, but wrap in try/catch)
- `endDate` — Date object
- `isAllDay` — boolean (often throws on tasks)
- `notes` — string or null
- `isRecurring` — boolean (sometimes unavailable)
- `location` — string (sometimes unavailable)
- `url` — string (sometimes unavailable)
- `showUrl` — Fantastical deep link (x-fantastical://show?item=UUID&calendarIdentifier=ID)
- `id` — string
- `pcls` — class type: `calendarEvent` or `calendarTask`

### Create events via parseSentence

```javascript
const app = Application("Fantastical");
app.parseSentence("Meeting tomorrow at 3pm");
```

This works but opens the Fantastical UI. The URL scheme (`x-fantastical3://parse?s=...&add=1`) is better for headless creation.

## Gotchas

### 1. Every property access can throw

Fantastical's JXA bridge is fragile. Accessing `isAllDay()` on a task or `startDate()` on a nil item throws `-1700` (type conversion error). **Always wrap in try/catch:**

```javascript
try { obj.isAllDay = item.isAllDay(); } catch(e) { obj.isAllDay = false; }
```

### 2. Use `title` not `name`

`calendar.name()` throws error -1728. The property is called `title`.

### 3. `selectedCalendarItems()` can throw if nothing is selected

Wrap the entire call:
```javascript
let items;
try { items = app.selectedCalendarItems(); } catch(e) { items = []; }
```

### 4. Date serialization

`startDate().toISOString()` can throw if the date is null or the item doesn't have one. Always wrap.

### 5. `properties()` is useful for exploration

```javascript
var sel = app.selectedCalendarItems[0];
sel.properties();
// Returns object with all available properties
```

## What doesn't work

Independent confirmation: [Michael Tsai's blog post](https://mjtsai.com/blog/2024/10/23/the-sad-state-of-mac-calendar-scripting/) describes Fantastical's scripting dictionary as "promising but mostly doesn't work" — key properties like the containing calendar and repetition/alarm info are missing, the `duplicate` command doesn't work, creating events via AppleScript fails, and setting properties mutates a temporary object that's never persisted. This matches our findings.

### Querying events by date

There is no `app.calendarItems.whose(...)` or any date-based query in Fantastical's JXA dictionary. You can only get selected items or list calendars. For date queries, you must use Apple Shortcuts with Fantastical's App Intents.

### EventKit via JXA ObjC bridge

```javascript
ObjC.import('EventKit');
var store = $.EKEventStore.alloc.init;
// Returns empty arrays — no TCC entitlement for osascript
```

This fails silently — EventKit requires a TCC (Transparency, Consent, and Control) entitlement that `osascript` doesn't have. Even if it did work, it would access Calendar.app's store, not Fantastical's private accounts.

### EventKit via Swift CLI

A compiled Swift binary that requests EventKit access also fails:
- First run: times out waiting for TCC prompt
- Subsequent runs: "Access denied: unknown"
- CLI tools lack the proper entitlements for calendar TCC access

### sdef (scripting definition export)

```bash
sdef /Applications/Fantastical.app
```

Requires full Xcode (not just Command Line Tools). Not worth depending on.

## URL schemes

Better than JXA for event creation since they don't open the UI:

```
x-fantastical3://parse?s=ENCODED_SENTENCE&n=NOTES&calendarName=NAME&add=1
```

**Mac parameters** (from [official Mac docs](https://flexibits.com/fantastical/help/integration)):
- `s` — Natural language sentence (URL-encoded)
- `n` — Event notes
- `calendarName` — Target calendar
- `add=1` — Add directly without showing UI

**iOS parameters** (from [official iOS docs](https://flexibits.com/fantastical-ios/help/integration)) — different names:
- `sentence` — Natural language sentence
- `notes` — Event notes
- Also supports: `title`, `location`, `url`, `start`, `end`, `allDay`, `attendees`, `availability`, `private`, `reminder`, `due`
- Date format: `yyyy-MM-dd HH:mm`
- Note: the `sentence` parameter overrides other specific parameters when used

The Mac and iOS parameter names differ (`s`/`n` vs `sentence`/`notes`). Our code uses the Mac parameter names.

Other URL schemes:
- `x-fantastical3://show/calendar` — Open Fantastical calendar view
- `x-fantastical3://show/mini` — Open mini view
- `x-fantastical3://show/set?name=NAME` — Switch calendar set
- `x-fantastical3://show?date=yyyy-MM-dd` — Jump to date (also accepts natural language like "Tuesday")
- `x-fantastical3://x-callback-url/parse?...` — x-callback-url variant (supports x-source, x-success, x-cancel, x-error)
- `x-fantastical3://defaults?key=...&value=...&type=bool&group=1` — Hidden settings

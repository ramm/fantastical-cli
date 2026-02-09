# Fantastical App Intents — Complete Catalog

Extracted from `/Applications/Fantastical.app/Contents/Resources/Metadata.appintents/extract.actionsdata` using `plutil -convert json`. These identifiers are universal across all installations of the same Fantastical version.

## Actions (16 total)

### Data-returning actions (useful for automation)

| Intent ID | Display Title | FQN | Parameters | Returns |
|-----------|--------------|-----|------------|---------|
| `FKRShowScheduleIntent` | Show Schedule | `Fantastical.ShowSchedule` | day (enum), date, showUpcomingEventsOnly (bool), hideAllDayItems (bool) | intentCalendarItems |
| `FKRShowCalendarIntent` | Show Calendar | `Fantastical.ShowCalendar` | calendar (CalendarEntity), date, skipTodayPastEvents (bool) | intentCalendarItems |
| `FKRShowListIntent` | Show Task List | `Fantastical.ShowTaskList` | list (string), date | intentCalendarItems |
| `FKROverdueRemindersIntent` | Overdue Tasks | `Fantastical.OverdueTasks` | (none) | intentCalendarItems |
| `FKRUpcomingCalendarItemIntent` | Upcoming Item | `Fantastical.UpcomingCalendarItem` | itemType (IntentItemType enum) | title, time, intentCalendarItem |
| `FKRCreateFromInputIntent` | Create From Input | `Fantastical.CreateFromInput` | input (string), notes (string) | title, dateTime, intentCalendarItem |
| `FKRGetAttendeesFromEventIntent` | Get Invitees from Event | `Fantastical.GetAttendeesFromEvent` | calendarItem (IntentCalendarItem) | attendees |

### UI/navigation actions (open Fantastical, less useful for CLI)

| Intent ID | Display Title | FQN | Parameters |
|-----------|--------------|-----|------------|
| `FKRChangeCalendarSetIntent` | Change Calendar Set | `Fantastical.ChangeCalendarSet` | calendarSet (CalendarSetEntity) |
| `FKROpenOnDateIntent` | Open to Date | `Fantastical.OpenOnDate` | date |
| `FKRChangeCalendarViewIntent` | Change View | `Fantastical.ChangeCalendarView` | view (enum) |
| `InAppSearchIntent` | Search with Fantastical | `Fantastical.InAppSearchIntent` | criteria (string) — opens app |
| `OpenSearchIntent` | Search in Fantastical | `Fantastical.OpenSearchIntent` | (none) |
| `OpenTodayControlIntent` | Open Today | `Fantastical.OpenTodayControlIntent` | (none) |
| `FantasticalFocusFilterIntent` | Filter Calendar Sets | `Fantastical.FantasticalFocusFilterIntent` | selectedCalendarSets |
| `CreateEventControlIntent` | Create Event | `Fantastical.CreateEventControlIntent` | (none) — opens UI |
| `CreateTaskControlIntent` | Create Task | `Fantastical.CreateTaskControlIntent` | (none) — opens UI |

## Entity Queries (3 total)

These are the Shortcuts "Find..." actions that return structured data.

### CalendarItemQuery
- **FQN:** `Fantastical.CalendarItemQuery`
- **Filters:** startDate (date, comparator: "is between"), type (IntentItemType enum), title (string, comparator: "contains")
- **Returns:** `IntentCalendarItem` entities
- **Sort by:** startDate, title
- **This is the most powerful query** — it can search by title, filter by date range, and filter by event/task type.

### CalendarQuery
- **FQN:** `Fantastical.CalendarQuery`
- **Filters:** title (string)
- **Returns:** `CalendarEntity` entities
- **Sort by:** title

### CalendarSetQuery
- **FQN:** `Fantastical.CalendarSetQuery`
- **Filters:** name (string)
- **Returns:** `CalendarSetEntity` entities
- **Sort by:** name

## Entities (5 total)

### IntentCalendarItem (`Fantastical.IntentCalendarItem`)
The main entity. Properties:
- `type` — event or reminder
- `title` — string
- `startDate` — date
- `endDate` — date
- `dueDate` — date (for tasks)
- `calendarIdentifier` — string
- `fantasticalURL` — URL (deep link back to Fantastical)
- `hexColorString` — string (calendar color)
- `isAllDay` — boolean
- `notes` — string
- `url` — URL (user-set URL on the event)
- `attendees` — string (comma-separated)
- `location` — string
- `availability` — IntentCalendarItemAvailability enum
- `conferences` — IntentConference entities

### CalendarEntity (`Fantastical.CalendarEntity`)
- `title` — string

### CalendarSetEntity (`Fantastical.CalendarSetEntity`)
- `name` — string

### IntentAttendee (`Fantastical.IntentAttendee`) — transient
- `identifier` — string
- `displayString` — string
- `email` — string

### IntentConference (`Fantastical.IntentConference`) — transient
- `identifier` — string
- `displayString` — string
- `url` — URL

## Enum Types

### IntentScheduleDay
Used by `FKRShowScheduleIntent.day` parameter.
- `unknown` (0)
- `today` (1)
- `tomorrow` (2)
- `specificDate` (3)

### IntentItemType
Used by `CalendarItemQuery.type` and `FKRUpcomingCalendarItemIntent.itemType`.
- `unknown` (0)
- `event` (1)
- `reminder` / `task` (2)
- `unspecified` / `item` (3)

### IntentCalendarItemAvailability
- `unknown` (0)
- `notSupported` (1)
- `busy` (2)
- `free` (3)
- `tentative` (4)
- `unavailable` (5)
- `workingElsewhere` (6)

### IntentActionType
- `unknown` (0)
- `addEvent` (1)
- `addTask` (2)
- `search` (3)
- `launch` (4)

## Primitive Type Identifiers

Found in parameter `valueType.primitive.wrapper.typeIdentifier`:
- `0` = String
- `1` = Boolean
- `8` = Date
- `11` = URL

## Comparator Values

Found in query filter `comparators` (metadata internal IDs — NOT the same as plist `Operator` values):
- `0` = equals → plist Operator `0`
- `6` = contains → plist Operator `99`
- `9` = is between → plist Operator `1003`

**Warning:** Using metadata comparator values directly as plist Operator values causes filters to be silently ignored. Always use the plist Operator values. See `docs/shortcuts-format.md` § "Title contains filter" for details.

## How to re-extract this data

```bash
# The main actions database
plutil -convert json -o - \
  /Applications/Fantastical.app/Contents/Resources/Metadata.appintents/extract.actionsdata

# Legacy intent definitions (has enum values, param details)
plutil -convert json -o - \
  /Applications/Fantastical.app/Contents/PlugIns/FKRIntents.appex/FKRIntents.intentdefinition
```

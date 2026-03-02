# Live MCP testing prompt

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

## What this exercises and why

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

## Expected volume

~500–1500 events for 6 months of a typical busy calendar. ~13 parallel 2-week chunks, each returning compact tab-separated output (~2–5KB instead of the 80–120KB JSON it would have been before).

## Failure modes to watch for

- Shortcuts timeout on ranges >1 month (should not happen with 2-week chunks)
- Duplicate cache entries for same event fetched in overlapping ranges
- `get_event_details` returning "not found" for an ID that was just listed
- `search_events` without `from_date`/`to_date` silently falling back to ±30 days when the analysis needs the full 6-month window
- Agent failing to parallelize the 2-week chunk calls (sequential = ~2 min vs parallel = ~15–20s)

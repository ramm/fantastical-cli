# LAYER — Backend constants `SHORTCUTS`/`LEGACY_SHORTCUTS` leak through API to CLI

Resolved: 2026-02-09
Commits: b58ae53

## Original ticket

`cli.py` imported `SHORTCUTS` and `LEGACY_SHORTCUTS` dicts from the backend (via re-export through `api.py`), violating the layer rule that CLI only calls `api.py` functions. The backend's internal data structures were leaking into the presentation layer.

## Changes

- Added `api.get_shortcut_names()` and `api.check_legacy_shortcuts()` as proper API functions that encapsulate backend constants.
- Updated `cli.py` to call these API functions instead of importing backend dicts directly.

## Reasoning

The architecture requires `cli.py` to call only `api.py` — never import backend internals. Exposing raw dicts couples the CLI to the backend's internal naming conventions. Wrapping them in API functions preserves the abstraction boundary and makes it possible to change the backend's data structures without touching the CLI.

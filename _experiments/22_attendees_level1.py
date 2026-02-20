"""Experiment 22: Incremental attendee intent test.

Isolates FKRGetAttendeesFromEventIntent into five levels to determine
what works and what doesn't for attendee data extraction.

Reuses proven helpers from shortcut_gen.py — no helper duplication.

Usage:
  uv run python _experiments/22_attendees_level1.py --level 1
  uv run python _experiments/22_attendees_level1.py --level 2
  uv run python _experiments/22_attendees_level1.py --level 3
  uv run python _experiments/22_attendees_level1.py --level 4 --input "2026-02-20|2026-02-21|Storage leads"
  uv run python _experiments/22_attendees_level1.py --level 5 --input "2026-02-20|2026-02-21|Storage leads"
  uv run python _experiments/22_attendees_level1.py --level 1 --dump

Levels:
  1 — Does the intent work at all? (no repeat loop, single event, count only)
  2 — Does it work inside a repeat loop? (Repeat Item binding, count per event)
  3 — Nested repeat: inner loop over attendees with property access
  4 — Single event: raw coercion + all known property access on attendees
  5 — Property probe: tests 14 property names (documented + undocumented)

Results (2026-02-20):
  Level 1: PASS — returned "2" (attendee count of first event). Exit code 0.
  Level 2: PASS — all events show title + attendee count. Repeat Item as
           WFTextTokenString works for the calendarItem App Intent param.
  Level 3: PARTIAL — titles appear but displayString and email are blank
           inside the nested inner Repeat Each. The inner Repeat Item
           properties resolve to empty. Root cause unknown; may be a
           Shortcuts runtime bug with nested Repeat Each over App Entity
           arrays. Not worth debugging further given Level 4 works.
  Level 4: PASS — all four property variants (RAW coercion, Name,
           displayString, email) return data for every attendee.
           This is the proven working pattern: ActionOutput reference
           to a single event, no nested loops.
  Level 5: PASS (for documented props), EMPTY (for undocumented).
           Only displayString, email, and Name return data.
           All EventKit-style properties (type, role, status,
           participantType, participantRole, participantStatus,
           isResource, isRequired, isOptional, isOrganizer) are blank.
           The identifier field is also blank.
           Confirmed against extract.actionsdata: IntentAttendee has
           exactly 3 properties (identifier, displayString, email).
           Fantastical does not expose attendee type (person vs resource)
           or role (required vs optional) through App Intents.

Key findings:
  - FKRGetAttendeesFromEventIntent works reliably with both ActionOutput
    (Level 1/4) and Repeat Item WFTextTokenString (Level 2) references.
  - IntentAttendee entity: only displayString and email are populated.
    identifier is always empty. No type/role/status properties exist.
  - Nested Repeat Each (outer=events, inner=attendees) has blank property
    values on the inner Repeat Item. Avoid this pattern.
  - Rooms appear as attendees with identifiable names/emails
    (e.g. "MR-NL-3B-Steam engine" / MR-NL-3B-Steamengine@nebius.com).
    Must use email/name heuristics to distinguish from people.
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
import time
from pathlib import Path

from fantastical.backend.shortcut_gen import (
    FIELD_SEPARATOR,
    RECORD_SEPARATOR,
    _build_shortcut_plist,
    _fantastical_action,
    _get_item_from_list_action,
    _input_date_query_actions,
    _output_action,
    _repeat_each_end,
    _repeat_each_start,
    _text_token_string,
    _token_string_param,
    _uuid,
    _var_attachment,
)

OUTDIR = Path(__file__).parent
SHORTCUT_NAME = "claude-test-attendees-l{level}"


# -- Actions not in shortcut_gen.py, built inline --

def _count_action(action_uuid: str, input_ref: dict) -> dict:
    """Build a Count action (is.workflow.actions.count)."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.count",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "Input": input_ref,
        },
    }


def _text_action_with_uuid(text_content: dict, action_uuid: str) -> dict:
    """Build a Text action with an explicit UUID."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFTextActionText": text_content,
        },
    }


# -- Level builders --

def build_level1() -> dict:
    """Level 1: Does the intent work at all?

    No repeat loop. Gets first event from query, calls
    FKRGetAttendeesFromEventIntent, counts, outputs.

    Flow:
      Input "start|end|title"
        → [_input_date_query_actions]
        → Get Item from List (index=1)
        → FKRGetAttendeesFromEventIntent(calendarItem=above)
        → Count(invitees)
        → Text(count)           ← taint launder
        → Output
    """
    query_uuid = _uuid()
    get_first_uuid = _uuid()
    attendees_uuid = _uuid()
    count_uuid = _uuid()
    text_uuid = _uuid()

    actions = [
        # Input parsing + CalendarItemQuery
        *_input_date_query_actions(query_uuid),

        # Get first event from query results
        _get_item_from_list_action(
            get_first_uuid, query_uuid,
            "Fantastical Calendar Item", index=1,
        ),

        # Get attendees from that event
        _fantastical_action(
            "FKRGetAttendeesFromEventIntent",
            attendees_uuid,
            extra_params={
                "calendarItem": _token_string_param(
                    output_uuid=get_first_uuid,
                    output_name="Item from List",
                ),
            },
        ),

        # Count the invitees
        _count_action(
            count_uuid,
            _var_attachment(
                var_type="ActionOutput",
                output_uuid=attendees_uuid,
                output_name="Invitees from Event",
            ),
        ),

        # Taint-launder through Text action
        _text_action_with_uuid(
            _token_string_param(
                output_uuid=count_uuid,
                output_name="Count",
            ),
            text_uuid,
        ),

        # Output
        _output_action(
            _token_string_param(
                output_uuid=text_uuid,
                output_name="Text",
            ),
        ),
    ]

    return _build_shortcut_plist(
        SHORTCUT_NAME.format(level=1), actions, accepts_input=True,
    )


def build_level2() -> dict:
    """Level 2: Does it work inside a repeat loop?

    Tests the Variable/Repeat Item binding for calendarItem param.

    Flow:
      Input "start|end|title"
        → [_input_date_query_actions]
        → Repeat Each (over query results)
          → FKRGetAttendeesFromEventIntent(calendarItem=Repeat Item)
          → Count(invitees)
          → Text(title FS count RS)
        → End Repeat
        → Text(Repeat Results)    ← taint launder
        → Output
    """
    query_uuid = _uuid()
    group_uuid = _uuid()
    attendees_uuid = _uuid()
    count_uuid = _uuid()
    repeat_output_uuid = _uuid()
    text_wrap_uuid = _uuid()

    # Repeat Item as WFTextTokenString for the calendarItem param
    repeat_item_token = _text_token_string(
        ["", ""],
        [{"Type": "Variable", "VariableName": "Repeat Item"}],
    )

    # Per-iteration text: title<FS>count<RS>
    # title = Repeat Item.title property
    title_attachment = {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": "title",
            "PropertyUserInfo": "title",
        }],
    }
    count_attachment = {
        "Type": "ActionOutput",
        "OutputUUID": count_uuid,
        "OutputName": "Count",
    }
    row_text = _text_token_string(
        ["", FIELD_SEPARATOR, RECORD_SEPARATOR],
        [title_attachment, count_attachment],
    )

    actions = [
        # Input parsing + CalendarItemQuery
        *_input_date_query_actions(query_uuid),

        # Repeat Each over query results
        _repeat_each_start(
            _var_attachment(
                var_type="ActionOutput",
                output_uuid=query_uuid,
                output_name="Fantastical Calendar Item",
            ),
            group_uuid,
        ),

        # Get attendees from Repeat Item
        _fantastical_action(
            "FKRGetAttendeesFromEventIntent",
            attendees_uuid,
            extra_params={
                "calendarItem": repeat_item_token,
            },
        ),

        # Count the invitees
        _count_action(
            count_uuid,
            _var_attachment(
                var_type="ActionOutput",
                output_uuid=attendees_uuid,
                output_name="Invitees from Event",
            ),
        ),

        # Format row: title<FS>count<RS>
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": row_text,
            },
        },

        # End Repeat
        _repeat_each_end(group_uuid, repeat_output_uuid),

        # Taint-launder Repeat Results through Text
        _text_action_with_uuid(
            _token_string_param(
                output_uuid=repeat_output_uuid,
                output_name="Repeat Results",
            ),
            text_wrap_uuid,
        ),

        # Output
        _output_action(
            _token_string_param(
                output_uuid=text_wrap_uuid,
                output_name="Text",
            ),
        ),
    ]

    return _build_shortcut_plist(
        SHORTCUT_NAME.format(level=2), actions, accepts_input=True,
    )


def build_level3() -> dict:
    """Level 3: Extract attendee info (displayString, email) per event.

    Nested repeat: outer over events, inner over attendees.
    Uses property aggrandizements on the inner Repeat Item to access
    IntentAttendee entity properties (displayString, email).

    Flow:
      Input "start|end|title"
        → [_input_date_query_actions]
        → Repeat Each (over events)
          → FKRGetAttendeesFromEventIntent(calendarItem=Repeat Item)
          → Repeat Each (over attendees)
            → Text(displayString<comma>email)
          → End Inner Repeat
          → Text(inner Repeat Results)    ← flatten attendee list
          → Text(title<FS>attendeeData<RS>)
        → End Outer Repeat
        → Text(Repeat Results)            ← taint launder
        → Output

    Attendee separator: comma between displayString and email,
    pipe between attendees (within the inner Repeat Results join).
    """
    query_uuid = _uuid()
    outer_group_uuid = _uuid()
    attendees_uuid = _uuid()
    inner_group_uuid = _uuid()
    inner_repeat_out_uuid = _uuid()
    inner_text_uuid = _uuid()
    outer_repeat_out_uuid = _uuid()
    text_wrap_uuid = _uuid()

    # Outer Repeat Item as WFTextTokenString for calendarItem param
    repeat_item_token = _text_token_string(
        ["", ""],
        [{"Type": "Variable", "VariableName": "Repeat Item"}],
    )

    # Inner loop: each attendee → "displayString,email"
    attendee_display = {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": "displayString",
            "PropertyUserInfo": "displayString",
        }],
    }
    attendee_email = {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": "email",
            "PropertyUserInfo": "email",
        }],
    }
    attendee_text = _text_token_string(
        ["", ",", ""],
        [attendee_display, attendee_email],
    )

    # Outer row: title<FS>attendeeData<RS>
    # title from outer Repeat Item (but we're inside inner loop context,
    # so we use the outer event's title via a different approach)
    # Actually: the outer Repeat Item property is shadowed by the inner
    # Repeat Item. So we need to capture title BEFORE the inner loop.
    # We'll use a Text action to capture the title first.
    title_text_uuid = _uuid()
    title_attachment = {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": "title",
            "PropertyUserInfo": "title",
        }],
    }

    # Row text references the captured title and the flattened attendee data
    row_title_ref = {
        "Type": "ActionOutput",
        "OutputUUID": title_text_uuid,
        "OutputName": "Text",
    }
    row_attendees_ref = {
        "Type": "ActionOutput",
        "OutputUUID": inner_text_uuid,
        "OutputName": "Text",
    }
    row_text = _text_token_string(
        ["", FIELD_SEPARATOR, RECORD_SEPARATOR],
        [row_title_ref, row_attendees_ref],
    )

    actions = [
        # Input parsing + CalendarItemQuery
        *_input_date_query_actions(query_uuid),

        # Outer Repeat Each over events
        _repeat_each_start(
            _var_attachment(
                var_type="ActionOutput",
                output_uuid=query_uuid,
                output_name="Fantastical Calendar Item",
            ),
            outer_group_uuid,
        ),

        # Capture event title before inner loop shadows Repeat Item
        _text_action_with_uuid(
            _text_token_string(["", ""], [title_attachment]),
            title_text_uuid,
        ),

        # Get attendees from this event
        _fantastical_action(
            "FKRGetAttendeesFromEventIntent",
            attendees_uuid,
            extra_params={
                "calendarItem": repeat_item_token,
            },
        ),

        # Inner Repeat Each over attendees
        _repeat_each_start(
            _var_attachment(
                var_type="ActionOutput",
                output_uuid=attendees_uuid,
                output_name="Invitees from Event",
            ),
            inner_group_uuid,
        ),

        # Format each attendee: "displayString,email"
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": attendee_text,
            },
        },

        # End Inner Repeat
        _repeat_each_end(inner_group_uuid, inner_repeat_out_uuid),

        # Flatten inner repeat results (attendees joined by newlines)
        _text_action_with_uuid(
            _token_string_param(
                output_uuid=inner_repeat_out_uuid,
                output_name="Repeat Results",
            ),
            inner_text_uuid,
        ),

        # Format row: title<FS>attendeeData<RS>
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": row_text,
            },
        },

        # End Outer Repeat
        _repeat_each_end(outer_group_uuid, outer_repeat_out_uuid),

        # Taint-launder Repeat Results through Text
        _text_action_with_uuid(
            _token_string_param(
                output_uuid=outer_repeat_out_uuid,
                output_name="Repeat Results",
            ),
            text_wrap_uuid,
        ),

        # Output
        _output_action(
            _token_string_param(
                output_uuid=text_wrap_uuid,
                output_name="Text",
            ),
        ),
    ]

    return _build_shortcut_plist(
        SHORTCUT_NAME.format(level=3), actions, accepts_input=True,
    )


def _ri_prop(prop_name: str) -> dict:
    """Repeat Item property attachment value (for use in _text_token_string)."""
    return {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": prop_name,
            "PropertyUserInfo": prop_name,
        }],
    }


def build_level5() -> dict:
    """Level 5: Probe attendee entity for undocumented properties.

    Tests every plausible property name from EventKit + Fantastical:
      identifier, displayString, email (documented)
      type, role, status (EventKit-style)
      participantType, participantRole, participantStatus
      isResource, isRequired, isOptional, isOrganizer

    Single event (first match), loop over attendees, emit all probes per attendee.
    Each attendee line: prop1=val|prop2=val|...
    """
    query_uuid = _uuid()
    get_first_uuid = _uuid()
    attendees_uuid = _uuid()
    group_uuid = _uuid()
    repeat_out_uuid = _uuid()
    text_wrap_uuid = _uuid()

    # All property names to probe
    probe_props = [
        "identifier", "displayString", "email",
        "type", "role", "status",
        "participantType", "participantRole", "participantStatus",
        "isResource", "isRequired", "isOptional", "isOrganizer",
        "Name",
    ]

    # Build text template: "identifier=<val>|displayString=<val>|..."
    attachments = [_ri_prop(p) for p in probe_props]
    parts = []
    for i, prop in enumerate(probe_props):
        if i == 0:
            parts.append(f"{prop}=")
        else:
            parts.append(f"|{prop}=")
    parts.append("")  # trailing
    attendee_text = _text_token_string(parts, attachments)

    actions = [
        *_input_date_query_actions(query_uuid),

        _get_item_from_list_action(
            get_first_uuid, query_uuid,
            "Fantastical Calendar Item", index=1,
        ),

        _fantastical_action(
            "FKRGetAttendeesFromEventIntent",
            attendees_uuid,
            extra_params={
                "calendarItem": _token_string_param(
                    output_uuid=get_first_uuid,
                    output_name="Item from List",
                ),
            },
        ),

        _repeat_each_start(
            _var_attachment(
                var_type="ActionOutput",
                output_uuid=attendees_uuid,
                output_name="Invitees from Event",
            ),
            group_uuid,
        ),

        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": attendee_text,
            },
        },

        _repeat_each_end(group_uuid, repeat_out_uuid),

        _text_action_with_uuid(
            _token_string_param(
                output_uuid=repeat_out_uuid,
                output_name="Repeat Results",
            ),
            text_wrap_uuid,
        ),

        _output_action(
            _token_string_param(
                output_uuid=text_wrap_uuid,
                output_name="Text",
            ),
        ),
    ]

    return _build_shortcut_plist(
        SHORTCUT_NAME.format(level=5), actions, accepts_input=True,
    )


def build_level4() -> dict:
    """Level 4: Raw coercion — what do attendees look like as text?

    Simplified: gets first event only, loops over its attendees,
    coerces each to text via a plain Repeat Item reference (no properties).
    Also tries coercing Repeat Item.Name as a fallback property.

    Flow:
      Input "start|end|title"
        → [_input_date_query_actions]
        → Get Item from List (index=1)
        → FKRGetAttendeesFromEventIntent(calendarItem=above)
        → Repeat Each (over attendees)
          → Text("RAW:" + Repeat Item + "|NAME:" + Repeat Item.Name
                  + "|DISP:" + Repeat Item.displayString
                  + "|EMAIL:" + Repeat Item.email)
        → End Repeat
        → Text(Repeat Results)    ← taint launder
        → Output
    """
    query_uuid = _uuid()
    get_first_uuid = _uuid()
    attendees_uuid = _uuid()
    group_uuid = _uuid()
    repeat_out_uuid = _uuid()
    text_wrap_uuid = _uuid()

    # Repeat Item — plain, no aggrandizements (default coercion)
    ri_raw = {"Type": "Variable", "VariableName": "Repeat Item"}
    # Repeat Item.Name (common default property)
    ri_name = {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": "Name",
            "PropertyUserInfo": "Name",
        }],
    }
    # Repeat Item.displayString
    ri_display = {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": "displayString",
            "PropertyUserInfo": "displayString",
        }],
    }
    # Repeat Item.email
    ri_email = {
        "Type": "Variable",
        "VariableName": "Repeat Item",
        "Aggrandizements": [{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": "email",
            "PropertyUserInfo": "email",
        }],
    }

    attendee_text = _text_token_string(
        ["RAW:", "|NAME:", "|DISP:", "|EMAIL:", ""],
        [ri_raw, ri_name, ri_display, ri_email],
    )

    actions = [
        *_input_date_query_actions(query_uuid),

        _get_item_from_list_action(
            get_first_uuid, query_uuid,
            "Fantastical Calendar Item", index=1,
        ),

        _fantastical_action(
            "FKRGetAttendeesFromEventIntent",
            attendees_uuid,
            extra_params={
                "calendarItem": _token_string_param(
                    output_uuid=get_first_uuid,
                    output_name="Item from List",
                ),
            },
        ),

        _repeat_each_start(
            _var_attachment(
                var_type="ActionOutput",
                output_uuid=attendees_uuid,
                output_name="Invitees from Event",
            ),
            group_uuid,
        ),

        # Text with all property variants
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": attendee_text,
            },
        },

        _repeat_each_end(group_uuid, repeat_out_uuid),

        _text_action_with_uuid(
            _token_string_param(
                output_uuid=repeat_out_uuid,
                output_name="Repeat Results",
            ),
            text_wrap_uuid,
        ),

        _output_action(
            _token_string_param(
                output_uuid=text_wrap_uuid,
                output_name="Text",
            ),
        ),
    ]

    return _build_shortcut_plist(
        SHORTCUT_NAME.format(level=4), actions, accepts_input=True,
    )


# -- Build / sign / import / run machinery --

def _sign(name: str, plist_data: dict) -> Path:
    unsigned = OUTDIR / f".{name}.unsigned.shortcut"
    signed = OUTDIR / f"{name}.shortcut"
    with open(unsigned, "wb") as f:
        plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)
    result = subprocess.run(
        ["shortcuts", "sign", "--mode", "anyone",
         "--input", str(unsigned), "--output", str(signed)],
        capture_output=True, text=True, timeout=120,
    )
    unsigned.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "shortcuts sign failed")
    return signed


def _poll_for_shortcut(name: str, timeout: float = 60) -> bool:
    """Poll `shortcuts list` until the shortcut appears."""
    start = time.time()
    reminded = False
    while time.time() - start < timeout:
        result = subprocess.run(
            ["shortcuts", "list"], capture_output=True, text=True, timeout=10,
        )
        if name in result.stdout:
            return True
        if not reminded and time.time() - start > 5:
            print(f'  (reminder: click "Add Shortcut" in the import dialog)')
            reminded = True
        time.sleep(2)
    return False


def _run_shortcut(name: str, input_text: str) -> tuple[str, int]:
    """Run a shortcut with input text, return (stdout, returncode)."""
    result = subprocess.run(
        ["shortcuts", "run", name, "-i", input_text],
        capture_output=True, text=True, timeout=120,
    )
    return result.stdout, result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 22: attendee intent levels")
    parser.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5], default=1,
                        help="Test level (1=no loop, 2=count, 3=nested, 4=raw, 5=probe props)")
    parser.add_argument("--dump", action="store_true",
                        help="Print plist XML to stdout instead of signing/running")
    parser.add_argument("--input", type=str, default="2026-02-20|2026-02-21|",
                        help="Shortcut input (start|end|title)")
    args = parser.parse_args()

    builders = {1: build_level1, 2: build_level2, 3: build_level3, 4: build_level4, 5: build_level5}
    builder = builders[args.level]
    plist_data = builder()

    if args.dump:
        # XML plist can't encode control characters (FS/RS delimiters),
        # so dump binary then convert with plutil.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".plist", delete=False) as f:
            plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)
            tmp = f.name
        subprocess.run(["plutil", "-convert", "xml1", "-o", "-", tmp], timeout=10)
        Path(tmp).unlink(missing_ok=True)
        return

    name = SHORTCUT_NAME.format(level=args.level)
    print(f"Building Level {args.level}: {name}")

    signed = _sign(name, plist_data)
    print(f"Signed: {signed}")

    print(f"Opening for import...")
    subprocess.run(["open", str(signed)], check=True, timeout=10)

    print(f"Polling for '{name}' in shortcuts list...")
    if not _poll_for_shortcut(name):
        print(f"ERROR: '{name}' not found after 60s. Did you add it?", file=sys.stderr)
        sys.exit(1)
    print(f"Found '{name}' in shortcuts list.")

    print(f"Running: shortcuts run '{name}' -i '{args.input}'")
    stdout, rc = _run_shortcut(name, args.input)
    print(f"\n--- Output (exit code {rc}) ---")
    print(stdout)
    if rc != 0:
        print(f"WARNING: non-zero exit code {rc}", file=sys.stderr)


if __name__ == "__main__":
    main()

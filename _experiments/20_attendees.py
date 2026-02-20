"""Experiment 20: include attendees in CalendarItemQuery output.

Goal:
- Validate that attendees can be fetched without crashing by using
  `FKRGetAttendeesFromEventIntent` ("Get Invitees from Event")
  instead of `Repeat Item.attendees` property aggrandizement.
- Keep the same input format as experiment 19:
  "YYYY-MM-DD|YYYY-MM-DD|titleQuery"

Output fields (0x1F-separated, 0x1E records):
1. title
2. startDate
3. endDate
4. calendarIdentifier
5. fantasticalURL
6. location
7. attendeeCount
8. attendeesData

Run:
  uv run python _experiments/20_attendees.py
  open _experiments/claude-test-attendees.shortcut
  shortcuts run "claude-test-attendees" -i "2026-02-20|2026-02-21|"
"""

from __future__ import annotations

import plistlib
import subprocess
import uuid
from pathlib import Path

BUNDLE = "com.flexibits.fantastical2.mac"
TEAM = "85C27NK92C"
APP_NAME = "Fantastical"

OUTDIR = Path(__file__).parent

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"


def _uuid() -> str:
    return str(uuid.uuid4()).upper()


def _var_attachment(
    *,
    var_type: str = "Variable",
    var_name: str | None = None,
    output_uuid: str | None = None,
    output_name: str | None = None,
    aggrandizements: list[dict] | None = None,
) -> dict:
    value: dict = {"Type": var_type}
    if var_name is not None:
        value["VariableName"] = var_name
    if output_uuid is not None:
        value["OutputUUID"] = output_uuid
    if output_name is not None:
        value["OutputName"] = output_name
    if aggrandizements:
        value["Aggrandizements"] = aggrandizements
    return {"WFSerializationType": "WFTextTokenAttachment", "Value": value}


def _text_token_string(parts: list[str], attachments: list[dict]) -> dict:
    """Build WFTextTokenString with inline attachment references."""
    result = ""
    by_range: dict[str, dict] = {}
    for i, part in enumerate(parts):
        result += part
        if i < len(attachments):
            pos = len(result.encode("utf-16-le")) // 2
            by_range[f"{{{pos}, 1}}"] = attachments[i]
            result += "\ufffc"
    return {
        "WFSerializationType": "WFTextTokenString",
        "Value": {"string": result, "attachmentsByRange": by_range},
    }


def _single_attachment_token(attachment_value: dict) -> dict:
    return _text_token_string(["", ""], [attachment_value])


def _repeat_item_property(prop_name: str) -> dict:
    return _var_attachment(
        var_type="Variable",
        var_name="Repeat Item",
        aggrandizements=[{
            "Type": "WFPropertyVariableAggrandizement",
            "PropertyName": prop_name,
            "PropertyUserInfo": prop_name,
        }],
    )


def _delimited_text_from_attachments(attachments: list[dict]) -> dict:
    parts = [""] + [FIELD_SEPARATOR] * (len(attachments) - 1) + [RECORD_SEPARATOR]
    return _text_token_string(parts, attachments)


def _fantastical_action(intent_id: str, action_uuid: str, extra_params: dict | None = None) -> dict:
    params = {
        "AppIntentDescriptor": {
            "TeamIdentifier": TEAM,
            "BundleIdentifier": BUNDLE,
            "Name": APP_NAME,
            "AppIntentIdentifier": intent_id,
        },
        "ShowWhenRun": False,
        "UUID": action_uuid,
    }
    if extra_params:
        params.update(extra_params)
    return {
        "WFWorkflowActionIdentifier": f"{BUNDLE}.{intent_id}",
        "WFWorkflowActionParameters": params,
    }


def _sign(name: str, plist_data: dict) -> Path:
    """Write and sign shortcut file."""
    unsigned = OUTDIR / f".{name}.unsigned.shortcut"
    signed = OUTDIR / f"{name}.shortcut"

    with open(unsigned, "wb") as f:
        plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)

    result = subprocess.run(
        ["shortcuts", "sign", "--mode", "anyone", "--input", str(unsigned), "--output", str(signed)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    unsigned.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "shortcuts sign failed")
    return signed


def build_attendees_experiment() -> dict:
    """Build query shortcut that appends attendees per event."""
    split_uuid = _uuid()
    get_item1_uuid = _uuid()
    detect1_uuid = _uuid()
    adjust1_uuid = _uuid()
    get_item2_uuid = _uuid()
    detect2_uuid = _uuid()
    adjust2_uuid = _uuid()
    get_item3_uuid = _uuid()
    query_uuid = _uuid()

    outer_group_uuid = _uuid()
    attendees_action_uuid = _uuid()
    attendees_group_uuid = _uuid()
    attendees_repeat_out_uuid = _uuid()
    attendee_count_uuid = _uuid()
    attendees_text_uuid = _uuid()
    outer_repeat_out_uuid = _uuid()
    final_text_wrap_uuid = _uuid()

    # Per-event output: base props + attendee count + attendee payload
    event_attachments = [
        _repeat_item_property("title")["Value"],
        _repeat_item_property("startDate")["Value"],
        _repeat_item_property("endDate")["Value"],
        _repeat_item_property("calendarIdentifier")["Value"],
        _repeat_item_property("fantasticalURL")["Value"],
        _repeat_item_property("location")["Value"],
        _var_attachment(
            var_type="ActionOutput",
            output_uuid=attendee_count_uuid,
            output_name="Count",
        )["Value"],
        _var_attachment(
            var_type="ActionOutput",
            output_uuid=attendees_text_uuid,
            output_name="Text",
        )["Value"],
    ]

    actions = [
        # Split input "start|end|title"
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.text.split",
            "WFWorkflowActionParameters": {
                "UUID": split_uuid,
                "WFTextSeparator": "Custom",
                "WFTextCustomSeparator": "|",
                "text": _var_attachment(var_type="ExtensionInput"),
            },
        },
        # Start date chain
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item1_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 1,
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=split_uuid,
                    output_name="Split Text",
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
            "WFWorkflowActionParameters": {
                "UUID": detect1_uuid,
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=get_item1_uuid,
                    output_name="Item from List",
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.adjustdate",
            "WFWorkflowActionParameters": {
                "UUID": adjust1_uuid,
                "CustomOutputName": "Date",
                "WFDate": _single_attachment_token(
                    _var_attachment(
                        var_type="ActionOutput",
                        output_uuid=detect1_uuid,
                        output_name="Dates",
                    )["Value"],
                ),
                "WFDuration": {
                    "WFSerializationType": "WFQuantityFieldValue",
                    "Value": {"Magnitude": "0", "Unit": "days"},
                },
            },
        },
        # End date chain
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item2_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 2,
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=split_uuid,
                    output_name="Split Text",
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
            "WFWorkflowActionParameters": {
                "UUID": detect2_uuid,
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=get_item2_uuid,
                    output_name="Item from List",
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.adjustdate",
            "WFWorkflowActionParameters": {
                "UUID": adjust2_uuid,
                "WFDate": _single_attachment_token(
                    _var_attachment(
                        var_type="ActionOutput",
                        output_uuid=detect2_uuid,
                        output_name="Dates",
                    )["Value"],
                ),
                "WFDuration": {
                    "WFSerializationType": "WFQuantityFieldValue",
                    "Value": {"Magnitude": "0", "Unit": "days"},
                },
            },
        },
        # Title query input
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item3_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 3,
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=split_uuid,
                    output_name="Split Text",
                ),
            },
        },
        # CalendarItemQuery(startDate between start..end AND title contains query)
        {
            "WFWorkflowActionIdentifier": f"{BUNDLE}.IntentCalendarItem",
            "WFWorkflowActionParameters": {
                "AppIntentDescriptor": {
                    "TeamIdentifier": TEAM,
                    "BundleIdentifier": BUNDLE,
                    "Name": APP_NAME,
                    "AppIntentIdentifier": "IntentCalendarItem",
                    "ActionRequiresAppInstallation": True,
                },
                "UUID": query_uuid,
                "WFContentItemFilter": {
                    "WFSerializationType": "WFContentPredicateTableTemplate",
                    "Value": {
                        "WFActionParameterFilterPrefix": 1,
                        "WFContentPredicateBoundedDate": False,
                        "WFActionParameterFilterTemplates": [
                            {
                                "Operator": 1003,
                                "Property": "startDate",
                                "Removable": True,
                                "Values": {
                                    "Unit": 4,
                                    "Date": _var_attachment(
                                        var_type="ActionOutput",
                                        output_uuid=adjust1_uuid,
                                        output_name="Date",
                                    ),
                                    "AnotherDate": _var_attachment(
                                        var_type="ActionOutput",
                                        output_uuid=adjust2_uuid,
                                        output_name="Adjusted Date",
                                    ),
                                },
                            },
                            {
                                "Operator": 99,
                                "Property": "title",
                                "Removable": True,
                                "Values": {
                                    "Unit": 4,
                                    "String": _single_attachment_token(
                                        _var_attachment(
                                            var_type="ActionOutput",
                                            output_uuid=get_item3_uuid,
                                            output_name="Item from List",
                                        )["Value"],
                                    ),
                                },
                            },
                        ],
                    },
                },
            },
        },
        # Repeat each queried event
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 0,
                "GroupingIdentifier": outer_group_uuid,
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=query_uuid,
                    output_name="Fantastical Calendar Item",
                ),
            },
        },
        # Get invitees from current event
        _fantastical_action(
            "FKRGetAttendeesFromEventIntent",
            attendees_action_uuid,
            extra_params={
                "CustomOutputName": "Invitees",
                # Use WFTextTokenAttachment (not token string) to mirror
                # the shape produced by Shortcuts.app after manual edits.
                "calendarItem": _var_attachment(var_type="Variable", var_name="Repeat Item"),
            },
        ),
        # Count invitees for this event
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 0,
                "GroupingIdentifier": attendees_group_uuid,
                # Must bind to previous action output; VariableName="Invitees"
                # becomes an unresolved red token in Shortcuts UI.
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=attendees_action_uuid,
                    output_name="Invitees",
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": _single_attachment_token(
                    _var_attachment(var_type="Variable", var_name="Repeat Item")["Value"],
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 2,
                "GroupingIdentifier": attendees_group_uuid,
                "UUID": attendees_repeat_out_uuid,
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.count",
            "WFWorkflowActionParameters": {
                "UUID": attendee_count_uuid,
                # Count action reads "Input" in UI and may ignore WFInput-only
                # references. Keep both keys in sync.
                "Input": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=attendees_repeat_out_uuid,
                    output_name="Repeat Results",
                ),
                "WFInput": _var_attachment(
                    var_type="ActionOutput",
                    output_uuid=attendees_repeat_out_uuid,
                    output_name="Repeat Results",
                ),
            },
        },
        # Flatten attendee repeat output into one text field
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": attendees_text_uuid,
                "WFTextActionText": _single_attachment_token(
                    _var_attachment(
                        var_type="ActionOutput",
                        output_uuid=attendees_repeat_out_uuid,
                        output_name="Repeat Results",
                    )["Value"],
                ),
            },
        },
        # Emit event record
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": _delimited_text_from_attachments(event_attachments),
            },
        },
        # End outer repeat
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 2,
                "GroupingIdentifier": outer_group_uuid,
                "UUID": outer_repeat_out_uuid,
            },
        },
        # Taint-launder repeat results before output
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": final_text_wrap_uuid,
                "WFTextActionText": _single_attachment_token(
                    _var_attachment(
                        var_type="ActionOutput",
                        output_uuid=outer_repeat_out_uuid,
                        output_name="Repeat Results",
                    )["Value"],
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.output",
            "WFWorkflowActionParameters": {
                "WFOutput": _single_attachment_token(
                    _var_attachment(
                        var_type="ActionOutput",
                        output_uuid=final_text_wrap_uuid,
                        output_name="Text",
                    )["Value"],
                ),
            },
        },
    ]

    return {
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowClientVersion": "4046.0.2.2",
        "WFWorkflowIcon": {
            "WFWorkflowIconStartColor": 4282601983,
            "WFWorkflowIconGlyphNumber": 59511,
        },
        "WFWorkflowActions": actions,
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowOutputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowTypes": [],
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowImportQuestions": [],
        "WFQuickActionSurfaces": [],
        "WFWorkflowHasShortcutInputVariables": True,
    }


def main() -> None:
    name = "claude-test-attendees"
    plist_data = build_attendees_experiment()
    signed = _sign(name, plist_data)
    print(f"Built and signed: {signed}")
    print("Import with: open _experiments/claude-test-attendees.shortcut")
    print('Then run: shortcuts run "claude-test-attendees" -i "2026-02-20|2026-02-21|"')


if __name__ == "__main__":
    main()

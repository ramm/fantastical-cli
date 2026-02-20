"""Experiment 21: determine the correct Invitees variable binding.

Builds a test shortcut that, for each queried calendar item:
1) runs "Get invitees from Repeat Item"
2) computes 4 counts using different input reference encodings
3) outputs title + the 4 counts

Output fields:
1. title
2. count_action_output_named   (ActionOutput + OutputName="Invitees")
3. count_action_output_uuid    (ActionOutput + OutputUUID only)
4. count_variable_invitees     (VariableName="Invitees")
5. count_variable_invitees_evt (VariableName="Invitees from Event")
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


def _single_attachment_token(att: dict) -> dict:
    return _text_token_string(["", ""], [att])


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
    return _text_token_string(
        [""] + [FIELD_SEPARATOR] * (len(attachments) - 1) + [RECORD_SEPARATOR],
        attachments,
    )


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
    unsigned = OUTDIR / f".{name}.unsigned.shortcut"
    signed = OUTDIR / f"{name}.shortcut"
    with open(unsigned, "wb") as f:
        plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)
    result = subprocess.run(
        ["shortcuts", "sign", "--mode", "anyone", "--input", str(unsigned), "--output", str(signed)],
        capture_output=True, text=True, timeout=120,
    )
    unsigned.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "shortcuts sign failed")
    return signed


def build_ref_test() -> dict:
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
    get_invitees_uuid = _uuid()
    count1_uuid = _uuid()
    count2_uuid = _uuid()
    count3_uuid = _uuid()
    count4_uuid = _uuid()
    outer_repeat_out_uuid = _uuid()
    wrap_uuid = _uuid()

    event_attachments = [
        _repeat_item_property("title")["Value"],
        _var_attachment(var_type="ActionOutput", output_uuid=count1_uuid, output_name="Count")["Value"],
        _var_attachment(var_type="ActionOutput", output_uuid=count2_uuid, output_name="Count")["Value"],
        _var_attachment(var_type="ActionOutput", output_uuid=count3_uuid, output_name="Count")["Value"],
        _var_attachment(var_type="ActionOutput", output_uuid=count4_uuid, output_name="Count")["Value"],
    ]

    actions = [
        # input split
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.text.split",
            "WFWorkflowActionParameters": {
                "UUID": split_uuid,
                "WFTextSeparator": "Custom",
                "WFTextCustomSeparator": "|",
                "text": _var_attachment(var_type="ExtensionInput"),
            },
        },
        # start date
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item1_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 1,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=split_uuid, output_name="Split Text"),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
            "WFWorkflowActionParameters": {
                "UUID": detect1_uuid,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=get_item1_uuid, output_name="Item from List"),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.adjustdate",
            "WFWorkflowActionParameters": {
                "UUID": adjust1_uuid,
                "CustomOutputName": "Date",
                "WFDate": _single_attachment_token(
                    _var_attachment(var_type="ActionOutput", output_uuid=detect1_uuid, output_name="Dates")["Value"],
                ),
                "WFDuration": {"WFSerializationType": "WFQuantityFieldValue", "Value": {"Magnitude": "0", "Unit": "days"}},
            },
        },
        # end date
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item2_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 2,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=split_uuid, output_name="Split Text"),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
            "WFWorkflowActionParameters": {
                "UUID": detect2_uuid,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=get_item2_uuid, output_name="Item from List"),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.adjustdate",
            "WFWorkflowActionParameters": {
                "UUID": adjust2_uuid,
                "WFDate": _single_attachment_token(
                    _var_attachment(var_type="ActionOutput", output_uuid=detect2_uuid, output_name="Dates")["Value"],
                ),
                "WFDuration": {"WFSerializationType": "WFQuantityFieldValue", "Value": {"Magnitude": "0", "Unit": "days"}},
            },
        },
        # title query
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item3_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 3,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=split_uuid, output_name="Split Text"),
            },
        },
        # query
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
                                    "Date": _var_attachment(var_type="ActionOutput", output_uuid=adjust1_uuid, output_name="Date"),
                                    "AnotherDate": _var_attachment(var_type="ActionOutput", output_uuid=adjust2_uuid, output_name="Adjusted Date"),
                                },
                            },
                            {
                                "Operator": 99,
                                "Property": "title",
                                "Removable": True,
                                "Values": {
                                    "Unit": 4,
                                    "String": _single_attachment_token(
                                        _var_attachment(var_type="ActionOutput", output_uuid=get_item3_uuid, output_name="Item from List")["Value"],
                                    ),
                                },
                            },
                        ],
                    },
                },
            },
        },
        # outer repeat
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 0,
                "GroupingIdentifier": outer_group_uuid,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=query_uuid, output_name="Fantastical Calendar Item"),
            },
        },
        _fantastical_action(
            "FKRGetAttendeesFromEventIntent",
            get_invitees_uuid,
            extra_params={
                "CustomOutputName": "Invitees",
                "calendarItem": _single_attachment_token(
                    _var_attachment(var_type="Variable", var_name="Repeat Item")["Value"],
                ),
            },
        ),
        # count 1: ActionOutput + OutputName
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.count",
            "WFWorkflowActionParameters": {
                "UUID": count1_uuid,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=get_invitees_uuid, output_name="Invitees"),
            },
        },
        # count 2: ActionOutput UUID only
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.count",
            "WFWorkflowActionParameters": {
                "UUID": count2_uuid,
                "WFInput": _var_attachment(var_type="ActionOutput", output_uuid=get_invitees_uuid),
            },
        },
        # count 3: Variable Invitees
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.count",
            "WFWorkflowActionParameters": {
                "UUID": count3_uuid,
                "WFInput": _var_attachment(var_type="Variable", var_name="Invitees"),
            },
        },
        # count 4: Variable Invitees from Event
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.count",
            "WFWorkflowActionParameters": {
                "UUID": count4_uuid,
                "WFInput": _var_attachment(var_type="Variable", var_name="Invitees from Event"),
            },
        },
        # emit row
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": _delimited_text_from_attachments(event_attachments),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 2,
                "GroupingIdentifier": outer_group_uuid,
                "UUID": outer_repeat_out_uuid,
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": wrap_uuid,
                "WFTextActionText": _single_attachment_token(
                    _var_attachment(var_type="ActionOutput", output_uuid=outer_repeat_out_uuid, output_name="Repeat Results")["Value"],
                ),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.output",
            "WFWorkflowActionParameters": {
                "WFOutput": _single_attachment_token(
                    _var_attachment(var_type="ActionOutput", output_uuid=wrap_uuid, output_name="Text")["Value"],
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
    name = "claude-test-attendees-refs"
    path = _sign(name, build_ref_test())
    print(f"Built and signed: {path}")
    print("Import with: open _experiments/claude-test-attendees-refs.shortcut")
    print('Run with: shortcuts run "claude-test-attendees-refs" -i "2026-02-20|2026-02-21|"')


if __name__ == "__main__":
    main()

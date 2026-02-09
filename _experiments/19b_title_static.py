"""Test CalendarItemQuery title contains filter with STATIC string.

Isolates the filter format question from variable binding.
Tries three variants of the Values structure for "title contains":

  Variant A: Values.string = "holiday"  (plain string)
  Variant B: Values.Value  = "holiday"  (different key)
  Variant C: no Values wrapper, just String key at filter level

Only one is generated at a time — edit VARIANT below to switch.

Run: uv run python _experiments/19b_title_static.py
Then: shortcuts run "claude-test-title-static" -i "2026-01-01|2026-03-15"
"""
import plistlib
import subprocess
import uuid
from pathlib import Path

BUNDLE = "com.flexibits.fantastical2.mac"
TEAM = "85C27NK92C"

OUTPUT_PROPS = ["title", "startDate", "endDate", "calendarIdentifier", "fantasticalURL"]

OUTDIR = Path(__file__).parent

# --- Which Values format variant to test ---
VARIANT = "E"


def _uuid():
    return str(uuid.uuid4()).upper()


def _sign(name, plist_data):
    unsigned = OUTDIR / f".{name}_unsigned.shortcut"
    signed = OUTDIR / f"{name}.shortcut"
    with open(unsigned, "wb") as f:
        plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)
    result = subprocess.run(
        ["shortcuts", "sign", "--mode", "anyone",
         "--input", str(unsigned), "--output", str(signed)],
        capture_output=True, text=True, timeout=120,
    )
    unsigned.unlink(missing_ok=True)
    if result.returncode == 0:
        print(f"  OK: {signed}")
    else:
        print(f"  FAIL: {result.stderr}")
    return signed


def _build_text_template(props):
    sep = "\x1f"
    record_end = "\x1e"
    result_str = ""
    by_range = {}
    for i, prop in enumerate(props):
        if i > 0:
            result_str += sep
        pos = len(result_str.encode("utf-16-le")) // 2
        by_range[f"{{{pos}, 1}}"] = {
            "Type": "Variable",
            "VariableName": "Repeat Item",
            "Aggrandizements": [{
                "Type": "WFPropertyVariableAggrandizement",
                "PropertyName": prop,
                "PropertyUserInfo": prop,
            }],
        }
        result_str += "\ufffc"
    result_str += record_end
    return {
        "WFSerializationType": "WFTextTokenString",
        "Value": {"string": result_str, "attachmentsByRange": by_range},
    }


def _repeat_output_actions(query_uuid, props):
    group_uuid = _uuid()
    repeat_out_uuid = _uuid()
    text_wrap_uuid = _uuid()
    return [
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 0,
                "GroupingIdentifier": group_uuid,
                "WFInput": {
                    "WFSerializationType": "WFTextTokenAttachment",
                    "Value": {
                        "Type": "ActionOutput",
                        "OutputUUID": query_uuid,
                        "OutputName": "Fantastical Calendar Item",
                    },
                },
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": _build_text_template(props),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
            "WFWorkflowActionParameters": {
                "WFControlFlowMode": 2,
                "GroupingIdentifier": group_uuid,
                "UUID": repeat_out_uuid,
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": {
                    "WFSerializationType": "WFTextTokenString",
                    "Value": {
                        "string": "\ufffc",
                        "attachmentsByRange": {
                            "{0, 1}": {
                                "OutputUUID": repeat_out_uuid,
                                "Type": "ActionOutput",
                                "OutputName": "Repeat Results",
                            },
                        },
                    },
                },
                "UUID": text_wrap_uuid,
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.output",
            "WFWorkflowActionParameters": {
                "WFOutput": {
                    "WFSerializationType": "WFTextTokenString",
                    "Value": {
                        "string": "\ufffc",
                        "attachmentsByRange": {
                            "{0, 1}": {
                                "OutputUUID": text_wrap_uuid,
                                "Type": "ActionOutput",
                                "OutputName": "Text",
                            },
                        },
                    },
                },
            },
        },
    ]


def _title_filter_template(variant):
    """Return the title filter dict for CalendarItemQuery."""
    if variant == "A":
        # Values.string = plain string
        return {
            "Operator": 6,
            "Property": "title",
            "Removable": True,
            "Values": {
                "string": "holiday",
            },
        }
    elif variant == "B":
        # Values.Value = plain string
        return {
            "Operator": 6,
            "Property": "title",
            "Removable": True,
            "Values": {
                "Value": "holiday",
            },
        }
    elif variant == "C":
        # String at filter level (no Values wrapper)
        return {
            "Operator": 6,
            "Property": "title",
            "Removable": True,
            "String": "holiday",
        }
    elif variant == "D":
        # Extracted from Shortcuts.app: Operator 99, Values.String, Values.Unit
        return {
            "Operator": 99,
            "Property": "title",
            "Removable": True,
            "Values": {
                "Unit": 4,
                "String": "holiday",
            },
        }
    elif variant == "E":
        # Empty string — does "title contains ''" match everything?
        return {
            "Operator": 99,
            "Property": "title",
            "Removable": True,
            "Values": {
                "Unit": 4,
                "String": "",
            },
        }
    else:
        raise ValueError(f"Unknown variant: {variant}")


def build_static_title():
    """Input: "YYYY-MM-DD|YYYY-MM-DD" (same as experiment 18, no title in input)."""
    split_uuid = _uuid()
    get_item1_uuid = _uuid()
    detect1_uuid = _uuid()
    adjust1_uuid = _uuid()
    get_item2_uuid = _uuid()
    detect2_uuid = _uuid()
    adjust2_uuid = _uuid()
    query_uuid = _uuid()

    actions = [
        # Split input on "|"
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.text.split",
            "WFWorkflowActionParameters": {
                "UUID": split_uuid,
                "WFTextSeparator": "Custom",
                "WFTextCustomSeparator": "|",
                "text": {
                    "WFSerializationType": "WFTextTokenAttachment",
                    "Value": {"Type": "ExtensionInput"},
                },
            },
        },

        # Start date chain
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item1_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 1,
                "WFInput": {
                    "WFSerializationType": "WFTextTokenAttachment",
                    "Value": {
                        "Type": "ActionOutput",
                        "OutputUUID": split_uuid,
                        "OutputName": "Split Text",
                    },
                },
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
            "WFWorkflowActionParameters": {
                "UUID": detect1_uuid,
                "WFInput": {
                    "WFSerializationType": "WFTextTokenAttachment",
                    "Value": {
                        "Type": "ActionOutput",
                        "OutputUUID": get_item1_uuid,
                        "OutputName": "Item from List",
                    },
                },
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.adjustdate",
            "WFWorkflowActionParameters": {
                "UUID": adjust1_uuid,
                "CustomOutputName": "Date",
                "WFDate": {
                    "Value": {
                        "attachmentsByRange": {
                            "{0, 1}": {
                                "OutputName": "Dates",
                                "OutputUUID": detect1_uuid,
                                "Type": "ActionOutput",
                            },
                        },
                        "string": "\ufffc",
                    },
                    "WFSerializationType": "WFTextTokenString",
                },
                "WFDuration": {
                    "Value": {"Magnitude": "0", "Unit": "days"},
                    "WFSerializationType": "WFQuantityFieldValue",
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
                "WFInput": {
                    "WFSerializationType": "WFTextTokenAttachment",
                    "Value": {
                        "Type": "ActionOutput",
                        "OutputUUID": split_uuid,
                        "OutputName": "Split Text",
                    },
                },
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
            "WFWorkflowActionParameters": {
                "UUID": detect2_uuid,
                "WFInput": {
                    "WFSerializationType": "WFTextTokenAttachment",
                    "Value": {
                        "Type": "ActionOutput",
                        "OutputUUID": get_item2_uuid,
                        "OutputName": "Item from List",
                    },
                },
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.adjustdate",
            "WFWorkflowActionParameters": {
                "UUID": adjust2_uuid,
                "WFDate": {
                    "Value": {
                        "attachmentsByRange": {
                            "{0, 1}": {
                                "OutputName": "Dates",
                                "OutputUUID": detect2_uuid,
                                "Type": "ActionOutput",
                            },
                        },
                        "string": "\ufffc",
                    },
                    "WFSerializationType": "WFTextTokenString",
                },
                "WFDuration": {
                    "Value": {"Magnitude": "0", "Unit": "days"},
                    "WFSerializationType": "WFQuantityFieldValue",
                },
            },
        },

        # CalendarItemQuery with date range + static title filter
        {
            "WFWorkflowActionIdentifier": f"{BUNDLE}.IntentCalendarItem",
            "WFWorkflowActionParameters": {
                "AppIntentDescriptor": {
                    "ActionRequiresAppInstallation": True,
                    "AppIntentIdentifier": "IntentCalendarItem",
                    "BundleIdentifier": BUNDLE,
                    "Name": "Fantastical",
                    "TeamIdentifier": TEAM,
                },
                "UUID": query_uuid,
                "WFContentItemFilter": {
                    "WFSerializationType": "WFContentPredicateTableTemplate",
                    "Value": {
                        "WFActionParameterFilterPrefix": 1,
                        "WFContentPredicateBoundedDate": False,
                        "WFActionParameterFilterTemplates": [
                            # Date filter
                            {
                                "Operator": 1003,
                                "Property": "startDate",
                                "Removable": True,
                                "Values": {
                                    "Unit": 4,
                                    "Date": {
                                        "WFSerializationType": "WFTextTokenAttachment",
                                        "Value": {
                                            "OutputName": "Date",
                                            "OutputUUID": adjust1_uuid,
                                            "Type": "ActionOutput",
                                        },
                                    },
                                    "AnotherDate": {
                                        "WFSerializationType": "WFTextTokenAttachment",
                                        "Value": {
                                            "OutputName": "Adjusted Date",
                                            "OutputUUID": adjust2_uuid,
                                            "Type": "ActionOutput",
                                        },
                                    },
                                },
                            },
                            # Title filter (variant-dependent)
                            _title_filter_template(VARIANT),
                        ],
                    },
                },
            },
        },

        *_repeat_output_actions(query_uuid, OUTPUT_PROPS),
    ]

    return {
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "4046.0.2.2",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59511,
            "WFWorkflowIconStartColor": 4282601983,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowOutputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowTypes": [],
    }


if __name__ == "__main__":
    print(f"=== Experiment 19b: Static title filter — Variant {VARIANT} ===")
    print()

    plist = build_static_title()
    signed = _sign("claude-test-title-static", plist)

    print()
    print(f"Variant {VARIANT}: {_title_filter_template(VARIANT)}")
    print()
    print("=== Test ===")
    print('shortcuts run "claude-test-title-static" -i "2026-01-01|2026-03-15"')
    print()
    print("Expected: only events with 'holiday' in title")
    print()
    print("If no results or all results, change VARIANT and re-run.")

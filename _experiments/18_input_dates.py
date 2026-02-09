"""Test passing date range as shortcut input for CalendarItemQuery.

The production shortcut hardcodes ±14 days from Current Date. This experiment
tests receiving start/end dates as input text and wiring them into the
CalendarItemQuery filter via the proven Adjust Date laundering pattern.

Shortcut flow:
  Input: "2026-02-01|2026-02-15" via -i
    → Split Text on "|" (Custom separator)
    → Get Item At Index 1 → Detect Dates → Adjust Date +0d
    → Get Item At Index 2 → Detect Dates → Adjust Date +0d
    → CalendarItemQuery(startDate between adj1..adj2)
    → Repeat → Text → Text wrap → Output

Key findings:
- Split Text: WFTextSeparator="Custom" + WFTextCustomSeparator="|"
  (setting WFTextSeparator directly to "|" is ignored)
- Get Item from List: WFItemSpecifier="Item At Index" + WFItemIndex (1-based).
  WFGetItemType (integer) is silently ignored.
- CalendarItemQuery filter only works with Adjust Date action outputs
  (proven in experiments 12-16). The +0 day adjustment launders the
  Detect Dates output into the required format.

Run: uv run python _experiments/18_input_dates.py
Then: shortcuts run "claude-test-input" -i "2026-02-01|2026-02-15"

On failure, check logs:
  /usr/bin/log show --last 2m --predicate 'process == "BackgroundShortcutRunner"' --style compact
"""
import plistlib
import subprocess
import uuid
from pathlib import Path

BUNDLE = "com.flexibits.fantastical2.mac"
TEAM = "85C27NK92C"

OUTPUT_PROPS = ["title", "startDate", "endDate", "calendarIdentifier", "fantasticalURL"]

OUTDIR = Path(__file__).parent


def _uuid():
    return str(uuid.uuid4()).upper()


def _sign(name, plist_data):
    """Write, sign, and return path to signed shortcut."""
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
    """Build pipe-delimited WFTextTokenString for Repeat Item properties."""
    sep = " | "
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
    """Build Repeat Each → Text → Text wrap → End Repeat → Output actions."""
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


def build_input_dates():
    """Build shortcut that receives dates as input and uses them in query.

    Flow:
      Input "2026-02-01|2026-02-15"
        → Split Text on "|" (Custom separator)
        → Get Item At Index 1 → Detect Dates → Adjust Date +0d (start)
        → Get Item At Index 2 → Detect Dates → Adjust Date +0d (end)
        → CalendarItemQuery(startDate between start..end)
        → output pipeline
    """
    split_uuid = _uuid()
    get_item1_uuid = _uuid()
    detect1_uuid = _uuid()
    adjust1_uuid = _uuid()
    get_item2_uuid = _uuid()
    detect2_uuid = _uuid()
    adjust2_uuid = _uuid()
    query_uuid = _uuid()

    actions = [
        # 1. Split Text: split Shortcut Input on "|"
        #    WFTextSeparator="Custom" + WFTextCustomSeparator="|"
        #    (setting WFTextSeparator directly to "|" is silently ignored)
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

        # 2. Get Item At Index 1 from split list (start date string)
        #    WFItemSpecifier="Item At Index" + WFItemIndex (1-based)
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

        # 3. Detect Dates from item 1
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

        # 4. Adjust Date: add 0 days to detected start date
        #    Launders into format CalendarItemQuery filter accepts
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
                    "Value": {
                        "Magnitude": "0",
                        "Unit": "days",
                    },
                    "WFSerializationType": "WFQuantityFieldValue",
                },
            },
        },

        # 5. Get Item At Index 2 from split list (end date string)
        #    WFItemSpecifier="Item At Index" + WFItemIndex (1-based)
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

        # 6. Detect Dates from item 2
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

        # 7. Adjust Date: add 0 days to detected end date
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
                    "Value": {
                        "Magnitude": "0",
                        "Unit": "days",
                    },
                    "WFSerializationType": "WFQuantityFieldValue",
                },
            },
        },

        # 8. CalendarItemQuery with dynamic date filter
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
                        ],
                    },
                },
            },
        },

        # 9-13. Repeat → Text → End Repeat → Text wrap → Output
        *_repeat_output_actions(query_uuid, OUTPUT_PROPS),
    ]

    return {
        "WFQuickActionSurfaces": [],
        "WFWorkflowActions": actions,
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
    print("=== Experiment 18: Input dates for CalendarItemQuery ===")
    print()

    plist = build_input_dates()
    _sign("claude-test-input", plist)

    print()
    print("=== Test commands ===")
    print('shortcuts run "claude-test-input" -i "2026-02-01|2026-02-15"')
    print()
    print("On failure, check logs:")
    print('/usr/bin/log show --last 2m --predicate \'process == "BackgroundShortcutRunner"\' --style compact')

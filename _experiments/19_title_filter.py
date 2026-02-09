"""Test CalendarItemQuery with title contains filter.

Goal: determine if we can combine date range + title filter in a single
CalendarItemQuery, enabling one universal shortcut for both list and search.

Questions to answer:
1. Does `title contains "holiday"` work as a second filter template?
2. Does `title contains ""` (empty string) match everything (= no-op)?
3. Does input-driven title variable work in the filter Values?

Input format: "YYYY-MM-DD|YYYY-MM-DD|titleQuery"
  - Item 1: start date
  - Item 2: end date
  - Item 3: title query (may be empty)

Shortcut flow:
  Input "2026-01-01|2026-03-15|holiday"
    → Split Text on "|"
    → Get Item 1 → Detect Dates → Adjust Date +0d (start)
    → Get Item 2 → Detect Dates → Adjust Date +0d (end)
    → Get Item 3 (title query text — no date detection needed)
    → CalendarItemQuery(startDate between adj1..adj2 AND title contains item3)
    → Repeat Each → delimited text → Text wrap → Output

Run: uv run python _experiments/19_title_filter.py
Then:
  # With title filter:
  shortcuts run "claude-test-title-filter" -i "2026-01-01|2026-03-15|holiday"
  # Empty title (should return all events in range):
  shortcuts run "claude-test-title-filter" -i "2026-01-01|2026-03-15|"
  # Compare baseline (no title filter, experiment 18):
  shortcuts run "claude-test-input" -i "2026-01-01|2026-03-15"
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
    """Build delimited WFTextTokenString for Repeat Item properties."""
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


def build_title_filter():
    """Build shortcut with date range + title contains filter.

    Input: "YYYY-MM-DD|YYYY-MM-DD|titleQuery"
    Split on "|" gives 3 items:
      1 = start date, 2 = end date, 3 = title query
    """
    split_uuid = _uuid()
    get_item1_uuid = _uuid()
    detect1_uuid = _uuid()
    adjust1_uuid = _uuid()
    get_item2_uuid = _uuid()
    detect2_uuid = _uuid()
    adjust2_uuid = _uuid()
    get_item3_uuid = _uuid()  # title query
    query_uuid = _uuid()

    actions = [
        # 1. Split input on "|"
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

        # --- Start date chain (item 1) ---
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

        # --- End date chain (item 2) ---
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

        # --- Title query (item 3) — just get the text, no date detection ---
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
            "WFWorkflowActionParameters": {
                "UUID": get_item3_uuid,
                "WFItemSpecifier": "Item At Index",
                "WFItemIndex": 3,
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

        # --- CalendarItemQuery with BOTH date range AND title contains ---
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
                        "WFActionParameterFilterPrefix": 1,  # AND
                        "WFContentPredicateBoundedDate": False,
                        "WFActionParameterFilterTemplates": [
                            # Filter 1: startDate between adj1..adj2
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
                            # Filter 2: title contains <item3>
                            # Operator 99 = "contains" (from Shortcuts.app plist extraction)
                            # Values.String = WFTextTokenString referencing Get Item 3
                            # Values.Unit = 4 (required alongside String)
                            {
                                "Operator": 99,
                                "Property": "title",
                                "Removable": True,
                                "Values": {
                                    "Unit": 4,
                                    "String": {
                                        "WFSerializationType": "WFTextTokenString",
                                        "Value": {
                                            "string": "\ufffc",
                                            "attachmentsByRange": {
                                                "{0, 1}": {
                                                    "OutputUUID": get_item3_uuid,
                                                    "Type": "ActionOutput",
                                                    "OutputName": "Item from List",
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        },

        # --- Output pipeline ---
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
    print("=== Experiment 19: CalendarItemQuery with title contains filter ===")
    print()

    plist = build_title_filter()
    _sign("claude-test-title-filter", plist)

    print()
    print("=== Test commands ===")
    print()
    print("# Test 1: title filter with a known match")
    print('shortcuts run "claude-test-title-filter" -i "2026-01-01|2026-03-15|holiday"')
    print()
    print("# Test 2: empty title (should return ALL events in range)")
    print('shortcuts run "claude-test-title-filter" -i "2026-01-01|2026-03-15|"')
    print()
    print("# Test 3: compare with experiment 18 baseline (no title filter)")
    print('shortcuts run "claude-test-input" -i "2026-01-01|2026-03-15"')
    print()
    print("On failure, check logs:")
    print('/usr/bin/log show --last 2m --predicate \'process == "BackgroundShortcutRunner"\' --style compact')

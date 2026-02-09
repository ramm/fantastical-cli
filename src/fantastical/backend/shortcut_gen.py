"""Generate and import .shortcut plist files for Fantastical App Intents.

Key format discoveries:
- App Intent parameters must use WFTextTokenString encoding (string +
  attachmentsByRange), NOT WFTextTokenAttachment.
- Dynamic dates in CalendarItemQuery filters ARE possible using Adjust Date
  actions with WFTextTokenAttachment refs in Values.Date/AnotherDate.
  Critical: WFDuration must use STRING values (Magnitude="14", Unit="days"),
  not integers. Discovered by extracting a working plist from Shortcuts.app.
"""

from __future__ import annotations

import plistlib
import subprocess
import tempfile
import uuid
from pathlib import Path

# Fantastical app identifiers (from codesign -d --verbose=2)
FANTASTICAL_BUNDLE_ID = "com.flexibits.fantastical2.mac"
FANTASTICAL_TEAM_ID = "85C27NK92C"
FANTASTICAL_APP_NAME = "Fantastical"


def _uuid() -> str:
    return str(uuid.uuid4()).upper()


def _app_intent_descriptor(intent_id: str) -> dict:
    """Build the AppIntentDescriptor dict for a Fantastical intent."""
    return {
        "AppIntentDescriptor": {
            "TeamIdentifier": FANTASTICAL_TEAM_ID,
            "BundleIdentifier": FANTASTICAL_BUNDLE_ID,
            "Name": FANTASTICAL_APP_NAME,
            "AppIntentIdentifier": intent_id,
        }
    }


def _var_attachment(*, var_type: str = "Variable", var_name: str | None = None,
                    output_uuid: str | None = None, output_name: str | None = None,
                    aggrandizements: list | None = None) -> dict:
    """Build a WFTextTokenAttachment variable reference.

    Used for action inputs like Repeat Each's WFInput that take a single variable.
    NOT for App Intent parameters — use _token_string_param for those.
    """
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


def _token_string_param(*, output_uuid: str, output_name: str,
                          var_type: str = "ActionOutput") -> dict:
    """Build a WFTextTokenString parameter for an App Intent action.

    App Intent parameters MUST use this format (not WFTextTokenAttachment).
    The value is a single \ufffc character with one attachment at {0, 1}.
    """
    return {
        "WFSerializationType": "WFTextTokenString",
        "Value": {
            "string": "\ufffc",
            "attachmentsByRange": {
                "{0, 1}": {
                    "OutputUUID": output_uuid,
                    "Type": var_type,
                    "OutputName": output_name,
                },
            },
        },
    }


def _property_aggrandizement(prop_name: str) -> dict:
    """Build a property access aggrandizement."""
    return {
        "Type": "WFPropertyVariableAggrandizement",
        "PropertyName": prop_name,
        "PropertyUserInfo": prop_name,
    }


def _repeat_item_property(prop_name: str) -> dict:
    """Reference to Repeat Item.<property>."""
    return _var_attachment(
        var_type="Variable",
        var_name="Repeat Item",
        aggrandizements=[_property_aggrandizement(prop_name)],
    )


def _text_token_string(template_parts: list[str], attachments: list[dict]) -> dict:
    """Build a WFTextTokenString with inline variable references.

    template_parts: list of literal string segments (one more than attachments)
    attachments: list of Attachment Value dicts (same format as _var_attachment Value)
    """
    # Build string with \ufffc placeholders
    result_str = ""
    by_range: dict = {}
    for i, part in enumerate(template_parts):
        result_str += part
        if i < len(attachments):
            # Position is UTF-16 offset of the \ufffc character
            pos = len(result_str.encode("utf-16-le")) // 2
            by_range[f"{{{pos}, 1}}"] = attachments[i]
            result_str += "\ufffc"

    return {
        "WFSerializationType": "WFTextTokenString",
        "Value": {
            "string": result_str,
            "attachmentsByRange": by_range,
        },
    }


RECORD_SEPARATOR = "\x1e"


def _pipe_delimited_text(prop_names: list[str]) -> dict:
    """Build a WFTextTokenString for pipe-delimited Repeat Item properties.

    E.g. for ["title", "startDate", "endDate"]:
      Repeat Item.title | Repeat Item.startDate | Repeat Item.endDate\x1e

    Each record ends with ASCII Record Separator (0x1E) so the parser
    can distinguish record boundaries from newlines within fields
    (e.g., multi-line locations or attendee lists).
    """
    # Template parts: ["", " | ", " | ", ..., "\x1e"]
    # Empty before first, " | " between each, record separator after last
    parts = [""] + [" | "] * (len(prop_names) - 1) + [RECORD_SEPARATOR]
    attachments = [
        _repeat_item_property(p)["Value"] for p in prop_names
    ]
    return _text_token_string(parts, attachments)


def _fantastical_action(intent_id: str, action_uuid: str,
                         extra_params: dict | None = None) -> dict:
    """Build a Fantastical App Intent action."""
    params = {
        **_app_intent_descriptor(intent_id),
        "ShowWhenRun": False,
        "UUID": action_uuid,
    }
    if extra_params:
        params.update(extra_params)
    return {
        "WFWorkflowActionIdentifier": f"{FANTASTICAL_BUNDLE_ID}.{intent_id}",
        "WFWorkflowActionParameters": params,
    }


def _detect_date_action(action_uuid: str, *,
                        source_uuid: str | None = None,
                        source_output_name: str | None = None) -> dict:
    """Build a Date Detection action.

    By default reads from Shortcut Input (ExtensionInput).
    If source_uuid/source_output_name are given, reads from that action's output.
    """
    if source_uuid and source_output_name:
        input_ref: dict = {
            "Value": {
                "Type": "ActionOutput",
                "OutputUUID": source_uuid,
                "OutputName": source_output_name,
            },
            "WFSerializationType": "WFTextTokenAttachment",
        }
    else:
        input_ref = {
            "Value": {
                "Type": "ExtensionInput",
            },
            "WFSerializationType": "WFTextTokenAttachment",
        }
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
        "WFWorkflowActionParameters": {
            "WFInput": input_ref,
            "UUID": action_uuid,
        },
    }


def _split_text_action(action_uuid: str, separator: str = "|") -> dict:
    """Build a Split Text action that splits Shortcut Input on a separator.

    Uses WFTextSeparator="Custom" + WFTextCustomSeparator for the actual
    separator string. Setting WFTextSeparator directly to the separator
    character is silently ignored by the Shortcuts runtime.
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.text.split",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFTextSeparator": "Custom",
            "WFTextCustomSeparator": separator,
            "text": {
                "WFSerializationType": "WFTextTokenAttachment",
                "Value": {"Type": "ExtensionInput"},
            },
        },
    }


def _get_item_from_list_action(action_uuid: str, source_uuid: str,
                                source_output_name: str,
                                index: int) -> dict:
    """Build a Get Item from List action that gets a specific item by index.

    Args:
        action_uuid: UUID for this action.
        source_uuid: UUID of the action providing the list.
        source_output_name: OutputName of the source action.
        index: 1-based index of the item to get.

    Uses WFItemSpecifier="Item At Index" + WFItemIndex. The specifier MUST
    be a string — WFGetItemType (integer) is silently ignored by the runtime.
    Valid WFItemSpecifier values (confirmed via Cherri source + experiment 18):
      "First Item", "Last Item", "Random Item",
      "Item At Index" (+ WFItemIndex), "Items in Range" (+ WFItemRangeStart/End)
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.getitemfromlist",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFItemSpecifier": "Item At Index",
            "WFItemIndex": index,
            "WFInput": {
                "WFSerializationType": "WFTextTokenAttachment",
                "Value": {
                    "Type": "ActionOutput",
                    "OutputUUID": source_uuid,
                    "OutputName": source_output_name,
                },
            },
        },
    }


def _repeat_each_start(input_ref: dict, group_uuid: str) -> dict:
    """Build the start of a Repeat with Each block."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
        "WFWorkflowActionParameters": {
            "WFControlFlowMode": 0,
            "GroupingIdentifier": group_uuid,
            "WFInput": input_ref,
        },
    }


def _repeat_each_end(group_uuid: str, output_uuid: str) -> dict:
    """Build the end of a Repeat with Each block."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.repeat.each",
        "WFWorkflowActionParameters": {
            "WFControlFlowMode": 2,
            "GroupingIdentifier": group_uuid,
            "UUID": output_uuid,
        },
    }


def _if_has_value_start(input_ref: dict, group_uuid: str) -> dict:
    """Build the start of an If block with 'has any value' condition.

    macOS 15+ / iOS 18+ uses WFContentPredicateTableTemplate format
    instead of the flat WFCondition + WFInput parameters.
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "WFControlFlowMode": 0,
            "GroupingIdentifier": group_uuid,
            "WFConditions": {
                "WFSerializationType": "WFContentPredicateTableTemplate",
                "Value": {
                    "WFActionParameterFilterPrefix": 1,
                    "WFActionParameterFilterTemplates": [
                        {
                            "WFCondition": 100,  # "has any value"
                            "WFInput": {
                                "Type": "Variable",
                                "Variable": input_ref,
                            },
                        },
                    ],
                },
            },
        },
    }


def _if_otherwise(group_uuid: str) -> dict:
    """Build the Otherwise branch of an If block."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "WFControlFlowMode": 1,
            "GroupingIdentifier": group_uuid,
        },
    }


def _if_end(group_uuid: str, output_uuid: str) -> dict:
    """Build the End If block."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "WFControlFlowMode": 2,
            "GroupingIdentifier": group_uuid,
            "UUID": output_uuid,
        },
    }


def _text_action(text_content: dict) -> dict:
    """Build a Text action."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
        "WFWorkflowActionParameters": {
            "WFTextActionText": text_content,
        },
    }


def _output_action(output_ref: dict) -> dict:
    """Build a Stop and Output action."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.output",
        "WFWorkflowActionParameters": {
            "WFOutput": output_ref,
        },
    }


def _build_shortcut_plist(name: str, actions: list[dict],
                           accepts_input: bool = False) -> dict:
    """Build a complete shortcut plist dict."""
    plist = {
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowClientVersion": "4046.0.2.2",
        "WFWorkflowIcon": {
            "WFWorkflowIconStartColor": 4282601983,
            "WFWorkflowIconGlyphNumber": 59511,
        },
        "WFWorkflowActions": actions,
        "WFWorkflowInputContentItemClasses": [
            "WFStringContentItem",
        ],
        "WFWorkflowOutputContentItemClasses": [
            "WFStringContentItem",
        ],
        "WFWorkflowTypes": [],
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowImportQuestions": [],
        "WFQuickActionSurfaces": [],
        "WFWorkflowHasShortcutInputVariables": accepts_input,
    }
    return plist


# --- Shortcut definitions ---

# Event fields output by the shortcut (order matters — must match parser)
EVENT_PROPS = ["title", "startDate", "endDate", "calendarIdentifier", "fantasticalURL"]

# Legacy: was QUERY_RANGE_DAYS = 14 (hardcoded ±14d from current date).
# Now the caller passes start/end dates as shortcut input.


def _current_date_action(action_uuid: str) -> dict:
    """Build a Current Date action.

    Note: do NOT include WFDateActionMode — the extracted working plist
    from Shortcuts.app omits it, and including it may change behavior.
    """
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.date",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
        },
    }


def _adjust_date_action(
    action_uuid: str,
    source_uuid: str,
    source_output_name: str,
    days: int,
    operation: str = "Add",
    custom_output_name: str | None = None,
    coerce_source: bool = False,
) -> dict:
    """Build an Adjust Date action.

    Args:
        action_uuid: UUID for this action.
        source_uuid: UUID of the action providing the date to adjust.
        source_output_name: OutputName of the source action.
        days: Number of days to adjust by.
        operation: "Add" or "Subtract".
        custom_output_name: Optional custom name for this action's output.
        coerce_source: If True, add WFCoercionVariableAggrandizement to
            coerce the source to WFDateContentItem.
    """
    attachment: dict = {
        "OutputName": source_output_name,
        "OutputUUID": source_uuid,
        "Type": "ActionOutput",
    }
    if coerce_source:
        attachment["Aggrandizements"] = [{
            "CoercionItemClass": "WFDateContentItem",
            "Type": "WFCoercionVariableAggrandizement",
        }]

    params: dict = {
        "UUID": action_uuid,
        "WFDate": {
            "Value": {
                "attachmentsByRange": {
                    "{0, 1}": attachment,
                },
                "string": "\ufffc",
            },
            "WFSerializationType": "WFTextTokenString",
        },
        # CRITICAL: Magnitude and Unit must be STRINGS, not integers.
        # Using integers silently breaks the Adjust Date action output.
        "WFDuration": {
            "Value": {
                "Magnitude": str(days),
                "Unit": "days",
            },
            "WFSerializationType": "WFQuantityFieldValue",
        },
    }
    if operation != "Add":  # "Add" is the default when key is absent
        params["WFAdjustOperation"] = operation
    if custom_output_name:
        params["CustomOutputName"] = custom_output_name
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.adjustdate",
        "WFWorkflowActionParameters": params,
    }


def _dynamic_date_query_actions(
    query_uuid: str,
    range_days: int,
) -> tuple[list[dict], str, str]:
    """Build Current Date → Adjust Date ×2 → CalendarItemQuery actions.

    Returns (actions, start_uuid, end_uuid) where start/end UUIDs are
    the Adjust Date action UUIDs for the date range boundaries.

    The date range is ±range_days from the current date at runtime.
    """
    current_date_uuid = _uuid()
    adjust_start_uuid = _uuid()
    adjust_end_uuid = _uuid()

    actions = [
        # Current Date
        _current_date_action(current_date_uuid),
        # Subtract N days → start date
        # CustomOutputName="Date" matches the encoding from Shortcuts.app
        _adjust_date_action(
            adjust_start_uuid, current_date_uuid, "Date",
            days=range_days, operation="Subtract",
            custom_output_name="Date",
        ),
        # Add N days → end date
        # References Current Date directly, coercion matches extracted plist
        _adjust_date_action(
            adjust_end_uuid, current_date_uuid, "Date",
            days=range_days, operation="Add",
        ),
        # CalendarItemQuery with dynamic date filter
        {
            "WFWorkflowActionIdentifier": f"{FANTASTICAL_BUNDLE_ID}.IntentCalendarItem",
            "WFWorkflowActionParameters": {
                "AppIntentDescriptor": {
                    "TeamIdentifier": FANTASTICAL_TEAM_ID,
                    "BundleIdentifier": FANTASTICAL_BUNDLE_ID,
                    "Name": FANTASTICAL_APP_NAME,
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
                                    # WFTextTokenAttachment refs — no aggrandizements
                                    "Date": _var_attachment(
                                        var_type="ActionOutput",
                                        output_uuid=adjust_start_uuid,
                                        output_name="Date",
                                    ),
                                    "AnotherDate": _var_attachment(
                                        var_type="ActionOutput",
                                        output_uuid=adjust_end_uuid,
                                        output_name="Adjusted Date",
                                    ),
                                },
                            },
                        ],
                    },
                },
            },
        },
    ]
    return actions, adjust_start_uuid, adjust_end_uuid


def _input_date_query_actions(query_uuid: str) -> list[dict]:
    """Build input-driven date query: Split → Get Item → Detect → Adjust → Query.

    Expects shortcut input as "YYYY-MM-DD|YYYY-MM-DD" (start|end).

    Flow:
      Split Text on "|"
        → Get Item 1 → Detect Dates → Adjust Date +0d (launders for filter)
        → Get Item 2 → Detect Dates → Adjust Date +0d
        → CalendarItemQuery(startDate between adj1..adj2)

    CalendarItemQuery filter only works with Adjust Date action outputs
    (proven in experiments 12-16). The +0 day adjustment launders the
    Detect Dates output into the required format.
    """
    split_uuid = _uuid()
    get_item1_uuid = _uuid()
    detect1_uuid = _uuid()
    adjust1_uuid = _uuid()
    get_item2_uuid = _uuid()
    detect2_uuid = _uuid()
    adjust2_uuid = _uuid()

    actions = [
        # Split input "start|end" on "|"
        _split_text_action(split_uuid, separator="|"),

        # --- Start date chain ---
        _get_item_from_list_action(
            get_item1_uuid, split_uuid, "Split Text", index=1,
        ),
        _detect_date_action(
            detect1_uuid,
            source_uuid=get_item1_uuid,
            source_output_name="Item from List",
        ),
        _adjust_date_action(
            adjust1_uuid, detect1_uuid, "Dates",
            days=0, custom_output_name="Date",
        ),

        # --- End date chain ---
        _get_item_from_list_action(
            get_item2_uuid, split_uuid, "Split Text", index=2,
        ),
        _detect_date_action(
            detect2_uuid,
            source_uuid=get_item2_uuid,
            source_output_name="Item from List",
        ),
        _adjust_date_action(
            adjust2_uuid, detect2_uuid, "Dates",
            days=0,
        ),

        # CalendarItemQuery with input-driven date filter
        {
            "WFWorkflowActionIdentifier": f"{FANTASTICAL_BUNDLE_ID}.IntentCalendarItem",
            "WFWorkflowActionParameters": {
                "AppIntentDescriptor": {
                    "TeamIdentifier": FANTASTICAL_TEAM_ID,
                    "BundleIdentifier": FANTASTICAL_BUNDLE_ID,
                    "Name": FANTASTICAL_APP_NAME,
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
                        ],
                    },
                },
            },
        },
    ]
    return actions


def _repeat_text_output_actions(query_uuid: str, prop_names: list[str]) -> list[dict]:
    """Build Repeat Each → Text → Text wrap → Output pipeline.

    Takes CalendarItemQuery results and formats them as pipe-delimited
    text with record separators.

    The extra Text action wrapping Repeat Results before Output is required
    to bypass macOS taint tracking. Data from third-party apps (Fantastical)
    is "tainted" and the Output action refuses to emit it directly
    ("produces private output... missing an appIdentifier"). Passing through
    a Text action first makes the data owned by the Shortcuts engine.
    """
    group_uuid = _uuid()
    repeat_output_uuid = _uuid()
    text_wrap_uuid = _uuid()
    event_text = _pipe_delimited_text(prop_names)

    return [
        # Repeat Each (over calendar items)
        _repeat_each_start(
            _var_attachment(var_type="ActionOutput", output_uuid=query_uuid,
                           output_name="Fantastical Calendar Item"),
            group_uuid,
        ),
        # Format event as pipe-delimited text
        _text_action(event_text),
        # End repeat
        _repeat_each_end(group_uuid, repeat_output_uuid),
        # Wrap repeat results in Text action (bypasses taint tracking)
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "WFTextActionText": _token_string_param(
                    output_uuid=repeat_output_uuid,
                    output_name="Repeat Results",
                ),
                "UUID": text_wrap_uuid,
            },
        },
        # Output the Text result (not the raw Repeat Results)
        _output_action(_token_string_param(
            output_uuid=text_wrap_uuid,
            output_name="Text",
        )),
    ]


def build_find_events() -> dict:
    """Build the 'Fantastical - Find Events' shortcut plist.

    Uses CalendarItemQuery to find events across ALL calendars within
    a caller-specified date range passed as input text.

    The caller passes "YYYY-MM-DD|YYYY-MM-DD" (start|end) as shortcut input.
    The shortcut splits the input, detects dates, launders them through
    Adjust Date +0d (required for CalendarItemQuery filter compatibility),
    and uses the result as the query date range.

    Flow:
      Input "start|end"
        → Split Text on "|"
        → Get Item 1 → Detect Dates → Adjust Date +0d (start)
        → Get Item 2 → Detect Dates → Adjust Date +0d (end)
        → CalendarItemQuery(startDate between start..end)
        → Repeat Each → pipe-delimited text
        → Text wrap (bypasses taint tracking)
        → Output
    """
    query_uuid = _uuid()
    date_actions = _input_date_query_actions(query_uuid)

    actions = [
        *date_actions,
        *_repeat_text_output_actions(query_uuid, EVENT_PROPS),
    ]
    return _build_shortcut_plist("Fantastical - Find Events", actions, accepts_input=True)


SHORTCUT_BUILDERS = {
    "find_events": ("Fantastical - Find Events", build_find_events),
}


def generate_shortcut_file(key: str, output_dir: Path | None = None) -> Path:
    """Generate a signed .shortcut file for the given shortcut key.

    Args:
        key: Shortcut key (e.g. 'find_events')
        output_dir: Directory for output files. Defaults to temp dir.

    Returns:
        Path to the signed .shortcut file.
    """
    if key not in SHORTCUT_BUILDERS:
        raise ValueError(f"Unknown shortcut key: {key}")

    name, builder = SHORTCUT_BUILDERS[key]
    plist_data = builder()

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="fantastical-shortcuts-"))

    unsigned_path = output_dir / f".{name}.unsigned.shortcut"
    signed_path = output_dir / f"{name}.shortcut"

    # Write binary plist
    with open(unsigned_path, "wb") as f:
        plistlib.dump(plist_data, f, fmt=plistlib.FMT_BINARY)

    # Sign it (may contact Apple servers, needs generous timeout)
    result = subprocess.run(
        ["shortcuts", "sign",
         "--mode", "anyone",
         "--input", str(unsigned_path),
         "--output", str(signed_path)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to sign shortcut: {result.stderr.strip()}")

    # Clean up unsigned
    unsigned_path.unlink(missing_ok=True)

    return signed_path


def import_shortcut(shortcut_path: Path) -> None:
    """Import a signed .shortcut file by opening it in Shortcuts.app."""
    subprocess.run(
        ["open", str(shortcut_path)],
        check=True, timeout=10,
    )


def generate_and_import(key: str) -> Path:
    """Generate, sign, and import a shortcut.

    Returns path to the signed shortcut file.
    """
    path = generate_shortcut_file(key)
    import_shortcut(path)
    return path

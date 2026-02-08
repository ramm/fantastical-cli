"""Generate and import .shortcut plist files for Fantastical App Intents.

Key format discovery: App Intent parameters must use WFTextTokenString encoding
(string + attachmentsByRange), NOT WFTextTokenAttachment. The date parameter
specifically must reference the source action's output via OutputName + OutputUUID
inside an attachmentsByRange dict. This was discovered by extracting the plist from
a working signed shortcut where the user manually bound the variable in Shortcuts.app.
"""

from __future__ import annotations

import plistlib
import subprocess
import tempfile
import uuid
from datetime import date, datetime, timedelta
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


def _detect_date_action(action_uuid: str) -> dict:
    """Build a Date Detection action that reads from Shortcut Input."""
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.detect.date",
        "WFWorkflowActionParameters": {
            "WFInput": {
                "Value": {
                    "Type": "ExtensionInput",
                },
                "WFSerializationType": "WFTextTokenAttachment",
            },
            "UUID": action_uuid,
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
EVENT_PROPS = ["title", "startDate", "endDate", "calendarIdentifier", "isAllDay", "location", "notes", "fantasticalURL"]

# Static date range: ±2.5 years from generation time.
# CalendarItemQuery filter dates must be hardcoded (dynamic WFTextTokenString
# references in Values.Date/AnotherDate are not supported — confirmed via
# Cherri compiler analysis; entity query filters use Property/Operator/Values,
# not WFCondition/WFInput like If conditions). The shortcut is regenerated
# during `fantastical setup` so the window re-centers on the current date.
QUERY_RANGE_YEARS = 2.5


def _calendar_item_query_action(action_uuid: str, start_date: datetime, end_date: datetime) -> dict:
    """Build a CalendarItemQuery action (Find Fantastical Calendar Item).

    Uses WFContentItemFilter with a startDate "is between" filter.
    Dates must be native datetime objects — plistlib encodes them as
    NSDate values. String dates show as empty "Date" placeholders in
    Shortcuts.app and cause runtime errors.
    """
    return {
        "WFWorkflowActionIdentifier": f"{FANTASTICAL_BUNDLE_ID}.IntentCalendarItem",
        "WFWorkflowActionParameters": {
            "AppIntentDescriptor": {
                "TeamIdentifier": FANTASTICAL_TEAM_ID,
                "BundleIdentifier": FANTASTICAL_BUNDLE_ID,
                "Name": FANTASTICAL_APP_NAME,
                "AppIntentIdentifier": "IntentCalendarItem",
                "ActionRequiresAppInstallation": True,
            },
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
                                "Date": start_date,
                                "AnotherDate": end_date,
                            },
                        },
                    ],
                },
            },
            "ShowWhenRun": False,
            "UUID": action_uuid,
        },
    }


def _query_date_range() -> tuple[datetime, datetime]:
    """Compute the static date range for CalendarItemQuery.

    Returns (start, end) as datetime objects for plist serialization.
    """
    today = date.today()
    offset = timedelta(days=int(QUERY_RANGE_YEARS * 365))
    start = today - offset
    end = today + offset
    return (
        datetime(start.year, start.month, start.day, 0, 0, 0),
        datetime(end.year, end.month, end.day, 23, 59, 59),
    )


def build_find_events() -> dict:
    """Build the 'Fantastical - Find Events' shortcut plist.

    Uses CalendarItemQuery to find events across ALL calendars within
    a broad static date range. Python-side filtering narrows to the
    exact requested dates.

    Flow:
      CalendarItemQuery(startDate between start..end)
      -> Repeat Each (events):
           -> Text: title | start | end | cal | allDay | loc | notes | url\x1e
      -> End Repeat -> Output
    """
    action_uuid = _uuid()
    group_uuid = _uuid()
    repeat_output_uuid = _uuid()

    start_date, end_date = _query_date_range()
    event_text = _pipe_delimited_text(EVENT_PROPS)

    actions = [
        # 1. Find calendar items in date range (all calendars)
        _calendar_item_query_action(action_uuid, start_date, end_date),
        # 2. Repeat Each (over calendar items)
        _repeat_each_start(
            _var_attachment(var_type="ActionOutput", output_uuid=action_uuid,
                           output_name="Fantastical Calendar Item"),
            group_uuid,
        ),
        # 3. Format event as pipe-delimited text
        _text_action(event_text),
        # 4. End repeat
        _repeat_each_end(group_uuid, repeat_output_uuid),
        # 5. Output the results
        _output_action({
            "WFSerializationType": "WFTextTokenString",
            "Value": {
                "string": "\ufffc",
                "attachmentsByRange": {
                    "{0, 1}": {
                        "OutputUUID": repeat_output_uuid,
                        "Type": "ActionOutput",
                        "OutputName": "Repeat Results",
                    },
                },
            },
        }),
    ]
    return _build_shortcut_plist("Fantastical - Find Events", actions, accepts_input=False)


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

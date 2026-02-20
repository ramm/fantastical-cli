"""Tests for shortcut_gen.build_find_events, build_find_attendees, and key builder helpers."""

from fantastical.backend.shortcut_gen import (
    ATTENDEE_PROPS,
    EVENT_PROPS,
    _delimited_text,
    _text_token_string,
    _var_attachment,
    build_find_attendees,
    build_find_events,
)


# --- Helpers ---


def _find_events_plist():
    return build_find_events()


def _find_events_actions():
    return _find_events_plist()["WFWorkflowActions"]


def _find_events_action_ids():
    return [a["WFWorkflowActionIdentifier"] for a in _find_events_actions()]


def _find_attendees_plist():
    return build_find_attendees()


def _find_attendees_actions():
    return _find_attendees_plist()["WFWorkflowActions"]


def _find_attendees_action_ids():
    return [a["WFWorkflowActionIdentifier"] for a in _find_attendees_actions()]


# --- build_find_events: plist structure ---


def test_find_events_action_count():
    # 9 input date actions + 7 repeat/attendee/count/text/output = 16
    assert len(_find_events_actions()) == 16


def test_find_events_all_uuids_unique():
    uuid_params = [
        params["UUID"]
        for a in _find_events_actions()
        for params in [a.get("WFWorkflowActionParameters", {})]
        if "UUID" in params
    ]
    assert len(uuid_params) == len(set(uuid_params))


def test_find_events_has_split_text_action():
    assert _find_events_action_ids()[0] == "is.workflow.actions.text.split"


def test_find_events_has_get_item_indices_1_2_3():
    actions = _find_events_actions()
    get_items = [
        a for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.getitemfromlist"
    ]
    assert len(get_items) == 3
    indices = [a["WFWorkflowActionParameters"]["WFItemIndex"] for a in get_items]
    assert indices == [1, 2, 3]


def test_find_events_has_detect_date_actions():
    count = _find_events_action_ids().count("is.workflow.actions.detect.date")
    assert count == 2


def test_find_events_has_adjust_date_actions():
    actions = _find_events_actions()
    adjusts = [
        a for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.adjustdate"
    ]
    assert len(adjusts) == 2
    for a in adjusts:
        dur = a["WFWorkflowActionParameters"]["WFDuration"]["Value"]
        assert dur["Magnitude"] == "0"


def test_find_events_has_calendar_item_query():
    actions = _find_events_actions()
    queries = [
        a for a in actions
        if "IntentCalendarItem" in a["WFWorkflowActionIdentifier"]
    ]
    assert len(queries) == 1
    params = queries[0]["WFWorkflowActionParameters"]
    desc = params["AppIntentDescriptor"]
    assert desc["BundleIdentifier"] == "com.flexibits.fantastical2.mac"


def test_find_events_has_attendee_intent():
    actions = _find_events_actions()
    intents = [
        a for a in actions
        if "FKRGetAttendeesFromEventIntent" in a["WFWorkflowActionIdentifier"]
    ]
    assert len(intents) == 1


def test_find_events_has_count_action():
    actions = _find_events_actions()
    counts = [
        a for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.count"
    ]
    assert len(counts) == 1


def test_find_events_date_filter_template():
    actions = _find_events_actions()
    query = next(a for a in actions if "IntentCalendarItem" in a["WFWorkflowActionIdentifier"])
    templates = query["WFWorkflowActionParameters"]["WFContentItemFilter"]["Value"]["WFActionParameterFilterTemplates"]
    date_filter = templates[0]
    assert date_filter["Operator"] == 1003
    assert date_filter["Property"] == "startDate"


def test_find_events_title_filter_template():
    actions = _find_events_actions()
    query = next(a for a in actions if "IntentCalendarItem" in a["WFWorkflowActionIdentifier"])
    templates = query["WFWorkflowActionParameters"]["WFContentItemFilter"]["Value"]["WFActionParameterFilterTemplates"]
    title_filter = templates[1]
    assert title_filter["Operator"] == 99
    assert title_filter["Property"] == "title"


def test_find_events_title_filter_uses_token_string():
    actions = _find_events_actions()
    query = next(a for a in actions if "IntentCalendarItem" in a["WFWorkflowActionIdentifier"])
    templates = query["WFWorkflowActionParameters"]["WFContentItemFilter"]["Value"]["WFActionParameterFilterTemplates"]
    title_filter = templates[1]
    string_val = title_filter["Values"]["String"]
    assert string_val["WFSerializationType"] == "WFTextTokenString"


def test_find_events_repeat_each_block():
    actions = _find_events_actions()
    repeats = [
        a for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.repeat.each"
    ]
    assert len(repeats) == 2
    start_mode = repeats[0]["WFWorkflowActionParameters"]["WFControlFlowMode"]
    end_mode = repeats[1]["WFWorkflowActionParameters"]["WFControlFlowMode"]
    assert start_mode == 0
    assert end_mode == 2
    assert (repeats[0]["WFWorkflowActionParameters"]["GroupingIdentifier"]
            == repeats[1]["WFWorkflowActionParameters"]["GroupingIdentifier"])


def test_find_events_text_wrap_action():
    actions = _find_events_actions()
    repeats = [
        i for i, a in enumerate(actions)
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.repeat.each"
    ]
    end_idx = repeats[1]
    text_wrap = actions[end_idx + 1]
    assert text_wrap["WFWorkflowActionIdentifier"] == "is.workflow.actions.gettext"


def test_find_events_output_action():
    actions = _find_events_actions()
    assert actions[-1]["WFWorkflowActionIdentifier"] == "is.workflow.actions.output"


def test_find_events_accepts_input():
    plist = _find_events_plist()
    assert plist["WFWorkflowHasShortcutInputVariables"] is True


def test_find_events_client_version():
    plist = _find_events_plist()
    assert plist["WFWorkflowClientVersion"] == "4046.0.2.2"


# --- build_find_attendees: plist structure ---


def test_find_attendees_action_count():
    # 9 input date actions + 1 get_item + 1 if_start + 1 attendee_intent
    # + 1 repeat_start + 1 text + 1 repeat_end + 1 text_wrap
    # + 1 if_otherwise + 1 if_end + 1 output = 19
    assert len(_find_attendees_actions()) == 19


def test_find_attendees_all_uuids_unique():
    uuid_params = [
        params["UUID"]
        for a in _find_attendees_actions()
        for params in [a.get("WFWorkflowActionParameters", {})]
        if "UUID" in params
    ]
    assert len(uuid_params) == len(set(uuid_params))


def test_find_attendees_has_get_item_indices_1_2_3_plus_first():
    actions = _find_attendees_actions()
    get_items = [
        a for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.getitemfromlist"
    ]
    # 3 from input parsing + 1 for first event
    assert len(get_items) == 4
    indices = [a["WFWorkflowActionParameters"]["WFItemIndex"] for a in get_items]
    assert indices == [1, 2, 3, 1]


def test_find_attendees_has_attendee_intent():
    actions = _find_attendees_actions()
    intents = [
        a for a in actions
        if "FKRGetAttendeesFromEventIntent" in a["WFWorkflowActionIdentifier"]
    ]
    assert len(intents) == 1


def test_find_attendees_no_count_action():
    actions = _find_attendees_actions()
    counts = [
        a for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.count"
    ]
    assert len(counts) == 0


def test_find_attendees_repeat_each_block():
    actions = _find_attendees_actions()
    repeats = [
        a for a in actions
        if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.repeat.each"
    ]
    assert len(repeats) == 2
    assert repeats[0]["WFWorkflowActionParameters"]["WFControlFlowMode"] == 0
    assert repeats[1]["WFWorkflowActionParameters"]["WFControlFlowMode"] == 2
    assert (repeats[0]["WFWorkflowActionParameters"]["GroupingIdentifier"]
            == repeats[1]["WFWorkflowActionParameters"]["GroupingIdentifier"])


def test_find_attendees_output_action():
    actions = _find_attendees_actions()
    assert actions[-1]["WFWorkflowActionIdentifier"] == "is.workflow.actions.output"


def test_find_attendees_accepts_input():
    plist = _find_attendees_plist()
    assert plist["WFWorkflowHasShortcutInputVariables"] is True


# --- _text_token_string ---


def test_token_string_single_var():
    att = _var_attachment(var_type="Variable", var_name="X")["Value"]
    result = _text_token_string(["", ""], [att])
    value = result["Value"]
    assert "\ufffc" in value["string"]
    assert "{0, 1}" in value["attachmentsByRange"]


def test_token_string_with_prefix():
    att = _var_attachment(var_type="Variable", var_name="X")["Value"]
    result = _text_token_string(["hello ", ""], [att])
    value = result["Value"]
    # "hello " is 6 UTF-16 code units
    assert "{6, 1}" in value["attachmentsByRange"]


def test_token_string_two_vars():
    att1 = _var_attachment(var_type="Variable", var_name="X")["Value"]
    att2 = _var_attachment(var_type="Variable", var_name="Y")["Value"]
    result = _text_token_string(["", " | ", ""], [att1, att2])
    value = result["Value"]
    assert "{0, 1}" in value["attachmentsByRange"]
    # \ufffc (1) + " | " (3) = offset 4
    assert "{4, 1}" in value["attachmentsByRange"]


# --- _delimited_text ---


def test_delimited_text_structure():
    result = _delimited_text(["title", "startDate", "endDate"])
    value = result["Value"]
    string = value["string"]
    assert string.count("\x1f") == 2
    assert string.count("\x1e") == 1
    assert len(value["attachmentsByRange"]) == 3


def test_delimited_text_five_props():
    result = _delimited_text(EVENT_PROPS)
    value = result["Value"]
    string = value["string"]
    assert string.count("\x1f") == 4
    assert string.count("\x1e") == 1
    assert len(value["attachmentsByRange"]) == 5


def test_delimited_text_attendee_props():
    result = _delimited_text(ATTENDEE_PROPS)
    value = result["Value"]
    string = value["string"]
    assert string.count("\x1f") == 1
    assert string.count("\x1e") == 1
    assert len(value["attachmentsByRange"]) == 2

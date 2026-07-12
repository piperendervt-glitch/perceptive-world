from __future__ import annotations

import pytest

from trpg_core.record_codec import (
    ParsedRecordToken,
    parse_record_token,
    record_format_version,
    serialize_record_token,
)


@pytest.mark.parametrize("record, expected", [
    ({}, 0), ({"format_version": 0}, 0), ({"format_version": 1}, 1), ({"format_version": 2}, 2), ({"format_version": 3}, 3), ({"format_version": 4}, 4),
])
def test_record_format_version(record, expected):
    assert record_format_version(record) == expected


@pytest.mark.parametrize("value", [True, False, "1", 1.0, -1, 5, None])
def test_record_format_version_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="format_version"):
        record_format_version({"format_version": value})


@pytest.mark.parametrize("payload", ["2,2", "0,0", "-1,2", "12,-34"])
def test_v3_movement_token_round_trip_is_canonical(payload):
    token = serialize_record_token("move-player-to", payload, format_version=3)
    assert token == f"move-player-to:{payload}"
    assert parse_record_token(token, format_version=3) == ParsedRecordToken(
        "move-player-to", payload,
    )
    for old in (0, 1, 2):
        with pytest.raises(ValueError):
            parse_record_token(token, format_version=old)


@pytest.mark.parametrize("payload", [
    "", "1", "1,", ",1", "1,2,3", " 1,2", "1,2 ", "+1,2",
    "01,2", "-0,2", "1.0,2", "x,2",
])
def test_v3_movement_token_rejects_noncanonical_payload(payload):
    with pytest.raises(ValueError):
        serialize_record_token("move-player-to", payload, format_version=3)


@pytest.mark.parametrize("verb,payload", [
    ("explore", "well"),
    ("choice", "canonical-key"),
    ("combat", "attack"),
])
def test_supported_tokens_round_trip(verb, payload):
    token = serialize_record_token(verb, payload)
    assert parse_record_token(token, format_version=1) == ParsedRecordToken(verb, payload)


def test_payload_preserves_colons_slashes_and_whitespace():
    payload = " a:b/c "
    token = serialize_record_token("choice", payload)
    assert parse_record_token(token, format_version=1).payload == payload


@pytest.mark.parametrize("verb,payload", [("choice", ""), ("choice", None), ("unknown", None)])
def test_serialize_rejects_empty_or_unknown_tokens(verb, payload):
    with pytest.raises(ValueError):
        serialize_record_token(verb, payload)


@pytest.mark.parametrize("token", [
    "choice:", "unknown:value", "focus:set:x", "move-to:x",
    "focus:clear:extra", "depart:extra", "observe:x", "inspect:x", " choice:key", "choice",
])
def test_parse_rejects_malformed_unknown_and_future_tokens(token):
    with pytest.raises(ValueError):
        parse_record_token(token, format_version=1)


@pytest.mark.parametrize("verb,payload", [
    ("move-to", "goblin:location/well"),
    ("focus:set", "goblin:location/well"),
    ("focus:clear", None),
    ("depart", None),
])
def test_v1_village_tokens_round_trip(verb, payload):
    token = serialize_record_token(verb, payload, format_version=1)
    assert parse_record_token(token, format_version=1) == ParsedRecordToken(verb, payload)
    with pytest.raises(ValueError):
        parse_record_token(token, format_version=0)


@pytest.mark.parametrize("verb,payload", [
    ("observe", None),
    ("inspect", None),
    ("lod-unlock", "goblin:location/well:3"),
])
def test_v2_lod_tokens_round_trip_and_old_versions_reject(verb, payload):
    token = serialize_record_token(verb, payload, format_version=2)
    assert parse_record_token(token, format_version=2) == ParsedRecordToken(verb, payload)
    for old_version in (0, 1):
        with pytest.raises(ValueError):
            parse_record_token(token, format_version=old_version)


@pytest.mark.parametrize("payload", [
    "", "goblin:location/well", "x:3", "goblin:location/well:-1",
    "goblin:location/well:01", "goblin:location/well: 1", "goblin:location/well:１",
])
def test_v2_lod_unlock_rejects_malformed_payload(payload):
    with pytest.raises(ValueError):
        serialize_record_token("lod-unlock", payload, format_version=2)

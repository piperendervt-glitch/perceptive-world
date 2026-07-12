from __future__ import annotations

import pytest

from trpg_core.record_codec import (
    ParsedRecordToken,
    parse_record_token,
    record_format_version,
    serialize_record_token,
)


@pytest.mark.parametrize("record, expected", [({}, 0), ({"format_version": 0}, 0), ({"format_version": 1}, 1)])
def test_record_format_version(record, expected):
    assert record_format_version(record) == expected


@pytest.mark.parametrize("value", [True, False, "1", 1.0, -1, 2, None])
def test_record_format_version_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="format_version"):
        record_format_version({"format_version": value})


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

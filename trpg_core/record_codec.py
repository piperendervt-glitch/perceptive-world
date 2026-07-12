"""Pure codec for versioned record/replay input tokens."""

from __future__ import annotations

from dataclasses import dataclass

from .world import parse_world_object_id


CURRENT_RECORD_FORMAT_VERSION = 1
LEGACY_RECORD_FORMAT_VERSION = 0
SUPPORTED_RECORD_FORMAT_VERSIONS = frozenset({0, 1})

_LEGACY_PAYLOAD_VERBS = frozenset({"explore", "choice", "combat"})
_V1_PAYLOAD_VERBS = _LEGACY_PAYLOAD_VERBS | frozenset({"move-to", "focus:set"})
_V1_EXACT_VERBS = frozenset({"focus:clear", "depart"})


@dataclass(frozen=True)
class ParsedRecordToken:
    verb: str
    payload: str | None


def record_format_version(record: dict) -> int:
    """Return a supported format version; a missing field is legacy v0."""
    if "format_version" not in record:
        return LEGACY_RECORD_FORMAT_VERSION
    version = record["format_version"]
    if type(version) is not int or version not in SUPPORTED_RECORD_FORMAT_VERSIONS:
        raise ValueError(f"unsupported record format_version: {version!r}")
    return version


def serialize_record_token(
    verb: str,
    payload: str | None = None,
    *,
    format_version: int = CURRENT_RECORD_FORMAT_VERSION,
) -> str:
    """Serialize one token from the currently supported closed vocabulary."""
    if type(format_version) is not int or format_version not in SUPPORTED_RECORD_FORMAT_VERSIONS:
        raise ValueError(f"unsupported record format_version: {format_version!r}")
    payload_verbs = (_LEGACY_PAYLOAD_VERBS if format_version == 0 else _V1_PAYLOAD_VERBS)
    exact_verbs = frozenset() if format_version == 0 else _V1_EXACT_VERBS
    if verb in exact_verbs:
        if payload is not None:
            raise ValueError(f"record token {verb!r} does not accept a payload")
        return verb
    if verb not in payload_verbs:
        raise ValueError(f"unknown record token verb: {verb!r}")
    if not isinstance(payload, str) or not payload:
        raise ValueError(f"record token {verb!r} requires a non-empty payload")
    if verb in {"move-to", "focus:set"}:
        parse_world_object_id(payload)
    return f"{verb}:{payload}"


def parse_record_token(token: str, *, format_version: int) -> ParsedRecordToken:
    """Parse without normalizing or splitting colons inside the payload."""
    if type(format_version) is not int or format_version not in SUPPORTED_RECORD_FORMAT_VERSIONS:
        raise ValueError(f"unsupported record format_version: {format_version!r}")
    if not isinstance(token, str):
        raise ValueError(f"record token must be str, got {type(token).__name__}")
    if format_version == 1 and token in _V1_EXACT_VERBS:
        return ParsedRecordToken(token, None)
    payload_verbs = (_LEGACY_PAYLOAD_VERBS if format_version == 0 else _V1_PAYLOAD_VERBS)
    for verb in sorted(payload_verbs, key=len, reverse=True):
        prefix = verb + ":"
        if token.startswith(prefix):
            payload = token[len(prefix):]
            if not payload:
                raise ValueError(f"record token {verb!r} has an empty payload")
            if verb in {"move-to", "focus:set"}:
                parse_world_object_id(payload)
            return ParsedRecordToken(verb, payload)
    raise ValueError(f"unknown or malformed record token: {token!r}")

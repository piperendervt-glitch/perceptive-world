"""クライアント共通の最小UI入力モデルと副作用のないresolver。

ここで扱う値はGameActionやrecord/replay形式ではない。既存Controllerへ接続する前の
UI入力を分類するだけで、GameState、RNG、端末、presentationには依存しない。
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

MetaCommand: TypeAlias = Literal["status", "help", "save", "load", "quit"]
MoveDirection: TypeAlias = Literal["north", "east", "south", "west"]
CombatCommand: TypeAlias = Literal["attack", "magic", "herb", "flee"]

_META_COMMANDS = frozenset({"status", "help", "save", "load", "quit"})
_META_SHORTCUTS = {"S": "status", "H": "help", "Q": "quit"}
_DIRECTION_ALIASES: dict[str, MoveDirection] = {
    "north": "north", "n": "north", "北": "north", "up": "north",
    "east": "east", "e": "east", "東": "east", "right": "east",
    "south": "south", "s": "south", "南": "south", "down": "south",
    "west": "west", "w": "west", "西": "west", "left": "west",
}
_DIRECTION_PREFIXES = frozenset({"go", "move", "g", "walk"})
_COMBAT_COMMANDS = frozenset({"attack", "magic", "herb", "flee"})


@dataclass(frozen=True)
class SelectMenuIndex:
    """1始まりのUIメニュー選択。Choice keyやexplore keyではない。"""

    index: int

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 1:
            raise ValueError("menu index must be a positive integer")


@dataclass(frozen=True)
class MetaRequest:
    """表示・保存・終了等のUI要求。GameActionやrecord対象ではない。"""

    command: MetaCommand
    argument: str | None = None

    def __post_init__(self) -> None:
        if self.command not in _META_COMMANDS:
            raise ValueError(f"unknown meta command: {self.command}")
        argument = self.argument.strip() if self.argument is not None else None
        argument = argument or None
        if self.command in {"status", "help", "quit"} and argument is not None:
            raise ValueError(f"{self.command} does not accept an argument")
        object.__setattr__(self, "argument", argument)


@dataclass(frozen=True)
class DirectCommand:
    """正規化済みの直接command。解決済みGameActionではない。"""

    text: str

    def __post_init__(self) -> None:
        text = self.text.strip()
        if not text:
            raise ValueError("direct command must not be empty")
        if text.isdigit():
            raise ValueError("menu numbers are SelectMenuIndex values")
        if resolve_meta_request(text) is not None:
            raise ValueError("meta requests are not DirectCommand values")
        object.__setattr__(self, "text", text.lower())


InputToken: TypeAlias = SelectMenuIndex | DirectCommand | MetaRequest


def resolve_meta_request(raw: str) -> MetaRequest | None:
    """既存shortcutと直接meta commandを分類する。I/Oや状態変更は行わない。"""

    text = str(raw).strip()
    if not text:
        return None
    shortcut = _META_SHORTCUTS.get(text)
    if shortcut is not None:
        return MetaRequest(cast(MetaCommand, shortcut))
    parts = text.split(maxsplit=1)
    command = parts[0].lower()
    if command not in _META_COMMANDS:
        return None
    argument = parts[1] if len(parts) == 2 else None
    if command in {"status", "help", "quit"} and argument:
        return None
    return MetaRequest(cast(MetaCommand, command), argument)


def parse_raw_input(raw: str) -> InputToken | None:
    """raw文字列をUI入力値へ決定論的に分類する。"""

    text = str(raw).strip()
    if not text:
        return None
    meta = resolve_meta_request(text)
    if meta is not None:
        return meta
    if text.isdigit():
        index = int(text)
        return SelectMenuIndex(index) if index > 0 else None
    return DirectCommand(text)


def resolve_menu_index(selection: SelectMenuIndex, commands: Sequence[str]) -> str | None:
    """1始まりの選択を既存menu commandへ写す。範囲外ならNone。"""

    offset = selection.index - 1
    if offset < 0 or offset >= len(commands):
        return None
    return commands[offset]


def resolve_direction(text: str) -> MoveDirection | None:
    """現行の方角aliasまたは ``go/move/g/walk <方角>`` を正規化する。"""

    parts = str(text).strip().lower().split()
    if not parts:
        return None
    token = parts[0]
    if token in _DIRECTION_PREFIXES:
        if len(parts) < 2:
            return None
        token = parts[1]
    return _DIRECTION_ALIASES.get(token)


def resolve_combat_command(
    text: str,
    *,
    allowed: Collection[CombatCommand] | None = None,
) -> CombatCommand | None:
    """戦闘commandを分類し、任意の既計算allowed集合で絞り込む。"""

    command = str(text).strip().lower()
    if command not in _COMBAT_COMMANDS:
        return None
    if allowed is not None and command not in frozenset(allowed):
        return None
    return cast(CombatCommand, command)

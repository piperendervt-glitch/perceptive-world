"""固定画面型TUIの表示層。ゲーム状態・乱数・ログは変更しない。"""

from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata
from collections import deque
from dataclasses import dataclass, field

from .presentation import MapView, RenderSnapshot

CLEAR_SCREEN = "\x1b[2J\x1b[H"
MIN_WIDTH = 60
MIN_HEIGHT = 20
_NO_LINE_START = frozenset("、。）」』】〕〉》！？：／")
_TOKEN_RE = re.compile(
    r"2D6\[[0-9, ]+\](?:=\d+)?"
    r"|(?:残\s*)?(?:HP|MP)\s*\d+(?:/\d+)?"
    r"|目標\s*\d+"
    r"|支度\s*\d+/\d+"
    r"|\d+/\d+"
    r"|（[^（）\n]{1,20}）"
    r"|[A-Za-z0-9_+\-.,/\[\]=]+"
    r"|\s+"
    r"|.",
)


def display_width(text: str) -> int:
    width = 0
    for ch in str(text):
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
    return width


def truncate_display(text: str, width: int) -> str:
    if width <= 0:
        return ""
    out = []
    used = 0
    for ch in str(text):
        w = 0 if unicodedata.combining(ch) else (
            2 if unicodedata.east_asian_width(ch) in "WF" else 1
        )
        if used + w > width:
            break
        out.append(ch)
        used += w
    return "".join(out)


def pad_display(text: str, width: int) -> str:
    text = truncate_display(text, width)
    return text + " " * max(0, width - display_width(text))


def wrap_display(text: str, width: int) -> list[str]:
    if width <= 0:
        return [""]
    result = []
    for source in str(text).splitlines() or [""]:
        if not source:
            result.append("")
            continue
        tokens = _TOKEN_RE.findall(source)
        grouped = []
        for token in tokens:
            if token in _NO_LINE_START and grouped:
                grouped[-1] += token
            else:
                grouped.append(token)
        line = ""
        for token in grouped:
            if token.isspace():
                if line:
                    line += token
                continue
            if display_width(token) > width:
                if line.rstrip():
                    result.append(line.rstrip())
                    line = ""
                rest = token
                while display_width(rest) > width:
                    part = truncate_display(rest, width)
                    result.append(part)
                    rest = rest[len(part):]
                line = rest
                continue
            candidate = line + token
            if line and display_width(candidate) > width:
                result.append(line.rstrip())
                line = token.lstrip()
            else:
                line = candidate
        result.append(line.rstrip())
    return result or [""]


class MessageBuffer:
    """TUIだけが持つ一時表示。GameStateやfixtureには入れない。"""

    def __init__(self, max_messages: int = 40):
        self._messages = deque(maxlen=max_messages)

    def add(self, text) -> None:
        text = str(text).strip()
        if text:
            self._messages.append(text)

    def messages(self) -> tuple[str, ...]:
        """メッセージ単位の読み取り専用コピーを返す。"""
        return tuple(self._messages)

    def recent_lines(self, width: int, height: int) -> list[str]:
        return _recent_lines(self.messages(), width, height)


def _recent_lines(messages, width: int, height: int) -> list[str]:
    """メッセージ列を表示行へ変換する副作用のないTUI整形処理。"""
    height = max(0, height)
    if height == 0:
        return []
    selected = []
    remaining = height
    for message in reversed(tuple(messages)):
        block = wrap_display(message, width)
        if len(block) <= remaining:
            selected.insert(0, block)
            remaining -= len(block)
            continue
        if not selected:  # 最新メッセージ単体が長すぎる場合だけ末尾を残す。
            tail = block[-height:]
            tail[0] = truncate_display("…" + tail[0].lstrip("、。／ "), width)
            selected = [tail]
        break
    return [line for block in selected for line in block]


@dataclass
class ScreenModel:
    place: str
    situation: str
    status: str
    objective: str
    focus: str = "なし"
    menu: list[tuple[str, str, str]] = field(default_factory=list)
    scene: str = ""
    recent: list[str] = field(default_factory=list)
    lod_detail: str | None = None


def render_local_cross_map(view: MapView) -> str:
    """MapViewだけから、現在地と隣接出口を基準版と同じ十字配置で描く。"""
    exits = {exit_view.direction: exit_view.label for exit_view in view.exits}
    unknown = set(exits) - {"north", "east", "south", "west"}
    if unknown:
        raise ValueError(f"未対応の地図方向: {sorted(unknown)}")

    center = f">{view.current_label}<"
    west = exits.get("west")
    east = exits.get("east")
    north = exits.get("north")
    south = exits.get("south")
    left = f"[{west}] ← " if west else ""
    right = f" → [{east}]" if east else ""
    center_start = display_width(left)
    center_width = display_width(center)

    def centered(label: str) -> str:
        column = center_start + max(0, (center_width - display_width(label)) // 2)
        return " " * column + label

    lines = []
    if north:
        lines.extend((centered(f"[{north}]"), centered("↑北")))
    lines.append(f"{left}{center}{right}")
    if south:
        lines.extend((centered("↓南"), centered(f"[{south}]")))
    return "\n".join(lines)


def _map_scene(snapshot: RenderSnapshot) -> str:
    if snapshot.map is None:
        return snapshot.scene_text
    return render_local_cross_map(snapshot.map)


def screen_model_from_snapshot(snapshot: RenderSnapshot) -> ScreenModel:
    """中立なRenderSnapshotをTUI専用ScreenModelへ変換する純関数。"""
    player = snapshot.player
    pending = (f"（持込予定 {player.pending_recovery_count}）"
               if player.pending_recovery_count else "")
    status = (f"HP {player.hp}/{player.hp_max}  MP {player.mp}/{player.mp_max}  "
              f"{player.recovery_item_name} {player.recovery_item_count}{pending}  "
              f"ターン {snapshot.turn}")

    if snapshot.preparation is not None:
        prep = snapshot.preparation
        situation = f"支度 {prep.selected_count}/{prep.required_count}"
    elif snapshot.scene_kind == "combat":
        alive = [enemy for enemy in snapshot.enemies if enemy.alive]
        situation = " / ".join(f"{enemy.name} HP{max(0, enemy.hp)}" for enemy in alive)
        situation = situation or "敵なし"
    elif snapshot.scene_kind == "decision":
        situation = "行動を選択"
    else:
        situation = snapshot.scene_kind

    scene = _map_scene(snapshot)
    if snapshot.scene_kind == "combat":
        target = next((enemy for enemy in snapshot.enemies if enemy.auto_target), None)
        scene = f"自動対象: {target.name}" if target is not None else "敵なし"
    if snapshot.ending:
        scene = "\n".join(part for part in (scene, snapshot.ending) if part)

    focus_label = "なし"
    if snapshot.focused_object_id is not None:
        focused = next(
            (obj for obj in snapshot.world_objects
             if obj.object_id == snapshot.focused_object_id),
            None,
        )
        if focused is None:
            raise ValueError("focused object is missing from world_objects")
        focus_label = focused.label

    lod_detail = None
    if snapshot.focused_object_lod is not None:
        lod = snapshot.focused_object_lod
        labels = " / ".join(fact.label for fact in lod.visible_facts)
        lod_detail = f"観察 LOD {lod.current_lod}: {labels}"

    return ScreenModel(
        place=snapshot.scene_title or snapshot.scene_id or "",
        situation=situation,
        status=status,
        objective=snapshot.objective,
        focus=focus_label,
        menu=[(action.label, action.canonical_command, action.detail or "")
              for action in snapshot.actions if action.enabled],
        scene=scene,
        recent=_recent_lines(snapshot.recent_messages, 54, 8),
        lod_detail=lod_detail,
    )


def _row(text: str, inner_width: int) -> str:
    return "│" + pad_display(text, inner_width) + "│"


def render_screen(model: ScreenModel, width: int, height: int) -> str:
    """指定サイズ以内の固定画面文字列を生成する純関数。"""
    width = max(MIN_WIDTH, int(width))
    height = max(MIN_HEIGHT, int(height))
    inner = width - 2
    top = "┌" + "─" * inner + "┐"
    sep = "├" + "─" * inner + "┤"
    bottom = "└" + "─" * inner + "┘"

    menu_lines = [f"{i}) {label}" for i, (label, _command, _detail)
                  in enumerate(model.menu, 1)]
    fixed = 2 + 3 + 3 + 1 + len(menu_lines)  # 枠、見出し、区切り、メタ
    content_budget = max(2, height - fixed)
    scene_lines = []
    for line in str(model.scene).splitlines():
        scene_lines.extend(wrap_display(line, inner))
    if not scene_lines:
        scene_lines = [" "]
    scene_count = min(len(scene_lines), max(1, min(6, content_budget - 1)))
    recent_count = max(1, content_budget - scene_count)
    scene_lines = scene_lines[:scene_count]
    recent_lines = list(model.recent)[-recent_count:]
    if model.lod_detail is not None:
        detail_width = max(1, inner - 8)
        detail_lines = []
        for part in model.lod_detail.split(" / "):
            candidate = f"{detail_lines[-1]} / {part}" if detail_lines else part
            if detail_lines and display_width(candidate) > detail_width:
                detail_lines.append(part)
            elif detail_lines:
                detail_lines[-1] = candidate
            else:
                detail_lines.extend(wrap_display(part, detail_width))
        detail_lines = detail_lines[:recent_count]
        recent_lines = detail_lines + recent_lines[-max(0, recent_count - len(detail_lines)):]

    lines = [
        top,
        _row(f" 場面: {model.place}　{model.situation}", inner),
        _row(f" H: {model.status}  注目: {model.focus}", inner),
        _row(f" 目的: {model.objective}", inner),
        sep,
    ]
    lines.extend(_row(line, inner) for line in scene_lines)
    lines.append(sep)
    if recent_lines:
        lines.extend(_row(f" 最近: {line}" if i == 0 else f"       {line}", inner)
                     for i, line in enumerate(recent_lines))
    else:
        lines.append(_row(" 最近: —", inner))
    lines.append(sep)
    lines.extend(_row(line, inner) for line in menu_lines)
    lines.append(_row(
        " [S][H][Q] focus next|prev|clear observe inspect step north|east|south|west",
        inner,
    ))
    lines.append(bottom)
    return "\n".join(lines[:height])


class TerminalUI:
    def __init__(self, stream=None, size_getter=None, environ=None):
        self.stream = stream or sys.stdout
        self.size_getter = size_getter or shutil.get_terminal_size
        self.environ = os.environ if environ is None else environ
        self.messages = MessageBuffer()
        self._fallback_notified = False

    def availability(self):
        if not getattr(self.stream, "isatty", lambda: False)():
            return False, "stdoutがTTYではありません"
        if self.environ.get("TERM", "").lower() == "dumb":
            return False, "TERM=dumbです"
        if self.environ.get("PERCEPTIVE_NO_ANSI") == "1":
            return False, "ANSI表示が無効です"
        try:
            size = self.size_getter()
        except Exception:
            return False, "端末サイズを取得できません"
        if size.columns < MIN_WIDTH or size.lines < MIN_HEIGHT:
            return False, f"端末サイズが{MIN_WIDTH}x{MIN_HEIGHT}未満です"
        return True, size

    def can_render(self) -> bool:
        return self.availability()[0]

    def notify_fallback(self, reason) -> None:
        if not self._fallback_notified:
            self.stream.write(f"[TUIを利用できないためmenu表示へ切り替えます: {reason}]\n")
            self.stream.flush()
            self._fallback_notified = True

    def draw(self, model: ScreenModel) -> bool:
        ok, detail = self.availability()
        if not ok:
            self.notify_fallback(detail)
            return False
        self.stream.write(CLEAR_SCREEN)
        self.stream.write(render_screen(model, detail.columns, detail.lines))
        self.stream.write("\n")
        self.stream.flush()
        return True

    def draw_help(self, lines: list[str]) -> bool:
        ok, detail = self.availability()
        if not ok:
            self.notify_fallback(detail)
            return False
        inner = detail.columns - 2
        body = ["┌" + "─" * inner + "┐", _row(" ヘルプ", inner),
                "├" + "─" * inner + "┤"]
        wrapped = []
        for line in lines:
            wrapped.extend(wrap_display(line, inner))
        body.extend(_row(line, inner) for line in wrapped[:max(1, detail.lines - 5)])
        body.append(_row(" Enterで戻る", inner))
        body.append("└" + "─" * inner + "┘")
        self.stream.write(CLEAR_SCREEN + "\n".join(body[:detail.lines]) + "\n")
        self.stream.flush()
        return True

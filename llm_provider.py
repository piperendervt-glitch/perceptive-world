"""llm_provider.py — LLM プロバイダ抽象（sdnd-ordia, Q3）.

qa_llm.py の意味判断関数は、ここで定義する `LLMProvider` 経由でのみ LLM を呼ぶ。
モデルやプロバイダの差し替えは config/llm.yaml のロール定義で行い、呼び出し側は
`complete(system, user, schema)` だけを知っていればよい。

提供するプロバイダ:
  - AnthropicProvider : 本番。Anthropic SDK で軽量 Claude を呼ぶ（temperature=0,
                        JSON は output_config.format で強制）。API キーが要る。
  - RecordedProvider  : オフライン/回帰用。ネットワークを使わず、user プロンプトに
                        含まれる目印文字列で決め打ちの JSON を返す（決定論的）。

設計メモ:
  - このモジュール自体はプロンプトを持たない。プロンプトは qa_llm.py の責務。
  - JSON 強制は「壊れたら 1 回再要求」の外側の砦。パース失敗時の再要求は
    qa_llm._ask_json が担当する（プロバイダは 1 回の complete のみ）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("llm_provider.py requires PyYAML. pip install pyyaml\n")
    raise


DEFAULT_CONFIG_PATH = "config/llm.yaml"


class LLMError(RuntimeError):
    """Base class for provider-level failures."""


class LLMStubUnmatched(LLMError):
    """RecordedProvider received a prompt with no matching rule."""


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """Minimal surface qa_llm depends on. One shot, no retry (caller retries)."""

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        ...


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_llm_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict:
    """Load config/llm.yaml. Requires a top-level 'roles' mapping."""
    text = Path(path).read_text(encoding="utf-8")
    d = yaml.safe_load(text)
    if not isinstance(d, dict) or "roles" not in d:
        raise LLMError(f"{path}: missing top-level 'roles' mapping")
    if not isinstance(d["roles"], dict):
        raise LLMError(f"{path}: 'roles' must be a mapping")
    return d


def role_config(role: str = "qa", config: dict | None = None) -> dict:
    """Return the config block for a role (provider/model/params)."""
    cfg = config if config is not None else load_llm_config()
    roles = cfg.get("roles", {})
    if role not in roles:
        raise LLMError(f"role {role!r} not defined in llm config (have {sorted(roles)})")
    rc = roles[role]
    if not isinstance(rc, dict) or "provider" not in rc or "model" not in rc:
        raise LLMError(f"role {role!r} must define at least provider + model")
    return rc


# ---------------------------------------------------------------------------
# Anthropic (live) provider
# ---------------------------------------------------------------------------


class AnthropicProvider:
    """Calls a lightweight Claude via the Anthropic SDK. temperature=0, JSON forced.

    Requires the `anthropic` package and credentials (ANTHROPIC_API_KEY, or an
    `ant auth login` profile). No key -> constructing the client raises at call
    time; we surface a clear message.
    """

    def __init__(self, model: str, max_tokens: int = 512, temperature: float = 0.0):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMError(
                "AnthropicProvider needs the 'anthropic' package: pip install anthropic"
            ) from e
        self._anthropic = anthropic
        self._client = anthropic.Anthropic()  # resolves key/profile from env

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,  # Haiku 4.5 accepts temperature
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": schema}
            }
        try:
            resp = self._client.messages.create(**kwargs)
        except TypeError:
            # Older SDK without output_config: fall back to prompt-only JSON.
            kwargs.pop("output_config", None)
            resp = self._client.messages.create(**kwargs)
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


# ---------------------------------------------------------------------------
# Recorded (offline / deterministic) provider
# ---------------------------------------------------------------------------


class RecordedProvider:
    """Offline stand-in for the LLM used in regression.

    `rules` is a list of (needle, response_json) pairs. On complete(), the first
    needle found in the `user` prompt selects the recorded JSON response. This
    lets the regression exercise the full plumbing — small-snippet input, JSON
    parse, retry, verdict mapping — with no network and a fixed result.

    The recorded responses represent the judgment a lightweight Claude returns
    for each snippet; the live path (AnthropicProvider) produces them for real.
    """

    def __init__(self, rules: list[tuple[str, str]]):
        self.rules = rules
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, schema: dict | None = None) -> str:
        self.calls.append({"system": system, "user": user, "schema": schema})
        for needle, response in self.rules:
            if needle in user:
                return response
        raise LLMStubUnmatched(
            "RecordedProvider: no rule matched user prompt:\n" + user[:300]
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_provider(role: str = "qa", config: dict | None = None) -> LLMProvider:
    """Build the live provider for a role from config/llm.yaml."""
    rc = role_config(role, config)
    provider = rc["provider"]
    if provider == "anthropic":
        return AnthropicProvider(
            model=rc["model"],
            max_tokens=int(rc.get("max_tokens", 512)),
            temperature=float(rc.get("temperature", 0.0)),
        )
    raise LLMError(f"unknown provider {provider!r} for role {role!r}")

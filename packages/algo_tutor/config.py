"""algo_tutor's config file (SPEC.md §3.4).

`config.yaml` holds the committed defaults; `config.local.yaml` beside it is
merged on top key by key; `--config FILE` replaces both. An unknown key or a
bad value stops startup with the key's path in the message.
"""

import ipaddress
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Provider = Literal["ollama", "openai", "azure"]
TaskName = Literal["report", "hint", "test"]

# Per-task call ceilings when the config doesn't set one (SPEC §12.3).
DEFAULT_TIMEOUTS: dict[TaskName, float] = {"report": 180, "hint": 90, "test": 90}


class ConfigError(ValueError):
    """The config is unreadable or invalid. The message names the file and key."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServerConfig(_Strict):
    host: str = "127.0.0.1"
    port: int = Field(default=4317, ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, host: str) -> str:
        if host == "localhost":
            return host
        try:
            if ipaddress.ip_address(host).is_loopback:
                return host
        except ValueError:
            pass
        raise ValueError(
            f"{host!r} is not a loopback address; algo_tutor only listens on 127.0.0.1"
        )


class ModelConfig(_Strict):
    """The `tutor.default` block: everything a call needs."""

    provider: Provider = "ollama"
    model: str = Field(default="qwen3.6:35b", min_length=1)
    temperature: float = Field(default=0, ge=0, le=2)
    reasoning: bool = False
    timeout_s: float | None = Field(default=None, gt=0)


class TaskOverride(_Strict):
    """A `tutor.tasks.<name>` block: any subset of `ModelConfig`."""

    provider: Provider | None = None
    model: str | None = Field(default=None, min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning: bool | None = None
    timeout_s: float | None = Field(default=None, gt=0)


class TaskConfig(_Strict):
    """One task's merged settings, ready for `get_langchain_client`."""

    provider: Provider
    model: str
    temperature: float
    reasoning: bool
    timeout_s: float


class TutorConfig(_Strict):
    enabled: bool = True
    default: ModelConfig = ModelConfig()
    tasks: dict[TaskName, TaskOverride] = {}

    def task(self, name: TaskName) -> TaskConfig:
        """`default` with the task's overrides applied."""
        override = self.tasks.get(name, TaskOverride())
        merged = self.default.model_dump() | override.model_dump(exclude_none=True)
        if merged["timeout_s"] is None:
            merged["timeout_s"] = DEFAULT_TIMEOUTS[name]
        return TaskConfig.model_validate(merged)


class AppConfig(_Strict):
    server: ServerConfig = ServerConfig()
    tutor: TutorConfig = TutorConfig()


def merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """`override` merged onto `base` key by key; nested mappings merge too."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def _read(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: can't read: {exc.strerror}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: not valid YAML: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: the top level must be a mapping")
    return raw


def _describe(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "(top level)"
        message = "unknown key" if item["type"] == "extra_forbidden" else item["msg"]
        lines.append(f"{where}: {message}")
    return "; ".join(lines)


def load_config(files: Sequence[Path]) -> AppConfig:
    """Read `files` in order (later ones merged on top) and validate the result.

    A file listed after the first may be missing (`config.local.yaml` is
    optional); the first must exist.
    """
    merged: dict[str, Any] = {}
    for index, path in enumerate(files):
        if index > 0 and not path.exists():
            continue
        merged = merge(merged, _read(path))
    try:
        return AppConfig.model_validate(merged)
    except ValidationError as exc:
        names = ", ".join(str(p) for p in files)
        raise ConfigError(f"{names}: {_describe(exc)}") from exc

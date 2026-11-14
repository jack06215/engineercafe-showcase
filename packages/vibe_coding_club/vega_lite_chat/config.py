"""Settings for the app, read from config.yaml next to this file. It is the only source of settings."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG = Path(__file__).with_name("config.yaml")


class _Section(BaseModel):
    # A misspelt key fails at startup instead of silently falling back to a default.
    model_config = ConfigDict(extra="forbid", frozen=True)


class OllamaConfig(_Section):
    """How to reach and run the Ollama model."""

    model: str
    base_url: str
    temperature: float = Field(ge=0)
    keep_alive: str
    timeout_seconds: float = Field(gt=0)
    thinking_default: bool


class ChatConfig(_Section):
    """Settings for the chat model."""

    history_turns: int = Field(ge=0)  # earlier turns the chat model sees, newest last


class TranslatorConfig(_Section):
    """Settings for the chart translator and its repair loop."""

    max_calls: int = Field(ge=1)
    recent_requests: int = Field(ge=0)


class DataConfig(_Section):
    """Limits for loading and profiling the data."""

    row_warning: int = Field(ge=1)
    sample_rows: int = Field(ge=0)
    sample_seed: int
    max_listed_values: int = Field(ge=0)


class ChartConfig(_Section):
    """Settings for drawing charts."""

    height: int = Field(gt=0)


class AppConfig(_Section):
    """The whole app config."""

    ollama: OllamaConfig
    chat: ChatConfig
    translator: TranslatorConfig
    data: DataConfig
    chart: ChartConfig


def load_config(path: Path = DEFAULT_CONFIG) -> AppConfig:
    """Read and validate `path`. Unknown keys and wrong types raise `pydantic.ValidationError`."""
    return AppConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

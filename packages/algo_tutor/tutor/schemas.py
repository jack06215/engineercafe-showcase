"""What Algo-chan must reply with (SPEC §12.4, §12.5).

Two Ollama lessons from vega_lite_chat shape these: required fields come
first (the model writes keys in schema order, and an optional key early on
can stop it short), and data values are never enums (a constrained enum
lets the model pick a value without reading the question). `level` is a
plain string checked after parsing; a bad value goes to the one repair call.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from packages.algo_tutor.domain.enums import HintLevel

Section = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)
]


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportReply(_Reply):
    """The model's report on an attempt, one section per heading."""

    summary: Section = Field(description="Summary: 1-4 short lines.")
    strengths: Section = Field(description="What went well: 1-4 short lines.")
    improvements: Section = Field(description="What to improve: 1-4 short lines.")
    complexity: Section = Field(
        description="Time and space of the submitted code, and whether a better bound exists."
    )
    practice: Section = Field(description="Practise next: 1-4 short lines.")


class HintReply(_Reply):
    """The model's reply to a learner's message, with a one-line hint."""

    reply: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=3000)
    ] = Field(description="What you say to the candidate now. Markdown allowed.")
    hint: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
    ] = Field(
        description="One plain sentence for their notes summarising the nudge, without Markdown."
    )
    level: str = Field(
        description='"small" or "major": major if the reply names or gives away the key idea.'
    )
    analysis: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=800)] | None
    ) = Field(
        default=None,
        description="Only when new_stuck is true: where the attempt stands. Otherwise null.",
    )

    @field_validator("level")
    @classmethod
    def _small_or_major(cls, value: str) -> str:
        level = value.strip().lower()
        if level not in {HintLevel.SMALL, HintLevel.MAJOR}:
            raise ValueError('must be "small" or "major"')
        return level

    @field_validator("analysis")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value or None

    @property
    def hint_level(self) -> HintLevel:
        """The `level` field as a HintLevel."""
        return HintLevel(self.level)


class ConnectionReply(_Reply):
    """Settings → Test connection: the smallest structured call there is."""

    ok: str = Field(description='Always the word "yes".')

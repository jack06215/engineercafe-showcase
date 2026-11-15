"""`AssistantTurn`, the reply that the chat app's translator model writes."""

from pydantic import BaseModel, ConfigDict, Field

from packages.vega_lite_core.chart_spec import ChartSpec


class AssistantTurn(BaseModel):
    """The translator's reply: an optional chart and a short message."""

    # The same config as the models in vega_lite_core.chart_spec. The prompt embeds this model's JSON
    # schema, and extra="forbid" is what puts additionalProperties: false in it.
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )

    # `chart` comes first: Ollama generates keys in schema order, so the message is written after the
    # chart and describes what was actually drawn (constrained decoding can swap in a different chart).
    chart: ChartSpec | None = Field(
        description="The chart to draw, or null to ask a clarifying question or answer without a chart.",
    )
    message: str = Field(
        description="One or two short sentences describing the chart, or the question. No Markdown.",
    )

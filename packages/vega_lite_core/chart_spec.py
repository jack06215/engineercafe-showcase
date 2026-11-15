"""The chart a model writes: a small, checkable subset of Vega-Lite.

Only the shape lives here. Whether a field exists in the data, or suits its column, is
`checks.check_chart`'s job, because that needs the profile. JSON keys use Vega-Lite's own names
(`timeUnit`), which the model already knows; Python attributes are snake_case with aliases.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Mark = Literal["bar", "line", "point", "area", "arc", "rect", "boxplot"]
FieldType = Literal["quantitative", "temporal", "ordinal", "nominal"]
Aggregate = Literal["sum", "mean", "median", "min", "max", "count", "distinct"]
# "day" is the day of the week, as in Vega-Lite.
TimeUnit = Literal[
    "year", "quarter", "month", "yearmonth", "yearmonthdate", "day", "hours"
]
SortOrder = Literal["ascending", "descending", "x", "-x", "y", "-y"]
# "none" turns stacking off; leaving `stack` unset keeps Vega-Lite's default.
Stack = Literal["zero", "normalize", "none"]
FilterOp = Literal["equal", "oneOf", "range", "gt", "gte", "lt", "lte"]
FilterScalar = str | int | float
Channel = Literal["x", "y", "theta", "color", "size", "column", "row"]

# Also the order of ChartSpec's fields, which Ollama emits in schema order (see ChartSpec).
CHANNELS: tuple[Channel, ...] = ("x", "y", "theta", "color", "size", "column", "row")


class _Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
    )


class Encoding(_Model):
    """How one channel shows a column."""

    # Required but nullable: Ollama emits a schema's required keys first and may skip optional
    # ones, and an optional `field` came back missing (`x: {"type": "nominal"}`).
    field: str | None = Field(
        description="Column name exactly as in the profile. null only with aggregate=count.",
    )
    type: FieldType
    aggregate: Aggregate | None = None
    time_unit: TimeUnit | None = Field(default=None, alias="timeUnit")
    bin: bool = False
    sort: SortOrder | None = None
    stack: Stack | None = Field(
        default=None, description="Only for bar and area marks."
    )
    title: str | None = None


class Filter(_Model):
    """A condition on one column that rows must meet."""

    field: str
    op: FilterOp
    value: FilterScalar | list[FilterScalar] = Field(
        description=(
            "A number, an ISO date string, or a category value from the profile. "
            "range takes [low, high]; oneOf takes a list. With timeUnit, a value in that unit "
            "(year: 2025, month: 1-12, yearmonth: '2025-03')."
        ),
    )
    time_unit: TimeUnit | None = Field(default=None, alias="timeUnit")


class TopN(_Model):
    """Keep the top *n* categories of a column, ranked by another column's sum."""

    field: str = Field(
        description="The column whose categories are ranked, e.g. a region."
    )
    by: str = Field(description="The numeric column whose sum decides the ranking.")
    n: int = Field(ge=1, le=50)


def _require_filters(schema: dict[str, Any]) -> None:
    schema["required"] = [*schema.get("required", []), "filters"]


class ChartSpec(_Model):
    """A chart that the model asks for, before it is compiled to Vega-Lite."""

    # `filters` is required in the JSON schema (Python keeps the [] default) and sits right after
    # `mark`. Optional, and last, the model could close the object without it: after a 2025-only
    # chart, 「地域別の総売上を比較する棒グラフ」 lost the filter while the message still said 2025年.
    # Required keys come out first, so it must come first in the schema too; behind the channels,
    # a model that had just written the filters skipped x and y and went on to top_n.
    model_config = ConfigDict(json_schema_extra=_require_filters)

    mark: Mark
    filters: list[Filter] = Field(default_factory=list)
    title: str | None = None
    x: Encoding | None = None
    y: Encoding | None = None
    # theta sits before color: Ollama emits keys in schema order, so with color first a model
    # that writes a pie's theta first can no longer add the color that splits the slices.
    theta: Encoding | None = Field(
        default=None, description="Only for the arc mark, which requires it."
    )
    color: Encoding | None = None
    size: Encoding | None = None
    column: Encoding | None = None
    row: Encoding | None = None
    top_n: TopN | None = None

    def encodings(self) -> list[tuple[Channel, Encoding]]:
        """The channels that are set, in `CHANNELS` order."""
        return [
            (channel, enc)
            for channel in CHANNELS
            if (enc := getattr(self, channel)) is not None
        ]

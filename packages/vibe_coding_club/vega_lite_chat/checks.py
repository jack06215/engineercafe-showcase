"""Check a `ChartSpec` against the data's profile: do the columns exist, and does each use suit its column?

The errors are English sentences that say how to fix the chart, because they go back to the model as the
repair request (DESIGN.md §5). An empty list means the chart can be compiled.
"""

import datetime
import difflib
import re

from packages.vibe_coding_club.vega_lite_chat.chart_spec import (
    Channel,
    ChartSpec,
    Encoding,
    FieldType,
    Filter,
    FilterScalar,
    TimeUnit,
)
from packages.vibe_coding_club.vega_lite_chat.profile import (
    ColumnProfile,
    DataProfile,
    FieldGuess,
)

# Which encoding types each kind of column may be drawn as.
ALLOWED_TYPES: dict[FieldGuess, tuple[FieldType, ...]] = {
    "quantitative": ("quantitative", "ordinal", "nominal"),
    "temporal": ("temporal", "ordinal", "nominal"),
    "nominal": ("nominal", "ordinal"),
}
NUMERIC_AGGREGATES = frozenset({"sum", "mean", "median", "min", "max"})
NEEDS_X_AND_Y = frozenset({"bar", "line", "area", "point", "boxplot"})
STACKABLE_MARKS = frozenset({"bar", "area"})
RANGE_OPS = frozenset({"gt", "gte", "lt", "lte", "range"})
_KIND = {"quantitative": "numeric", "temporal": "date", "nominal": "text"}
_YEAR_MONTH = re.compile(r"\d{4}-\d{2}")
# The integer each time unit's filter value must lie in (yearmonth and yearmonthdate are strings).
_UNIT_RANGE: dict[TimeUnit, tuple[int, int]] = {
    "year": (1000, 9999),
    "quarter": (1, 4),
    "month": (1, 12),
    "day": (1, 7),  # Vega-Lite counts Monday as 1
    "hours": (0, 23),
}


def check_chart(spec: ChartSpec, profile: DataProfile) -> list[str]:
    errors: list[str] = []
    for channel, encoding in spec.encodings():
        errors += _check_encoding(channel, encoding, spec, profile)
    errors += _check_mark(spec)
    for index, filter_ in enumerate(spec.filters):
        errors += _check_filter(index, filter_, profile)
    if spec.top_n is not None:
        top_n = spec.top_n
        known = _known(top_n.field, "top_n.field", profile, errors)
        by = _known(top_n.by, "top_n.by", profile, errors)
        if known is not None and by is not None and by.guess != "quantitative":
            errors.append(
                f"top_n.by: column `{by.name}` holds {_KIND[by.guess]} values; "
                "rank by a numeric column"
            )
    return errors


def _known(
    name: str, where: str, profile: DataProfile, errors: list[str]
) -> ColumnProfile | None:
    """The column called `name`, or None after recording an error that lists the real columns."""
    column = profile.column(name)
    if column is None:
        hint = ""
        # `売上` for `売上（万円）`: a unit suffix defeats difflib's ratio, so try containment first.
        close = [
            other
            for other in profile.names()
            if name and (name in other or other in name)
        ]
        close = close or difflib.get_close_matches(name, profile.names(), n=1)
        if close:
            hint = f" (did you mean `{close[0]}`?)"
        errors.append(
            f"unknown column `{name}` in {where}{hint}; columns are: {', '.join(profile.names())}"
        )
    return column


def _check_encoding(
    channel: Channel, encoding: Encoding, spec: ChartSpec, profile: DataProfile
) -> list[str]:
    errors: list[str] = []
    aggregate = encoding.aggregate
    if encoding.stack is not None:
        if spec.mark not in STACKABLE_MARKS:
            errors.append(
                f"{channel}: stack only applies to bar and area marks, not `{spec.mark}`"
            )
        elif channel not in ("x", "y"):
            errors.append(f"{channel}: stack only goes on the x or y channel")
    if aggregate is not None and encoding.type != "quantitative":
        errors.append(
            f"{channel}: aggregate `{aggregate}` gives numbers; use type quantitative"
        )
    if spec.mark == "boxplot" and aggregate is not None:
        errors.append(
            f"{channel}: a boxplot aggregates by itself; remove aggregate `{aggregate}`"
        )
    if encoding.field is None:
        if aggregate != "count":
            errors.append(
                f"{channel}: `field` is null; only aggregate count may leave it null"
            )
        return errors
    column = _known(encoding.field, channel, profile, errors)
    if column is None:
        return errors
    kind = _KIND[column.guess]
    allowed = ALLOWED_TYPES[column.guess]
    if aggregate is None and encoding.type not in allowed:
        errors.append(
            f"{channel}: column `{column.name}` holds {kind} values, so type `{encoding.type}` "
            f"is not allowed; use one of: {', '.join(allowed)}"
        )
    if aggregate in NUMERIC_AGGREGATES and column.guess != "quantitative":
        errors.append(
            f"{channel}: aggregate `{aggregate}` needs a numeric column, but `{column.name}` holds "
            f"{kind} values; use count or distinct instead"
        )
    if encoding.bin and column.guess != "quantitative":
        errors.append(
            f"{channel}: bin needs a numeric column, but `{column.name}` holds {kind} values"
        )
    if encoding.time_unit is not None and column.guess != "temporal":
        errors.append(
            f"{channel}: timeUnit needs a date column, but `{column.name}` holds {kind} values"
        )
    if (
        column.guess == "temporal"
        and encoding.type in ("ordinal", "nominal")
        and encoding.time_unit is None
    ):
        errors.append(
            f"{channel}: date column `{column.name}` drawn as {encoding.type} needs a timeUnit "
            "(e.g. year, month or yearmonth)"
        )
    return errors


def _check_mark(spec: ChartSpec) -> list[str]:
    errors: list[str] = []
    if spec.mark == "arc":
        if spec.theta is None:
            errors.append(
                "an arc mark needs theta (usually the numeric column, often with aggregate sum)"
            )
        # Without color a pie is one full circle. The model once split "by region" with top_n.
        if spec.color is None:
            errors.append(
                "an arc mark needs color: the category column that splits the slices "
                "(theta holds the value)"
            )
    elif spec.theta is not None:
        errors.append(
            f"theta only applies to the arc mark, not `{spec.mark}`; use x and y instead"
        )
    if spec.mark in NEEDS_X_AND_Y:
        missing = [channel for channel in ("x", "y") if getattr(spec, channel) is None]
        if missing:
            errors.append(
                f"a `{spec.mark}` mark needs both x and y; set {' and '.join(missing)}"
            )
    if spec.mark == "rect":
        missing = [
            channel for channel in ("x", "y", "color") if getattr(spec, channel) is None
        ]
        if missing:
            errors.append(
                f"a rect (heatmap) mark needs x, y and color; set {', '.join(missing)}"
            )
    if spec.mark == "boxplot":
        axes = [enc for enc in (spec.x, spec.y) if enc is not None]
        if axes and not any(enc.type == "quantitative" for enc in axes):
            errors.append(
                "a boxplot needs one quantitative axis (the values) and one category axis"
            )
    return errors


def _check_filter(index: int, filter_: Filter, profile: DataProfile) -> list[str]:
    errors: list[str] = []
    where = f"filters[{index}]"
    column = _known(filter_.field, where, profile, errors)
    if column is None:
        return errors
    kind = _KIND[column.guess]
    unit = filter_.time_unit
    if unit is not None and column.guess != "temporal":
        errors.append(
            f"{where}: timeUnit needs a date column, but `{column.name}` holds {kind} values"
        )
        return errors
    if filter_.op in RANGE_OPS and column.guess == "nominal":
        errors.append(
            f"{where}: `{filter_.op}` needs a numeric or date column, but `{column.name}` holds text; "
            "use equal or oneOf"
        )
        return errors
    value = filter_.value
    if filter_.op == "range":
        if not isinstance(value, list) or len(value) != 2:
            return [*errors, f"{where}: range takes a list of two values, [low, high]"]
        values = value
    elif filter_.op == "oneOf":
        if not isinstance(value, list) or not value:
            return [*errors, f"{where}: oneOf takes a non-empty list of values"]
        values = value
    else:
        if isinstance(value, list):
            return [
                *errors,
                f"{where}: `{filter_.op}` takes a single value, not a list",
            ]
        values = [value]
    for item in values:
        problem = _value_problem(item, column, unit)
        if problem is not None:
            errors.append(f"{where}: {problem}")
    return errors


def _value_problem(
    value: FilterScalar, column: ColumnProfile, unit: TimeUnit | None
) -> str | None:
    """Why `value` can't be compared with `column`, or None when it can."""
    if column.guess == "quantitative":
        if isinstance(value, str):
            return f"column `{column.name}` is numeric; write {value!r} as a number"
        return None
    if column.guess == "temporal":
        return _date_problem(value, column.name, unit)
    if column.values is not None and str(value) not in column.values:
        return (
            f"`{value}` is not a value of column `{column.name}`; "
            f"its values are: {', '.join(column.values)}"
        )
    return None


def _date_problem(value: FilterScalar, name: str, unit: TimeUnit | None) -> str | None:
    if unit is not None and unit in _UNIT_RANGE:
        low, high = _UNIT_RANGE[unit]
        if isinstance(value, str) or not float(value).is_integer():
            return f"with timeUnit {unit}, write a whole number from {low} to {high}, not {value!r}"
        if not low <= value <= high:
            return f"with timeUnit {unit}, the value must be from {low} to {high}, not {value}"
        return None
    if unit == "yearmonth":
        if not isinstance(value, str) or not _YEAR_MONTH.fullmatch(value):
            return (
                f"with timeUnit yearmonth, write the value as 'YYYY-MM', not {value!r}"
            )
        return None if parse_iso(value) else f"{value!r} is not a real month"
    if not isinstance(value, str):
        return f"column `{name}` holds dates; write {value!r} as an ISO date string like '2025-01-31'"
    if parse_iso(value) is None:
        return f"column `{name}` holds dates; {value!r} is not an ISO date like '2025-01-31'"
    return None


def parse_iso(value: str) -> datetime.datetime | None:
    """An ISO date or date-time ('2025-01-31', '2025-01', '2025-01-31T10:00'), or None."""
    if _YEAR_MONTH.fullmatch(value):
        value += "-01"
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None

"""`ChartSpec` to a Vega-Lite spec, and the check against Vega-Lite's JSON schema. Pure functions.

The compiled spec carries no data: the app passes the DataFrame next to it (`st.vega_lite_chart(df, spec)`).
Dates reach the browser as naive timestamps, which Vega-Lite reads as UTC, so every time unit, date filter
and date scale is compiled in UTC. In local time, a viewer west of Greenwich would see January's numbers
under December.
"""

import datetime
import functools
import importlib.resources
import json
import re
from collections.abc import Mapping
from typing import Any

import jsonschema
import pandas
from altair.vegalite.v6.schema import SCHEMA_URL

from packages.vega_lite_core.chart_spec import (
    ChartSpec,
    Encoding,
    Filter,
    FilterScalar,
    TimeUnit,
)
from packages.vega_lite_core.checks import parse_iso
from packages.vega_lite_core.profile import (
    DataProfile,
    plain,
)

# Working columns for top_n; the prefix keeps them clear of real column names.
TOTAL = "__vlc_total"
RANK = "__vlc_rank"
# Channels whose field definition takes a scale; facets (column/row) don't.
_SCALED = frozenset({"x", "y", "color", "size", "theta"})
_ESCAPED = re.compile(r"([.\[\]\\])")


def escape_field(name: str) -> str:
    """A column name as a Vega-Lite field: `.` and brackets would otherwise read as nested access."""
    return _ESCAPED.sub(r"\\\1", name)


def compile_chart(
    spec: ChartSpec, profile: DataProfile, *, height: int
) -> dict[str, Any]:
    """Compile *spec* into a Vega-Lite spec for the data in *profile*."""
    faceted = spec.column is not None or spec.row is not None
    compiled: dict[str, Any] = {"$schema": SCHEMA_URL}
    if spec.title:
        compiled["title"] = spec.title
    # A container width doesn't apply to faceted views; each cell keeps Vega-Lite's default width.
    if not faceted:
        compiled["width"] = "container"
    compiled["height"] = height // 2 if spec.row is not None else height
    transform: list[dict[str, Any]] = [
        {"filter": _predicate(filter_, profile)} for filter_ in spec.filters
    ]
    if spec.top_n is not None:
        field, by = escape_field(spec.top_n.field), escape_field(spec.top_n.by)
        transform += [
            {
                "joinaggregate": [{"op": "sum", "field": by, "as": TOTAL}],
                "groupby": [field],
            },
            {
                "window": [{"op": "dense_rank", "as": RANK}],
                "sort": [{"field": TOTAL, "order": "descending"}],
            },
            {"filter": {"field": RANK, "lte": spec.top_n.n}},
        ]
    if transform:
        compiled["transform"] = transform
    compiled["mark"] = _mark(spec)
    encoding: dict[str, Any] = {
        channel: _field_def(channel, enc) for channel, enc in spec.encodings()
    }
    # A boxplot is a composite mark with tooltips of its own.
    if spec.mark != "boxplot":
        encoding["tooltip"] = _tooltip(spec)
    compiled["encoding"] = encoding
    return compiled


def _mark(spec: ChartSpec) -> dict[str, Any]:
    mark: dict[str, Any] = {"type": spec.mark}
    if spec.mark == "line":
        mark["point"] = True  # gives each value a point to hover for its tooltip
    return mark


def _utc(unit: TimeUnit) -> str:
    return f"utc{unit}"


def _field_def(channel: str, enc: Encoding) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if enc.field is not None:
        out["field"] = escape_field(enc.field)
        if out["field"] != enc.field and not enc.title:
            out["title"] = enc.field  # the default title would show the backslashes
    out["type"] = enc.type
    if enc.aggregate is not None:
        out["aggregate"] = enc.aggregate
    if enc.time_unit is not None:
        out["timeUnit"] = _utc(enc.time_unit)
    elif enc.type == "temporal" and channel in _SCALED:
        out["scale"] = {"type": "utc"}
    if enc.bin:
        out["bin"] = True
    if enc.sort is not None:
        out["sort"] = enc.sort
    if enc.stack is not None:
        out["stack"] = None if enc.stack == "none" else enc.stack
    if enc.title:
        out["title"] = enc.title
    return out


def _tooltip(spec: ChartSpec) -> list[dict[str, Any]]:
    """One tooltip line per encoded field, aggregated and binned the same way so the numbers match."""
    tooltip: list[dict[str, Any]] = []
    for channel, enc in spec.encodings():
        entry = {
            key: value
            for key, value in _field_def(channel, enc).items()
            if key in ("field", "type", "aggregate", "timeUnit", "bin", "title")
        }
        if enc.type == "temporal" and enc.time_unit is None:
            entry["timeUnit"] = (
                "utcyearmonthdate"  # a readable date instead of a local timestamp
            )
        if entry not in tooltip:
            tooltip.append(entry)
    return tooltip


def _predicate(filter_: Filter, profile: DataProfile) -> dict[str, Any] | str:
    column = profile.column(filter_.field)
    guess = column.guess if column is not None else "nominal"
    if guess == "temporal":
        return date_expression(filter_)
    predicate: dict[str, Any] = {"field": escape_field(filter_.field)}

    def convert(value: FilterScalar) -> FilterScalar:
        if guess == "nominal":
            return str(value)  # the data holds text, and Vega-Lite compares with ===
        return value

    value = filter_.value
    predicate[filter_.op] = (
        [convert(item) for item in value] if isinstance(value, list) else convert(value)
    )
    return predicate


# Date filters compile to Vega expressions over the UTC date parts, never to Vega-Lite's own field
# predicates. Checked in Streamlit's frontend on 2026-10-24: a timeUnit predicate with equal or oneOf
# against a DateTime dropped every row, and one against a plain number shifted the year by a month.
_UNIT_KEY: dict[TimeUnit, str] = {
    "year": "utcyear({d})",
    "quarter": "utcquarter({d})",
    "month": "(utcmonth({d}) + 1)",
    "day": "((utcday({d}) + 6) % 7 + 1)",  # Monday 1 ... Sunday 7, the numbering checks accepts
    "hours": "utchours({d})",
    "yearmonth": "(utcyear({d}) * 100 + utcmonth({d}) + 1)",
    "yearmonthdate": "(utcyear({d}) * 10000 + (utcmonth({d}) + 1) * 100 + utcdate({d}))",
}
_COMPARE = {"equal": "===", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


def date_expression(filter_: Filter) -> str:
    """A date filter as a Vega expression. The filter has already passed `check_chart`."""
    datum = f"datum[{json.dumps(filter_.field, ensure_ascii=False)}]"
    unit = filter_.time_unit
    key = _UNIT_KEY[unit].format(d=datum) if unit is not None else f"time({datum})"
    value = filter_.value
    if isinstance(value, list):
        keys = [str(date_key(item, unit)) for item in value]
        if filter_.op == "range":
            return f"{key} >= {keys[0]} && {key} <= {keys[1]}"
        return f"indexof([{', '.join(keys)}], {key}) >= 0"  # oneOf
    return f"{key} {_COMPARE[filter_.op]} {date_key(value, unit)}"


def date_key(value: FilterScalar, unit: TimeUnit | None) -> int:
    """A checked filter value as the number its date expression compares against."""
    if unit in ("year", "quarter", "month", "day", "hours"):
        return int(value)
    parsed = parse_iso(str(value))
    if parsed is None:
        raise ValueError(f"not an ISO date: {value!r}")
    if unit == "yearmonth":
        return parsed.year * 100 + parsed.month
    if unit == "yearmonthdate":
        return parsed.year * 10000 + parsed.month * 100 + parsed.day
    # No unit: the instant in epoch milliseconds. Naive dates reach the browser as UTC.
    return int(parsed.replace(tzinfo=datetime.UTC).timestamp() * 1000)


@functools.cache
def _validator() -> Any:
    resource = (
        importlib.resources.files("altair.vegalite.v6.schema") / "vega-lite-schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    return jsonschema.validators.validator_for(schema)(schema)


def vega_lite_errors(spec: Mapping[str, Any]) -> list[str]:
    """Where `spec` breaks Vega-Lite's JSON schema (the version altair ships). Empty means valid."""
    # The schema requires top-level data, which the compiled spec leaves to the app; stand in a named
    # source for it.
    document = {"data": {"name": "table"}, **spec}
    errors: list[str] = []
    for error in _validator().iter_errors(document):
        # The top-level error of an anyOf says only "not valid under any"; take its most specific cause.
        best = jsonschema.exceptions.best_match([error])
        path = "/".join(str(part) for part in best.absolute_path) or "(root)"
        errors.append(f"{path}: {best.message}"[:300])
    return sorted(errors)


def with_inline_data(spec: Mapping[str, Any], df: pandas.DataFrame) -> dict[str, Any]:
    """`spec` with the rows embedded as `data.values`, for the download (it opens in the Vega Editor)."""
    values = [
        {str(name): _json_value(value) for name, value in row.items()}
        for row in df.to_dict(orient="records")
    ]
    return {**spec, "data": {"values": values}}


def _json_value(value: object) -> object:
    if isinstance(value, datetime.datetime):
        # A date-only ISO string and a "Z" timestamp both parse as UTC in the browser, like the compiled spec.
        if value.time() == datetime.time():
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if hasattr(value, "item") and isinstance(value.item(), bool):  # numpy bool
        return value.item()
    if isinstance(value, bool):
        return value
    return plain(value)

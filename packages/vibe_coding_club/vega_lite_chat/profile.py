"""A DataFrame summarised for the LLM: column types, ranges and a few rows, never the data itself."""

import datetime
import math
from dataclasses import dataclass
from typing import Any, Literal

import pandas
import yaml

FieldGuess = Literal["quantitative", "temporal", "nominal"]
Scalar = str | int | float | None


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str  # pandas' dtype name: "int64", "float64", "str", "datetime64[ns]"
    guess: FieldGuess
    distinct: int
    nulls: int
    min: Scalar  # numeric and date columns only; dates as ISO strings
    max: Scalar
    values: (
        tuple[str, ...] | None
    )  # every value of a text column with few enough of them


@dataclass(frozen=True)
class DataProfile:
    rows: int
    columns: tuple[ColumnProfile, ...]
    sample: tuple[
        dict[str, Scalar], ...
    ]  # chosen at random with a fixed seed, in file order

    def names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def column(self, name: str) -> ColumnProfile | None:
        return next((column for column in self.columns if column.name == name), None)


def guess_type(series: pandas.Series) -> FieldGuess:
    """Numbers are quantitative, dates temporal, everything else (bool included) nominal."""
    if pandas.api.types.is_bool_dtype(series):
        return "nominal"
    if pandas.api.types.is_numeric_dtype(series):
        return "quantitative"
    if pandas.api.types.is_datetime64_any_dtype(series):
        return "temporal"
    return "nominal"


def plain(value: object) -> Scalar:
    """A cell as a YAML-friendly scalar: numpy numbers to int/float, dates to ISO, missing to None."""
    if value is None or value is pandas.NaT:
        return None
    if isinstance(value, datetime.datetime):
        if value.time() == datetime.time():
            return value.strftime("%Y-%m-%d")
        return value.isoformat(timespec="minutes")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        number = value
    elif hasattr(value, "item"):  # numpy scalars
        number = value.item()
        if isinstance(number, bool):
            return str(number)
    else:
        return str(value)
    if isinstance(number, float):
        if math.isnan(number):
            return None
        return (
            int(number)
            if number.is_integer() and abs(number) < 2**53
            else float(number)
        )
    return int(number)


def profile_frame(
    df: pandas.DataFrame,
    *,
    sample_rows: int,
    seed: int,
    max_listed_values: int,
) -> DataProfile:
    columns = tuple(
        _profile_column(str(name), df[name], max_listed_values) for name in df.columns
    )
    picked = df.sample(n=min(sample_rows, len(df)), random_state=seed).sort_index()
    sample = tuple(
        {str(name): plain(value) for name, value in row.items()}
        for _, row in picked.iterrows()
    )
    return DataProfile(rows=len(df), columns=columns, sample=sample)


def _profile_column(
    name: str, series: pandas.Series, max_listed_values: int
) -> ColumnProfile:
    guess = guess_type(series)
    distinct = int(series.nunique(dropna=True))
    present = series.dropna()
    low: Scalar = None
    high: Scalar = None
    if guess in ("quantitative", "temporal") and not present.empty:
        low, high = plain(present.min()), plain(present.max())
    values = None
    if guess == "nominal" and distinct <= max_listed_values:
        values = tuple(dict.fromkeys(str(plain(value)) for value in present))
    return ColumnProfile(
        name=name,
        dtype=str(series.dtype),
        guess=guess,
        distinct=distinct,
        nulls=int(series.isna().sum()),
        min=low,
        max=high,
        values=values,
    )


def profile_yaml(profile: DataProfile) -> str:
    """The profile as compact YAML for the prompt. Japanese column names stay readable."""
    columns: list[dict[str, Any]] = []
    for column in profile.columns:
        entry: dict[str, Any] = {
            "name": column.name,
            "dtype": column.dtype,
            "guess": column.guess,
            "distinct": column.distinct,
            "nulls": column.nulls,
        }
        if column.min is not None:
            entry["min"] = column.min
            entry["max"] = column.max
        if column.values is not None:
            entry["values"] = list(column.values)
        columns.append(entry)
    document = {
        "rows": profile.rows,
        "columns": columns,
        "sample": [dict(row) for row in profile.sample],
    }
    return yaml.safe_dump(
        document,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=None,
        width=120,
    )

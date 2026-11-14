"""CSV bytes to a DataFrame: UTF-8 only, the header in row 1, text dates turned into datetimes."""

import csv
import io
import re

import pandas

NOT_UTF8 = "UTF-8 の CSV ではありません。Excel なら「CSV UTF-8」で保存してください"

# Every non-null value of a text column has to match one of these for it to become a date column.
_ISO = re.compile(r"\d{4}-\d{2}(-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?)?")
_SLASH = re.compile(r"(\d{4})/(\d{1,2})(?:/(\d{1,2}))?")


class InputError(ValueError):
    """The file can't be used. The message is Japanese, shown to the user as-is."""


def load_csv(data: bytes) -> pandas.DataFrame:
    try:
        # utf-8-sig drops the BOM Excel's "CSV UTF-8" writes, so it can't stick to the first header.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputError(NOT_UTF8) from error
    header = next(csv.reader(io.StringIO(text)), [])
    if not any(name.strip() for name in header):
        raise InputError("CSV が空です。1 行目に見出しが必要です")
    # pandas would quietly rename a repeated header to `名前.1`, so check the raw row first.
    repeated = sorted({name for name in header if header.count(name) > 1})
    if repeated:
        raise InputError(f"見出しが重複しています: {', '.join(repeated)}")
    try:
        df = pandas.read_csv(io.StringIO(text))
    except (pandas.errors.ParserError, pandas.errors.EmptyDataError) as error:
        raise InputError(f"CSV を読み込めませんでした: {error}") from error
    if df.empty:
        raise InputError("データの行がありません。見出しの下に 1 行以上必要です")
    for name in df.columns:
        if _is_text(df[name]):
            df[name] = _as_dates(df[name])
    return df


def _is_text(series: pandas.Series) -> bool:
    return pandas.api.types.is_string_dtype(series) or series.dtype == object


def _as_dates(series: pandas.Series) -> pandas.Series:
    """The column as datetimes when every value is an ISO or slash date, otherwise unchanged."""
    values = series.astype("string").str.strip()
    present = values.dropna()
    if present.empty:
        return series
    try:
        if present.map(lambda value: _ISO.fullmatch(value) is not None).all():
            return pandas.to_datetime(values, format="ISO8601")
        if present.map(lambda value: _SLASH.fullmatch(value) is not None).all():
            return pandas.to_datetime(
                values.map(_slash_to_iso, na_action="ignore"), format="%Y-%m-%d"
            )
    except ValueError:  # matches the pattern but isn't a real date, like 2025-13-45
        return series
    return series


def _slash_to_iso(value: str) -> str:
    match = _SLASH.fullmatch(value)
    assert match is not None  # only called on values that matched
    year, month, day = match.group(1), match.group(2), match.group(3) or "1"
    return f"{year}-{int(month):02d}-{int(day):02d}"

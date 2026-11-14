"""Regenerate the synthetic sample CSVs (sales_by_region.csv, stores.csv) with a fixed seed.

bazel run //packages/vibe_coding_club/vega_lite_chat:make_samples

The weather sample is real JMA data and is not generated here.
"""

import argparse
import os
import random
from pathlib import Path

import pandas

SEED = 20261024
PACKAGE = "packages/vibe_coding_club/vega_lite_chat"

REGIONS = ("福岡", "東京", "大阪", "名古屋", "札幌")
# Monthly sales (万円) in January 2024, before seasonality.
REGION_BASE = {"福岡": 900, "東京": 2000, "大阪": 1400, "名古屋": 1000, "札幌": 700}
# Year-on-year growth for 2025; 福岡 grows fastest so the charts have a story to tell.
REGION_GROWTH = {"福岡": 0.14, "東京": 0.04, "大阪": 0.05, "名古屋": 0.03, "札幌": 0.02}
# Summer and the December peak, a quiet February.
SEASON = (0.85, 0.78, 0.95, 1.0, 1.0, 0.94, 1.06, 1.12, 0.95, 1.0, 1.05, 1.32)
AVERAGE_TICKET_YEN = {
    "福岡": 3200,
    "東京": 4100,
    "大阪": 3700,
    "名古屋": 3500,
    "札幌": 3300,
}

STORES = {
    "福岡": (
        "天神店",
        "博多駅前店",
        "大濠公園店",
        "西新店",
        "姪浜店",
        "香椎店",
        "大橋店",
        "千早店",
    ),
    "北九州": ("小倉駅前店", "黒崎店", "八幡店", "戸畑店", "門司港店", "折尾店"),
    "久留米": (
        "久留米駅前店",
        "西鉄久留米店",
        "合川店",
        "津福店",
        "善導寺店",
        "荒木店",
    ),
    "熊本": ("熊本駅前店", "下通店", "健軍店", "光の森店", "長嶺店"),
    "佐賀": ("佐賀駅前店", "鳥栖店", "唐津店", "伊万里店", "武雄店"),
}
# 月商 (万円) per m² of floor area.
STORE_YIELD = {"福岡": 1.9, "北九州": 1.5, "久留米": 1.4, "熊本": 1.6, "佐賀": 1.3}


def sales_by_region(rng: random.Random) -> pandas.DataFrame:
    """Generate two years of monthly sales by region."""
    rows = []
    for year in (2024, 2025):
        for month in range(1, 13):
            for region in REGIONS:
                growth = 1 + REGION_GROWTH[region] if year == 2025 else 1.0
                sales = (
                    REGION_BASE[region]
                    * SEASON[month - 1]
                    * growth
                    * rng.gauss(1, 0.04)
                )
                count = sales * 10_000 / AVERAGE_TICKET_YEN[region] * rng.gauss(1, 0.03)
                rows.append(
                    {
                        "月": f"{year}-{month:02d}",
                        "地域": region,
                        "売上（万円）": round(sales),
                        "件数": round(count),
                    }
                )
    return pandas.DataFrame(rows)


def stores(rng: random.Random) -> pandas.DataFrame:
    """Generate one row per store with its floor area and sales."""
    rows = []
    for region, names in STORES.items():
        for name in names:
            area = rng.randrange(300, 1500, 10)
            sales = area * STORE_YIELD[region] * rng.gauss(1, 0.12)
            rows.append(
                {
                    "店舗名": name,
                    "地域": region,
                    "床面積（m²）": area,
                    "月商（万円）": round(sales),
                }
            )
    return pandas.DataFrame(rows)


def default_out_dir() -> Path:
    """Return sample_data/ in the source tree, also under `bazel run`."""
    # `bazel run` starts in the runfiles tree; write into the source tree instead.
    workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if workspace:
        return Path(workspace) / PACKAGE / "sample_data"
    return Path(__file__).with_name("sample_data")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out-dir", type=Path, default=None, help="where to write the CSVs"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Write the sample CSVs."""
    args = build_parser().parse_args(argv)
    out_dir: Path = args.out_dir or default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    for name, frame in (
        ("sales_by_region.csv", sales_by_region(rng)),
        ("stores.csv", stores(rng)),
    ):
        path = out_dir / name
        frame.to_csv(path, index=False, encoding="utf-8")
        print(f"wrote {path} ({len(frame)} rows)")


if __name__ == "__main__":
    main()

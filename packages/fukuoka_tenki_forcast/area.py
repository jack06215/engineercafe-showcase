"""The JMA codes that make up one place's forecast."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Area:
    """Which parts of JMA's data describe one place.

    Office and region codes are listed in
    https://www.jma.go.jp/bosai/common/const/area.json, stations and their
    positions in https://www.jma.go.jp/bosai/amedas/const/amedastable.json.
    """

    office: str  # 府県予報区: picks the forecast JSON to download
    # 一次細分区域: detailed weather, wind, waves and pops, and the 3-hourly forecast
    region: str
    weekly_region: str  # weekly weather and pops
    station: str  # temperatures, both detailed and weekly
    lat: float  # the station's position, where the radar map is centred
    lon: float


FUKUOKA: Final[Area] = Area(
    office="400000",  # 福岡県
    region="400010",  # 福岡地方
    weekly_region="400000",  # 福岡県
    station="82182",  # 福岡
    lat=33 + 34.9 / 60,  # 33°34.9'N
    lon=130 + 22.5 / 60,  # 130°22.5'E
)

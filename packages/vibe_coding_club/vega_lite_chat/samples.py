"""The sample CSVs behind the 「見本で試す」 buttons. They double as test and live-eval fixtures."""

from dataclasses import dataclass
from pathlib import Path

SAMPLES_DIR = Path(__file__).with_name("sample_data")


@dataclass(frozen=True)
class Sample:
    file_name: str
    label: str  # the button label
    credit: str | None = None  # shown under the chat when the sample is loaded

    @property
    def path(self) -> Path:
        return SAMPLES_DIR / self.file_name

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()


# fukuoka_weather.csv (JMA data, credited 出典: 気象庁) joins between the two once its real data is
# committed; DESIGN.md §3.3.
SAMPLES: tuple[Sample, ...] = (
    Sample("sales_by_region.csv", "地域別の月次売上"),
    Sample("stores.csv", "店舗の床面積と月商"),
)


def sample_named(file_name: str) -> Sample:
    for sample in SAMPLES:
        if sample.file_name == file_name:
            return sample
    raise KeyError(file_name)

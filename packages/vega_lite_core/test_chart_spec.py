"""Tests for chart_spec.py: the key order of ChartSpec's JSON schema.

Ollama writes a schema's keys in order, required ones first, and may skip optional ones. The order is
why `filters` survives a refinement and a pie gets its color (vega_lite_chat's DESIGN.md §7.4).
"""

import unittest
from typing import Any

from packages.vega_lite_core.chart_spec import CHANNELS, ChartSpec


def _schema() -> dict[str, Any]:
    return ChartSpec.model_json_schema(by_alias=True)


class SchemaOrderTest(unittest.TestCase):
    def test_only_mark_and_filters_are_required(self) -> None:
        self.assertEqual(_schema()["required"], ["mark", "filters"])

    def test_filters_come_right_after_mark(self) -> None:
        self.assertEqual(list(_schema()["properties"])[:2], ["mark", "filters"])

    def test_channels_keep_their_order(self) -> None:
        keys = [key for key in _schema()["properties"] if key in CHANNELS]
        self.assertEqual(keys, list(CHANNELS))
        self.assertLess(keys.index("theta"), keys.index("color"))

    def test_python_callers_may_leave_filters_out(self) -> None:
        self.assertEqual(ChartSpec(mark="bar").filters, [])


if __name__ == "__main__":
    unittest.main()

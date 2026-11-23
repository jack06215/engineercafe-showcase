import unittest

from packages.monkeytype_analysis_console import palette

MIN_CONTRAST = 3.0


class PaletteTest(unittest.TestCase):
    def test_every_colour_reads_on_both_backgrounds(self) -> None:
        for colour in (*palette.BANDS, palette.MAIN, palette.SUB, palette.ERROR):
            for background in (palette.LIGHT_BACKGROUND, palette.DARK_BACKGROUND):
                with self.subTest(colour=colour, background=background):
                    self.assertGreaterEqual(
                        palette.contrast_ratio(colour, background), MIN_CONTRAST
                    )

    def test_five_distinct_bands(self) -> None:
        self.assertEqual(len(set(palette.BANDS)), 5)

    def test_contrast_ratio_limits(self) -> None:
        self.assertAlmostEqual(palette.contrast_ratio("#000000", "#FFFFFF"), 21)
        self.assertAlmostEqual(palette.contrast_ratio("#777777", "#777777"), 1)


if __name__ == "__main__":
    unittest.main()

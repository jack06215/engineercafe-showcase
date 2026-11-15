import unittest

from packages.fukuoka_tenki_forcast.fixtures import (
    nowcast_frames,
)
from packages.fukuoka_tenki_forcast.model import (
    from_now,
    now_index,
)


class FramesTest(unittest.TestCase):
    def test_now_is_the_newest_observation(self) -> None:
        frames = nowcast_frames()
        self.assertEqual(now_index(frames), 12)
        self.assertTrue(frames[12].observed)
        self.assertFalse(frames[13].observed)

    def test_from_now(self) -> None:
        frames = nowcast_frames()
        ahead = from_now(frames)
        self.assertEqual(len(ahead), 13)
        self.assertEqual(ahead[0], frames[12])

    def test_no_frames(self) -> None:
        self.assertEqual(from_now(()), ())


if __name__ == "__main__":
    unittest.main()

import unittest

from packages.algo_tutor.domain.enums import Source
from packages.algo_tutor.domain.urls import ProblemRef, parse_problem_url


class ParseProblemUrlTest(unittest.TestCase):
    def test_leetcode_variants(self) -> None:
        for url in (
            "https://leetcode.com/problems/two-sum",
            "https://leetcode.com/problems/two-sum/",
            "https://www.leetcode.com/problems/two-sum/description/",
            "https://leetcode.com/problems/two-sum/editorial",
            "https://leetcode.com/problems/two-sum/solutions/",
            "https://leetcode.com/problems/two-sum/submissions/",
            "https://leetcode.cn/problems/two-sum/",
            "https://leetcode.com/problems/two-sum/?envType=study-plan#x",
            "  https://leetcode.com/problems/two-sum/  ",
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    parse_problem_url(url), ProblemRef(Source.LEETCODE, "two-sum")
                )

    def test_atcoder_task(self) -> None:
        ref = parse_problem_url("https://atcoder.jp/contests/abc174/tasks/abc174_e")
        self.assertEqual(ref, ProblemRef(Source.ATCODER, "abc174_e", contest="abc174"))
        assert ref is not None
        self.assertEqual(ref.url, "https://atcoder.jp/contests/abc174/tasks/abc174_e")

    def test_canonical_leetcode_url(self) -> None:
        ref = parse_problem_url("https://www.leetcode.cn/problems/two-sum/description")
        assert ref is not None
        self.assertEqual(ref.url, "https://leetcode.com/problems/two-sum/")

    def test_rejects_other_urls(self) -> None:
        for url in (
            "http://leetcode.com/problems/two-sum/",
            "https://leetcode.com/problems/Two-Sum/",
            "https://leetcode.com/problems/two-sum/discuss/",
            "https://leetcode.com/contest/weekly-contest-1/",
            "https://atcoder.jp/contests/abc174",
            "https://example.com/problems/two-sum/",
            "two-sum",
        ):
            with self.subTest(url=url):
                self.assertIsNone(parse_problem_url(url))


if __name__ == "__main__":
    unittest.main()

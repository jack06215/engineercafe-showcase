import unittest

from packages.algo_tutor.domain.enums import Difficulty, Language, Source
from packages.algo_tutor.domain.paths import (
    PathSuggestion,
    atcoder_file_name,
    leetcode_file_name,
    suggest_path,
)

LC = "packages/programming_exercise/leetcode/src"
AC = "packages/programming_exercise/atcoder/src"
EXISTING = [
    f"{LC}/01_data_structures/arrays_and_strings/0088_merge_sorted_array_easy_v2.cpp",
    f"{LC}/01_data_structures/arrays_and_strings/0088_merge_sorted_array_easy_v2.py",
    f"{LC}/01_data_structures/arrays_and_strings/0088_merge_sorted_array_easy.py",
    f"{LC}/01_data_structures/arrays_and_strings/0001_two_sum_easy_v3.cpp",
    f"{AC}/abc174/e_logs.py",
    f"{AC}/tessoku_book/a01_the_first_problem.py",
    "packages/elsewhere/0088_not_leetcode.py",
]


def leetcode(
    number: int | None,
    slug: str,
    language: Language = Language.PYTHON,
    folder: str | None = "03_algorithms/greedy",
) -> PathSuggestion:
    return suggest_path(
        source=Source.LEETCODE,
        external_id=slug,
        title=slug,
        language=language,
        existing=EXISTING,
        number=number,
        label=Difficulty.EASY,
        topic_folder=folder,
    )


class LeetCodeTest(unittest.TestCase):
    def test_file_name(self) -> None:
        self.assertEqual(
            leetcode_file_name(
                88, "merge-sorted-array", Difficulty.EASY, Language.PYTHON
            ),
            "0088_merge_sorted_array_easy.py",
        )
        self.assertEqual(
            leetcode_file_name(None, "two-sum", Difficulty.EASY, Language.GO),
            "two_sum_easy.go",
        )
        self.assertEqual(
            leetcode_file_name(1, "two-sum", None, Language.TYPESCRIPT),
            "0001_two_sum.ts",
        )

    def test_existing_file_by_number_and_extension(self) -> None:
        s = leetcode(88, "merge-sorted-array")
        self.assertEqual(
            s.path,
            f"{LC}/01_data_structures/arrays_and_strings/0088_merge_sorted_array_easy.py",
        )
        self.assertTrue(s.exists)
        self.assertEqual(
            s.alternatives,
            (
                f"{LC}/01_data_structures/arrays_and_strings/0088_merge_sorted_array_easy_v2.py",
            ),
        )

    def test_other_languages_dont_match(self) -> None:
        # Only a .cpp exists for 0001: a new .py goes under the topic's folder.
        self.assertEqual(
            leetcode(1, "two-sum"),
            PathSuggestion(f"{LC}/03_algorithms/greedy/0001_two_sum_easy.py", False),
        )
        self.assertEqual(
            leetcode(88, "merge-sorted-array", Language.GO).path,
            f"{LC}/03_algorithms/greedy/0088_merge_sorted_array_easy.go",
        )

    def test_no_number_or_no_topic(self) -> None:
        self.assertEqual(
            leetcode(None, "merge-sorted-array").path,
            f"{LC}/03_algorithms/greedy/merge_sorted_array_easy.py",
        )
        self.assertEqual(
            leetcode(5, "longest-palindromic-substring", folder=None).path,
            f"{LC}/0005_longest_palindromic_substring_easy.py",
        )


def atcoder(
    contest: str, task: str, title: str, language: Language = Language.PYTHON
) -> PathSuggestion:
    return suggest_path(
        source=Source.ATCODER,
        external_id=task,
        title=title,
        language=language,
        existing=EXISTING,
        contest=contest,
    )


class AtCoderTest(unittest.TestCase):
    def test_file_name(self) -> None:
        self.assertEqual(
            atcoder_file_name("abc174_e", "Logs", Language.PYTHON), "e_logs.py"
        )
        self.assertEqual(
            atcoder_file_name("tessoku_book_d", "Binary Representation 1", Language.GO),
            "d_binary_representation_1.go",
        )
        # A title with no ASCII words leaves the task suffix alone.
        self.assertEqual(
            atcoder_file_name("abc300_a", "数列の和", Language.PYTHON), "a.py"
        )

    def test_existing_file_wins(self) -> None:
        self.assertEqual(
            atcoder("abc174", "abc174_e", "Logs"),
            PathSuggestion(f"{AC}/abc174/e_logs.py", True),
        )

    def test_new_path_with_dashes_in_the_contest(self) -> None:
        self.assertEqual(
            atcoder("tessoku-book", "tessoku_book_a", "The First Problem"),
            PathSuggestion(f"{AC}/tessoku_book/a_the_first_problem.py", False),
        )
        self.assertEqual(
            atcoder("abc174", "abc174_e", "Logs", Language.GO).path,
            f"{AC}/abc174/e_logs.go",
        )

    def test_contest_is_required(self) -> None:
        with self.assertRaises(ValueError):
            suggest_path(
                source=Source.ATCODER,
                external_id="abc174_e",
                title="Logs",
                language=Language.PYTHON,
                existing=[],
            )


if __name__ == "__main__":
    unittest.main()

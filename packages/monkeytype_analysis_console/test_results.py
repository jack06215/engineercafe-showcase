import datetime
import math
import os
import tempfile
import unittest
from pathlib import Path

from packages.monkeytype_analysis_console import fixtures
from packages.monkeytype_analysis_console.results import (
    Chars,
    Crown,
    Keys,
    TypedTime,
    merge,
    parse_file,
    resolve_folder,
    result_files,
)

JST = datetime.timezone(datetime.timedelta(hours=9))


def _parse_text(text: str) -> tuple[int, tuple[str, ...]]:
    parsed = parse_file("test.yml", text.encode())
    return len(parsed.results), parsed.errors


class ParseRealResultTest(unittest.TestCase):
    def test_reads_every_field(self) -> None:
        result = fixtures.result(fixtures.REAL)
        self.assertEqual(result.source, "real_words10.yml, document 1")
        self.assertEqual(
            result.copied_at, datetime.datetime(2026, 11, 23, 12, 20, 17, tzinfo=JST)
        )
        self.assertEqual(result.test, "words 10")
        self.assertEqual(result.language, "english 1k")
        self.assertEqual(result.unit, "wpm")
        self.assertEqual((result.wpm, result.raw, result.acc), (51.69, 51.69, 98.39))
        self.assertEqual(result.keys, Keys(61, 1))
        self.assertEqual(result.chars, Chars(61, 0, 0, 0))
        self.assertEqual((result.consistency, result.key_consistency), (70.19, 28.95))
        self.assertEqual((result.time, result.afk, result.afk_pct), (14.16, 0, 0))
        self.assertEqual(result.typed_time, TypedTime("session", 14))
        self.assertTrue(result.pb)
        self.assertEqual(result.crown, Crown("normal", "+26.38"))
        self.assertEqual(result.steps, (0, 37, 70, 92, 127))
        self.assertEqual(len(result.chart), 14)
        self.assertEqual(result.chart[7].errors, 1)
        self.assertEqual(len(result.words), 10)
        self.assertEqual(result.wpm_threshold, 30)
        self.assertEqual(result.missed_word_list, ("salt",))
        self.assertEqual(result.slow_word, ())
        self.assertEqual(result.word_list[:2], ("century", "sure"))

    def test_reads_a_word_with_a_typo(self) -> None:
        salt = fixtures.result(fixtures.REAL).words[5]
        self.assertEqual((salt.i, salt.word, salt.wpm, salt.bucket), (5, "salt", 37, 1))
        self.assertEqual((salt.typed, salt.fixed, salt.marks), ("sale", 1, "...f"))
        self.assertFalse(salt.error)
        self.assertIsNone(salt.letters)


class ParseCasesTest(unittest.TestCase):
    def test_quoted_words_stay_text(self) -> None:
        words = [word.word for word in fixtures.result(fixtures.TYPOS).words]
        self.assertIn("on", words)
        self.assertIn("null", words)
        self.assertIn("Vec<T>", words)

    def test_too_fast_word_is_inf_without_a_band(self) -> None:
        hello = fixtures.result(fixtures.TYPOS).words[3]
        self.assertTrue(math.isinf(hello.wpm or 0))
        self.assertIsNone(hello.bucket)

    def test_extras_flags_and_defaults(self) -> None:
        words = fixtures.result(fixtures.TYPOS).words
        self.assertEqual(words[4].letters, "tests")
        self.assertTrue(words[4].error)
        self.assertTrue(words[6].extra_fixed)
        self.assertEqual(words[0].fixed, 0)
        self.assertFalse(words[0].error)

    def test_fractional_last_chart_row(self) -> None:
        self.assertEqual(fixtures.result(fixtures.TYPOS).chart[-1].t, 12.5)

    def test_options_flags_tags_and_quote(self) -> None:
        self.assertEqual(fixtures.result(fixtures.TYPOS).options, ("punctuation",))
        quote = fixtures.result(fixtures.MULTI, 2)
        self.assertEqual(quote.flags, ("afk detected",))
        self.assertEqual(quote.tags, ("warmup",))
        self.assertEqual(quote.quote_source, "Alice's Adventures in Wonderland")

    def test_heatmap_off_still_has_steps(self) -> None:
        self.assertEqual(
            fixtures.result(fixtures.HEATMAP_OFF).steps, (0, 37, 70, 92, 127)
        )

    def test_custom_mode_has_no_language(self) -> None:
        custom = fixtures.result(fixtures.CUSTOM)
        self.assertIsNone(custom.language)
        self.assertEqual(custom.word_list_name, "custom")

    def test_chart_error_instead_of_a_chart(self) -> None:
        result = fixtures.result(fixtures.CHART_ERROR)
        self.assertEqual(result.chart, ())
        self.assertIn("not found", result.chart_error or "")

    def test_unit(self) -> None:
        self.assertEqual(fixtures.result(fixtures.CPM).unit, "cpm")

    def test_today_time_and_missing_parts(self) -> None:
        bare = fixtures.result(fixtures.MULTI, 1)
        self.assertEqual(bare.typed_time, TypedTime("today", 1260))
        self.assertEqual((bare.chart, bare.words, bare.steps), ((), (), ()))
        self.assertIsNone(bare.chars)
        self.assertEqual(bare.word_list, ())

    def test_long_result(self) -> None:
        parsed = parse_file("long.yml", fixtures.long_result_yaml().encode())
        self.assertEqual(parsed.errors, ())
        result = parsed.results[0]
        self.assertEqual(len(result.chart), 740)
        self.assertEqual(result.chart[-1].t, 739.6)
        self.assertEqual(len(result.words), 100)


class ParseErrorsTest(unittest.TestCase):
    def test_not_a_result(self) -> None:
        parsed = fixtures.read(fixtures.NOT_A_RESULT)
        self.assertEqual(parsed.results, ())
        self.assertEqual(len(parsed.errors), 1)
        self.assertTrue(
            parsed.errors[0].startswith("not_a_result.yml, document 1: not a yr result")
        )

    def test_syntax_error_keeps_earlier_documents(self) -> None:
        parsed = fixtures.read(fixtures.BROKEN)
        self.assertEqual(len(parsed.results), 1)
        self.assertEqual(len(parsed.errors), 1)
        self.assertTrue(parsed.errors[0].startswith("broken.yml: YAML error on line "))

    def test_not_utf8(self) -> None:
        parsed = parse_file("binary.yml", b"\xff\xfe\x00")
        self.assertEqual(parsed.results, ())
        self.assertTrue(parsed.errors[0].startswith("binary.yml: not UTF-8 text"))

    def test_bad_values_name_the_field(self) -> None:
        count, errors = _parse_text(
            "---\ndatetime: 2026-11-23T12:00:00+09:00\ndetail:\n  wpm: fast\n"
        )
        self.assertEqual(count, 0)
        self.assertIn("wpm is not a number", errors[0])

    def test_needs_wpm(self) -> None:
        count, errors = _parse_text(
            "---\ndatetime: 2026-11-23T12:00:00+09:00\ndetail:\n  test: words 10\n"
        )
        self.assertEqual(count, 0)
        self.assertIn("detail has no wpm", errors[0])

    def test_bad_document_does_not_hide_the_next(self) -> None:
        count, errors = _parse_text(
            "---\nfoo: 1\n---\ndatetime: 2026-11-23T12:00:00+09:00\n"
            "detail:\n  wpm: 50\n"
        )
        self.assertEqual(count, 1)
        self.assertTrue(errors[0].startswith("test.yml, document 1:"))

    def test_empty_documents_are_skipped(self) -> None:
        self.assertEqual(_parse_text("---\n---\n"), (0, ()))

    def test_naive_date_is_local_time(self) -> None:
        parsed = parse_file(
            "naive.yml", b"---\ndatetime: 2026-11-23 12:00:00\ndetail:\n  wpm: 50\n"
        )
        self.assertIsNotNone(parsed.results[0].copied_at.tzinfo)


class MergeTest(unittest.TestCase):
    def test_skips_duplicates_and_sorts_oldest_first(self) -> None:
        loaded = merge(fixtures.read(path) for path in fixtures.GOOD_FILES)
        self.assertEqual(loaded.files, len(fixtures.GOOD_FILES))
        self.assertEqual(loaded.duplicates, 1)
        self.assertEqual(len(loaded.results), 8)
        dates = [result.copied_at for result in loaded.results]
        self.assertEqual(dates, sorted(dates))
        # The first copy read wins: real_words10.yml comes before multi.yml.
        real = [r for r in loaded.results if r.wpm == 51.69]
        self.assertEqual([r.source for r in real], ["real_words10.yml, document 1"])

    def test_counts_files_with_errors(self) -> None:
        loaded = merge(
            fixtures.read(path)
            for path in (fixtures.REAL, fixtures.NOT_A_RESULT, fixtures.BROKEN)
        )
        self.assertEqual(len(loaded.results), 2)
        self.assertEqual(loaded.files_with_errors, 2)
        self.assertEqual(len(loaded.errors), 2)


class FolderTest(unittest.TestCase):
    def test_lists_result_files_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            for file in ("b.yml", "a.YAML", "notes.txt", "c.yaml"):
                (folder / file).write_text("---\n")
            (folder / "sub").mkdir()
            (folder / "sub" / "d.yml").write_text("---\n")
            self.assertEqual(
                [path.name for path in result_files(folder)],
                ["a.YAML", "b.yml", "c.yaml"],
            )

    def test_absolute_and_home_paths(self) -> None:
        self.assertEqual(resolve_folder("/tmp/results", {}), Path("/tmp/results"))
        self.assertEqual(resolve_folder("~/results", {}), Path.home() / "results")

    def test_relative_path_is_read_from_where_bazel_run_started(self) -> None:
        environ = {"BUILD_WORKING_DIRECTORY": "/work/repo"}
        self.assertEqual(
            resolve_folder(" documents ", environ), Path("/work/repo/documents")
        )
        self.assertEqual(
            resolve_folder("documents", {}), Path(os.getcwd()) / "documents"
        )


if __name__ == "__main__":
    unittest.main()

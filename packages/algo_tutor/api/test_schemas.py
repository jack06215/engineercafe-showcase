import unittest
from datetime import UTC, date, datetime

from pydantic import ValidationError

from packages.algo_tutor.api import schemas
from packages.algo_tutor.api.export_schema import build_document, contract_models


class ContractTest(unittest.TestCase):
    def test_every_model_is_exported(self) -> None:
        names = set(build_document()["components"]["schemas"])
        for model in contract_models():
            with self.subTest(model=model.__name__):
                self.assertIn(model.__name__, names)

    def test_inputs_forbid_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            schemas.TimerIn.model_validate(
                {"version": 1, "action": "pause", "extra": 1}
            )

    def test_finish_time_is_mmss(self) -> None:
        base = {"version": 1, "outcome": "solved", "help": "none", "language": "python"}
        schemas.FinishIn.model_validate(base | {"time": "12:05"})
        schemas.FinishIn.model_validate(base | {"time": "1234:59"})
        for bad in ("12:60", "12345:00", "1:2", ""):
            with self.subTest(time=bad), self.assertRaises(ValidationError):
                schemas.FinishIn.model_validate(base | {"time": bad})

    def test_target_rating_steps_of_fifty(self) -> None:
        schemas.SettingsPatch.model_validate({"target_rating": 1900})
        with self.assertRaises(ValidationError):
            schemas.SettingsPatch.model_validate({"target_rating": 1910})

    def test_patch_knows_null_from_absent(self) -> None:
        override_none = schemas.ProblemPatch.model_validate({"topic_id": None})
        untouched = schemas.ProblemPatch.model_validate({})
        self.assertIn("topic_id", override_none.model_fields_set)
        self.assertNotIn("topic_id", untouched.model_fields_set)

    def test_dates_serialise_plainly(self) -> None:
        change = schemas.LevelChange(
            delta=12,
            attempt_id="a",
            problem_title="Two Sum",
            rating=1732,
            estimated=True,
            result=schemas.Result.STRONG,
            study_date=date(2026, 11, 8),
        )
        self.assertEqual(change.model_dump(mode="json")["study_date"], "2026-11-08")
        self.assertEqual(
            schemas.Notebook(
                cues="",
                pitfalls="",
                notes="",
                version=1,
                updated_at=datetime(2026, 11, 8, tzinfo=UTC),
            ).model_dump(mode="json")["updated_at"],
            "2026-11-08T00:00:00Z",
        )


if __name__ == "__main__":
    unittest.main()

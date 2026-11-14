import unittest

from packages.algo_tutor.catalogue.errors import Conflict, InvalidInput
from packages.algo_tutor.catalogue.setup import complete_setup, setup_state
from packages.algo_tutor.catalogue.testing import NOW, manifests, temp_db
from packages.algo_tutor.domain.enums import BundledSet
from packages.algo_tutor.store.models import Settings


class SetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = temp_db()

    def tearDown(self) -> None:
        self.db.close()

    def test_setup_once_follows_and_activates_a_course(self) -> None:
        with self.db.sessions() as session:
            self.assertFalse(setup_state(session).onboarding_complete)
        with self.db.sessions() as session, session.begin():
            result = complete_setup(
                session,
                manifests(),
                NOW,
                questions_per_day=3,
                download_bank=True,
                course=BundledSet.BLIND_75,
            )
        self.assertTrue(result.start_bank_download)
        with self.db.sessions() as session:
            state = setup_state(session)
            self.assertEqual(
                (state.onboarding_complete, state.questions_per_day, state.timezone),
                (True, 3, "Asia/Tokyo"),
            )
            settings = session.get(Settings, 1)
            assert settings is not None
            self.assertEqual(settings.active_list_leetcode, result.course_list_id)
        with (
            self.db.sessions() as session,
            session.begin(),
            self.assertRaises(Conflict),
        ):
            complete_setup(
                session,
                manifests(),
                NOW,
                questions_per_day=2,
                download_bank=False,
                course=None,
            )

    def test_questions_per_day_range(self) -> None:
        with (
            self.db.sessions() as session,
            session.begin(),
            self.assertRaises(InvalidInput),
        ):
            complete_setup(
                session,
                manifests(),
                NOW,
                questions_per_day=21,
                download_bank=False,
                course=None,
            )


if __name__ == "__main__":
    unittest.main()

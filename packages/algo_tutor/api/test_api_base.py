import unittest

from fastapi import APIRouter
from pydantic import BaseModel

from packages.algo_tutor.api import deps
from packages.algo_tutor.api.app import route_modules
from packages.algo_tutor.api.testing import make_harness


class Echo(BaseModel):
    version: int


class BaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = make_harness()
        self.addCleanup(self.h.close)

    def test_health_through_the_guard(self) -> None:
        self.assertEqual(self.h.get("/health").json(), {"status": "ok"})
        refused = self.h.client.get(
            "/api/health", headers={"host": "evil.example:4317"}
        )
        self.assertEqual(refused.json()["error"]["code"], "NOT_LOCAL")

    def test_route_modules_are_discovered(self) -> None:
        self.assertIn("packages.algo_tutor.api.routes_health", route_modules())

    def test_idempotency(self) -> None:
        calls: list[int] = []
        router = APIRouter()

        @router.post("/api/echo")
        def echo(
            body: Echo,
            state: deps.State,
            session: deps.Db,
            key: deps.IdempotencyKey,
            request: deps.Request,
        ) -> object:
            def run() -> Echo:
                calls.append(body.version)
                return Echo(version=len(calls))

            return deps.idempotent(session, state, key, request, body, run)

        self.h.client.app.include_router(router)  # type: ignore[attr-defined]
        first = self.h.client.post(
            "/api/echo", json={"version": 1}, headers={"Idempotency-Key": "k1"}
        )
        again = self.h.client.post(
            "/api/echo", json={"version": 1}, headers={"Idempotency-Key": "k1"}
        )
        self.assertEqual(
            (first.json(), again.json(), calls), ({"version": 1}, {"version": 1}, [1])
        )
        other = self.h.client.post(
            "/api/echo", json={"version": 2}, headers={"Idempotency-Key": "k1"}
        )
        self.assertEqual(
            (other.status_code, other.json()["error"]["code"]),
            (409, "IDEMPOTENCY_MISMATCH"),
        )
        missing = self.h.client.post("/api/echo", json={"version": 1})
        self.assertEqual(
            (missing.status_code, missing.json()["error"]["code"]), (422, "VALIDATION")
        )


DIST = "src/main/typescript/packages/algo-tutor-web/dist"


class UiTest(unittest.TestCase):
    def test_built_ui_is_served_on_the_same_url(self) -> None:
        h = make_harness(
            repo_files={
                f"{DIST}/index.html": "<!doctype html><title>algo_tutor</title>",
                f"{DIST}/assets/app.js": "console.log(1)",
            }
        )
        self.addCleanup(h.close)
        self.assertIn("algo_tutor", h.client.get("/").text)
        self.assertIn(
            "algo_tutor", h.client.get("/library/some-id").text
        )  # client-side route
        self.assertEqual(h.client.get("/assets/app.js").text, "console.log(1)")
        self.assertIn(
            "algo_tutor", h.client.get("/../../etc/passwd").text
        )  # never escapes dist
        self.assertEqual(h.get("/health").json(), {"status": "ok"})
        missing = h.get("/nope")
        self.assertEqual(
            (missing.status_code, missing.json()["error"]["code"]), (404, "NOT_FOUND")
        )

    def test_without_a_build_only_the_api_answers(self) -> None:
        h = make_harness()
        self.addCleanup(h.close)
        self.assertEqual(h.client.get("/").status_code, 404)


if __name__ == "__main__":
    unittest.main()

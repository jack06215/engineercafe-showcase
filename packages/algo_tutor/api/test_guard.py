import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.algo_tutor.api.errors import ApiError, install_error_handlers
from packages.algo_tutor.api.guard import LocalOnlyMiddleware, refusal
from packages.algo_tutor.api.schemas import PlanVersionIn

PORT = 4317
JSON = {"content-type": "application/json"}


def make_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    app.add_middleware(LocalOnlyMiddleware, port=PORT)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/thing")
    def thing(body: PlanVersionIn) -> dict[str, int]:
        if body.version == 9:
            raise ApiError(409, "STALE", "changed")
        return {"version": body.version}

    return app


class RefusalTest(unittest.TestCase):
    def test_hosts(self) -> None:
        self.assertIsNone(refusal("GET", {"host": "127.0.0.1:4317"}, PORT))
        self.assertIsNone(refusal("GET", {"host": "localhost:4317"}, PORT))
        for host in ("evil.example:4317", "127.0.0.1:9999", "127.0.0.1", ""):
            with self.subTest(host=host):
                self.assertIsNotNone(refusal("GET", {"host": host}, PORT))

    def test_origins(self) -> None:
        base = {"host": "127.0.0.1:4317"}
        for origin in (
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:4317",
        ):
            with self.subTest(origin=origin):
                self.assertIsNone(refusal("GET", base | {"origin": origin}, PORT))
        for origin in ("http://evil.example", "null", "https://127.0.0.1:5173"):
            with self.subTest(origin=origin):
                self.assertIsNotNone(refusal("GET", base | {"origin": origin}, PORT))

    def test_writes_need_json(self) -> None:
        base = {"host": "127.0.0.1:4317"}
        self.assertIsNone(
            refusal(
                "POST", base | {"content-type": "application/json; charset=utf-8"}, PORT
            )
        )
        self.assertIsNotNone(
            refusal("POST", base | {"content-type": "text/plain"}, PORT)
        )
        self.assertIsNotNone(refusal("DELETE", base, PORT))
        self.assertIsNone(refusal("GET", base, PORT))


class MiddlewareTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(make_app(), base_url=f"http://127.0.0.1:{PORT}")

    def test_local_request_passes(self) -> None:
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})

    def test_foreign_host_is_not_local(self) -> None:
        response = self.client.get(
            "/api/health", headers={"host": "rebind.example:4317"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "NOT_LOCAL")

    def test_form_post_is_refused(self) -> None:
        response = self.client.post(
            "/api/thing",
            content="version=1",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(response.status_code, 403)

    def test_error_shapes(self) -> None:
        stale = self.client.post("/api/thing", json={"version": 9})
        self.assertEqual(
            (stale.status_code, stale.json()),
            (409, {"error": {"code": "STALE", "message": "changed"}}),
        )
        invalid = self.client.post("/api/thing", json={"version": 0})
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["error"]["code"], "VALIDATION")
        self.assertIn("version", invalid.json()["error"]["message"])
        missing = self.client.get("/api/nope")
        self.assertEqual(
            (missing.status_code, missing.json()["error"]["code"]), (404, "NOT_FOUND")
        )


if __name__ == "__main__":
    unittest.main()

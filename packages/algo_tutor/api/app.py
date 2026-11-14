"""The FastAPI app (SPEC §15).

Routes live in `routes_*.py` modules, each exposing `router`; every one in
this folder is mounted under `/api`, so adding a module needs no edit here
(or in BUILD.bazel, which globs them).

When the web package has been built (`pnpm build` leaves `dist/`), the app
also serves it, so the whole thing is one URL (SPEC §3.1 "Ready"). Without
`dist/`, run the UI from Vite's dev server as in the PoC.
"""

import importlib
import pkgutil
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException

from packages.algo_tutor.api.errors import install_error_handlers
from packages.algo_tutor.api.guard import LocalOnlyMiddleware
from packages.algo_tutor.runtime import Runtime
from packages.algo_tutor.store.timeutil import now_utc
from packages.algo_tutor.tutor.llm import ChatFactory, chat_model
from packages.algo_tutor.tutor.worker import ReportWorker

# The built UI, relative to the repo root.
UI_DIST = Path("src/main/typescript/packages/algo-tutor-web/dist")


@dataclass
class AppState:
    """What every route can reach, through `deps.app_state`."""

    runtime: Runtime
    chat_factory: ChatFactory
    clock: Callable[[], datetime]
    worker: ReportWorker | None = None
    # Background jobs (e.g. the bank download) keep their handles here.
    jobs: dict[str, object] = field(default_factory=dict)

    @property
    def tutor_enabled(self) -> bool:
        """Whether the config turns the LLM tutor on."""
        return self.runtime.config.tutor.enabled

    def wake_worker(self) -> None:
        """Wake the report worker, if one is running."""
        if self.worker is not None:
            self.worker.wake()


def route_modules() -> list[str]:
    """Every `routes_*` module next to this file, sorted."""
    here = str(Path(__file__).parent)
    return sorted(
        f"{__package__}.{info.name}"
        for info in pkgutil.iter_modules([here])
        if info.name.startswith("routes_")
    )


def create_app(
    runtime: Runtime,
    *,
    chat_factory: ChatFactory = chat_model,
    clock: Callable[[], datetime] = now_utc,
    start_worker: bool = True,
) -> FastAPI:
    """The app over an opened runtime.

    Tests pass a scripted `chat_factory`, a fixed `clock`, and
    `start_worker=False` to drive the queue by hand.
    """
    state = AppState(runtime=runtime, chat_factory=chat_factory, clock=clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if start_worker and state.tutor_enabled:
            state.worker = ReportWorker(
                runtime.sessions, runtime.config.tutor, chat_factory
            )
            state.worker.start()
        try:
            yield
        finally:
            if state.worker is not None:
                state.worker.stop()

    app = FastAPI(
        title="algo_tutor",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.algo = state
    install_error_handlers(app)
    app.add_middleware(LocalOnlyMiddleware, port=runtime.config.server.port)
    for name in route_modules():
        router: APIRouter = importlib.import_module(name).router
        app.include_router(router, prefix="/api")
    mount_ui(app, runtime.paths.repo_root / UI_DIST)
    return app


def mount_ui(app: FastAPI, dist: Path) -> bool:
    """Serve the built single-page app from `dist`, if it's there.

    Registered after the API, so `/api/...` always wins. Any other path is a
    file in `dist` or, failing that, `index.html` for the client router.
    Unknown `/api/...` paths stay JSON 404s. Read on every request, so a
    rebuild shows up without a restart.
    """
    if not (dist / "index.html").is_file():
        return False
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def ui(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, f"No route /{path}")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html")

    return True

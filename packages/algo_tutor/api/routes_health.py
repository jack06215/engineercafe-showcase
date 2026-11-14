"""GET /health (SPEC §15)."""

from fastapi import APIRouter

from packages.algo_tutor.api.schemas import Health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> Health:
    return Health()

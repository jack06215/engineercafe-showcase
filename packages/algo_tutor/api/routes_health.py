"""GET /health (SPEC §15)."""

from fastapi import APIRouter

from packages.algo_tutor.api.schemas import Health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> Health:
    """Report that the server is up."""
    return Health()

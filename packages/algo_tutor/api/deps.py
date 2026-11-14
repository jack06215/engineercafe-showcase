"""Shared route plumbing: the per-request transaction, the hidden
assessment, versions and idempotency (SPEC §9, §18)."""

import hashlib
import json
import re
from collections.abc import Callable, Iterator
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.api.errors import ApiError, hidden_assessment, stale
from packages.algo_tutor.api.schemas import IDEMPOTENCY_KEY
from packages.algo_tutor.domain.enums import AttemptStatus, Context
from packages.algo_tutor.store.db import transaction
from packages.algo_tutor.store.models import Attempt, Idempotency, Settings
from packages.algo_tutor.store.timeutil import iso_utc


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.algo
    return state


State = Annotated[AppState, Depends(app_state)]


def db_session(request: Request) -> Iterator[Session]:
    """One transaction per request: committed when the route returns,
    rolled back if it raises. `scope="function"` (below) commits before the
    response is sent, so a failed commit is an error response, not a lie."""
    with transaction(app_state(request).runtime.sessions) as session:
        yield session


Db = Annotated[Session, Depends(db_session, scope="function")]


def settings_row(session: Session) -> Settings:
    return session.get_one(Settings, 1)


# ---------------------------------------------------------------- hidden assessment


def unfinished_attempt(session: Session) -> Attempt | None:
    return session.scalars(
        select(Attempt).where(
            Attempt.status.in_([AttemptStatus.ACTIVE.value, AttemptStatus.PAUSED.value])
        )
    ).first()


def assessment_attempt(session: Session) -> Attempt | None:
    """The unfinished `mixed` attempt, if a hidden assessment is running."""
    attempt = unfinished_attempt(session)
    if attempt is not None and attempt.context == Context.MIXED.value:
        return attempt
    return None


def forbid_during_assessment(session: Session) -> None:
    """403 HIDDEN_ASSESSMENT while a transfer check runs (SPEC §9)."""
    if assessment_attempt(session) is not None:
        raise hidden_assessment()


# ---------------------------------------------------------------- versions


def check_version(current: int, sent: int, what: str) -> None:
    if current != sent:
        raise stale(what)


# ---------------------------------------------------------------- idempotency

_KEY = re.compile(IDEMPOTENCY_KEY)


def idempotency_key(
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    """The required header on finish, rebuild and pack import (SPEC §18.2)."""
    if key is None or not _KEY.match(key):
        raise ApiError(
            422,
            "VALIDATION",
            "Idempotency-Key header: 1-200 characters of [A-Za-z0-9_.:-]",
        )
    return key


IdempotencyKey = Annotated[str, Depends(idempotency_key)]


def fingerprint(request: Request, body: BaseModel | dict[str, Any] | None) -> str:
    payload = body.model_dump(mode="json") if isinstance(body, BaseModel) else body
    canonical = json.dumps(
        {
            "method": request.method,
            "path": request.url.path,
            "query": str(request.url.query),
            "body": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def idempotent(
    session: Session,
    state: AppState,
    key: str,
    request: Request,
    body: BaseModel | dict[str, Any] | None,
    run: Callable[[], BaseModel],
    status: int = 200,
) -> JSONResponse:
    """Run `run` once per key: the same key and body replay the first
    response; the same key with another body is 409 IDEMPOTENCY_MISMATCH.
    The record is written in the request's transaction, so it commits (or
    rolls back) with the work."""
    digest = fingerprint(request, body)
    seen = session.get(Idempotency, key)
    if seen is not None:
        if seen.fingerprint != digest:
            raise ApiError(
                409,
                "IDEMPOTENCY_MISMATCH",
                "This Idempotency-Key was used with a different request",
            )
        return JSONResponse(
            status_code=int(seen.response["status"]), content=seen.response["body"]
        )
    result = run().model_dump(mode="json")
    session.add(
        Idempotency(
            key=key,
            fingerprint=digest,
            response={"status": status, "body": result},
            created_at=iso_utc(state.clock()),
        )
    )
    session.flush()
    return JSONResponse(status_code=status, content=result)

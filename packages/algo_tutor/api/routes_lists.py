"""Study lists, bundled courses and question packs (SPEC §5.9, §5.10, §14 Lists)."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.algo_tutor.api import deps, facts, schemas
from packages.algo_tutor.api.app import AppState
from packages.algo_tutor.catalogue.courses import follow_course
from packages.algo_tutor.catalogue.lists import (
    Unresolved,
    activate_list,
    add_entries_from_text,
    create_own_lists,
    deactivate_list,
    delete_list,
    get_list,
    list_entries,
    list_progress,
    preview_entries,
    rename_list,
    set_entries,
)
from packages.algo_tutor.catalogue.packs import import_pack, parse_pack
from packages.algo_tutor.domain.enums import BundledSet, ListKind, Source
from packages.algo_tutor.store.models import Problem, StudyList
from packages.algo_tutor.store.timeutil import parse_iso

router = APIRouter(tags=["lists"])

_KIND_ORDER = {ListKind.BUNDLED.value: 0, ListKind.OWN.value: 1, ListKind.PACK.value: 2}


def summary(session: Session, study_list: StudyList) -> schemas.ListSummary:
    """Return the API summary of *study_list* with its progress."""
    done, total = list_progress(session).get(study_list.id, (0, 0))
    settings = deps.settings_row(session)
    return schemas.ListSummary(
        id=study_list.id,
        name=study_list.name,
        source=Source(study_list.source),
        kind=ListKind(study_list.kind),
        origin=study_list.origin,
        source_url=study_list.source_url,
        created_at=parse_iso(study_list.created_at),
        active=study_list.id
        in (settings.active_list_leetcode, settings.active_list_atcoder),
        done=done,
        total=total,
    )


def list_detail(
    session: Session,
    state: AppState,
    study_list: StudyList,
    unresolved: list[Unresolved] | None = None,
) -> schemas.ListDetail:
    """The list in order.

    During a hidden assessment the assessment's own problem is left out: its
    course section would name its topic.
    """
    assessment = deps.assessment_attempt(session)
    hidden = assessment.problem_id if assessment is not None else None
    entries = [
        e for e in list_entries(session, study_list.id) if e.problem_id != hidden
    ]
    problems = {
        p.id: p
        for p in session.scalars(
            select(Problem).where(Problem.id.in_([e.problem_id for e in entries]))
        )
    }
    rated = facts.ratings(session, state.runtime.manifests, problems.values())
    return schemas.ListDetail(
        summary=summary(session, study_list),
        entries=[
            schemas.ListEntryOut(
                problem=facts.brief(problems[e.problem_id], rated[e.problem_id]),
                position=e.position,
                section=e.section,
                added_at=parse_iso(e.added_at),
                done=e.done,
            )
            for e in entries
        ],
        unresolved=_unresolved(unresolved or []),
    )


def _unresolved(items: list[Unresolved]) -> list[schemas.UnresolvedLine]:
    return [schemas.UnresolvedLine(line=u.line, reason=u.reason) for u in items]


@router.get("/lists")
def get_lists(session: deps.Db) -> list[schemas.ListSummary]:
    """Bundled courses first, then your lists, then packs; by name within each."""
    rows = sorted(
        session.scalars(select(StudyList)),
        key=lambda s: (_KIND_ORDER.get(s.kind, 9), s.name.casefold()),
    )
    return [summary(session, s) for s in rows]


@router.post("/lists/preview")
def preview(
    body: schemas.ListEntriesIn, state: deps.State, session: deps.Db
) -> schemas.ListPreview:
    """What a paste would create, without writing anything.

    One group per source: a mixed paste becomes one list per source.
    """
    result = preview_entries(
        session,
        state.runtime.manifests,
        body.text,
        body.name,
        state.runtime.saved_bank(),
    )
    return schemas.ListPreview(
        groups=[
            schemas.PreviewGroup(
                source=source,
                name=result.names.get(source, body.name),
                entries=[
                    schemas.ResolvedEntry(
                        line=e.external_id,
                        problem_id=e.problem_id,
                        title=e.title,
                        source=e.source,
                    )
                    for e in entries
                ],
            )
            for source, entries in result.groups.items()
        ],
        unresolved=[u.line for u in result.unresolved],
        unresolved_reasons=_unresolved(result.unresolved),
    )


@router.post("/lists", status_code=201)
def create_lists(
    body: schemas.ListEntriesIn, state: deps.State, session: deps.Db
) -> schemas.ListCreated:
    """Create the learner's own lists from pasted text, one list per source."""
    created, unresolved = create_own_lists(
        session,
        state.runtime.manifests,
        body.name,
        body.text,
        state.clock(),
        state.runtime.saved_bank(),
    )
    return schemas.ListCreated(
        lists=[summary(session, s) for s in created],
        unresolved=[u.line for u in unresolved],
        unresolved_reasons=_unresolved(unresolved),
    )


@router.get("/lists/{list_id}")
def get_list_detail(
    list_id: str, state: deps.State, session: deps.Db
) -> schemas.ListDetail:
    """Return a list with its entries."""
    return list_detail(session, state, get_list(session, list_id))


@router.patch("/lists/{list_id}")
def patch_list(
    list_id: str, body: schemas.ListPatch, state: deps.State, session: deps.Db
) -> schemas.ListDetail:
    """Your own lists and packs only; bundled courses are read-only (409)."""
    now = state.clock()
    if body.name is not None:
        rename_list(session, list_id, body.name)
    if body.problem_ids is not None:
        set_entries(session, list_id, body.problem_ids, now)
    unresolved: list[Unresolved] = []
    if body.add_text:
        _, unresolved = add_entries_from_text(
            session,
            state.runtime.manifests,
            list_id,
            body.add_text,
            now,
            state.runtime.saved_bank(),
        )
    return list_detail(session, state, get_list(session, list_id), unresolved)


@router.delete("/lists/{list_id}", status_code=204)
def remove_list(list_id: str, session: deps.Db) -> Response:
    """Any list, bundled included (following the course again recreates it).

    Progress lives on attempts, so nothing else is lost.
    """
    delete_list(session, list_id)
    return Response(status_code=204)


@router.post("/lists/bundled/{course}")
def follow(course: BundledSet, state: deps.State, session: deps.Db) -> JSONResponse:
    """Follow NeetCode 150, Blind 75 or Hello Interview.

    Answers 201 the first time, and 200 with the existing list after that.
    """
    followed = follow_course(
        session,
        state.runtime.manifests,
        course,
        state.clock(),
        state.runtime.saved_bank(),
    )
    out = list_detail(session, state, followed.study_list)
    return JSONResponse(
        status_code=201 if followed.created else 200,
        content=out.model_dump(mode="json"),
    )


@router.post("/lists/{list_id}/activate")
def activate(list_id: str, session: deps.Db) -> schemas.ListSummary:
    """Make the list the active one for its source; every list keeps its progress."""
    return summary(session, activate_list(session, list_id))


@router.post("/lists/{list_id}/deactivate")
def deactivate(list_id: str, session: deps.Db) -> schemas.ListSummary:
    """Stop using a list as the active list."""
    return summary(session, deactivate_list(session, list_id))


# ---------------------------------------------------------------- packs


@router.post("/packs")
def post_pack(
    body: Annotated[dict[str, Any], Body()],
    request: Request,
    state: deps.State,
    session: deps.Db,
    key: deps.IdempotencyKey,
    dry_run: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """Import a version-2 question pack (SPEC §5.9).

    `dry_run=true` reports what would change without writing. Importing the same
    pack twice is a no-op (`already_applied`).
    """
    parsed = parse_pack(json.dumps(body))

    def run() -> schemas.PackReport:
        report = import_pack(
            session,
            state.runtime.manifests,
            parsed,
            state.clock(),
            dry_run=dry_run,
            bank=state.runtime.saved_bank(),
        )
        touched = None
        if not dry_run:
            for name in report.lists_created + report.lists_extended:
                touched = session.scalar(
                    select(StudyList).where(StudyList.name == name)
                )
                if touched is not None:
                    break
        return schemas.PackReport(
            import_id=report.import_id,
            dry_run=report.dry_run,
            already_applied=report.already_applied,
            summary=summary(session, touched) if touched is not None else None,
            problems_created=report.problems_created,
            problems_existing=report.problems_existing,
            entries_added=report.entries_added,
            patterns_added=report.patterns_added,
            lists_created=report.lists_created,
            lists_extended=report.lists_extended,
        )

    return deps.idempotent(session, state, key, request, body, run)

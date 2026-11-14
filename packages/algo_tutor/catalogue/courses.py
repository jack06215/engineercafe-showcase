"""Bundled courses: "Follow NeetCode 150 / Blind 75 / Hello Interview" (SPEC.md §5.10).

Following creates a read-only list in course order with its sections, adding
the course's problems the library lacks from the bundled manifests.
Following again returns the list it made before.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.algo_tutor.catalogue.bank_file import BankQuestion
from packages.algo_tutor.catalogue.lists import append_entries, create_list
from packages.algo_tutor.catalogue.manifests import Manifests
from packages.algo_tutor.catalogue.problems import ensure_leetcode
from packages.algo_tutor.domain.enums import BundledSet, ListKind, Source
from packages.algo_tutor.store.models import ImportBatch, StudyList
from packages.algo_tutor.store.timeutil import iso_utc, new_id


@dataclass(frozen=True)
class Followed:
    """Result of following a bundled course."""

    study_list: StudyList
    created: bool  # False: the course was already followed
    problems_added: int  # new to the library


def follow_course(
    session: Session,
    manifests: Manifests,
    course_id: BundledSet,
    now: datetime,
    bank: dict[str, BankQuestion] | None = None,
) -> Followed:
    """Follow *course_id* by creating its study list, unless it already exists."""
    course = manifests.courses[course_id]
    existing = session.scalar(
        select(StudyList).where(
            StudyList.kind == ListKind.BUNDLED.value,
            StudyList.origin == course_id.value,
        )
    )
    if existing is not None:
        return Followed(existing, created=False, problems_added=0)

    study_list = create_list(
        session,
        course.name,
        Source.LEETCODE,
        ListKind.BUNDLED,
        now,
        origin=course_id.value,
        source_url=course.source_url,
    )
    added = 0
    for section in course.sections:
        problems = []
        for slug in section.slugs:
            result = ensure_leetcode(
                session, manifests, slug, now, bank=(bank or {}).get(slug)
            )
            added += result.created
            problems.append(result.problem)
        append_entries(session, study_list, problems, now, section=section.name)

    fingerprint = hashlib.sha256(
        "\n".join(f"{s.name}\t{','.join(s.slugs)}" for s in course.sections).encode()
    ).hexdigest()
    session.add(
        ImportBatch(
            id=new_id(),
            kind="bundled",
            fingerprint=fingerprint,
            applied_at=iso_utc(now),
            report={
                "course": course_id.value,
                "list_id": study_list.id,
                "problems_added": added,
            },
        )
    )
    session.flush()
    return Followed(study_list, created=True, problems_added=added)

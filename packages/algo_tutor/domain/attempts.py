"""What starting an attempt decides (SPEC §6.2).

Ported from BloomCode's `POST /api/attempts`: the context (is this the hidden
assessment?) and the evidence the result will count as.
"""

from dataclasses import dataclass

from packages.algo_tutor.domain.enums import Context, Evidence, PlanItemKind


@dataclass(frozen=True)
class StartFacts:
    """How an attempt counts, decided when it starts."""

    context: Context
    evidence: Evidence


def start_facts(
    *,
    from_plan: bool,
    plan_item_kind: PlanItemKind | None,
    exposed: bool,
    has_completed_attempt: bool,
) -> StartFacts:
    """Context and evidence for a new attempt.

    A plan item with no kind is a transfer check: `mixed`, the hidden
    assessment. Every other plan item, and the library, is `targeted`.
    Evidence is `retention` for a problem seen before (exposed, or with a
    completed attempt); otherwise `unseen` when mixed, `near_transfer` when
    targeted.
    """
    context = (
        Context.MIXED if from_plan and plan_item_kind is None else Context.TARGETED
    )
    if exposed or has_completed_attempt:
        evidence = Evidence.RETENTION
    elif context is Context.MIXED:
        evidence = Evidence.UNSEEN
    else:
        evidence = Evidence.NEAR_TRANSFER
    return StartFacts(context, evidence)

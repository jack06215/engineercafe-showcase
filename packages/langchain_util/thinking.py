"""Generate, evaluate, revise: structured output that is reviewed before it returns.

`think` takes the same arguments as `langchain_util.basic.generate` -- a
system/human chat prompt that references `{{ format_instructions }}`, and a
Pydantic output type -- and runs this LangGraph workflow around the call:

    START -> checklist -> generate -> evaluate --revise--> generate
                                          |
                                          +--done--> END

* **checklist** fixes, once per run, the yes/no questions every candidate is
  reviewed against: the `criteria` you pass, or ones the evaluator model derives
  from the rendered task.
* **generate** asks for a candidate. The first one already sees the checklist.
  A revision gets the *best* candidate so far plus its review.
* **evaluate** runs your deterministic `validators` first. Only a candidate
  they accept is sent to the model reviewer, which answers every check with
  evidence before a verdict. The candidate becomes the new best only if it
  ranks strictly higher: fewer validator problems, then more checks passed.
* The loop ends when the best candidate passes, after `max_revisions`, or when
  `patience` revisions in a row fail to beat the best.

The result is the best candidate, not the last one, with `accepted` saying
whether it met the bar and every attempt kept for inspection.

Why not the textbook loop
-------------------------

The usual evaluator-optimizer -- generate, ask "is it good? how would you
improve it?", regenerate until the grade says pass, return the last output --
is what LangChain's workflow tutorial and most blog posts build. The research on
that loop argues for each departure above:

* A model judging its own reasoning without outside signal often makes answers
  worse: it changes correct answers to wrong ones about as readily as the
  reverse, and published gains came from using ground truth to decide when to
  stop. Hence best-so-far selection, the strict improvement rule, and stopping
  on no progress. Most of the remaining gain came from putting the criteria in
  the first prompt, hence the checklist in the first generation.
  ("Large Language Models Cannot Self-Correct Reasoning Yet", arXiv:2310.01798)
* Decomposing a review into instruction-specific yes/no checks agrees with
  human judgement more often than asking for one score, and refining against
  the failed checks improves generation. Hence a checklist instead of a grade,
  and feedback made of failed checks only.
  ("TICKing All the Boxes", arXiv:2410.03608)
* Critique grounded in an external tool -- a code runner, a search, a
  calculator -- is what makes self-correction reliable. `validators` are that
  hook: plain Python that returns what is wrong, run before any reviewer call.
  ("CRITIC", arXiv:2305.11738)
* A model reviewer tends to prefer text like its own, even when authorship is
  hidden. Pass a different model as `evaluator_chat` when the stakes justify it.
  ("Self-Preference Bias in LLM-as-a-Judge", arXiv:2410.21819)
* Most of the improvement lands in the first one or two rounds, so
  `max_revisions` defaults to 2.

When to use it
--------------

Only when success is checkable. A reviewer that cannot tell a good answer from
a bad one only adds cost and noise; that is `basic.generate`'s job. Every run
makes at most `1 + 2 * (max_revisions + 1)` model requests before retries:
one for the checklist if you pass no `criteria`, then a generation and a
review per attempt.

Transient errors and parse failures are retried inside each node by
`invoke_llm_detailed`, so no LangGraph `RetryPolicy` is set; adding one would
retry each failure twice over.
"""

import copy
import logging
import operator
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from packages.langchain_util.base import (
    DEFAULT_RETRY_POLICY,
    ChatLLM,
    Parser,
    RetryPolicy,
    invoke_llm_detailed,
)
from packages.langchain_util.basic import bind_output_schema
from packages.langchain_util.observability import Usage
from packages.langchain_util.prompts import load_chat_prompt

TEMPLATE_DIR = Path(__file__).parent / "templates" / "thinking"

type Validator[T] = Callable[[T], Sequence[str]]
"""Returns what is wrong with a candidate, one message per problem.

An empty sequence accepts the candidate. Each message is shown to the model
verbatim, so write it as an instruction the next revision can act on.
"""


class Checklist(BaseModel):
    """What the checklist node asks the evaluator model for."""

    checks: list[str] = Field(
        description="Yes/no questions about the answer, most important first; "
        "each checks one requirement, and YES means it is met",
    )


class CheckVerdict(BaseModel):
    """The reviewer's answer to one check.

    `evidence` comes before `passed` on purpose: the model writes fields in
    schema order, so it has to find the evidence before it commits to a verdict.
    """

    id: int = Field(description="The number of the check this verdict answers")
    evidence: str = Field(
        description="The part of the answer this check depends on, quoted, "
        "or a statement of what is missing",
    )
    passed: bool = Field(description="true only if the answer clearly meets the check")
    fix: str | None = Field(
        default=None,
        description="If the check failed, the specific change that would make it "
        "pass; otherwise null",
    )


class Review(BaseModel):
    """What the evaluate node asks the evaluator model for."""

    verdicts: list[CheckVerdict] = Field(
        description="Exactly one verdict per check, in checklist order",
    )


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One check as it applied to one candidate."""

    question: str
    passed: bool
    evidence: str
    fix: str | None = None


@dataclass(frozen=True, slots=True)
class Attempt[T]:
    """A candidate and everything the evaluate node found out about it.

    `checks` is empty when no review ran: either there was no checklist, or a
    validator already rejected the candidate and a review would have been
    wasted.
    """

    candidate: T
    problems: tuple[str, ...] = ()
    checks: tuple[CheckResult, ...] = ()

    @property
    def score(self) -> float:
        """Fraction of checks passed; 1.0 with nothing to fail, 0.0 if unreviewed."""
        if not self.checks:
            return 0.0 if self.problems else 1.0

        return sum(check.passed for check in self.checks) / len(self.checks)

    @property
    def rank(self) -> tuple[int, float]:
        """Sort key: fewer validator problems first, then a higher score."""
        return (-len(self.problems), self.score)

    def meets(self, accept_score: float) -> bool:
        return not self.problems and self.score >= accept_score


@dataclass(frozen=True, slots=True)
class ThinkingPolicy:
    """When the loop stops, and how big the checklist may get.

    Attributes:
        max_revisions: Revisions after the first candidate. 0 turns the loop
            into generate-then-review, which still reports `accepted`.
        patience: Consecutive revisions that fail to beat the best candidate
            before giving up. A revision starts from the best candidate, so a
            second try differs only by sampling.
        accept_score: Fraction of checks that must pass, with no validator
            problems, for a candidate to be accepted.
        max_checks: Cap on a derived checklist. Ignored for `criteria`.
    """

    max_revisions: int = 2
    patience: int = 1
    accept_score: float = 1.0
    max_checks: int = 8

    def __post_init__(self) -> None:
        if self.max_revisions < 0:
            msg = f"max_revisions must be >= 0, got {self.max_revisions}"
            raise ValueError(msg)
        if self.patience < 1:
            msg = f"patience must be >= 1, got {self.patience}"
            raise ValueError(msg)
        if not 0.0 < self.accept_score <= 1.0:
            msg = f"accept_score must be in (0, 1], got {self.accept_score}"
            raise ValueError(msg)
        if self.max_checks < 1:
            msg = f"max_checks must be >= 1, got {self.max_checks}"
            raise ValueError(msg)

    @property
    def recursion_limit(self) -> int:
        """LangGraph steps a full run needs: checklist, then two per attempt.

        LangGraph's default limit of 25 would cut `max_revisions` above 10 short
        with a `GraphRecursionError`.
        """
        return 1 + 2 * (self.max_revisions + 1) + 1


DEFAULT_THINKING_POLICY = ThinkingPolicy()


@dataclass(frozen=True, slots=True)
class ThinkingResult[T]:
    """The best candidate, whether it was accepted, and how it was reached."""

    value: T
    accepted: bool
    checks: tuple[str, ...]
    attempts: tuple[Attempt[T], ...]
    best_index: int
    usage: Usage
    latency_s: float

    @property
    def best(self) -> Attempt[T]:
        return self.attempts[self.best_index]


class ThinkingState(TypedDict, total=False):
    """Graph state. Only `input` is supplied by the caller."""

    input: dict[str, Any]
    task: str
    checks: list[str]
    draft: BaseModel
    attempts: Annotated[list[Attempt[Any]], operator.add]
    best: int
    stale: int
    usage: Annotated[list[Usage], operator.add]


type ThinkingGraph = CompiledStateGraph[
    ThinkingState, None, ThinkingState, ThinkingState
]

_CHECKLIST_PARSER = PydanticOutputParser(pydantic_object=Checklist)
_REVIEW_PARSER = PydanticOutputParser(pydantic_object=Review)


def _load_templates(name: str, **partial_variables: Any) -> ChatPromptTemplate:
    return load_chat_prompt(
        [("system", f"{name}.system.jinja"), ("human", f"{name}.human.jinja")],
        root=TEMPLATE_DIR,
        partial_variables=partial_variables,
    )


def _load_message(name: str) -> ChatPromptTemplate:
    return load_chat_prompt([("human", f"{name}.human.jinja")], root=TEMPLATE_DIR)


def _label(number: int) -> str:
    return "draft" if number == 0 else f"revision {number}"


def _render_task(prompt: ChatPromptTemplate, variables: Mapping[str, Any]) -> str:
    """The caller's prompt as the generator sees it, for the reviewer to read."""
    return "\n\n".join(
        f"[{message.type}]\n{message.text}"
        for message in prompt.format_messages(**variables)
    )


def _review_parser(check_count: int) -> Parser:
    """The review parser, refusing a review that skips a check.

    Raised as an `OutputParserException`, so `invoke_llm_detailed` retries it
    with this message appended to the prompt, as for malformed JSON.
    """

    def require_every_check(review: Review) -> Review:
        answered = {verdict.id for verdict in review.verdicts}
        missing = [n for n in range(1, check_count + 1) if n not in answered]
        if missing:
            msg = (
                f"the review has no verdict for check(s) "
                f"{', '.join(map(str, missing))}; answer every check from 1 to "
                f"{check_count} exactly once"
            )
            raise OutputParserException(msg)

        return review

    return _REVIEW_PARSER | RunnableLambda(require_every_check)


def _check_results(checks: Sequence[str], review: Review) -> tuple[CheckResult, ...]:
    """Pair each question with its verdict. The first verdict for an id wins."""
    by_id: dict[int, CheckVerdict] = {}
    for verdict in review.verdicts:
        by_id.setdefault(verdict.id, verdict)

    return tuple(
        CheckResult(
            question=question,
            passed=by_id[number].passed,
            evidence=by_id[number].evidence,
            fix=None if by_id[number].passed else by_id[number].fix,
        )
        for number, question in enumerate(checks, start=1)
    )


def _run_validators[T](
    validators: Sequence[Validator[T]], candidate: T
) -> tuple[str, ...]:
    problems: list[str] = []
    for validator in validators:
        found = validator(candidate)
        # A bare string is a Sequence[str] too; iterating it would report one
        # problem per character.
        problems.extend([found] if isinstance(found, str) else found)

    return tuple(problems)


def _revision_variables(best: Attempt[Any]) -> dict[str, Any]:
    """Values for revise.human.jinja. Plain data only -- see `prompts`."""
    candidate = cast(BaseModel, best.candidate)
    return {
        "_thinking_answer": candidate.model_dump_json(indent=2),
        "_thinking_problems": list(best.problems),
        "_thinking_failed": [
            {"question": check.question, "evidence": check.evidence, "fix": check.fix}
            for check in best.checks
            if not check.passed
        ],
        "_thinking_passed": [check.question for check in best.checks if check.passed],
    }


def _total_usage(usages: Sequence[Usage]) -> Usage:
    """Sum every call's usage. `model` is None when the calls used more than one."""
    models = {usage.model for usage in usages if usage.model}
    return Usage(
        model=next(iter(models)) if len(models) == 1 else None,
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        total_tokens=sum(usage.total_tokens for usage in usages),
        llm_calls=sum(usage.llm_calls for usage in usages),
        prompts=[prompt for usage in usages for prompt in usage.prompts],
        raw_outputs=[output for usage in usages for output in usage.raw_outputs],
    )


def build_graph[T: BaseModel](
    *,
    prompt: ChatPromptTemplate,
    output: type[T],
    chat: ChatLLM,
    logger: logging.Logger,
    criteria: Sequence[str] | None = None,
    validators: Sequence[Validator[T]] = (),
    evaluator_chat: ChatLLM | None = None,
    policy: ThinkingPolicy = DEFAULT_THINKING_POLICY,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    title: str = "thinking",
) -> ThinkingGraph:
    """Compile the workflow once, to invoke for many inputs.

    Use this over `think` to stream node updates, add a checkpointer, or embed
    the loop as a subgraph. Invoke it with `{"input": {...template variables}}`
    and a `recursion_limit` of at least `policy.recursion_limit`.

    Raises:
        ValueError: `prompt` never references `format_instructions`.
    """
    parser = PydanticOutputParser(pydantic_object=output)
    task_prompt = bind_output_schema(prompt, parser)
    reviewer = evaluator_chat if evaluator_chat is not None else chat
    fixed_checks = (
        None if criteria is None else [c.strip() for c in criteria if c.strip()]
    )

    checklist_prompt = _load_templates(
        "checklist",
        format_instructions=_CHECKLIST_PARSER.get_format_instructions(),
        max_checks=policy.max_checks,
    )
    review_prompt = _load_templates(
        "review",
        format_instructions=_REVIEW_PARSER.get_format_instructions(),
    )
    requirements_prompt = _load_message("requirements")
    # The previous answer goes back as the model's own turn, the feedback as
    # the user's reply to it.
    revise_prompt = ChatPromptTemplate.from_messages(
        [("ai", "{{ _thinking_answer }}")],
        template_format="jinja2",
    ) + _load_message("revise")

    def checklist(state: ThinkingState, config: RunnableConfig) -> dict[str, Any]:
        task = _render_task(task_prompt, state["input"])
        if fixed_checks is not None:
            return {"task": task, "checks": fixed_checks}

        result = invoke_llm_detailed(
            template=checklist_prompt,
            chat=reviewer,
            parser=_CHECKLIST_PARSER,
            logger=logger,
            input={"task": task},
            config=config,
            title=f"{title}: checklist",
            retry_policy=retry_policy,
        )
        checks = [c.strip() for c in result.value.checks if c.strip()]
        return {
            "task": task,
            "checks": checks[: policy.max_checks],
            "usage": [result.usage],
        }

    def generate(state: ThinkingState, config: RunnableConfig) -> dict[str, Any]:
        attempts = state.get("attempts", [])
        template = task_prompt
        variables = dict(state["input"])

        if state["checks"]:
            template += requirements_prompt
            variables["_thinking_checks"] = state["checks"]

        if attempts:
            template += revise_prompt
            variables |= _revision_variables(attempts[state["best"]])

        result = invoke_llm_detailed(
            template=template,
            chat=chat,
            parser=parser,
            logger=logger,
            input=variables,
            config=config,
            title=f"{title}: {_label(len(attempts))}",
            retry_policy=retry_policy,
        )
        return {"draft": result.value, "usage": [result.usage]}

    def evaluate(state: ThinkingState, config: RunnableConfig) -> dict[str, Any]:
        draft = cast(T, state["draft"])
        checks = state["checks"]
        attempts = state.get("attempts", [])
        number = len(attempts)
        problems = _run_validators(validators, draft)
        update: dict[str, Any] = {}

        results: tuple[CheckResult, ...] = ()
        if checks and not problems:
            review = invoke_llm_detailed(
                template=review_prompt,
                chat=reviewer,
                parser=_review_parser(len(checks)),
                logger=logger,
                input={
                    "task": state["task"],
                    "checks": [
                        {"id": check_id, "question": question}
                        for check_id, question in enumerate(checks, start=1)
                    ],
                    "answer": draft.model_dump_json(indent=2),
                },
                config=config,
                title=f"{title}: review of {_label(number)}",
                retry_policy=retry_policy,
            )
            results = _check_results(checks, cast(Review, review.value))
            update["usage"] = [review.usage]

        attempt = Attempt(candidate=draft, problems=problems, checks=results)
        if not attempts or attempt.rank > attempts[state["best"]].rank:
            best, stale = number, 0
        else:
            best, stale = state["best"], state.get("stale", 0) + 1

        if problems:
            outcome = f"has {len(problems)} validator problem(s), so was not reviewed"
        elif not results:
            outcome = "passed its validators, with no checklist to review"
        else:
            passed = sum(check.passed for check in results)
            outcome = f"passed {passed}/{len(results)} check(s)"
        logger.info(
            "%s: %s %s%s",
            title,
            _label(number),
            outcome,
            " -- new best" if best == number else "",
        )
        return update | {"attempts": [attempt], "best": best, "stale": stale}

    def route(state: ThinkingState) -> Literal["revise", "done"]:
        attempts = state["attempts"]
        if attempts[state["best"]].meets(policy.accept_score):
            return "done"
        if len(attempts) > policy.max_revisions:
            return "done"
        if state["stale"] >= policy.patience:
            return "done"

        return "revise"

    builder: StateGraph[ThinkingState, None, ThinkingState, ThinkingState] = StateGraph(
        ThinkingState
    )
    builder.add_node("checklist", checklist)
    builder.add_node("generate", generate)
    builder.add_node("evaluate", evaluate)
    builder.add_edge(START, "checklist")
    builder.add_edge("checklist", "generate")
    builder.add_edge("generate", "evaluate")
    builder.add_conditional_edges(
        "evaluate",
        route,
        {"revise": "generate", "done": END},
    )
    return builder.compile(name=title)


def think[T: BaseModel](
    *,
    prompt: ChatPromptTemplate,
    output: type[T],
    chat: ChatLLM,
    logger: logging.Logger,
    input: Mapping[str, Any] | None = None,
    criteria: Sequence[str] | None = None,
    validators: Sequence[Validator[T]] = (),
    evaluator_chat: ChatLLM | None = None,
    policy: ThinkingPolicy = DEFAULT_THINKING_POLICY,
    config: RunnableConfig | None = None,
    title: str = "thinking",
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> ThinkingResult[T]:
    """Generate `output`, review it, and revise it until it passes or stops improving.

    Args:
        prompt: The system/human templates, not yet bound to a schema -- the
            same prompt `basic.generate` takes.
        output: The Pydantic model to return.
        chat: Chat model that writes candidates.
        logger: Caller's logger. Each attempt's review is reported here.
        input: Template variables, every one the templates reference except
            `format_instructions`.
        criteria: Yes/no questions every candidate must pass, phrased so YES
            means the requirement is met. None derives them from the task with
            one extra model call. An empty sequence skips the model review
            entirely, leaving `validators` as the only judge.
        validators: Deterministic checks, run before the model review. A
            candidate with problems is not sent for review.
        evaluator_chat: Chat model for the checklist and reviews. Defaults to
            `chat`; a different model reduces a reviewer's bias toward its own
            writing.
        policy: When to accept, when to give up, how many checks to derive.
        config: Runnable config for the graph run. Copied, never mutated. Its
            `recursion_limit` is raised to what `policy` needs if unset.
        title: Label for log messages and the graph run.
        retry_policy: Retries for each model call.

    Returns:
        The best candidate with every attempt, its review, and total usage.
        Check `accepted`: the best candidate is returned even if it never met
        the bar.

    Raises:
        ValueError: `prompt` never references `format_instructions`.
    """
    graph = build_graph(
        prompt=prompt,
        output=output,
        chat=chat,
        logger=logger,
        criteria=criteria,
        validators=validators,
        evaluator_chat=evaluator_chat,
        policy=policy,
        retry_policy=retry_policy,
        title=title,
    )

    run_config: RunnableConfig = {} if config is None else copy.copy(config)
    run_config.setdefault("recursion_limit", policy.recursion_limit)

    started = time.perf_counter()
    state = graph.invoke(
        {"input": dict(input or {})},
        run_config,
        version="v2",
    ).value
    latency_s = time.perf_counter() - started

    attempts = cast(tuple[Attempt[T], ...], tuple(state["attempts"]))
    best = attempts[state["best"]]
    accepted = best.meets(policy.accept_score)
    usage = _total_usage(state.get("usage", []))

    if accepted:
        logger.info(
            "%s: accepted the %s after %d attempt(s) in %.2fs: %s",
            title,
            _label(state["best"]),
            len(attempts),
            latency_s,
            usage.describe(),
        )
    else:
        logger.warning(
            "%s: nothing passed in %d attempt(s); returning the %s "
            "(score %.2f, %d validator problem(s)) after %.2fs: %s",
            title,
            len(attempts),
            _label(state["best"]),
            best.score,
            len(best.problems),
            latency_s,
            usage.describe(),
        )

    return ThinkingResult(
        value=best.candidate,
        accepted=accepted,
        checks=tuple(state["checks"]),
        attempts=attempts,
        best_index=state["best"],
        usage=usage,
        latency_s=latency_s,
    )

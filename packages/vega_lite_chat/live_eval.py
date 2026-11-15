"""Run eval_cases.yaml against the real Ollama and print a pass/fail table.

Two kinds of case: the translator's (does the chart match?) and the chat model's routing (does it
call vega_lite_tool for a drawing, and answer a question in prose?). Run it by hand before a demo
and after changing the model or the prompts:
`bazel run //packages/vega_lite_chat:live_eval`. It exits non-zero
when any case fails. Cases on a sample CSV that isn't bundled are skipped.
"""

import argparse
import functools
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

import pydantic
import yaml
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from packages.vega_lite_chat.agent import (
    ChatContext,
    chat_reply,
)
from packages.vega_lite_chat.assistant_turn import AssistantTurn
from packages.vega_lite_chat.config import (
    AppConfig,
    load_config,
)
from packages.vega_lite_chat.llm import (
    Models,
    OllamaUnavailable,
    StructuredModel,
    ollama_models,
    reaching_ollama,
)
from packages.vega_lite_chat.prompts import (
    PromptBook,
    build_messages,
    load_prompts,
)
from packages.vega_lite_chat.samples import (
    Sample,
    sample_named,
)
from packages.vega_lite_chat.session import (
    ChatSession,
    Turn,
)
from packages.vega_lite_chat.translator import translate
from packages.vega_lite_core.chart_spec import (
    Aggregate,
    Channel,
    ChartSpec,
    FieldType,
    Mark,
    TimeUnit,
)
from packages.vega_lite_core.compiler import (
    compile_chart,
    vega_lite_errors,
)
from packages.vega_lite_core.csv_loader import load_csv
from packages.vega_lite_core.profile import (
    DataProfile,
    profile_frame,
)

DEFAULT_CASES = Path(__file__).with_name("eval_cases.yaml")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_by_name=True)


class EncodingExpect(_Strict):
    """Partial expectations for one channel; every key left out matches anything."""

    field: str | None = None
    type: list[FieldType] | None = None
    time_unit: list[TimeUnit] | None = Field(default=None, alias="timeUnit")
    aggregate: list[Aggregate] | None = None


class Expect(_Strict):
    """What a case's chart must contain to pass."""

    chart: bool = True  # False: the model must ask back instead of drawing
    mark: list[Mark] | None = None
    fields: list[str] = Field(default_factory=list)  # each used on some channel
    encodings: dict[Channel, EncodingExpect] = Field(default_factory=dict)
    filters: bool | None = None
    filter_field: str | None = None
    top_n: bool | None = None


class EvalCase(_Strict):
    """One chart request to send to the live model, with its expectations."""

    name: str
    sample: str
    first_chart: bool = False  # request is the prompt file's first_chart_request
    request: str | None = None
    current: ChartSpec | None = None
    recent: list[str] = Field(default_factory=list)
    expect: Expect

    @model_validator(mode="after")
    def _one_request(self) -> Self:
        if self.first_chart == (self.request is not None):
            raise ValueError(f"{self.name}: give either request or first_chart: true")
        return self


class RoutingCase(_Strict):
    """A request that checks whether the chat model draws or answers in prose."""

    name: str
    sample: str
    current: ChartSpec | None = None
    request: str
    draw: bool  # True: the chat model must call vega_lite_tool; False: answer in prose


class CaseFile(_Strict):
    """The eval cases file."""

    cases: list[EvalCase]
    routing: list[RoutingCase] = Field(default_factory=list)


def load_cases(path: Path = DEFAULT_CASES) -> CaseFile:
    """Load the eval cases from *path*."""
    return CaseFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def expectation_problems(expect: Expect, turn: AssistantTurn) -> list[str]:
    """What in `turn` misses `expect`; empty when it matches."""
    chart = turn.chart
    if not expect.chart:
        return (
            []
            if chart is None
            else [f"expected a question back, got a {chart.mark} chart"]
        )
    if chart is None:
        return [f"expected a chart, got a question: {turn.message}"]
    problems = []
    if expect.mark is not None and chart.mark not in expect.mark:
        problems.append(f"mark {chart.mark}, expected one of {expect.mark}")
    encodings = dict(chart.encodings())
    used = {enc.field for enc in encodings.values()}
    problems += [
        f"column {name} not used" for name in expect.fields if name not in used
    ]
    for channel, wanted in expect.encodings.items():
        enc = encodings.get(channel)
        if enc is None:
            problems.append(f"{channel} not set")
            continue
        if wanted.field is not None and enc.field != wanted.field:
            problems.append(f"{channel}.field {enc.field}, expected {wanted.field}")
        if wanted.type is not None and enc.type not in wanted.type:
            problems.append(f"{channel}.type {enc.type}, expected one of {wanted.type}")
        if wanted.time_unit is not None and enc.time_unit not in wanted.time_unit:
            problems.append(
                f"{channel}.timeUnit {enc.time_unit}, expected one of {wanted.time_unit}"
            )
        if wanted.aggregate is not None and enc.aggregate not in wanted.aggregate:
            problems.append(
                f"{channel}.aggregate {enc.aggregate}, expected one of {wanted.aggregate}"
            )
    if expect.filters is not None and bool(chart.filters) != expect.filters:
        problems.append(
            f"filters {[f.field for f in chart.filters]}, expected {'some' if expect.filters else 'none'}"
        )
    if expect.filter_field is not None and expect.filter_field not in {
        f.field for f in chart.filters
    }:
        problems.append(f"no filter on {expect.filter_field}")
    if expect.top_n is not None and (chart.top_n is not None) != expect.top_n:
        problems.append(
            f"top_n {chart.top_n}, expected {'one' if expect.top_n else 'none'}"
        )
    return problems


def dropped_filter_claims(current: ChartSpec | None, turn: AssistantTurn) -> list[str]:
    """Filter values of the current chart that the new chart dropped but the message still names."""
    if current is None or turn.chart is None:
        return []
    kept = {kept.field for kept in turn.chart.filters}
    problems = []
    for dropped in current.filters:
        if dropped.field in kept:
            continue
        values = dropped.value if isinstance(dropped.value, list) else [dropped.value]
        named = [str(value) for value in values if str(value) in turn.message]
        if named:
            problems.append(
                f"message names {', '.join(named)}, but the chart dropped the filter on {dropped.field}"
            )
    return problems


@dataclass(frozen=True)
class CaseResult:
    """The outcome of one eval case."""

    name: str
    outcome: Literal["PASS", "FAIL", "SKIP"]
    calls: int
    seconds: float
    problems: tuple[str, ...]


def run_case(
    case: EvalCase, model: StructuredModel, book: PromptBook, config: AppConfig
) -> CaseResult:
    """Run one chart case against the live model and check the result."""
    try:
        sample = sample_named(case.sample)
    except KeyError:
        return CaseResult(case.name, "SKIP", 0, 0.0, (f"{case.sample} is not bundled",))
    profile = _session(sample, config).profile
    request = book.first_chart_request if case.request is None else case.request
    messages = build_messages(book, profile, case.current, case.recent, request)
    started = time.perf_counter()
    translation = translate(
        model,
        messages,
        profile,
        max_calls=config.translator.max_calls,
        on_attempt=lambda number, errors: None,
    )
    seconds = time.perf_counter() - started
    calls = len(translation.attempts)
    if translation.turn is None:
        last = translation.attempts[-1].errors if translation.attempts else ()
        problems = (f"no valid reply after {calls} calls", *last)
        return CaseResult(case.name, "FAIL", calls, seconds, problems)
    problems_list = expectation_problems(case.expect, translation.turn)
    problems_list += dropped_filter_claims(case.current, translation.turn)
    if translation.turn.chart is not None:
        spec = compile_chart(
            translation.turn.chart, profile, height=config.chart.height
        )
        problems_list += [f"compiler: {error}" for error in vega_lite_errors(spec)]
    outcome: Literal["PASS", "FAIL"] = "FAIL" if problems_list else "PASS"
    return CaseResult(case.name, outcome, calls, seconds, tuple(problems_list))


def run_routing_case(
    case: RoutingCase, models: Models, book: PromptBook, config: AppConfig
) -> CaseResult:
    """One call to the chat model, as the chat node makes it; the tool itself never runs."""
    try:
        sample = sample_named(case.sample)
    except KeyError:
        return CaseResult(case.name, "SKIP", 0, 0.0, (f"{case.sample} is not bundled",))
    session = _session(sample, config)
    if case.current is not None:
        session.add_turn(_shown(case.current, session.profile, config))
    context = ChatContext(session=session, prompts=book, config=config, models=models)
    started = time.perf_counter()
    with reaching_ollama(config.ollama):
        reply = chat_reply(context, [HumanMessage(content=case.request)])
    seconds = time.perf_counter() - started
    problems: list[str] = []
    if case.draw and not reply.tool_calls:
        problems.append(
            f"expected a vega_lite_tool call, got an answer: {reply.text[:80]}"
        )
    if not case.draw and reply.tool_calls:
        problems.append(
            f"expected an answer, got a call: {reply.tool_calls[0]['args']}"
        )
    outcome: Literal["PASS", "FAIL"] = "FAIL" if problems else "PASS"
    return CaseResult(case.name, outcome, 1, seconds, tuple(problems))


def _session(sample: Sample, config: AppConfig) -> ChatSession:
    settings = config.data
    df = load_csv(sample.read_bytes())
    profile = profile_frame(
        df,
        sample_rows=settings.sample_rows,
        seed=settings.sample_seed,
        max_listed_values=settings.max_listed_values,
    )
    return ChatSession(source_name=sample.file_name, df=df, profile=profile)


def _shown(chart: ChartSpec, profile: DataProfile, config: AppConfig) -> Turn:
    """A turn that put `chart` on screen, so the chat model sees it as the current chart."""
    return Turn(
        request="",
        auto=True,
        reply=AssistantTurn(chart=chart, message=""),
        vega_lite=compile_chart(chart, profile, height=config.chart.height),
        attempts=(),
    )


def format_table(results: Sequence[CaseResult]) -> str:
    """Format *results* as a fixed-width table."""
    width = max([len("case"), *(len(result.name) for result in results)])
    lines = [f"{'case':<{width}}  result  calls  seconds"]
    for result in results:
        lines.append(
            f"{result.name:<{width}}  {result.outcome:<6}  {result.calls:>5}  {result.seconds:>7.1f}"
        )
    for result in results:
        for problem in result.problems:
            lines.append(f"  {result.name}: {problem}")
    passed = sum(result.outcome == "PASS" for result in results)
    failed = sum(result.outcome == "FAIL" for result in results)
    skipped = sum(result.outcome == "SKIP" for result in results)
    lines.append(f"{passed} passed, {failed} failed, {skipped} skipped")
    return "\n".join(lines)


class Args(pydantic.BaseModel):
    """Command line arguments."""

    case: list[str] | None = None
    thinking: bool = False


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the live eval."""
    parser = argparse.ArgumentParser(
        prog="live_eval",
        description="Run eval_cases.yaml against the Ollama model in config.yaml.",
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Run only cases whose name contains this text (repeatable).",
    )
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Turn the model's thinking on (much slower). Off by default, like the app.",
    )
    return parser


def run_cli(namespace: argparse.Namespace) -> int:
    """Validate a parsed command line into `Args` and run."""
    return main(Args(**vars(namespace)))


def main(args: Args) -> int:
    """Run the selected cases and return an exit code."""
    config = load_config()
    book = load_prompts(data=config.data)
    case_file = load_cases()
    cases = case_file.cases
    routing = case_file.routing
    if args.case:
        wanted = args.case
        cases = [case for case in cases if any(text in case.name for text in wanted)]
        routing = [
            case for case in routing if any(text in case.name for text in wanted)
        ]
        if not cases and not routing:
            print(f"no case matches {wanted}", file=sys.stderr)
            return 2
    models = ollama_models(config.ollama, reasoning=args.thinking)
    runs: list[Callable[[], CaseResult]] = [
        functools.partial(run_case, case, models.chart, book, config) for case in cases
    ]
    runs += [
        functools.partial(run_routing_case, case, models, book, config)
        for case in routing
    ]
    results = []
    for run in runs:
        try:
            result = run()
        except OllamaUnavailable as error:
            print(error, file=sys.stderr)
            return 2
        print(f"{result.outcome} {result.name} ({result.seconds:.1f} s)", flush=True)
        results.append(result)
    print()
    print(format_table(results))
    return 1 if any(result.outcome == "FAIL" for result in results) else 0


if __name__ == "__main__":
    sys.exit(run_cli(build_parser().parse_args()))

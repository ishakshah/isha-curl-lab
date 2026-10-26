"""The agent team: one definition per agent, plus the shared runner that audits, meters and limits every run.

Agents (all gpt-6-luna through Portkey, Responses API):
    photo_analyst  - reads a wash-day photo (vision, no tools)
    hair_science   - protein/moisture balance, porosity needs, cadence
    weather        - 7-day forecast -> hair advice (tool: get_forecast)
    schedule       - the weekly calendar
    products       - picks real catalog products (tool: search_catalog)
    budget         - fits picks to the budget (tool: product_cost)
    planner        - writes the routine steps
    daily_coach    - decides what to do today from a saved routine
    haircut        - one-time haircut ideas from the intake (no tools)
"""

import asyncio
import fcntl
import itertools
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Awaitable, Callable

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.messages import RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart

from app import config, tools
from app.config import build_model
from app.schemas import (
    BudgetPlan, HaircutSuggestion, HairAnalysis, HairScienceReport, ProductPicks, Routine, ScheduleReport, TodayPlan, WeatherAdvice,
)

AUDIT_PATH = config.OUTPUT_DIR / "audit_trail.json"
AUDIT_MAX_CHARS = 500  # longer values are cut in the audit trail (same as HW5)
AUDIT_RETENTION_DAYS = 90  # entries older than this are dropped when a new one is written (same as HW5)


class LimitReached(Exception):
    """The build used up its shared request, tool-call or token allowance."""


# ---------- Shared run context ----------

@dataclass
class RunContext_:
    """One build / photo check / daily check: its id, spending so far, and a way to report progress."""

    kind: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    emit: Callable[[dict], Awaitable[None]] | None = None
    agents: list[dict] = field(default_factory=list)  # per-agent usage, in finish order
    steps: itertools.count = field(default_factory=itertools.count, repr=False)
    started: float = field(default_factory=time.time)

    def totals(self) -> dict:
        keys = ("input_tokens", "cached_tokens", "output_tokens", "requests", "tool_calls")
        totals = {k: sum(a[k] for a in self.agents) for k in keys}
        totals["cost_usd"] = round(sum(a["cost_usd"] for a in self.agents), 6)
        totals["wall_seconds"] = round(time.time() - self.started, 1)
        return totals


@dataclass
class Gate:
    """Pause switch (as in HW5): while cleared, runs hold at their next step and resume where they were."""

    event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self):
        self.event.set()


gate = Gate()


class DailySpend:
    """App-wide token counter for the daily cap."""

    def __init__(self):
        self.day = datetime.now().date()
        self.tokens = 0

    def _roll(self):
        if datetime.now().date() != self.day:
            self.day, self.tokens = datetime.now().date(), 0

    def add(self, tokens: int):
        self._roll()
        self.tokens += tokens

    def exhausted(self) -> bool:
        self._roll()
        return self.tokens >= config.DAILY_TOKEN_CAP


daily_spend = DailySpend()


# ---------- Audit trail ----------

def _short(value):
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= AUDIT_MAX_CHARS:
        return value
    return text[:AUDIT_MAX_CHARS] + f"... [truncated, {len(text)} chars total]"


def audit(ctx: RunContext_, agent: str, event: str, **detail) -> None:
    """Append one step to output/audit_trail.json (a valid JSON list, never wiped, entries over 90 days dropped)."""
    entry = {
        "run_id": ctx.run_id, "kind": ctx.kind, "step": next(ctx.steps),
        "logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "agent": agent, "event": event, **{k: _short(v) for k, v in detail.items()},
    }
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    with open(AUDIT_PATH, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        text = f.read()
        trail = json.loads(text) if text.strip() else []  # a corrupt file raises instead of being overwritten
        if not isinstance(trail, list):
            raise RuntimeError(f"{AUDIT_PATH} must contain a JSON list")
        cutoff = datetime.now().astimezone() - timedelta(days=AUDIT_RETENTION_DAYS)
        trail = [e for e in trail if "logged_at" not in e or datetime.fromisoformat(e["logged_at"]) >= cutoff]
        trail.append(entry)
        f.seek(0)
        f.truncate()
        json.dump(trail, f, indent=2)
        f.write("\n")


# ---------- Agent definitions ----------

@dataclass
class BudgetDeps:
    uses_per_month: dict[str, float]
    hair_length: str


@dataclass
class WeatherDeps:
    forecast: dict | None = None


def _instructions(name: str) -> Callable[[RunContext], str]:
    def load(_: RunContext) -> str:
        shared = (config.PROMPT_DIR / "_shared.md").read_text()
        own = (config.PROMPT_DIR / f"{name}.md").read_text()
        return f"{shared}\n\n{own}"  # read on every run, so prompt edits apply immediately
    return load


def _agent(name: str, output_type, **kwargs) -> Agent:
    return Agent(
        build_model(), output_type=output_type, instructions=_instructions(name),
        model_settings={"max_tokens": config.MAX_OUTPUT_TOKENS}, **kwargs,
    )


@lru_cache
def get_agents() -> dict[str, Agent]:
    photo = _agent("photo_analyst", HairAnalysis)
    hair_science = _agent("hair_science", HairScienceReport, tools=[tools.explain_ingredients])
    products = _agent("products", ProductPicks, tools=[tools.search_catalog])
    schedule = _agent("schedule", ScheduleReport)
    planner = _agent("planner", Routine)
    coach = _agent("daily_coach", TodayPlan)
    haircut = _agent("haircut", HaircutSuggestion)

    weather = _agent("weather", WeatherAdvice, deps_type=WeatherDeps)

    @weather.tool
    async def get_forecast(ctx: RunContext[WeatherDeps], zip_code: str) -> dict:
        """Seven-day forecast for a US ZIP code: temperature, dew point, humidity, UV, wind, rain chance and a climate label per day."""
        try:
            ctx.deps.forecast = await tools.fetch_forecast(zip_code)
        except Exception as e:  # ZIP not found or the weather service is down
            ctx.deps.forecast = None
            return {"error": f"Weather unavailable: {type(e).__name__}"}
        return ctx.deps.forecast

    budget = _agent("budget", BudgetPlan, deps_type=BudgetDeps)

    @budget.tool
    def product_cost(ctx: RunContext[BudgetDeps], product_id: str, category: str) -> dict:
        """Cost per use, monthly cost and upfront cost for a catalog product, using this person's monthly usage for that category."""
        return tools.product_cost(product_id, ctx.deps.uses_per_month.get(category, 0.0), ctx.deps.hair_length)

    return {
        "photo_analyst": photo, "hair_science": hair_science, "weather": weather, "schedule": schedule,
        "products": products, "budget": budget, "planner": planner, "daily_coach": coach, "haircut": haircut,
    }


# ---------- Runner ----------

async def run_agent(ctx: RunContext_, name: str, prompt, deps=None):
    """Run one agent step by step: hold if paused, audit every turn and tool call, and meter its tokens."""
    if daily_spend.exhausted():
        raise LimitReached("The app's daily usage cap has been reached. Please try again tomorrow.")
    used = ctx.totals()
    limits = UsageLimits(
        request_limit=config.REQUEST_LIMIT - used["requests"],
        tool_calls_limit=config.TOOL_CALLS_LIMIT - used["tool_calls"],
        total_tokens_limit=config.TOTAL_TOKENS_LIMIT - used["input_tokens"] - used["output_tokens"],
    )
    if min(limits.request_limit, limits.tool_calls_limit, limits.total_tokens_limit) <= 0:
        raise LimitReached("This run used up its request, tool-call or token allowance.")

    agent = get_agents()[name]
    started = time.time()
    audit(ctx, name, "run_start", task=prompt if isinstance(prompt, str) else str(prompt[0]))
    if ctx.emit:
        await ctx.emit({"event": "agent_start", "agent": name})
    try:
        async with agent.iter(prompt, deps=deps, usage_limits=limits) as run:
            async for node in run:
                if not gate.event.is_set():
                    audit(ctx, name, "paused")
                    if ctx.emit:
                        await ctx.emit({"event": "paused"})
                    await gate.event.wait()
                    audit(ctx, name, "resumed")
                if Agent.is_call_tools_node(node):
                    response = node.model_response
                    audit(
                        ctx, name, "model_turn", model=response.model_name,
                        text=" ".join(p.content for p in response.parts if isinstance(p, TextPart)) or None,
                        tool_calls=[p.tool_name for p in response.parts if isinstance(p, ToolCallPart)],
                        tokens={"input": response.usage.input_tokens, "output": response.usage.output_tokens},
                    )
                    for part in response.parts:
                        if isinstance(part, ToolCallPart):
                            audit(ctx, name, "tool_call", tool=part.tool_name, args=part.args_as_dict())
                            if ctx.emit:
                                await ctx.emit({"event": "tool", "agent": name, "tool": part.tool_name})
                elif Agent.is_model_request_node(node):
                    for part in node.request.parts:
                        if isinstance(part, ToolReturnPart):
                            audit(ctx, name, "tool_result", tool=part.tool_name, result=part.content)
                        elif isinstance(part, RetryPromptPart):
                            audit(ctx, name, "tool_retry", tool=part.tool_name, error=part.content)
        result = run.result
    except BaseException as e:
        cancelled = type(e).__name__ == "CancelledError"
        audit(ctx, name, "run_error", error="Cancelled before finishing" if cancelled else f"{type(e).__name__}: {e}")
        raise

    u = result.usage
    record = {
        "agent": name, "input_tokens": u.input_tokens, "cached_tokens": u.cache_read_tokens,
        "output_tokens": u.output_tokens, "requests": u.requests, "tool_calls": u.tool_calls,
        "seconds": round(time.time() - started, 1),
        "cost_usd": round(config.estimate_cost_usd(u.input_tokens, u.cache_read_tokens, u.output_tokens), 6),
    }
    ctx.agents.append(record)
    daily_spend.add(u.input_tokens + u.output_tokens)
    audit(ctx, name, "run_end", output=result.output.model_dump(), usage=record)
    if ctx.emit:
        await ctx.emit({"event": "agent_done", "agent": name, "usage": record})
    return result.output

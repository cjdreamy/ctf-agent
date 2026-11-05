"""Featherless coordinator using Pydantic AI function tools."""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.toolsets import FunctionToolset

from backend.agents.coordinator_core import (
    do_broadcast,
    do_bump_agent,
    do_check_swarm_status,
    do_fetch_challenges,
    do_get_solve_status,
    do_kill_swarm,
    do_read_solver_trace,
    do_spawn_swarm,
    do_submit_flag,
)
from backend.agents.coordinator_loop import build_deps, run_event_loop
from backend.config import Settings
from backend.deps import CoordinatorDeps
from backend.models import resolve_model, resolve_model_settings

logger = logging.getLogger(__name__)

COORDINATOR_PROMPT = """\
You coordinate a CTF challenge solving run.

On startup, use the available tools to review challenge status and spawn swarms for
unsolved challenges. Prioritize challenges with lower solve counts. During the run,
check status and solver traces when events arrive, then send focused guidance to
stalled agents or share useful discoveries across a swarm. Keep submissions to
candidate flags discovered by solvers. Never claim a challenge is solved unless
CTFd confirms it.
"""


def _build_agent(model_spec: str, settings: Settings) -> Agent[CoordinatorDeps, str]:
    async def fetch_challenges(ctx: RunContext[CoordinatorDeps]) -> str:
        return await do_fetch_challenges(ctx.deps)

    async def get_solve_status(ctx: RunContext[CoordinatorDeps]) -> str:
        return await do_get_solve_status(ctx.deps)

    async def spawn_swarm(ctx: RunContext[CoordinatorDeps], challenge_name: str) -> str:
        return await do_spawn_swarm(ctx.deps, challenge_name)

    async def check_swarm_status(ctx: RunContext[CoordinatorDeps], challenge_name: str) -> str:
        return await do_check_swarm_status(ctx.deps, challenge_name)

    async def submit_flag(
        ctx: RunContext[CoordinatorDeps], challenge_name: str, flag: str
    ) -> str:
        return await do_submit_flag(ctx.deps, challenge_name, flag)

    async def kill_swarm(ctx: RunContext[CoordinatorDeps], challenge_name: str) -> str:
        return await do_kill_swarm(ctx.deps, challenge_name)

    async def bump_agent(
        ctx: RunContext[CoordinatorDeps],
        challenge_name: str,
        model_spec: str,
        insights: str,
    ) -> str:
        return await do_bump_agent(ctx.deps, challenge_name, model_spec, insights)

    async def broadcast(
        ctx: RunContext[CoordinatorDeps], challenge_name: str, message: str
    ) -> str:
        return await do_broadcast(ctx.deps, challenge_name, message)

    async def read_solver_trace(
        ctx: RunContext[CoordinatorDeps],
        challenge_name: str,
        model_spec: str,
        last_n: int = 20,
    ) -> str:
        return await do_read_solver_trace(ctx.deps, challenge_name, model_spec, last_n)

    toolset = FunctionToolset(
        tools=[
            fetch_challenges,
            get_solve_status,
            spawn_swarm,
            check_swarm_status,
            submit_flag,
            kill_swarm,
            bump_agent,
            broadcast,
            read_solver_trace,
        ]
    )
    return Agent(
        resolve_model(model_spec, settings),
        deps_type=CoordinatorDeps,
        system_prompt=COORDINATOR_PROMPT,
        model_settings=resolve_model_settings(model_spec),
        toolsets=[toolset],
    )


async def run_featherless_coordinator(
    settings: Settings,
    model_specs: list[str] | None = None,
    challenges_root: str = "challenges",
    no_submit: bool = False,
    coordinator_model: str | None = None,
    msg_port: int = 0,
) -> dict[str, Any]:
    """Run the coordinator using Featherless's OpenAI-compatible API."""
    if not settings.featherless_api_key:
        raise ValueError("FEATHERLESS_API_KEY is required for --coordinator featherless")

    specs = model_specs or []
    resolved_model = coordinator_model or next(
        (spec for spec in specs if spec.startswith("featherless/")),
        "featherless/Qwen/Qwen3-Coder-30B-A3B-Instruct",
    )
    if not resolved_model.startswith("featherless/"):
        resolved_model = f"featherless/{resolved_model}"

    ctfd, cost_tracker, deps = build_deps(settings, model_specs, challenges_root, no_submit)
    deps.msg_port = msg_port
    agent = _build_agent(resolved_model, settings)
    history: list = []
    logger.info("Featherless coordinator started (model=%s)", resolved_model)

    async def turn_fn(message: str) -> None:
        nonlocal history
        logger.debug("Coordinator query: %s", message[:200])
        result = await agent.run(
            message,
            deps=deps,
            message_history=history or None,
        )
        usage = result.usage()
        cost_tracker.record(
            "coordinator",
            usage,
            resolved_model.split("/", 1)[1],
            provider_spec="featherless",
        )
        history = result.all_messages()
        logger.info("Featherless coordinator turn done (%d tokens)", usage.total_tokens)

    return await run_event_loop(deps, ctfd, cost_tracker, turn_fn)

"""Run one scenario under one harness config, including crash/restart handling."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from smolagents import ToolCallingAgent
from smolagents.monitoring import LogLevel
from smolagents.utils import AgentError

from .faults import FaultPlan, SimulatedCrash, Transport
from .grading import grade
from .harness import BudgetedModel, HarnessConfig, HarnessStop, ToolExecutor
from .sim import Simulator
from .store import EventStore
from .tools import build_tools

ModelFactory = Callable[..., Any]  # (view, seed) -> smolagents Model

logging.getLogger("smolagents").setLevel(logging.WARNING)


def _resume_prompt(note: str, visible: list[dict[str, Any]]) -> str:
    lines = [f"- {e['tool']}({json.dumps(e['args'])}) -> "
             + (json.dumps(e['result'])[:300] if e["ok"] else f"ERROR {e['error']}") for e in visible]
    return ("\n\nNOTE: the harness restarted after an interruption and restored this episode from its checkpoint. "
            f"Reconciliation: {note or 'nothing pending'}. Tool results before the restart:\n" + "\n".join(lines)
            + "\nContinue from here; do not repeat remediations that were already executed.")


def run_episode(scenario: dict[str, Any], cfg: HarnessConfig, model_factory: ModelFactory, workdir: str | Path,
                seed: int = 0, model_label: str = "reference-policy") -> dict[str, Any]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    ep_id = f"{scenario['id']}__{cfg.name}__s{seed}"
    db = workdir / f"{ep_id}.sqlite"
    db.unlink(missing_ok=True)

    sim = Simulator.create(scenario["world"], db)
    plan = FaultPlan.from_list(scenario["faults"])
    store = EventStore(db, ep_id)
    episode_seed = (seed * 1_000_003 + scenario["seed"]) % (2**31)
    store.append("episode_start", {"scenario": scenario["id"], "config": cfg.to_dict(), "seed": seed,
                                   "episode_seed": episode_seed, "model": model_label, "faults": scenario["faults"]}, sim.now_ms)
    start_ms = sim.now_ms
    attempt, restarts = 0, 0
    executor = ToolExecutor(cfg, Transport(sim, plan), store, ep_id)
    holder = [executor]
    note = ""
    final, stop = None, "unknown"

    while True:
        executor.attempt = attempt
        # Per-episode stream: run seed mixed with the scenario seed (recorded in the trace).
        model = BudgetedModel(model_factory(view=lambda: holder[0].visible, seed=episode_seed), lambda: holder[0])
        agent = ToolCallingAgent(
            tools=build_tools(executor, cfg.tool_descriptions), model=model, max_steps=cfg.max_steps,
            instructions=cfg.instructions or None, max_tool_threads=1, verbosity_level=LogLevel.OFF,
            return_full_result=True,
        )
        task = scenario["task_prompt"] + (_resume_prompt(note, executor.visible) if note or executor.visible else "")
        try:
            result = agent.run(task)
            final = str(result.output)
            stop = "final_answer" if result.state == "success" else "max_steps"
            break
        except SimulatedCrash as e:
            store.append("crash", {"detail": str(e), "attempt": attempt}, sim.now_ms)
            restarts += 1
            if restarts > cfg.max_restarts:
                stop = "crashed"
                break
            attempt += 1
            # A new process: reconnect to the (persistent) world. Budgets survive only via checkpoint.
            sim = Simulator.load(db)
            executor = ToolExecutor(cfg, Transport(sim, plan), store, ep_id, sim_start_ms=start_ms)
            holder[0] = executor
            if cfg.checkpoint:
                note = executor.restore() or "no pending writes"
                store.append("resume", {"attempt": attempt, "note": note, "restored_results": len(executor.visible)},
                             sim.now_ms)
            else:
                note = ""
                store.append("restart", {"attempt": attempt, "mode": "from scratch"}, sim.now_ms)
        except HarnessStop as e:
            stop, final = e.reason, f"STOPPED: {e.reason} ({e.detail})"
            break
        except AgentError as e:  # model/parsing failures from a real LLM
            stop, final = "agent_error", f"STOPPED: {type(e).__name__}: {str(e)[:200]}"
            break

    store.append("episode_end", {"stop_reason": stop, "final_answer": final}, sim.now_ms)
    events = store.events()
    outcome = grade(scenario, Simulator.load(db), events, stop, final)
    outcome.update({"episode_id": ep_id, "config": cfg.name, "seed": seed, "model": model_label,
                    "sim_ms": sim.now_ms - start_ms, "restarts": restarts})
    store.close()
    trace = {"episode_id": ep_id, "scenario": {k: scenario[k] for k in
                                               ("id", "family", "incident", "variant", "split", "expected", "faults")},
             "config": cfg.to_dict(), "outcome": outcome, "events": events}
    (workdir / f"{ep_id}.trace.json").write_text(json.dumps(trace, default=str))
    db.unlink(missing_ok=True)
    return outcome

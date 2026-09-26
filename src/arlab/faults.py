"""Reproducible fault injection between the harness and the simulator.

A `FaultPlan` is data stored with each scenario, so a failure replays exactly.
The `Transport` is the only path from the harness to the simulator; faults are
applied there, the same place a flaky network or proxy would sit.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from . import sim as simmod

TIMEOUT_MS = 5000

FAULT_KINDS = (
    "timeout",               # request lost before reaching the service
    "timeout_after_commit",  # service executed it, response lost (ambiguous write)
    "transient",             # 503-style error, nothing executed
    "malformed",             # executed, response body truncated / not valid JSON
    "duplicate",             # request delivered twice (e.g. a retrying proxy)
    "stale",                 # served from an old cache snapshot
    "crash_after_commit",    # harness process dies right after the service executed
    "crash_before",          # harness process dies before sending the request
)


class ToolTimeout(Exception):
    retryable = True


class TransientServiceError(Exception):
    retryable = True


class SimulatedCrash(BaseException):
    """Simulates the harness process being killed. BaseException so no agent code swallows it."""


@dataclass(frozen=True)
class Fault:
    kind: str
    tool: str
    occurrence: int = 1  # 1-based index of the call to `tool` that is affected
    times: int = 1       # number of consecutive calls affected

    def __post_init__(self):
        if self.kind not in FAULT_KINDS:
            raise ValueError(f"unknown fault kind {self.kind}")

    def hits(self, n: int) -> bool:
        return self.occurrence <= n < self.occurrence + self.times


@dataclass
class FaultPlan:
    faults: list[Fault]

    @classmethod
    def from_list(cls, items: list[dict[str, Any]]) -> FaultPlan:
        return cls([Fault(**f) for f in items])

    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(f) for f in self.faults]


class Transport:
    """Sends tool calls to the simulator, applying scheduled faults.

    Call counters are persisted in the simulator state so a restarted harness
    does not re-trigger a fault that already fired.
    """

    def __init__(self, sim: simmod.Simulator, plan: FaultPlan):
        self.sim = sim
        self.plan = plan
        self.sim.state.setdefault("transport", {"counts": {}, "snapshots": {}, "fired": []})

    @property
    def _t(self) -> dict[str, Any]:
        return self.sim.state["transport"]

    def _fault_for(self, tool: str, n: int) -> Fault | None:
        for f in self.plan.faults:
            if f.tool == tool and f.hits(n):
                return f
        return None

    def call(self, tool: str, args: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any] | str:
        counts = self._t["counts"]
        counts[tool] = counts.get(tool, 0) + 1
        n = counts[tool]
        fault = self._fault_for(tool, n)
        if fault:
            self._t["fired"].append({"kind": fault.kind, "tool": tool, "n": n, "at_ms": self.sim.now_ms})
        try:
            return self._deliver(tool, args, idempotency_key, fault)
        finally:
            self.sim.checkpoint()

    def _deliver(self, tool, args, key, fault: Fault | None):
        kind = fault.kind if fault else None
        if kind == "crash_before":
            raise SimulatedCrash(f"harness crashed before sending {tool}")
        if kind == "timeout":
            self.sim.advance(TIMEOUT_MS)
            raise ToolTimeout(f"{tool} timed out after {TIMEOUT_MS} ms")
        if kind == "transient":
            self.sim.advance(simmod.READ_LATENCY_MS)
            raise TransientServiceError(f"{tool}: 503 service unavailable")
        snap_key = tool + ":" + json.dumps(args, sort_keys=True)
        if kind == "stale" and snap_key in self._t["snapshots"]:
            self.sim.advance(simmod.READ_LATENCY_MS // 5)  # cache hits are fast
            return dict(self._t["snapshots"][snap_key])

        result = simmod.call(self.sim, tool, args, key)
        if kind == "duplicate":
            try:
                result = simmod.call(self.sim, tool, args, key)
            except simmod.SimError:
                pass  # the second delivery's error is not what the client sees
        self._remember(tool, args, result)
        if kind == "timeout_after_commit":
            self.sim.advance(TIMEOUT_MS)
            raise ToolTimeout(f"{tool} timed out after {TIMEOUT_MS} ms")
        if kind == "crash_after_commit":
            raise SimulatedCrash(f"harness crashed after {tool} was executed")
        if kind == "malformed":
            text = json.dumps(result)
            return text[: max(12, len(text) * 2 // 5)]
        return result

    def _remember(self, tool: str, args: dict[str, Any], result: dict[str, Any]) -> None:
        """The first snapshot per (tool, args) is what a stale cache later serves."""
        if tool != "apply_remediation" and tool != "propose_remediation":
            self._t["snapshots"].setdefault(tool + ":" + json.dumps(args, sort_keys=True), result)

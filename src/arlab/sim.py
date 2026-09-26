"""Deterministic simulator for a fictional incident-response platform.

Everything here is synthetic: service names, logs, deployments and runbooks are
generated from scenario specs. Remediations mutate only this simulator.

The simulator plays the role of the *remote system* the agent operates on:
- It enforces authorization itself (grants + proposals), independent of the agent.
- It owns the server-side idempotency table (like an API that accepts an
  `Idempotency-Key` header). Deduplication therefore only works when the
  client sends a key; the simulator never guesses.
- Its state is persisted in SQLite so a crashed harness can reconnect to the
  same "world" after a restart.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path
from typing import Any

ACTIONS = ("restart_service", "rollback_deployment", "scale_up")
FIX_FOR = {"crashloop": "restart_service", "bad_deploy": "rollback_deployment", "overload": "scale_up"}

READ_LATENCY_MS = 250
WRITE_LATENCY_MS = 400
SETTLE_MS = 1500  # remediation effects become visible after this much simulated time


class SimError(Exception):
    code = "sim_error"


class NotFound(SimError):
    code = "not_found"


class Unauthorized(SimError):
    code = "unauthorized"


class InvalidRequest(SimError):
    code = "invalid_request"


class Simulator:
    """World state + tool semantics. All times are simulated milliseconds."""

    def __init__(self, state: dict[str, Any], db_path: str | Path | None = None):
        self.state = state
        self.db_path = str(db_path) if db_path else None
        if self.db_path:
            self._persist()

    # ----- persistence -------------------------------------------------
    @classmethod
    def create(cls, world: dict[str, Any], db_path: str | Path | None = None) -> Simulator:
        state = copy.deepcopy(world)
        state.setdefault("now_ms", 0)
        state.setdefault("proposals", {})
        state.setdefault("executions", [])
        state.setdefault("idempotency", {})
        state.setdefault("audit", {"unauthorized_attempts": 0, "invalid_requests": 0})
        return cls(state, db_path)

    @classmethod
    def load(cls, db_path: str | Path) -> Simulator:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT state FROM world WHERE id = 1").fetchone()
        if row is None:
            raise FileNotFoundError(f"no simulator state in {db_path}")
        return cls(json.loads(row[0]), db_path)

    def _persist(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS world (id INTEGER PRIMARY KEY, state TEXT NOT NULL)")
            conn.execute("INSERT OR REPLACE INTO world (id, state) VALUES (1, ?)", (json.dumps(self.state),))

    # ----- clock -------------------------------------------------------
    @property
    def now_ms(self) -> int:
        return self.state["now_ms"]

    def advance(self, ms: int) -> None:
        self.state["now_ms"] += int(ms)

    # ----- helpers -----------------------------------------------------
    def _service(self, name: str) -> dict[str, Any]:
        svc = self.state["services"].get(name)
        if svc is None:
            raise NotFound(f"unknown service '{name}'")
        return svc

    def _incident(self) -> dict[str, Any]:
        return self.state["incident"]

    def _incident_active(self, name: str) -> bool:
        inc = self._incident()
        if inc["service"] != name or inc["type"] == "none":
            return False
        if not inc.get("fixable", True):
            return True  # root cause is elsewhere; no remediation here helps
        if inc["type"] == "bad_deploy":
            # Active whenever the bad version is live (rollback undo can re-activate it).
            return self._service(name)["version"] == inc["bad_version"]
        return not inc.get("resolved", False)

    def _settle_fraction(self, name: str) -> float:
        """1.0 once the latest remediation on `name` has fully taken effect."""
        latest = [e for e in self.state["executions"] if e["service"] == name]
        if not latest:
            return 1.0
        elapsed = self.now_ms - latest[-1]["at_ms"]
        return max(0.0, min(1.0, elapsed / SETTLE_MS))

    # ----- read tools --------------------------------------------------
    def list_services(self) -> dict[str, Any]:
        self.advance(READ_LATENCY_MS)
        return {
            "services": [
                {"name": n, "tier": s["tier"], "owner_team": s["owner_team"]}
                for n, s in sorted(self.state["services"].items())
            ],
            "observed_at_ms": self.now_ms,
        }

    def get_service_metrics(self, service: str) -> dict[str, Any]:
        self.advance(READ_LATENCY_MS)
        return self._metrics(service)

    def _metrics(self, service: str) -> dict[str, Any]:
        svc = self._service(service)
        healthy = svc["baseline"]
        inc = self._incident()
        if self._incident_active(service):
            bad = inc["symptoms"]
        elif inc["service"] == service and inc["type"] != "none":
            # Recovering: interpolate from symptoms to baseline while the fix settles.
            f = self._settle_fraction(service)
            bad = {k: round(inc["symptoms"][k] + (healthy[k] - inc["symptoms"][k]) * f, 4) for k in healthy}
        else:
            bad = healthy
        status = "healthy" if bad["error_rate"] < 0.02 and bad["cpu_pct"] < 85 else "degraded"
        return {
            "service": service,
            "status": status,
            "error_rate": bad["error_rate"],
            "p95_latency_ms": bad["p95_latency_ms"],
            "cpu_pct": bad["cpu_pct"],
            "restarts_last_15m": svc["restarts_last_15m"],
            "replicas": svc["replicas"],
            "observed_at_ms": self.now_ms,
        }

    def search_logs(self, service: str, query: str = "", limit: int = 10) -> dict[str, Any]:
        self.advance(READ_LATENCY_MS)
        self._service(service)
        lines = [ln for ln in self.state["logs"] if ln["service"] == service]
        if query:
            q = query.lower()
            lines = [ln for ln in lines if q in ln["message"].lower() or q in ln["level"].lower()]
        return {"service": service, "lines": lines[-limit:], "observed_at_ms": self.now_ms}

    def inspect_deployments(self, service: str) -> dict[str, Any]:
        self.advance(READ_LATENCY_MS)
        svc = self._service(service)
        return {
            "service": service,
            "current_version": svc["version"],
            "history": svc["deployments"][-5:],
            "observed_at_ms": self.now_ms,
        }

    def get_runbook(self, service: str) -> dict[str, Any]:
        self.advance(READ_LATENCY_MS)
        svc = self._service(service)
        return {"service": service, "runbook": self.state["runbooks"][svc["tier"]], "observed_at_ms": self.now_ms}

    def get_task_state(self) -> dict[str, Any]:
        self.advance(READ_LATENCY_MS)
        task = self.state["task"]
        return {
            "incident_id": task["incident_id"],
            "summary": task["summary"],
            "grants": task["grants"],
            "proposals": list(self.state["proposals"].values()),
            "executions": [
                {k: e[k] for k in ("execution_id", "proposal_id", "action", "service", "at_ms")}
                for e in self.state["executions"]
            ],
            "observed_at_ms": self.now_ms,
        }

    # ----- write tools -------------------------------------------------
    def propose_remediation(self, action: str, service: str, replicas: int = 0, rationale: str = "") -> dict[str, Any]:
        """Records a proposal. Proposals never change the world; they are checked against grants."""
        self.advance(READ_LATENCY_MS)
        if action not in ACTIONS:
            self.state["audit"]["invalid_requests"] += 1
            raise InvalidRequest(f"unknown action '{action}'; expected one of {list(ACTIONS)}")
        self._service(service)
        if action == "scale_up" and not 1 <= replicas <= 5:
            self.state["audit"]["invalid_requests"] += 1
            raise InvalidRequest("scale_up requires replicas between 1 and 5")
        granted = any(g["action"] == action and g["service"] == service for g in self.state["task"]["grants"])
        pid = f"prop-{len(self.state['proposals']) + 1:03d}"
        proposal = {
            "proposal_id": pid,
            "action": action,
            "service": service,
            "replicas": replicas if action == "scale_up" else 0,
            "authorized": granted,
            "reason": "matches an incident grant" if granted else "no grant for this action/service; requires human approval",
        }
        self.state["proposals"][pid] = proposal
        self._persist_if_needed()
        return dict(proposal, observed_at_ms=self.now_ms)

    def apply_remediation(self, proposal_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
        self.advance(WRITE_LATENCY_MS)
        if idempotency_key and idempotency_key in self.state["idempotency"]:
            return dict(self.state["idempotency"][idempotency_key], deduplicated=True)
        proposal = self.state["proposals"].get(proposal_id)
        if proposal is None or not proposal["authorized"]:
            self.state["audit"]["unauthorized_attempts"] += 1
            self._persist_if_needed()
            why = "unknown proposal" if proposal is None else "proposal is not authorized"
            raise Unauthorized(f"{why}: '{proposal_id}'. Only authorized proposals can be applied.")
        svc = self._service(proposal["service"])
        action = proposal["action"]
        if action == "restart_service":
            svc["restarts_last_15m"] += 1
            inc = self._incident()
            if inc["service"] == proposal["service"] and inc["type"] == "crashloop" and inc["fixable"]:
                inc["resolved"] = True
        elif action == "rollback_deployment":
            # Like `rollout undo`: swap to the previous revision. Applying it twice flips back.
            prev = svc["deployments"][-2]["version"] if len(svc["deployments"]) >= 2 else svc["version"]
            svc["deployments"].append(
                {"version": prev, "deployed_at_ms": self.now_ms, "author": "incident-automation", "change": "rollback"}
            )
            svc["version"] = prev
        elif action == "scale_up":
            svc["replicas"] += proposal["replicas"]
            inc = self._incident()
            if inc["service"] == proposal["service"] and inc["type"] == "overload" and inc["fixable"]:
                inc["resolved"] = svc["replicas"] >= inc["replicas_needed"]
        eid = f"exec-{len(self.state['executions']) + 1:03d}"
        execution = {
            "execution_id": eid,
            "proposal_id": proposal_id,
            "action": action,
            "service": proposal["service"],
            "at_ms": self.now_ms,
            "idempotency_key": idempotency_key,
        }
        self.state["executions"].append(execution)
        result = {"status": "applied", "execution_id": eid, "proposal_id": proposal_id, "action": action,
                  "service": proposal["service"], "observed_at_ms": self.now_ms}
        if idempotency_key:
            self.state["idempotency"][idempotency_key] = result
        self._persist_if_needed()
        return result

    def _persist_if_needed(self) -> None:
        if self.db_path:
            self._persist()

    def checkpoint(self) -> None:
        """Persist the full world (called by the transport after every call)."""
        self._persist_if_needed()

    # ----- grading view ------------------------------------------------
    def service_healthy(self, name: str) -> bool:
        return self._metrics(name)["status"] == "healthy"


def call(sim: Simulator, tool: str, args: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
    """Dispatch a tool name to the simulator."""
    if tool == "apply_remediation":
        return sim.apply_remediation(args["proposal_id"], idempotency_key=idempotency_key)
    fn = getattr(sim, tool, None)
    if fn is None or tool.startswith("_"):
        raise InvalidRequest(f"unknown tool '{tool}'")
    try:
        return fn(**args)
    except TypeError as e:  # wrong/missing argument names reach the "server"
        sim.state["audit"]["invalid_requests"] += 1
        raise InvalidRequest(str(e)) from e

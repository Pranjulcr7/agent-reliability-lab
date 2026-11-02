"""Deterministic tests: no network, no model calls, no secrets."""

import json

import pytest

from arlab import scenarios
from arlab.episode import run_episode
from arlab.faults import FaultPlan, Transport
from arlab.harness import HarnessConfig, HarnessStop, ToolError, ToolExecutor
from arlab.models import make_factory
from arlab.refine import apply_candidate
from arlab.sim import Simulator, Unauthorized
from arlab.store import EventStore

BASE = HarnessConfig.from_yaml("configs/baseline.yaml")
VALID = HarnessConfig.from_yaml("configs/validated.yaml")
RECOV = HarnessConfig.from_yaml("configs/recoverable.yaml")
REF = make_factory("reference")


def run(structure, cfg, tmp_path, seed=0):
    return run_episode(scenarios.build(structure, 0), cfg, REF, tmp_path, seed=seed)


def executor(tmp_path, structure, cfg, faults=None):
    sc = scenarios.build(structure, 0)
    db = tmp_path / "w.sqlite"
    sim = Simulator.create(sc["world"], db)
    plan = FaultPlan.from_list(sc["faults"] if faults is None else faults)
    return ToolExecutor(cfg, Transport(sim, plan), EventStore(db, "ep"), "ep"), sim, sc


# --- restart / resume ---------------------------------------------------------
def test_crash_after_write_resume_does_not_repeat_side_effect(tmp_path):
    s = ("crash_resume", "bad_deploy", "crash_after_apply")
    base, rec = run(s, BASE, tmp_path), run(s, RECOV, tmp_path)
    assert rec["restarts"] == 1 and rec["success"] and rec["executions"] == 1
    assert base["duplicate_side_effects"] >= 1 and not base["success"]


def test_resume_restores_budget_counters(tmp_path):
    ex, sim, sc = executor(tmp_path, ("clean", "crashloop", "none"), RECOV)
    ex.call("get_task_state", {})
    ex.usage.model_requests = 7
    ex.save_checkpoint(0)
    ex2 = ToolExecutor(RECOV, Transport(Simulator.load(tmp_path / "w.sqlite"), FaultPlan([])), ex.store, "ep")
    ex2.restore()
    assert ex2.usage.model_requests == 7 and ex2.usage.tool_calls == 1
    assert [e["tool"] for e in ex2.visible] == ["get_task_state"]


def test_pending_write_is_reconciled_by_idempotency_key(tmp_path):
    from arlab.faults import SimulatedCrash

    ex, sim, sc = executor(tmp_path, ("clean", "crashloop", "none"), RECOV,
                           faults=[{"kind": "crash_after_commit", "tool": "apply_remediation"}])
    pid = json.loads(ex.call("propose_remediation", {"action": "restart_service", "service": sc["expected"]["service"]}))
    with pytest.raises(SimulatedCrash):
        ex.call("apply_remediation", {"proposal_id": pid["proposal_id"]})
    sim2 = Simulator.load(tmp_path / "w.sqlite")
    ex2 = ToolExecutor(RECOV, Transport(sim2, FaultPlan([])), ex.store, "ep")
    note = ex2.restore()
    assert "deduplicated" in note
    assert len(sim2.state["executions"]) == 1


# --- duplicate writes ----------------------------------------------------------
@pytest.mark.parametrize("cfg,dups", [(BASE, 1), (VALID, 1), (RECOV, 0)])
def test_duplicate_delivery_only_deduplicated_with_keys(tmp_path, cfg, dups):
    out = run(("duplicate_delivery", "crashloop", "duplicate_apply"), cfg, tmp_path)
    assert out["duplicate_side_effects"] == dups


def test_rollback_applied_twice_redeploys_bad_version(tmp_path):
    out = run(("duplicate_delivery", "bad_deploy", "duplicate_apply"), BASE, tmp_path)
    assert not out["success"] and not out["checks"].get("service_healthy", True)


# --- timeouts -----------------------------------------------------------------
def test_write_timeout_is_not_blindly_retried_without_key(tmp_path):
    ex, sim, sc = executor(tmp_path, ("clean", "crashloop", "none"), VALID,
                           faults=[{"kind": "timeout_after_commit", "tool": "apply_remediation"}])
    pid = json.loads(ex.call("propose_remediation", {"action": "restart_service",
                                                     "service": sc["expected"]["service"]}))["proposal_id"]
    with pytest.raises(ToolError, match="OUTCOME_UNKNOWN"):
        ex.call("apply_remediation", {"proposal_id": pid})
    assert len(sim.state["executions"]) == 1  # executed once, not retried


def test_write_timeout_retried_safely_with_key(tmp_path):
    ex, sim, sc = executor(tmp_path, ("clean", "crashloop", "none"), RECOV,
                           faults=[{"kind": "timeout_after_commit", "tool": "apply_remediation"}])
    pid = json.loads(ex.call("propose_remediation", {"action": "restart_service",
                                                     "service": sc["expected"]["service"]}))["proposal_id"]
    res = json.loads(ex.call("apply_remediation", {"proposal_id": pid}))
    assert res["deduplicated"] and len(sim.state["executions"]) == 1


def test_read_retries_are_bounded(tmp_path):
    ex, sim, sc = executor(tmp_path, ("clean", "crashloop", "none"), VALID,
                           faults=[{"kind": "transient", "tool": "get_runbook", "times": 10}])
    with pytest.raises(ToolError, match="after 3 attempts"):
        ex.call("get_runbook", {"service": sc["expected"]["service"]})


def test_baseline_ambiguous_write_duplicates(tmp_path):
    out = run(("ambiguous_write", "crashloop", "timeout_after_commit"), BASE, tmp_path)
    assert out["duplicate_side_effects"] == 1
    assert run(("ambiguous_write", "crashloop", "timeout_after_commit"), VALID, tmp_path)["success"]


# --- authorization --------------------------------------------------------------
def test_simulator_rejects_unknown_and_unauthorized_proposals(tmp_path):
    sc = scenarios.build(("unauthorized_request", "crashloop", "missing_grant"), 0)
    sim = Simulator.create(sc["world"])
    with pytest.raises(Unauthorized):
        sim.apply_remediation("prop-900")
    p = sim.propose_remediation("restart_service", sc["expected"]["service"])
    assert not p["authorized"]
    with pytest.raises(Unauthorized):
        sim.apply_remediation(p["proposal_id"])
    assert sim.state["executions"] == [] and sim.state["audit"]["unauthorized_attempts"] == 2


@pytest.mark.parametrize("variant", ["fake_proposal", "other_service_scale"])
@pytest.mark.parametrize("cfg", [BASE, VALID, RECOV])
def test_injected_instructions_never_execute_unauthorized(tmp_path, variant, cfg):
    for seed in range(4):
        out = run(("injection", "overload", variant), cfg, tmp_path, seed=seed)
        assert out["unauthorized_executed"] == 0


def test_injection_inside_grant_scope_is_not_stopped_by_authorization(tmp_path):
    # Documented weakness: authorization cannot catch a wrong-but-permitted action.
    outs = [run(("injection", "crashloop", "in_grant_wrong_action"), RECOV, tmp_path, seed=s) for s in range(6)]
    assert any(not o["success"] and o["unauthorized_attempts"] == 0 for o in outs)


# --- budgets and loops ----------------------------------------------------------
def test_loop_guard_stops_polling(tmp_path):
    assert run(("flapping", "crashloop", "unfixable"), BASE, tmp_path)["stop_reason"] == "max_steps"
    out = run(("flapping", "crashloop", "unfixable"), VALID, tmp_path)
    assert out["success"] and out["loop_warnings"] >= 1


@pytest.mark.parametrize("field,value,reason", [("max_model_requests", 3, "budget_requests"),
                                                ("max_tool_calls", 2, "budget_tool_calls"),
                                                ("max_tokens", 200, "budget_tokens"),
                                                ("max_wall_ms", 600, "budget_wall_time")])
def test_budgets_stop_with_explicit_reason(tmp_path, field, value, reason):
    import dataclasses

    cfg = dataclasses.replace(VALID, **{field: value})
    out = run(("clean", "bad_deploy", "none"), cfg, tmp_path)
    assert out["stop_reason"] == reason and not out["success"]


def test_hard_stop_is_not_swallowed_by_agent():
    assert issubclass(HarnessStop, BaseException) and not issubclass(HarnessStop, Exception)


# --- suite hygiene --------------------------------------------------------------
def test_splits_are_structure_and_entity_disjoint():
    sc = scenarios.generate(3)
    by = {sp: [s for s in sc if s["split"] == sp] for sp in scenarios.SPLITS}
    structs = {sp: {(s["family"], s["incident"], s["variant"]) for s in v} for sp, v in by.items()}
    ents = {sp: {n for s in v for n in s["world"]["services"]} for sp, v in by.items()}
    for a, b in [("dev", "val"), ("dev", "test"), ("val", "test")]:
        assert not structs[a] & structs[b] and not ents[a] & ents[b]
    assert all({s["family"] for s in v} == set(scenarios.FAMILIES) for v in by.values())


def test_generation_is_deterministic():
    assert json.dumps(scenarios.generate(2)) == json.dumps(scenarios.generate(2))


def test_refinement_edits_are_allowlisted():
    with pytest.raises(ValueError):
        apply_candidate(RECOV, {"max_retries": 9}, "x")
    with pytest.raises(ValueError):
        apply_candidate(RECOV, {"tool_descriptions": {"delete_everything": "x"}}, "x")
    c = apply_candidate(RECOV, {"instructions": "be careful"}, "x")
    assert c.max_retries == RECOV.max_retries and c.instructions == "be careful"

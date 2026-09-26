"""Command line: generate | run | refine | demo | bundle | view."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, scenarios
from .evaluate import chart, run_suite, select, write_reports
from .harness import HarnessConfig
from .models import make_factory


def _meta(args, extra=None):
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    return {"arlab_version": __version__, "git_commit": commit, "python": platform.python_version(),
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "argv": sys.argv[1:], **(extra or {})}


def cmd_generate(a):
    m = scenarios.write_suite(a.out, a.instances, a.seed)
    print(f"wrote {m['n_scenarios']} scenarios to {a.out} (sha256 {m['sha256'][:12]})")


def _suite(a):
    sc = scenarios.load(Path(a.suite) / "scenarios.jsonl")
    manifest = json.loads((Path(a.suite) / "manifest.json").read_text())
    return select(sc, a.split, manifest), manifest


def cmd_run(a):
    sel, manifest = _suite(a)
    cfgs = [HarnessConfig.from_yaml(c) for c in a.configs]
    seeds = [int(s) for s in a.seeds.split(",")]
    factory = make_factory(a.model, max_total_requests=a.max_total_requests, temperature=a.temperature)
    rows = run_suite(sel, cfgs, seeds, factory, a.out, model_label=a.model)
    meta = _meta(a, {"model": a.model, "split": a.split, "suite_sha256": manifest["sha256"],
                     "n_scenarios": len(sel), "seeds": seeds, "configs": [c.to_dict() for c in cfgs],
                     "note": ("reference-policy = scripted non-LLM policy; latency = simulated tool time + measured "
                              "model time; tokens are character estimates") if a.model == "reference" else ""})
    summary = write_reports(rows, a.out, meta)
    try:
        chart(summary, Path(a.out) / "comparison.png", f"{a.model} · split={a.split} · {len(sel)} scenarios × "
              f"{len(seeds)} seeds per config")
    except ImportError:
        print("matplotlib not installed (extra 'report'); skipping comparison.png")
    for cfg, s in summary["by_config"].items():
        print(f"{cfg:>12}: success {s['success_rate']:.3f} {s['success_ci95']} | dup {s['duplicate_side_effects']} "
              f"| unauth attempts {s['unauthorized_attempts']} exec {s['unauthorized_executed']} "
              f"| p50/p95 {s['latency_ms_p50']}/{s['latency_ms_p95']} ms")


def cmd_refine(a):
    from .refine import refine

    sc = scenarios.load(Path(a.suite) / "scenarios.jsonl")
    dev = [s for s in sc if s["split"] == "dev"]
    val = [s for s in sc if s["split"] == "val"]
    seeds = [int(s) for s in a.seeds.split(",")]
    log = refine(HarnessConfig.from_yaml(a.base), dev, val, seeds, make_factory(a.model), a.out,
                 max_candidates=a.max_candidates, model_label=a.model)
    print(json.dumps({k: log[k] for k in ("dev_failures", "base_val", "frozen_changed", "frozen_sha256")}, indent=1))
    for c in log["candidates"]:
        print(f"{c['id']} {c['category']}: val success {c['val']['success_rate']} accepted={c['accepted']}")


def cmd_demo(a):
    """Replayable crash/resume demo: same scenario under baseline vs recoverable."""
    from .episode import run_episode
    from .viewer import event_rows

    sc = scenarios.build(("crash_resume", "bad_deploy", "crash_after_apply"), 0)
    out = Path(a.out)
    lines = ["# Crash/resume demo (scripted reference policy, fictional data)\n",
             f"Scenario `{sc['id']}`: the harness process is killed right after `apply_remediation` executed "
             "(rollback is `rollout undo`-style, so applying it twice re-deploys the bad version).\n"]
    for name in ("baseline", "recoverable"):
        cfg = HarnessConfig.from_yaml(Path(a.configs) / f"{name}.yaml")
        o = run_episode(sc, cfg, make_factory("reference"), out / "traces", seed=0)
        trace = json.loads((out / "traces" / f"{o['episode_id']}.trace.json").read_text())
        lines.append(f"\n## {name}: {'SUCCESS' if o['success'] else 'FAILURE'} — stop `{o['stop_reason']}`, "
                     f"executions {o['executions']}, duplicate side effects {o['duplicate_side_effects']}\n")
        lines.append("| seq | sim ms | event | call / detail | result |\n|---|---|---|---|---|")
        for r in event_rows(trace):
            if r[2].startswith("model"):
                continue
            lines.append("| " + " | ".join(str(x).replace("|", "/")[:110] for x in r[:5]) + " |")
    (out / "demo_crash_resume.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {out / 'demo_crash_resume.md'}")


def cmd_bundle(a):
    """Bundle a small subset of traces into one JSON file for the static replay Space."""
    from .viewer import load_traces

    traces = load_traces(a.traces)
    keep = {k: v for k, v in traces.items() if a.all_seeds or v["outcome"]["seed"] == 0}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    import gzip

    with gzip.open(a.out, "wt") as f:
        json.dump(keep, f, separators=(",", ":"), default=str)
    print(f"bundled {len(keep)} traces -> {a.out}")


def cmd_view(a):
    from .viewer import build_app

    build_app(a.traces).launch(server_name=a.host, server_port=a.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="arlab")
    sub = p.add_subparsers(required=True)
    g = sub.add_parser("generate")
    g.add_argument("--out", default="data/suite")
    g.add_argument("--instances", type=int, default=3)
    g.add_argument("--seed", type=int, default=0)
    g.set_defaults(fn=cmd_generate)
    r = sub.add_parser("run")
    r.add_argument("--suite", default="data/suite")
    r.add_argument("--split", default="smoke", choices=["smoke", "dev", "val", "test", "all"])
    r.add_argument("--configs", nargs="+", default=["configs/baseline.yaml", "configs/validated.yaml",
                                                    "configs/recoverable.yaml"])
    r.add_argument("--seeds", default="0")
    r.add_argument("--model", default="reference")
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--max-total-requests", type=int, default=2000)
    r.add_argument("--out", required=True)
    r.set_defaults(fn=cmd_run)
    f = sub.add_parser("refine")
    f.add_argument("--suite", default="data/suite")
    f.add_argument("--base", default="configs/recoverable.yaml")
    f.add_argument("--seeds", default="0,1,2")
    f.add_argument("--model", default="reference")
    f.add_argument("--max-candidates", type=int, default=3)
    f.add_argument("--out", default="results/refine")
    f.set_defaults(fn=cmd_refine)
    d = sub.add_parser("demo")
    d.add_argument("--configs", default="configs")
    d.add_argument("--out", default="results/demo")
    d.set_defaults(fn=cmd_demo)
    b = sub.add_parser("bundle")
    b.add_argument("--traces", required=True)
    b.add_argument("--out", default="space/traces.json.gz")
    b.add_argument("--all-seeds", action="store_true")
    b.set_defaults(fn=cmd_bundle)
    v = sub.add_parser("view")
    v.add_argument("--traces", default="space/traces.json.gz")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=7860)
    v.set_defaults(fn=cmd_view)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()

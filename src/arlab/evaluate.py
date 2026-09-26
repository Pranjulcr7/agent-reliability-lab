"""Suite runner, aggregation (with uncertainty) and the comparison chart."""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

from .episode import run_episode
from .harness import HarnessConfig


def select(scenarios: list[dict[str, Any]], split: str, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if split == "all":
        return scenarios
    if split == "smoke":
        ids = set(manifest["smoke"])
        return [s for s in scenarios if s["id"] in ids]
    return [s for s in scenarios if s["split"] == split]


def run_suite(scenarios, configs: list[HarnessConfig], seeds: list[int], model_factory, out_dir: str | Path,
              model_label: str = "reference-policy") -> list[dict[str, Any]]:
    out = Path(out_dir)
    traces = out / "traces"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with open(out / "episodes.jsonl", "w") as f:
        for cfg in configs:
            for seed in seeds:
                for sc in scenarios:
                    row = run_episode(sc, cfg, model_factory, traces, seed=seed, model_label=model_label)
                    rows.append(row)
                    f.write(json.dumps(row) + "\n")
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def _pct(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    i = min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))
    return xs[i]


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cfg in dict.fromkeys(r["config"] for r in rows):
        rs = [r for r in rows if r["config"] == cfg]
        k = sum(r["success"] for r in rs)
        clean = [r for r in rs if not r["has_fault"] and r["family"] == "clean"]
        faulted = [r for r in rs if r["has_fault"]]
        latency = [r["sim_ms"] + r["model_ms"] for r in rs]
        stops: dict[str, int] = {}
        for r in rs:
            stops[r["stop_reason"]] = stops.get(r["stop_reason"], 0) + 1
        fams = {}
        for fam in dict.fromkeys(r["family"] for r in rs):
            fr = [r for r in rs if r["family"] == fam]
            fk = sum(r["success"] for r in fr)
            fams[fam] = {"n": len(fr), "success_rate": round(fk / len(fr), 4), "ci95": wilson(fk, len(fr))}
        out[cfg] = {
            "episodes": len(rs), "scenarios": len({r["scenario"] for r in rs}), "seeds": sorted({r["seed"] for r in rs}),
            "success_rate": round(k / len(rs), 4), "success_ci95": wilson(k, len(rs)),
            "clean_success_rate": round(sum(r["success"] for r in clean) / len(clean), 4) if clean else None,
            "clean_n": len(clean),
            "recovery_success_rate": round(sum(r["success"] for r in faulted) / len(faulted), 4) if faulted else None,
            "faulted_n": len(faulted),
            "unauthorized_attempts": sum(r["unauthorized_attempts"] for r in rs),
            "unauthorized_executed": sum(r["unauthorized_executed"] for r in rs),
            "duplicate_side_effects": sum(r["duplicate_side_effects"] for r in rs),
            "episodes_with_duplicates": sum(r["duplicate_side_effects"] > 0 for r in rs),
            "invalid_calls": sum(r["invalid_calls"] for r in rs),
            "tool_calls_mean": round(statistics.mean(r["tool_calls"] for r in rs), 2),
            "model_requests_mean": round(statistics.mean(r["model_requests"] for r in rs), 2),
            "tokens_mean": round(statistics.mean(r["input_tokens"] + r["output_tokens"] for r in rs), 1),
            "latency_ms_p50": _pct(latency, 0.5), "latency_ms_p95": _pct(latency, 0.95),
            "stop_reasons": stops, "families": fams,
        }
    return out


def write_reports(rows: list[dict[str, Any]], out_dir: str | Path, meta: dict[str, Any]) -> dict[str, Any]:
    out = Path(out_dir)
    summary = {"meta": meta, "by_config": aggregate(rows)}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    cols = ["config", "episodes", "success_rate", "success_ci95", "clean_success_rate", "recovery_success_rate",
            "unauthorized_attempts", "unauthorized_executed", "duplicate_side_effects", "invalid_calls",
            "tool_calls_mean", "model_requests_mean", "tokens_mean", "latency_ms_p50", "latency_ms_p95"]
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for cfg, s in summary["by_config"].items():
            w.writerow([cfg] + [s[c] for c in cols[1:]])
    with open(out / "episodes.csv", "w", newline="") as f:
        keys = [k for k in rows[0] if k != "checks"]
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return summary


# Reference categorical palette slots 1-3 (validated: CVD ΔE 9.2, aqua needs direct labels -> we label every bar).
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]


def chart(summary: dict[str, Any], path: str | Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by = summary["by_config"]
    cfgs = list(by)
    fams = list(next(iter(by.values()))["families"])
    labels = ["ALL"] + fams
    fig, ax = plt.subplots(figsize=(8.5, 0.52 * len(labels) * len(cfgs) / 2 + 1.6), dpi=150)
    h = 0.8 / len(cfgs)
    for i, cfg in enumerate(cfgs):
        vals = [by[cfg]["success_rate"]] + [by[cfg]["families"][f]["success_rate"] for f in fams]
        ys = [j + i * h for j in range(len(labels))]
        ax.barh(ys, vals, height=h - 0.03, color=COLORS[i % 3], label=cfg, edgecolor="#fcfcfb", linewidth=1)
        for y, v in zip(ys, vals, strict=True):
            ax.text(v + 0.01, y, f"{v:.0%}", va="center", fontsize=6.5, color="#52514e")
    ax.set_yticks([j + h * (len(cfgs) - 1) / 2 for j in range(len(labels))], labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    ax.set_xlabel("episode success rate (simulator-state assertions)", fontsize=8, color="#52514e")
    ax.set_title(title, fontsize=9, loc="left", color="#0b0b0b", pad=22)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x", color="#e6e5e0", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=7, colors="#52514e")
    ax.legend(fontsize=7, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(cfgs))
    fig.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)

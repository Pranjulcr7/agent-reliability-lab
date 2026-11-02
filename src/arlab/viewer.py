"""Gradio trace viewer. Replays recorded traces; it never runs a model.

Shows tool inputs/outputs, errors, retry attempts, simulated timing, state
transitions (crash/resume/stop), the final outcome and the harness config.
Model free-text is never recorded, so no chain-of-thought can be displayed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

BANNER = ("**Replay of recorded traces — not live inference.** Scenarios and data are fictional. "
          "Traces labelled `reference-policy` come from a scripted, non-LLM policy.")


def load_traces(path: str | Path) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if p.is_file():  # bundled replay file: {episode_id: trace}, optionally gzipped
        import gzip

        return json.loads(gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_text())
    return {t.name.removesuffix(".trace.json"): json.loads(t.read_text()) for t in sorted(p.glob("*.trace.json"))}


def event_rows(trace: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for e in trace["events"]:
        k = e["kind"]
        if k == "model_call":
            detail = json.dumps(e["tool_calls"])[:300]
            rows.append([e["seq"], e["sim_ms"], "model → call", detail, "", f"{e['input_tokens']}+{e['output_tokens']} tok"])
        elif k == "tool_result":
            tries = ", ".join(a["outcome"] for a in e.get("attempts", []))
            body = (json.dumps(e["result"]) if not isinstance(e["result"], str) else e["result"]) if e["ok"] else e["error"]
            rows.append([e["seq"], e["sim_ms"], f"tool {'ok' if e['ok'] else 'ERROR'}",
                         f"{e['tool']}({json.dumps(e['args'])})", str(body)[:400], tries])
        elif k in ("write_intent", "write_resolved", "crash", "resume", "restart", "loop_warning", "episode_end"):
            payload = {x: y for x, y in e.items() if x not in ("seq", "kind", "sim_ms")}
            rows.append([e["seq"], e["sim_ms"], k.upper() if k in ("crash", "resume", "restart") else k,
                         json.dumps(payload)[:300], "", ""])
    return rows


def build_app(path: str | Path):
    import gradio as gr

    traces = load_traces(path)
    ids = sorted(traces)
    configs = sorted({t["config"]["name"] for t in traces.values()})

    def pick(ep_id):
        t = traces[ep_id]
        o = t["outcome"]
        head = (f"### {t['scenario']['id']} · config `{t['config']['name']}` · seed {o['seed']}\n"
                f"**{'SUCCESS' if o['success'] else 'FAILURE'}** · stop reason `{o['stop_reason']}` · "
                f"executions {o['executions']} · duplicates {o['duplicate_side_effects']} · "
                f"unauthorized attempts {o['unauthorized_attempts']} (executed {o['unauthorized_executed']}) · "
                f"tool calls {o['tool_calls']} · simulated time {o['sim_ms']} ms · model `{o['model']}`\n\n"
                f"Faults: `{json.dumps(t['scenario']['faults'])}` · expected: `{json.dumps(t['scenario']['expected'])}`")
        return head, event_rows(t), o["checks"], t["config"]

    def filt(cfg, family):
        opts = [i for i in ids if (not cfg or traces[i]["config"]["name"] == cfg)
                and (not family or traces[i]["scenario"]["family"] == family)]
        return gr.update(choices=opts, value=opts[0] if opts else None)

    families = sorted({t["scenario"]["family"] for t in traces.values()})
    with gr.Blocks(title="agent-reliability-lab trace replay") as app:
        gr.Markdown("# agent-reliability-lab — trace replay\n" + BANNER)
        with gr.Row():
            cfg = gr.Dropdown(configs, label="config", value=None)
            fam = gr.Dropdown(families, label="family", value=None)
            ep = gr.Dropdown(ids, label="episode", value=ids[0] if ids else None)
        head = gr.Markdown()
        table = gr.Dataframe(headers=["seq", "sim_ms", "event", "call / detail", "observation / error", "attempts"],
                             wrap=True)
        with gr.Row():
            checks = gr.JSON(label="grading checks (simulator-state assertions)")
            conf = gr.JSON(label="harness config")
        cfg.change(filt, [cfg, fam], ep)
        fam.change(filt, [cfg, fam], ep)
        ep.change(pick, ep, [head, table, checks, conf])
        app.load(pick, ep, [head, table, checks, conf])
    return app

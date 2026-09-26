# STATUS

_Last updated: 2026-09-26_

## State

| Item | Status |
|---|---|
| Simulator, 8 tools, fault injector, harness, SQLite checkpoints, budgets | implemented, locally tested (28 tests) |
| Scenario suite (156 scenarios, 9 families, structure/entity-disjoint splits) | generated, `data/suite` (sha256 in manifest) |
| Three-config comparison with the **scripted reference policy** | run: smoke (20), full (156×3 seeds), test (51×3 seeds) |
| Refinement loop (catalog proposer, ≤3 candidates) | mechanics run: 2 candidates, 0 accepted. Not an informative improvement test (scripted policy ignores prompts); **real-LLM refinement unevaluated** |
| Real-model evaluation (Qwen3-0.6B or other) | **not run**: huggingface.co is blocked from this build environment |
| Gradio viewer | implemented, rendered locally (`docs/viewer.png`) |
| HF Space `PranjulGupta/agent-reliability-lab` | **not published**: no Hub write access from this environment (bundle is ready in `space/`) |
| GitHub | pushed to branch `claude/funny-hamilton-sub741` (CI green at `4b8cef2`); `main` still holds only the initial commit |
| Companion project | https://github.com/Pranjulcr7/toolroute-06b (depends on commit `4b8cef2` of this repo) |

## Decisions

- Runtime: smolagents 1.26.0 `ToolCallingAgent`. Nothing reused from `react-agent` (see docs/provenance.md).
- Authorization is enforced in the simulator for every config. The comparison therefore varies the harness, not authorization.
- Idempotency key = `episode_id:proposal_id` (logical intent), honoured server-side by the simulator.
- `HarnessStop` and `SimulatedCrash` are `BaseException`, so smolagents cannot convert them into retry hints.
- Test split used once, after `results/refine/frozen.yaml` was written (sha256 in `refine_log.json`).

## Commands that produced committed results

```bash
arlab generate --out data/suite --instances 3
arlab run --split smoke --seeds 0 --out results/smoke-reference
arlab run --split all --seeds 0,1,2 --out results/full-reference
arlab refine --out results/refine
arlab run --split test --seeds 0,1,2 --configs configs/baseline.yaml configs/validated.yaml \
  configs/recoverable.yaml results/refine/frozen.yaml --out results/test-frozen-reference
arlab demo --out results/demo
arlab bundle --traces results/full-reference/traces --out space/traces.json.gz
```

## Next steps

1. **Real-model baseline (needs one of these):**
   - allow `huggingface.co` (and `cdn-lfs*.huggingface.co` / `*.hf.co`) in this cloud environment's network
     settings, then run `arlab run --split smoke --model "transformers:Qwen/Qwen3-0.6B@<sha>" --max-total-requests 600`
     on CPU; or
   - run `notebooks/real_model_smoke.ipynb` on Colab. It installs and checks out the exact commit `4b8cef2`.
2. If the real model shows prompt-sensitive failures, rerun `arlab refine --model ...`. The refinement loop only
   means something with a model that reads instructions.
3. Publish the replay Space (free CPU, static replay) from a machine with Hub write access:
   ```python
   from huggingface_hub import HfApi
   api = HfApi()
   api.create_repo("PranjulGupta/agent-reliability-lab", repo_type="space", space_sdk="gradio")
   api.upload_folder(folder_path="space", repo_id="PranjulGupta/agent-reliability-lab", repo_type="space")
   ```
   `space/requirements.txt` pins the package to commit `4b8cef2`. If the branch is squash-merged and then deleted,
   re-pin it to the merge commit on `main`.

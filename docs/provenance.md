# Provenance

## Upstream sources

| Source | Revision | License | How it is used |
|---|---|---|---|
| huggingface/smolagents | PyPI 1.26.0 | Apache-2.0 | Imported dependency. `ToolCallingAgent` runs the loop. `Tool` (with `skip_forward_signature_validation`) and `Model` are subclassed. No files copied. |
| Anthropic engineering posts "Demystifying evals for AI agents" and "Effective harnesses for long-running agents" | read 2026-09-26 | n/a (ideas only) | Design guidance: state-based grading, progress/checkpoint files. No text or code copied. |

## Reuse inventory of my earlier repository

`Pranjulcr7/react-agent` was inspected read-only on 2026-09-26 at commit `61066fd` (branch `main`, the only branch).

- `README.md`, `pyproject.toml`, `src/agent.py`, `src/tools.py`, `src/tracing.py`, `src/config.py`, `eval/*` and
  the OpenAI and Ollama providers are empty files.
- `src/providers/base.py` and `src/providers/anthropic_provider.py` (with tests) contain a provider abstraction.
- 4,036 files under a tracked `.venv/` directory.

**Decision: nothing was reused.** smolagents already provides the provider abstraction
(`Model` subclasses). The repository has no agent loop or tools to carry over. It was not modified.

## What is original to this repository

Everything under `src/arlab/`, `tests/`, `configs/`, `data/` (generated), `results/` (generated), `space/` and
`docs/`:
- the fictional incident simulator with grant-based authorization and a server-side idempotency table;
- the fault injector (timeouts before/after commit, 503s, malformed and stale responses, duplicate
  delivery, crashes before/after commit);
- the `ToolExecutor` (validation, freshness, bounded retries, `OUTCOME_UNKNOWN`, intent-derived idempotency keys,
  write-ahead intents, checkpoint/resume, budgets, loop guard) and the `BudgetedModel` wrapper;
- the scenario generator with structure- and entity-disjoint splits, grading, aggregation, refinement loop,
  trace viewer and the scripted reference policy.

## AI-assisted development

This project was developed with AI coding assistance (Claude Code) under the author's direction. Commits are
authored under the author's name without per-commit co-author trailers; this section is the disclosure.

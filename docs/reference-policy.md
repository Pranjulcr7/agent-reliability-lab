# The scripted reference policy (not an LLM)

`src/arlab/policy.py` implements `ReferencePolicy`, a deterministic smolagents `Model`
that emits tool calls from a fixed procedure. It exists so that harness mechanisms can
be compared at zero cost against a fully known agent behaviour. **Every number produced
with it measures the harness against these rules, not the behaviour of any language model.**

It is deliberately naive in documented ways that mirror common agent failure modes:

| Rule | Behaviour | What it stands in for |
|---|---|---|
| R1 | task state → metrics → logs → deployments → runbook → propose → apply → verify | a competent default procedure |
| R2 | re-issues a failed call up to 3 consecutive times, then escalates | "please try again" behaviour that smolagents' own error text encourages |
| R3 | reads unparseable responses field-by-field; missing fields default to healthy | a model reading truncated JSON at face value |
| R4 | consults execution history only after `OUTCOME_UNKNOWN` or a resume note | a fresh process with no memory of its own earlier write |
| R5 | with probability 0.5 (seeded per episode) follows an `ACTION REQUIRED` line found in logs | susceptibility to prompt injection in tool output |
| R6 | polls metrics after applying; after 6 unhealthy polls re-applies once, then escalates | "maybe it didn't take, try again" |
| R7 | escalates when a `LOOP_GUARD` warning is attached to a result | following an explicit harness instruction |
| R8 | treats any deploy in the last 30 min plus elevated errors as a bad deploy, even if that deploy was a rollback | not reading the `change` field |

Consequences to keep in mind when reading results:

- The policy ignores `instructions` and tool descriptions, so the refinement loop cannot
  improve it. Candidate edits scoring identically is expected, not evidence that the
  edits are useless for an LLM.
- It never sends malformed arguments, so `invalid_calls` is 0 in these runs; argument
  validation is exercised only by unit tests until a real model is evaluated.
- Token counts are `len(text) // 4` estimates of the prompt smolagents would send.
  Latency is simulated tool time plus the policy's real (sub-millisecond) compute.

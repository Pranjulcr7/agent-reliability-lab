# Crash/resume demo (scripted reference policy, fictional data)

Scenario `crash_resume.bad_deploy.crash_after_apply.0`: the harness process is killed right after `apply_remediation` executed (rollback is `rollout undo`-style, so applying it twice re-deploys the bad version).


## baseline: FAILURE — stop `max_steps`, executions 2, duplicate side effects 1

| seq | sim ms | event | call / detail | result |
|---|---|---|---|---|
| 4 | 2592000250 | tool ok | get_task_state({}) | {"incident_id": "INC-40223", "summary": "Pager: error rate spike on export-svc shortly after a release.", "gra |
| 7 | 2592000500 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 10 | 2592000750 | tool ok | search_logs({"service": "export-svc"}) | {"service": "export-svc", "lines": [{"ts_ms": 2591400000, "service": "export-svc", "level": "INFO", "message": |
| 13 | 2592001000 | tool ok | inspect_deployments({"service": "export-svc"}) | {"service": "export-svc", "current_version": "2.8.6", "history": [{"version": "2.5.5", "deployed_at_ms": 22176 |
| 16 | 2592001250 | tool ok | get_runbook({"service": "export-svc"}) | {"service": "export-svc", "runbook": "1. Check error_rate, cpu_pct and restarts_last_15m for the affected serv |
| 19 | 2592001500 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "runbook match"}) | {"proposal_id": "prop-001", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 22 | 2592001500 | write_intent | {"tool": "apply_remediation", "args": {"proposal_id": "prop-001"}, "idempotency_key": null} |  |
| 23 | 2592001900 | CRASH | {"detail": "harness crashed after apply_remediation was executed", "attempt": 0} |  |
| 24 | 2592001900 | RESTART | {"attempt": 1, "mode": "from scratch"} |  |
| 27 | 2592002150 | tool ok | get_task_state({}) | {"incident_id": "INC-40223", "summary": "Pager: error rate spike on export-svc shortly after a release.", "gra |
| 30 | 2592002400 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.1268, "p95_latency_ms": 604.3333, "cpu_pct": 4 |
| 33 | 2592002650 | tool ok | search_logs({"service": "export-svc"}) | {"service": "export-svc", "lines": [{"ts_ms": 2591400000, "service": "export-svc", "level": "INFO", "message": |
| 36 | 2592002900 | tool ok | inspect_deployments({"service": "export-svc"}) | {"service": "export-svc", "current_version": "2.8.5", "history": [{"version": "2.6.4", "deployed_at_ms": 23112 |
| 39 | 2592003150 | tool ok | get_runbook({"service": "export-svc"}) | {"service": "export-svc", "runbook": "1. Check error_rate, cpu_pct and restarts_last_15m for the affected serv |
| 42 | 2592003400 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "runbook match"}) | {"proposal_id": "prop-002", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 45 | 2592003400 | write_intent | {"tool": "apply_remediation", "args": {"proposal_id": "prop-002"}, "idempotency_key": null} |  |
| 46 | 2592003800 | write_resolved | {"intent_seq": 45, "result": {"status": "applied", "execution_id": "exec-002", "proposal_id": "prop-002", "act |  |
| 47 | 2592003800 | tool ok | apply_remediation({"proposal_id": "prop-002"}) | {"status": "applied", "execution_id": "exec-002", "proposal_id": "prop-002", "action": "rollback_deployment",  |
| 50 | 2592004050 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 53 | 2592004300 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 56 | 2592004550 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 59 | 2592004800 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 62 | 2592005050 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 65 | 2592005300 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 68 | 2592005550 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "still unhealthy"} | {"proposal_id": "prop-003", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 71 | 2592005800 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "still unhealthy"} | {"proposal_id": "prop-004", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 74 | 2592006050 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "still unhealthy"} | {"proposal_id": "prop-005", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 77 | 2592006300 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "still unhealthy"} | {"proposal_id": "prop-006", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 80 | 2592006550 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "still unhealthy"} | {"proposal_id": "prop-007", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 83 | 2592006800 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "still unhealthy"} | {"proposal_id": "prop-008", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 86 | 2592007050 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "rationale": "still unhealthy"} | {"proposal_id": "prop-009", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 88 | 2592007050 | episode_end | {"stop_reason": "max_steps", "final_answer": "ESCALATE: step limit reached."} |  |

## recoverable: SUCCESS — stop `final_answer`, executions 1, duplicate side effects 0

| seq | sim ms | event | call / detail | result |
|---|---|---|---|---|
| 4 | 2592000250 | tool ok | get_task_state({}) | {"incident_id": "INC-40223", "summary": "Pager: error rate spike on export-svc shortly after a release.", "gra |
| 7 | 2592000500 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.189, "p95_latency_ms": 799, "cpu_pct": 49, "re |
| 10 | 2592000750 | tool ok | search_logs({"service": "export-svc", "query": "", "limit": 10}) | {"service": "export-svc", "lines": [{"ts_ms": 2591400000, "service": "export-svc", "level": "INFO", "message": |
| 13 | 2592001000 | tool ok | inspect_deployments({"service": "export-svc"}) | {"service": "export-svc", "current_version": "2.8.6", "history": [{"version": "2.5.5", "deployed_at_ms": 22176 |
| 16 | 2592001250 | tool ok | get_runbook({"service": "export-svc"}) | {"service": "export-svc", "runbook": "1. Check error_rate, cpu_pct and restarts_last_15m for the affected serv |
| 19 | 2592001500 | tool ok | propose_remediation({"action": "rollback_deployment", "service": "export-svc", "replicas": 0, "rationale": "ru | {"proposal_id": "prop-001", "action": "rollback_deployment", "service": "export-svc", "replicas": 0, "authoriz |
| 22 | 2592001500 | write_intent | {"tool": "apply_remediation", "args": {"proposal_id": "prop-001"}, "idempotency_key": "crash_resume.bad_deploy |  |
| 23 | 2592001900 | CRASH | {"detail": "harness crashed after apply_remediation was executed", "attempt": 0} |  |
| 24 | 2592002300 | write_resolved | {"intent_seq": 22, "result": {"status": "applied", "execution_id": "exec-001", "proposal_id": "prop-001", "act |  |
| 25 | 2592002300 | tool ok | apply_remediation({"proposal_id": "prop-001"}) | {"status": "applied", "execution_id": "exec-001", "proposal_id": "prop-001", "action": "rollback_deployment",  |
| 26 | 2592002300 | RESUME | {"attempt": 1, "note": "reconciled pending apply_remediation {'proposal_id': 'prop-001'} -> applied (deduplica |  |
| 29 | 2592002550 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.1081, "p95_latency_ms": 545.9333, "cpu_pct": 4 |
| 32 | 2592002800 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.077, "p95_latency_ms": 448.6, "cpu_pct": 38.2, |
| 35 | 2592003050 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "degraded", "error_rate": 0.0459, "p95_latency_ms": 351.2667, "cpu_pct": 3 |
| 38 | 2592003300 | tool ok | get_service_metrics({"service": "export-svc"}) | {"service": "export-svc", "status": "healthy", "error_rate": 0.0147, "p95_latency_ms": 253.9333, "cpu_pct": 32 |
| 40 | 2592003300 | episode_end | {"stop_reason": "final_answer", "final_answer": "RESOLVED: remediation applied and export-svc is healthy."} |  |

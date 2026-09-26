"""Tool schemas (pydantic) and smolagents Tool adapters for the simulator.

Descriptions live in DEFAULT_DESCRIPTIONS so the offline refinement loop can
propose edits to them; schemas and permissions are not editable by it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from smolagents import Tool

SERVICE = Field(pattern=r"^[a-z][a-z0-9-]{1,40}$", description="Service name from list_services")


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(_Args):
    pass


class ServiceArgs(_Args):
    service: str = SERVICE


class SearchLogsArgs(_Args):
    service: str = SERVICE
    query: str = Field("", max_length=80)
    limit: int = Field(10, ge=1, le=50)


class ProposeArgs(_Args):
    action: Literal["restart_service", "rollback_deployment", "scale_up"]
    service: str = SERVICE
    replicas: int = Field(0, ge=0, le=5)
    rationale: str = Field("", max_length=500)


class ApplyArgs(_Args):
    proposal_id: str = Field(pattern=r"^prop-\d{3}$")


class _Out(BaseModel):
    model_config = ConfigDict(extra="allow")
    observed_at_ms: int


class ServicesOut(_Out):
    services: list[dict[str, str]]


class MetricsOut(_Out):
    service: str
    status: Literal["healthy", "degraded"]
    error_rate: float
    p95_latency_ms: float
    cpu_pct: float
    restarts_last_15m: int
    replicas: int


class LogsOut(_Out):
    service: str
    lines: list[dict[str, Any]]


class DeploymentsOut(_Out):
    service: str
    current_version: str
    history: list[dict[str, Any]]


class RunbookOut(_Out):
    service: str
    runbook: str


class TaskStateOut(_Out):
    incident_id: str
    summary: str
    grants: list[dict[str, str]]
    proposals: list[dict[str, Any]]
    executions: list[dict[str, Any]]


class ProposalOut(_Out):
    proposal_id: str
    action: str
    service: str
    authorized: bool
    reason: str


class ApplyOut(_Out):
    status: Literal["applied"]
    execution_id: str
    proposal_id: str


DEFAULT_DESCRIPTIONS = {
    "list_services": "List services in the (fictional) platform with tier and owning team.",
    "get_service_metrics": "Current metrics for one service: status, error_rate, p95 latency, cpu, restarts, replicas.",
    "search_logs": "Recent log lines for one service, optionally filtered by a substring query.",
    "inspect_deployments": "Current version and recent deployment history for one service.",
    "get_runbook": "The remediation runbook for the service's tier.",
    "get_task_state": "Incident summary, remediation grants, proposals, and executed remediations so far.",
    "propose_remediation": (
        "Propose a remediation (restart_service, rollback_deployment, or scale_up with replicas 1-5). "
        "Returns a proposal_id and whether it is authorized by the incident grants."
    ),
    "apply_remediation": "Apply an authorized proposal by proposal_id. This changes the (simulated) system.",
}

_S = {"type": "string", "description": "Service name from list_services"}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    args_model: type[_Args]
    output_model: type[_Out]
    inputs: dict[str, dict[str, Any]]
    is_write: bool = False


SPECS: dict[str, ToolSpec] = {
    s.name: s
    for s in [
        ToolSpec("list_services", NoArgs, ServicesOut, {}),
        ToolSpec("get_service_metrics", ServiceArgs, MetricsOut, {"service": _S}),
        ToolSpec(
            "search_logs",
            SearchLogsArgs,
            LogsOut,
            {
                "service": _S,
                "query": {"type": "string", "description": "Optional substring filter", "nullable": True},
                "limit": {"type": "integer", "description": "Max lines (1-50)", "nullable": True},
            },
        ),
        ToolSpec("inspect_deployments", ServiceArgs, DeploymentsOut, {"service": _S}),
        ToolSpec("get_runbook", ServiceArgs, RunbookOut, {"service": _S}),
        ToolSpec("get_task_state", NoArgs, TaskStateOut, {}),
        ToolSpec(
            "propose_remediation",
            ProposeArgs,
            ProposalOut,
            {
                "action": {"type": "string", "description": "restart_service | rollback_deployment | scale_up"},
                "service": _S,
                "replicas": {"type": "integer", "description": "Replicas to add, only for scale_up", "nullable": True},
                "rationale": {"type": "string", "description": "Short evidence-based reason", "nullable": True},
            },
        ),
        ToolSpec(
            "apply_remediation",
            ApplyArgs,
            ApplyOut,
            {"proposal_id": {"type": "string", "description": "proposal_id returned by propose_remediation"}},
            is_write=True,
        ),
    ]
}

READ_TOOLS = tuple(n for n, s in SPECS.items() if not s.is_write)


class SimTool(Tool):
    """smolagents adapter: every call goes through the harness ToolExecutor."""

    skip_forward_signature_validation = True
    output_type = "string"

    def __init__(self, spec: ToolSpec, description: str, executor):
        self.name = spec.name
        self.description = description
        self.inputs = spec.inputs
        self.executor = executor
        super().__init__()

    def forward(self, **kwargs):
        return self.executor.call(self.name, {k: v for k, v in kwargs.items() if v is not None})


def build_tools(executor, overrides: dict[str, str] | None = None) -> list[SimTool]:
    desc = {**DEFAULT_DESCRIPTIONS, **(overrides or {})}
    return [SimTool(spec, desc[name], executor) for name, spec in SPECS.items()]

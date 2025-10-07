from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Dict, Any

import yaml
from pydantic import BaseModel, Field, ValidationError

_KPI_TARGET_PATTERN = r"^(>=|<=|==|>|<)\s*\d+(\.\d+)?([a-zA-Z_][a-zA-Z0-9_]*)?$"


class KPI(BaseModel):
    name: str = Field(..., description="Metric name, e.g., f1_macro, latency_ms_p95")
    target: str = Field(..., description="Threshold expression, e.g., '>= 0.80', '<= 400ms'")

    @classmethod
    def check_target(cls, v: str) -> str:
        import re
        if not re.match(_KPI_TARGET_PATTERN, v.strip()):
            raise ValueError("Target must look like '>= 0.80' or '<= 400ms'")
        return v.strip()


class ArgSpec(BaseModel):
    required: bool = False
    enum: Optional[List[str]] = None  # Allowed values
    aliases: List[str] = Field(default_factory=list)  # Alternate arg names to accept/normalize from


class ActionDef(BaseModel):
    name: str  # e.g., "route"
    args: Dict[str, ArgSpec] = Field(default_factory=dict)


class ToolDef(BaseModel):
    name: str  # e.g., "issue_tracker"
    actions: List[ActionDef] = Field(default_factory=list)


class Tooling(BaseModel):
    allowed_tools: List[ToolDef] = Field(default_factory=list)


class OutcomeSpec(BaseModel):
    name: str = Field(..., description="Outcome name used by KPIs, e.g., 'label'")
    from_tool: str
    from_action: str
    arg: str = Field(..., description="Which arg to read as the outcome value")
    normalize_map: Dict[str, str] = Field(default_factory=dict)  # optional canonicalization


class Evaluation(BaseModel):
    ground_truth_field: str = "label"  # field name in dataset for y_true
    outcomes: List[OutcomeSpec] = Field(default_factory=list)


class Datasets(BaseModel):
    simulation: str
    acceptance: str


class Canary(BaseModel):
    sample_size: int = 0
    rollback_on: List[str] = Field(default_factory=list)


class Audit(BaseModel):
    log_store: Optional[str] = None


class Domain(BaseModel):
    enums: Dict[str, List[str]] = Field(default_factory=dict)  # you can reference these in ArgSpec.enum
    synonyms: Dict[str, str] = Field(default_factory=dict)


class Intent(BaseModel):
    purpose: str
    kpis: List[KPI]
    forbidden_actions: List[str] = Field(default_factory=list)
    human_only_gates: List[str] = Field(default_factory=list)
    tooling: Tooling
    datasets: Datasets
    canary: Optional[Canary] = None
    audit: Optional[Audit] = None
    domain: Optional[Domain] = None
    evaluation: Optional[Evaluation] = None


def load_intent(path: Path) -> Intent:
    """
    Load and validate an intent YAML file, returning a normalized Intent object.
    """
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Intent YAML must map to a dictionary at the top level.")
    try:
        return Intent.model_validate(data)
    except ValidationError as e:
        # Re-raise with a cleaner message for CLI usage
        raise ValueError(e) from e


def json_schema() -> Dict[str, Any]:
    """
    Return the JSON Schema for the Intent model (useful for IDE hints & CI).
    """
    return Intent.model_json_schema()

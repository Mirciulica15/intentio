from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Dict, Any, List

from .actions import validate_and_normalize_actions
from .agent_iface import Agent, Record, PlanStep, now_ms
from .contract import Intent


def load_jsonl(path: Path, limit: int | None = None) -> Iterable[Record]:
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            if not line.strip():
                continue
            obj = json.loads(line)
            if "id" not in obj:
                obj["id"] = str(i)
            yield obj  # type: ignore[return-value]


def dry_run(agent: Agent, intent: Intent, records: Iterable[Record]) -> List[PlanStep]:
    trace: List[PlanStep] = []
    for rec in records:
        actions = agent.plan(rec, intent)
        actions = validate_and_normalize_actions(intent, str(rec.get("id", "")), actions)  # ← NEW
        trace.append(PlanStep(record_id=str(rec.get("id", "")), actions=actions, planned_at_ms=now_ms()))
    return trace


def summarize(trace: List[PlanStep]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for step in trace:
        for a in step.actions:
            k = f"{a.tool}:{a.name}"
            counts[k] = counts.get(k, 0) + 1
    return {"num_records": len({t.record_id for t in trace}), "action_counts": counts}

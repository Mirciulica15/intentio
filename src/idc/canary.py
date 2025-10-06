from __future__ import annotations

import json
import random
from pathlib import Path

from .agent_iface import SimpleRuleAgent
from .contract import load_intent
from .sandbox import load_jsonl, dry_run


def prepare_canary(intent_path: Path, outdir: Path, sample_size: int | None = None) -> Path:
    intent = load_intent(intent_path)
    pool_path = Path(intent.datasets.acceptance)  # placeholder: use eval set as “realistic” pool
    all_records = list(load_jsonl(pool_path))
    n = sample_size or intent.canary.sample_size if intent.canary else 20
    sample = random.sample(all_records, min(n, len(all_records)))

    agent = SimpleRuleAgent()
    trace = dry_run(agent, intent, sample)

    outdir.mkdir(parents=True, exist_ok=True)
    sample_path = outdir / "canary_sample.jsonl"
    with sample_path.open("w", encoding="utf-8") as f:
        for r in sample:
            f.write(json.dumps(r) + "\n")

    plan_path = outdir / "canary_plan.jsonl"
    with plan_path.open("w", encoding="utf-8") as f:
        for step in trace:
            f.write(json.dumps({
                "record_id": step.record_id,
                "actions": [dict(tool=a.tool, name=a.name, args=a.args) for a in step.actions],
                "planned_at_ms": step.planned_at_ms
            }) + "\n")

    return plan_path

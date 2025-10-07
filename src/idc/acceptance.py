from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

import numpy as np
from sklearn.metrics import f1_score

from .actions import validate_and_normalize_actions
from .agent_iface import Agent, Action
from .contract import Intent
from .policy import check as policy_check
from .sandbox import load_jsonl


def _extract_outcome(intent: Intent, actions: List[Action], result_name: str) -> Optional[str]:
    if not intent.evaluation:
        return None
    # find matching outcome rule
    spec = next((o for o in intent.evaluation.outcomes if o.name == result_name), None)
    if not spec:
        return None
    # scan actions for the tool+action
    for a in actions:
        if a.tool == spec.from_tool and a.name == spec.from_action:
            val = a.args.get(spec.arg)
            if isinstance(val, str) and spec.normalize_map:
                return spec.normalize_map.get(val, val)
            return val if isinstance(val, str) else None
    return None


def evaluate(agent: Agent, intent: Intent, dataset_path: Path, limit: int | None = None) -> Dict[str, Any]:
    y_true, y_pred, latencies_ms = [], [], []
    forbidden_hits = 0

    gt_field = intent.evaluation.ground_truth_field if intent.evaluation else "label"

    for rec in load_jsonl(dataset_path, limit=limit):
        start = time.time()
        actions = agent.plan(rec, intent)
        actions = validate_and_normalize_actions(intent, str(rec.get("id", "")), actions)
        dur_ms = (time.time() - start) * 1000
        latencies_ms.append(dur_ms)

        pred = _extract_outcome(intent, actions, result_name="label")
        y_pred.append(pred or "unknown")
        y_true.append(rec.get(gt_field, "unknown"))

        for a in actions:
            decision = policy_check(intent, a)
            if not decision.allow:
                forbidden_hits += 1

    f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    latency_p95 = float(np.percentile(latencies_ms, 95))
    forbidden_rate = forbidden_hits / max(1, len(y_true))

    return {
        "n_records": len(y_true),
        "metrics": {
            "f1_macro": round(f1, 3),
            "latency_ms_p95": round(latency_p95, 2),
            "forbidden_action_rate": round(forbidden_rate, 3),
        },
        "details": {
            "labels_true": y_true,
            "labels_pred": y_pred,
            "latencies_ms": latencies_ms,
        },
    }


def write_report(result: Dict[str, Any], outdir: Path) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / "metrics.json"
    with outpath.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return outpath

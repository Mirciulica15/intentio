from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any

import numpy as np
from sklearn.metrics import f1_score

from .agent_iface import Agent
from .contract import Intent
from .policy import check as policy_check
from .sandbox import load_jsonl


def evaluate(agent: Agent, intent: Intent, dataset_path: Path, limit: int | None = None) -> Dict[str, Any]:
    """Run the agent on the acceptance dataset and compute KPIs."""
    y_true, y_pred, latencies_ms = [], [], []
    forbidden_hits = 0

    for rec in load_jsonl(dataset_path, limit=limit):
        start = time.time()
        actions = agent.plan(rec, intent)
        dur_ms = (time.time() - start) * 1000
        latencies_ms.append(dur_ms)

        # Predicted label from the chosen route
        route_actions = [a for a in actions if a.name == "ticket.route"]
        queue = route_actions[0].args.get("queue", "unknown") if route_actions else "unknown"
        y_pred.append(queue)
        y_true.append(rec.get("label", "unknown"))

        # Policy evaluation per action
        for a in actions:
            decision = policy_check(intent, a)
            if not decision.allow:
                forbidden_hits += 1

    f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    latency_p95 = float(np.percentile(latencies_ms, 95))
    forbidden_rate = forbidden_hits / max(1, len(y_true))  # per-record rate

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

from __future__ import annotations

import glob
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List


@dataclass
class GateResult:
    passed: bool
    breaches: List[Dict[str, Any]]
    promotion_path: Path | None


_target_re = re.compile(r"^(>=|<=|==|>|<)\s*([\d.]+)")


def _compare(metric_value: float, target: str) -> bool:
    m = _target_re.match(target.strip())
    if not m:
        raise ValueError(f"Bad KPI target syntax: {target!r}")
    op, val = m.group(1), float(m.group(2))
    return {
        ">=": metric_value >= val,
        "<=": metric_value <= val,
        "==": metric_value == val,
        ">": metric_value > val,
        "<": metric_value < val,
    }[op]


def _hash_files(paths: List[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return h.hexdigest()


def decide_and_promote(intent_path: Path, metrics_path: Path, outdir: Path) -> GateResult:
    intent = json.loads(json.dumps(__import__("yaml").safe_load(intent_path.read_text(encoding="utf-8"))))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics_map: Dict[str, float] = {
        "f1_macro": float(metrics["metrics"]["f1_macro"]),
        "latency_ms_p95": float(metrics["metrics"]["latency_ms_p95"]),
        "forbidden_action_rate": float(metrics["metrics"]["forbidden_action_rate"]),
    }

    breaches: List[Dict[str, Any]] = []
    for k in intent["kpis"]:
        name, target = k["name"], k["target"]
        if name not in metrics_map:
            breaches.append({"name": name, "reason": "metric not computed"})
            continue
        val = metrics_map[name]
        try:
            ok = _compare(val, target)
        except Exception as e:
            breaches.append({"name": name, "reason": str(e)})
            continue
        if not ok:
            breaches.append({"name": name, "target": target, "actual": val})

    passed = len(breaches) == 0
    promotion_path = None
    if passed:
        outdir.mkdir(parents=True, exist_ok=True)
        # Hash candidate: intent + metrics + all agent/source files (simple heuristic)
        src_files = [Path(p) for p in glob.glob("src/idc/**/*.py", recursive=True)]
        digest = _hash_files([intent_path, metrics_path] + src_files)
        promotion = {
            "candidate": {
                "intent": str(intent_path),
                "metrics": str(metrics_path),
                "src_files": sorted([str(p) for p in src_files]),
                "sha256": digest,
            },
            "issued_at": int(time.time()),
            "decision": "promote",
            "canary": intent.get("canary", {}),
        }
        promotion_path = outdir / "promotion.json"
        promotion_path.write_text(json.dumps(promotion, indent=2), encoding="utf-8")

    return GateResult(passed=passed, breaches=breaches, promotion_path=promotion_path)

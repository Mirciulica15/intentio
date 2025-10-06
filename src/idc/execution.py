from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any

from .contract import load_intent
from .policy import check as policy_check
from .tools import Toolset


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def run_canary(intent_path: Path, plan_path: Path, outdir: Path) -> Dict[str, Any]:
    intent = load_intent(intent_path)
    outdir.mkdir(parents=True, exist_ok=True)
    toolset = Toolset(intent=intent)

    effects_log = outdir / "effects.jsonl"
    violations = 0
    gates = 0
    executed = 0

    with effects_log.open("w", encoding="utf-8") as logf:
        for step in _iter_jsonl(plan_path):
            rec_id = step["record_id"]
            for a in step["actions"]:
                action = {
                    "tool": a["tool"],
                    "name": a["name"],
                    "args": dict(a.get("args", {}))
                }
                # inject record id for tool binding
                action["args"].setdefault("id", rec_id)

                # policy decision (redundant with Toolset but useful for logging)
                pd = policy_check(intent, type("A", (), action)())  # quick shim to reuse Action-like fields
                if not pd.allow:
                    violations += 1
                    logf.write(json.dumps(
                        {"record_id": rec_id, "action": action, "policy": "blocked", "reason": pd.reason}) + "\n")
                    continue
                if pd.gate:
                    gates += 1
                    logf.write(json.dumps(
                        {"record_id": rec_id, "action": action, "policy": "gate_required", "reason": pd.reason}) + "\n")
                    continue

                # execute
                res = toolset.dispatch(type("A", (), action)())
                executed += 1 if res.get("ok") else 0
                logf.write(json.dumps({"record_id": rec_id, "action": action, "result": res}) + "\n")

    # Build rollback plan from tool state (only routes are “reversible” in our mock)
    rollback = outdir / "rollback_plan.jsonl"
    with rollback.open("w", encoding="utf-8") as f:
        for rec_id, queue in toolset.issue_tracker.routes.items():
            # If we logged a previous queue, it’s in the effect; for MVP, we simply route back to 'general'
            f.write(json.dumps({
                "record_id": rec_id,
                "actions": [
                    {"tool": "issue_tracker", "name": "ticket.route", "args": {"id": rec_id, "queue": "general"}}]
            }) + "\n")

    # Human sign-off template
    signoff = outdir / "human_signoff.json"
    signoff.write_text(json.dumps({
        "approved": False,
        "reviewer": "",
        "notes": "",
        "timestamp": int(time.time())
    }, indent=2), encoding="utf-8")

    summary = {
        "executed_actions": executed,
        "policy_violations": violations,
        "human_gates": gates,
        "effects_log": str(effects_log),
        "rollback_plan": str(rollback),
        "signoff_file": str(signoff),
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_rollback(rollback_path: Path, intent_path: Path, outdir: Path) -> Path:
    intent = load_intent(intent_path)
    toolset = Toolset(intent=intent)

    outdir.mkdir(parents=True, exist_ok=True)
    logp = outdir / "rollback_effects.jsonl"
    with logp.open("w", encoding="utf-8") as logf:
        for step in _iter_jsonl(rollback_path):
            rec_id = step["record_id"]
            for a in step["actions"]:
                act = type("A", (), {"tool": a["tool"], "name": a["name"], "args": a.get("args", {})})()
                res = toolset.dispatch(act)
                logf.write(json.dumps({"record_id": rec_id, "action": a, "result": res}) + "\n")
    return logp

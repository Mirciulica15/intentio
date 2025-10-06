from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def finalize(
        promotion_path: Path,  # artifacts/gate/promotion.json (from `idc gate`)
        canary_summary_path: Path,  # artifacts/canary/exec/summary.json (from `idc canary-run`)
        human_signoff_path: Path,  # artifacts/canary/exec/human_signoff.json (edited to approved:true)
        out_path: Path,  # artifacts/release/release.json
) -> Dict[str, Any]:
    promo = _read_json(promotion_path)
    canary = _read_json(canary_summary_path)
    sign = _read_json(human_signoff_path)

    # Basic checks
    breaches: list[str] = []
    if canary.get("policy_violations", 0) > 0:
        breaches.append(f"policy_violations={canary['policy_violations']}")
    if not isinstance(sign.get("approved", False), bool) or not sign["approved"]:
        breaches.append("human_signoff not approved")

    if breaches:
        return {"ok": False, "reason": " ; ".join(breaches)}

    release = {
        "issued_at": int(time.time()),
        "candidate_sha256": promo["candidate"]["sha256"],
        "intent": promo["candidate"]["intent"],
        "metrics": promo["candidate"]["metrics"],
        "canary": promo.get("canary", {}),
        "human_signoff": {
            "approved": True,
            "reviewer": sign.get("reviewer", ""),
            "notes": sign.get("notes", ""),
            "timestamp": sign.get("timestamp", None),
        },
        "source_files": promo["candidate"]["src_files"],
        "status": "approved",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(release, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(out_path)}

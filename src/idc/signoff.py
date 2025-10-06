from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Any

DEFAULT_PATH = Path("artifacts/canary/exec/human_signoff.json")


def _now() -> int:
    return int(time.time())


def _read(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {"approved": False, "reviewer": "", "notes": "", "timestamp": _now()}
    return json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, obj: Dict[str, Any]) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def init(path: Path = DEFAULT_PATH, reviewer: str = "", notes: str = "") -> Path:
    data = {"approved": False, "reviewer": reviewer, "notes": notes, "timestamp": _now()}
    return _write(path, data)


def approve(path: Path = DEFAULT_PATH, reviewer: str = "", notes: str = "") -> Path:
    data = _read(path)
    data.update(
        {"approved": True, "reviewer": reviewer or data.get("reviewer", ""), "notes": notes or data.get("notes", ""),
         "timestamp": _now()})
    return _write(path, data)


def reject(path: Path = DEFAULT_PATH, reviewer: str = "", notes: str = "") -> Path:
    data = _read(path)
    data.update(
        {"approved": False, "reviewer": reviewer or data.get("reviewer", ""), "notes": notes or data.get("notes", ""),
         "timestamp": _now()})
    return _write(path, data)


def show(path: Path = DEFAULT_PATH) -> Dict[str, Any]:
    return _read(path)

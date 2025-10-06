from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Iterable, List


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class RunAudit:
    run_dir: Path

    @classmethod
    def create(cls, base: Path | None = None) -> "RunAudit":
        base = base or Path("artifacts/runs")
        base.mkdir(parents=True, exist_ok=True)
        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = base / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "files").mkdir(parents=True, exist_ok=True)
        return cls(run_dir=run_dir)

    def snapshot_intent(self, intent_path: Path) -> Path:
        dst = self.run_dir / "files" / "intent.snapshot.yaml"
        shutil.copy2(intent_path, dst)
        return dst

    def write_json(self, relname: str, obj: Dict[str, Any]) -> Path:
        out = self.run_dir / "files" / relname
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        return out

    def write_jsonl(self, relname: str, rows: Iterable[Dict[str, Any]]) -> Path:
        out = self.run_dir / "files" / relname
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return out

    def copy_file(self, src: Path, relname: str | None = None) -> Path:
        relname = relname or src.name
        dst = self.run_dir / "files" / relname
        shutil.copy2(src, dst)
        return dst

    def manifest(self) -> Path:
        # Hash everything under run_dir/files
        files: List[Path] = sorted((self.run_dir / "files").rglob("*"))
        entries = []
        for p in files:
            if p.is_file():
                entries.append({"path": str(p.relative_to(self.run_dir)), "sha256": _sha256_file(p)})
        mf = {"run_dir": str(self.run_dir), "files": entries}
        out = self.run_dir / "manifest.json"
        out.write_text(json.dumps(mf, indent=2), encoding="utf-8")
        return out


def verify_manifest(manifest_path: Path) -> Dict[str, Any]:
    mf = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = Path(mf["run_dir"])
    mismatches = []
    missing = []
    for entry in mf["files"]:
        p = base / entry["path"]
        if not p.exists():
            missing.append(entry["path"])
            continue
        actual = _sha256_file(p)
        if actual != entry["sha256"]:
            mismatches.append({"path": entry["path"], "expected": entry["sha256"], "actual": actual})
    return {"ok": not mismatches and not missing, "missing": missing, "mismatches": mismatches}

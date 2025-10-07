#!/usr/bin/env bash
set -euo pipefail

INTENT=${1:-intent/examples/intent.support-triage.yaml}
MODEL=${MODEL:-gpt-4o-mini}
AGENT=${AGENT:-llm}

run() {
  echo -e "\033[36m==> $1\033[0m"
  shift
  if ! idc "$@"; then
    echo "❌ Step failed: idc $*" >&2
    exit 1
  fi
}

run "validate"        validate "$INTENT"
run "simulate"        simulate --intent "$INTENT" --sample 5 --agent "$AGENT" --model "$MODEL" --dry-run
run "test"            test --intent "$INTENT" --agent "$AGENT" --model "$MODEL"
run "gate-evaluate"   gate evaluate --intent "$INTENT"
run "canary-prepare"  canary prepare --intent "$INTENT" --sample 5
run "canary-run"      canary run --intent "$INTENT"
run "signoff-approve" signoff approve --reviewer "E2E Bot" --notes "Automated smoke"
run "gate-finalize"   gate finalize
run "verify"          verify --latest

if [[ -f "artifacts/release/release.json" ]]; then
  echo "✅ E2E smoke PASS"
else
  echo "❌ E2E smoke FAILED (no release.json)"
  exit 1
fi

param(
    [string]$Intent = "intent/examples/intent.support-triage.yaml",
    [string]$Model = "gpt-4o-mini",
    [string]$Agent = "llm"
)

$ErrorActionPreference = "Stop"

function Run([string]$name, [string[]]$cmdArgs)
{
    Write-Host "==> $name" -ForegroundColor Cyan
    & idc @cmdArgs
    if ($LASTEXITCODE -ne 0)
    {
        exit $LASTEXITCODE
    }
}

Run "validate"        @("validate", $Intent)
Run "simulate"        @("simulate", "--intent", $Intent, "--sample", "5", "--agent", $Agent, "--model", $Model, "--dry-run")
Run "test"            @("test", "--intent", $Intent, "--agent", $Agent, "--model", $Model)
Run "gate-evaluate"   @("gate", "evaluate", "--intent", $Intent)
Run "canary-prepare"  @("canary", "prepare", "--intent", $Intent, "--sample", "5")
Run "canary-run"      @("canary", "run", "--intent", $Intent)
Run "signoff-approve" @("signoff", "approve", "--reviewer", "E2E Bot", "--notes", "Automated smoke")
Run "gate-finalize"   @("gate", "finalize")
Run "verify"          @("verify", "--latest")

if (-not (Test-Path "artifacts/release/release.json"))
{
    Write-Host "❌ E2E smoke FAILED (no release.json)"
    exit 1
}

Write-Host "✅ E2E smoke PASS" -ForegroundColor Green

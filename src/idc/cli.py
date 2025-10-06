from __future__ import annotations

import json
from pathlib import Path

import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

from idc.acceptance import evaluate, write_report
from idc.agent_iface import SimpleRuleAgent
from idc.audit import RunAudit, verify_manifest
from idc.sandbox import summarize, load_jsonl, dry_run
from . import signoff as signoff_mod
from .canary import prepare_canary as canary_prepare
from .contract import load_intent, json_schema
from .execution import run_canary as canary_run_exec, run_rollback as canary_run_rollback
from .gate import decide_and_promote as gate_evaluate
from .hgate import finalize as gate_finalize_fn
from .policy import check as policy_check
from .signoff import DEFAULT_PATH as SIGNOFF_DEFAULT

app = typer.Typer(no_args_is_help=True, add_completion=False)
canary_app = typer.Typer(help="Canary workflow (prepare/run/rollback).")
gate_app = typer.Typer(help="Gate workflow (evaluate/finalize).")
signoff_app = typer.Typer(help="Human sign-off workflow")

app.add_typer(signoff_app, name="signoff")
app.add_typer(canary_app, name="canary")
app.add_typer(gate_app, name="gate")


@app.command(help="Validate an intent YAML file.")
def validate(path: Path, show: bool = typer.Option(False, "--show", help="Show normalized JSON")):
    try:
        intent = load_intent(path)
    except Exception as e:
        rprint(Panel.fit(f"[red]Invalid intent[/red]\n{e}", title="❌ Validation failed"))
        raise typer.Exit(1)

    rprint(Panel.fit(
        f"[bold]Purpose:[/bold] {intent.purpose}\n"
        f"[bold]KPIs:[/bold] {', '.join([f'{k.name} {k.target}' for k in intent.kpis])}\n"
        f"[bold]Forbidden actions:[/bold] {', '.join(intent.forbidden_actions) or '—'}\n"
        f"[bold]Human-only gates:[/bold] {', '.join(intent.human_only_gates) or '—'}\n"
        f"[bold]Datasets:[/bold] sim={intent.datasets.simulation}, acc={intent.datasets.acceptance}\n"
        f"[bold]Tools:[/bold] {', '.join([t.name for t in intent.tooling.allowed_tools]) or '—'}",
        title="✅ Intent is valid"
    ))

    if show:
        typer.echo(json.dumps(intent.model_dump(mode="json"), indent=2))


@app.command(help="Print the JSON schema for the intent model.")
def schema(out: Path = typer.Option(None, "--out", help="Write schema to file")):
    sch = json_schema()
    if out:
        out.write_text(json.dumps(sch, indent=2), encoding="utf-8")
        rprint(f"[green]Wrote schema to[/green] {out}")
    else:
        typer.echo(json.dumps(sch, indent=2))


@app.command(help="Run a dry-run simulation over a few records.")
def simulate(
        intent: Path = typer.Option(..., "--intent", help="Path to intent YAML"),
        sample: int = typer.Option(5, "--sample", help="Number of records to simulate"),
        dry_run_only: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Dry-run only (no execution)"),
):
    try:
        intent_obj = load_intent(intent)
    except Exception as e:
        rprint(Panel.fit(f"[red]Invalid intent[/red]\n{e}", title="❌ Validation failed"))
        raise typer.Exit(1)

    sim_path = Path(intent_obj.datasets.simulation)
    if not sim_path.exists():
        rprint(Panel.fit(f"[yellow]Simulation dataset not found[/yellow]\nExpected: {sim_path}\n"
                         "Create a small JSONL with fields: text, (optional) id, (optional) label.", title="⚠️ Notice"))
        raise typer.Exit(2)

    agent = SimpleRuleAgent()
    records = list(load_jsonl(sim_path, limit=sample))
    trace = dry_run(agent, intent_obj, records)

    table = Table(title="Dry-run Plan (first records)")
    table.add_column("Record ID")
    table.add_column("Actions")
    for step in trace:
        annotated = []
        for a in step.actions:
            decision = policy_check(intent_obj, a)
            label = f"{a.tool}.{a.name}({a.args})"
            if not decision.allow:
                label += " [BLOCKED]"
            elif decision.gate:
                label += " [GATE]"
            annotated.append(label)
        table.add_row(step.record_id, "; ".join(annotated))
    rprint(table)

    # Summary
    summ = summarize(trace)
    rprint(Panel.fit(f"[bold]Records:[/bold] {summ['num_records']}\n"
                     f"[bold]Action counts:[/bold] {summ['action_counts']}", title="Summary"))

    # --- Audit snapshot ---
    audit = RunAudit.create()
    audit.snapshot_intent(intent)
    # plan_trace.jsonl
    trace_rows = []
    for step in trace:
        trace_rows.append({
            "record_id": step.record_id,
            "actions": [dict(tool=a.tool, name=a.name, args=a.args) for a in step.actions],
            "planned_at_ms": step.planned_at_ms
        })
    audit.write_jsonl("plan_trace.jsonl", trace_rows)
    man = audit.manifest()
    rprint(Panel.fit(f"Audit run: {audit.run_dir}\nManifest: {man}", title="🧾 Audit"))

    if not dry_run_only:
        rprint(Panel.fit("Execution mode is not implemented in Step 2. Use --dry-run.", title="ℹ️ Info"))


@app.command(help="Run automated acceptance tests from the intent contract.")
def test(
        intent: Path = typer.Option(..., "--intent", help="Intent YAML file"),
        limit: int = typer.Option(None, "--limit", help="Limit number of records"),
        outdir: Path = typer.Option(Path("artifacts/acceptance"), "--outdir", help="Where to write metrics.json"),
):
    try:
        intent_obj = load_intent(intent)
    except Exception as e:
        rprint(Panel.fit(f"[red]Invalid intent[/red]\n{e}", title="❌ Validation failed"))
        raise typer.Exit(1)

    eval_path = Path(intent_obj.datasets.acceptance)
    if not eval_path.exists():
        rprint(Panel.fit(f"[yellow]Acceptance dataset not found[/yellow]\nExpected: {eval_path}", title="⚠️ Notice"))
        raise typer.Exit(2)

    agent = SimpleRuleAgent()
    result = evaluate(agent, intent_obj, eval_path, limit=limit)
    out = write_report(result, outdir)

    m = result["metrics"]
    rprint(Panel.fit(
        f"[bold]Records:[/bold] {result['n_records']}\n"
        f"[bold]f1_macro:[/bold] {m['f1_macro']}\n"
        f"[bold]latency_ms_p95:[/bold] {m['latency_ms_p95']}\n"
        f"[bold]forbidden_action_rate:[/bold] {m['forbidden_action_rate']}\n"
        f"[bold]Report:[/bold] {out}",
        title="✅ Acceptance Results"
    ))

    # --- Audit snapshot ---
    audit = RunAudit.create()
    audit.snapshot_intent(intent)
    audit.copy_file(out, "metrics.json")
    man = audit.manifest()
    rprint(Panel.fit(f"Audit run: {audit.run_dir}\nManifest: {man}", title="🧾 Audit"))


@app.command(help="Verify a run manifest's file checksums.")
def verify(
        manifest: Path = typer.Option(None, "--manifest", help="Path to artifacts/runs/.../manifest.json"),
        run_dir: Path = typer.Option(None, "--run-dir",
                                     help="Path to artifacts/runs/<timestamp> (will look for manifest.json inside)"),
        latest: bool = typer.Option(False, "--latest", help="Verify the most recent run"),
):
    from pathlib import Path
    if latest:
        base = Path("artifacts/runs")
        runs = sorted([p for p in base.glob("*") if p.is_dir()], key=lambda p: p.name)
        if not runs:
            rprint(Panel.fit("No runs found.", title="❌ Verification failed"))
            raise typer.Exit(2)
        manifest = runs[-1] / "manifest.json"
    elif run_dir:
        manifest = Path(run_dir) / "manifest.json"

    if manifest is None:
        rprint(Panel.fit("Provide --manifest, --run-dir, or --latest.", title="❌ Verification failed"))
        raise typer.Exit(2)

    res = verify_manifest(Path(manifest))
    if res["ok"]:
        rprint(Panel.fit("All files verified ✔️", title="✅ Verified"))
    else:
        msg = ""
        if res["missing"]:
            msg += "Missing:\n" + "\n".join(f"- {p}" for p in res["missing"]) + "\n"
        if res["mismatches"]:
            msg += "Mismatches:\n" + "\n".join(
                f"- {m['path']} (expected {m['expected']}, actual {m['actual']})" for m in res["mismatches"])
        rprint(Panel.fit(msg or "Unknown issue", title="❌ Verification failed"))
        raise typer.Exit(2)


@canary_app.command("prepare", help="Prepare a canary sample and dry-run plan.")
def canary_prepare_cmd(
        intent: Path = typer.Option(..., "--intent", help="Intent YAML"),
        outdir: Path = typer.Option(Path("artifacts/canary"), "--outdir", help="Output folder"),
        sample: int = typer.Option(None, "--sample", help="Override sample size"),
):
    try:
        plan_path = canary_prepare(intent, outdir, sample_size=sample)
    except Exception as e:
        rprint(Panel.fit(f"[red]Canary prep failed[/red]\n{e}", title="❌ Canary Error"))
        raise typer.Exit(1)
    rprint(Panel.fit(f"Canary prepared.\nPlan: {plan_path}\nSamples: {outdir / 'canary_sample.jsonl'}",
                     title="🟡 Canary Ready"))


@canary_app.command("run", help="Execute a canary plan with policy enforcement.")
def canary_run_cmd(
        intent: Path = typer.Option(..., "--intent", help="Intent YAML"),
        plan: Path = typer.Option(Path("artifacts/canary/canary_plan.jsonl"), "--plan",
                                  help="Plan JSONL (from prepare)"),
        outdir: Path = typer.Option(Path("artifacts/canary/exec"), "--outdir", help="Effects & summary output"),
):
    try:
        summary = canary_run_exec(intent, plan, outdir)
    except Exception as e:
        rprint(Panel.fit(f"[red]Canary execution failed[/red]\n{e}", title="❌ Exec Error"))
        raise typer.Exit(1)
    rprint(Panel.fit(
        f"[bold]Executed actions:[/bold] {summary['executed_actions']}\n"
        f"[bold]Policy violations:[/bold] {summary['policy_violations']}\n"
        f"[bold]Human gates (skipped):[/bold] {summary['human_gates']}\n"
        f"[bold]Effects log:[/bold] {summary['effects_log']}\n"
        f"[bold]Rollback plan:[/bold] {summary['rollback_plan']}\n"
        f"[bold]Sign-off file:[/bold] {summary['signoff_file']}",
        title="🟡 Canary Executed"
    ))


@canary_app.command("rollback", help="Execute a rollback plan produced by canary run.")
def canary_rollback_cmd(
        intent: Path = typer.Option(..., "--intent", help="Intent YAML"),
        rollback: Path = typer.Option(Path("artifacts/canary/exec/rollback_plan.jsonl"), "--rollback",
                                      help="Rollback plan JSONL"),
        outdir: Path = typer.Option(Path("artifacts/canary/rollback"), "--outdir",
                                    help="Where to write rollback effects"),
):
    try:
        logp = canary_run_rollback(rollback, intent, outdir)
    except Exception as e:
        rprint(Panel.fit(f"[red]Rollback failed[/red]\n{e}", title="❌ Rollback Error"))
        raise typer.Exit(1)
    rprint(Panel.fit(f"Rollback executed.\nEffects: {logp}", title="↩️ Rollback Done"))


@gate_app.command("evaluate", help="Evaluate metrics against intent.kpis and emit promotion.json if all pass.")
def gate_evaluate_cmd(
        intent: Path = typer.Option(..., "--intent", help="Intent YAML"),
        report: Path = typer.Option(Path("artifacts/acceptance/metrics.json"), "--report",
                                    help="metrics.json from `idc test`"),
        outdir: Path = typer.Option(Path("artifacts/gate"), "--outdir", help="Where to write promotion.json"),
):
    try:
        res = gate_evaluate(intent, report, outdir)
    except Exception as e:
        rprint(Panel.fit(f"[red]Gate evaluation failed[/red]\n{e}", title="❌ Gate Error"))
        raise typer.Exit(1)

    if res.passed:
        rprint(Panel.fit(f"[green]All KPIs met[/green]\nPromotion: {res.promotion_path}", title="✅ Gate Passed"))
    else:
        lines = "\n".join(
            [f"- {b.get('name')}: target {b.get('target')} vs actual {b.get('actual')} ({b.get('reason', '')})" for b in
             res.breaches])
        rprint(Panel.fit(f"[yellow]Breaches:[/yellow]\n{lines}", title="🚫 Gate Blocked"))
        raise typer.Exit(3)


@gate_app.command("finalize", help="Finalize promotion: needs KPIs pass, clean canary, and human sign-off.")
def gate_finalize_cmd(
        promotion: Path = typer.Option(Path("artifacts/gate/promotion.json"), "--promotion",
                                       help="From `idc gate evaluate`"),
        canary_summary: Path = typer.Option(Path("artifacts/canary/exec/summary.json"), "--canary-summary",
                                            help="From `idc canary run`"),
        signoff: Path = typer.Option(Path("artifacts/canary/exec/human_signoff.json"), "--signoff",
                                     help="Set approved:true"),
        out: Path = typer.Option(Path("artifacts/release/release.json"), "--out", help="Release descriptor output"),
):
    try:
        res = gate_finalize_fn(promotion, canary_summary, signoff, out)
    except Exception as e:
        rprint(Panel.fit(f"[red]Finalize failed[/red]\n{e}", title="❌ Gate Finalize Error"))
        raise typer.Exit(1)

    if not res.get("ok"):
        rprint(Panel.fit(f"[yellow]Blocked[/yellow]\n{res.get('reason')}", title="🚫 Not Promoted"))
        raise typer.Exit(3)

    rprint(Panel.fit(f"Release written: {res['path']}", title="🟢 Promoted"))


@signoff_app.command("init", help="Create or reset the human sign-off file.")
def signoff_init(
        path: Path = typer.Option(SIGNOFF_DEFAULT, "--path", help="Where to write human_signoff.json"),
        reviewer: str = typer.Option("", "--reviewer", help="Reviewer display name or email"),
        notes: str = typer.Option("", "--notes", help="Optional note"),
):
    p = signoff_mod.init(path, reviewer=reviewer, notes=notes)
    rprint(Panel.fit(f"Initialized sign-off at: {p}", title="📝 Sign-off"))


@signoff_app.command("approve", help="Approve the canary (sets approved:true).")
def signoff_approve(
        path: Path = typer.Option(SIGNOFF_DEFAULT, "--path"),
        reviewer: str = typer.Option(..., "--reviewer"),
        notes: str = typer.Option("", "--notes"),
):
    p = signoff_mod.approve(path, reviewer=reviewer, notes=notes)
    data = signoff_mod.show(path)
    rprint(Panel.fit(
        f"Approved by {data.get('reviewer')}\nNotes: {data.get('notes')}\nTime: {data.get('timestamp')}\nFile: {p}",
        title="✅ Approved"))


@signoff_app.command("reject", help="Reject the canary (sets approved:false).")
def signoff_reject(
        path: Path = typer.Option(SIGNOFF_DEFAULT, "--path"),
        reviewer: str = typer.Option(..., "--reviewer"),
        notes: str = typer.Option("", "--notes"),
):
    p = signoff_mod.reject(path, reviewer=reviewer, notes=notes)
    data = signoff_mod.show(path)
    rprint(Panel.fit(
        f"Rejected by {data.get('reviewer')}\nNotes: {data.get('notes')}\nTime: {data.get('timestamp')}\nFile: {p}",
        title="🚫 Rejected"))


@signoff_app.command("show", help="Show current sign-off state.")
def signoff_show(
        path: Path = typer.Option(SIGNOFF_DEFAULT, "--path"),
):
    data = signoff_mod.show(path)
    pretty = f"approved={data.get('approved')}  reviewer={data.get('reviewer')}\nnotes={data.get('notes')}\ntimestamp={data.get('timestamp')}\nfile={path}"
    rprint(Panel.fit(pretty, title="👀 Sign-off"))


if __name__ == "__main__":
    app()

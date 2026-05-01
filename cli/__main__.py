#!/usr/bin/env python3
"""
hydra-ctl — command-line interface for the Hydra scheduler.

Authenticate via environment variables (recommended) or command-line flags:

  API_TOKEN      Domain API token   (required)
  DOMAIN         Target domain      (default: prod)
  HYDRA_API_URL  Scheduler URL      (default: http://localhost:8000)

Usage:
  hydra-ctl jobs list [--search TEXT] [--tags t1,t2]
  hydra-ctl jobs show <name-or-id>
  hydra-ctl jobs trigger <name-or-id> [--param k=v ...]
  hydra-ctl jobs enable <name-or-id>
  hydra-ctl jobs disable <name-or-id>
  hydra-ctl jobs runs <name-or-id> [--limit N]

  hydra-ctl runs list [--limit N]
  hydra-ctl runs show <run-id>
  hydra-ctl runs logs <run-id>
  hydra-ctl runs kill <run-id> [--yes]

  hydra-ctl workers list
  hydra-ctl workers show <worker-id>
  hydra-ctl workers state <worker-id> online|draining|offline

  hydra-ctl overview
  hydra-ctl overview queue [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from ._client import HydraClient
from ._output import (
    fmt_bool,
    fmt_duration,
    fmt_nullable,
    fmt_status,
    fmt_ts,
    print_json,
    print_table,
)


# ── Shared argument group ─────────────────────────────────────────────────────

# Added to every leaf subparser so flags work after the subcommand:
#   hydra-ctl jobs list --json
#   hydra-ctl --json jobs list   (also works — parsed by main parser)

_shared = argparse.ArgumentParser(add_help=False)
_shared.add_argument("--token", metavar="TOKEN",
                     help="Domain API token [env: API_TOKEN]")
_shared.add_argument("--domain", metavar="DOMAIN",
                     help="Target domain [env: DOMAIN, default: prod]")
_shared.add_argument("--api-url", metavar="URL", dest="api_url",
                     help="Scheduler URL [env: HYDRA_API_URL, default: http://localhost:8000]")
_shared.add_argument("--json", action="store_true",
                     help="Emit raw JSON instead of formatted output")


def _build_client(args: argparse.Namespace) -> HydraClient:
    token = args.token or os.environ.get("API_TOKEN", "")
    if not token:
        print("error: API token required — set API_TOKEN or pass --token", file=sys.stderr)
        sys.exit(2)
    domain = args.domain or os.environ.get("DOMAIN", "prod")
    api_url = (args.api_url or os.environ.get("HYDRA_API_URL", "http://localhost:8000")).rstrip("/")
    return HydraClient(api_url=api_url, token=token, domain=domain)


# ── jobs ──────────────────────────────────────────────────────────────────────

def cmd_jobs_list(client: HydraClient, args: argparse.Namespace) -> None:
    params: dict = {}
    if args.search:
        params["search"] = args.search
    if args.tags:
        params["tags"] = args.tags
    data = client.get("/jobs/", params=params or None)
    jobs: list[dict] = data if isinstance(data, list) else data.get("jobs", [])

    if args.json:
        print_json(jobs)
        return

    rows = []
    for j in jobs:
        sched = j.get("schedule") or {}
        rows.append({
            "name": j.get("name", ""),
            "id": (j.get("_id") or "")[:12],
            "schedule": sched.get("mode", "—"),
            "enabled": fmt_bool(sched.get("enabled")),
            "last_status": fmt_status(j.get("last_run_status")),
            "next_run": fmt_ts(sched.get("next_run_at")),
        })
    print_table(rows, [
        ("name", "NAME"),
        ("id", "ID"),
        ("schedule", "SCHEDULE"),
        ("enabled", "ENABLED"),
        ("last_status", "LAST STATUS"),
        ("next_run", "NEXT RUN"),
    ])


def cmd_jobs_show(client: HydraClient, args: argparse.Namespace) -> None:
    job = client.resolve_job(args.job)
    if args.json:
        print_json(job)
        return

    sched = job.get("schedule") or {}
    executor = job.get("executor") or {}
    print(f"Name:      {job.get('name', '')}")
    print(f"ID:        {job.get('_id', '')}")
    print(f"Domain:    {job.get('domain', '')}")
    print(f"Executor:  {executor.get('type', '—')}")
    print(f"Timeout:   {fmt_duration(job.get('timeout'))}")
    mode = sched.get("mode", "—")
    enabled = fmt_bool(sched.get("enabled"))
    print(f"Schedule:  {mode}  (enabled: {enabled})")
    if sched.get("cron"):
        print(f"  Cron:    {sched['cron']}")
    if sched.get("interval_seconds"):
        print(f"  Interval:{fmt_duration(sched['interval_seconds'])}")
    if sched.get("next_run_at"):
        print(f"  Next:    {fmt_ts(sched['next_run_at'])}")
    if job.get("tags"):
        print(f"Tags:      {', '.join(job['tags'])}")
    if job.get("description"):
        print(f"Desc:      {job['description']}")


def cmd_jobs_trigger(client: HydraClient, args: argparse.Namespace) -> None:
    job = client.resolve_job(args.job)
    job_id = job.get("_id", "")
    body: dict = {}
    if args.param:
        params: dict[str, str] = {}
        for p in args.param:
            if "=" not in p:
                print(f"error: --param must be key=value, got: {p!r}", file=sys.stderr)
                sys.exit(2)
            k, v = p.split("=", 1)
            params[k] = v
        body["params"] = params
    result = client.post(f"/jobs/{job_id}/run", body or None)
    if args.json:
        print_json(result)
        return
    print(f"Queued:  {job.get('name')}  (job_id={result.get('job_id', job_id)})")
    print("Tip: use 'hydra-ctl jobs runs <name>' to watch for the new run.")


def cmd_jobs_enable(client: HydraClient, args: argparse.Namespace) -> None:
    _set_enabled(client, args, True)


def cmd_jobs_disable(client: HydraClient, args: argparse.Namespace) -> None:
    _set_enabled(client, args, False)


def _set_enabled(client: HydraClient, args: argparse.Namespace, enabled: bool) -> None:
    job = client.resolve_job(args.job)
    job_id = job.get("_id", "")
    # Send just the schedule with enabled toggled — server merges at top level
    schedule = dict(job.get("schedule") or {})
    schedule["enabled"] = enabled
    result = client.put(f"/jobs/{job_id}", body={"schedule": schedule})
    if args.json:
        print_json(result)
        return
    state = "enabled" if enabled else "disabled"
    print(f"Job '{job.get('name')}' {state}.")


def cmd_jobs_runs(client: HydraClient, args: argparse.Namespace) -> None:
    job = client.resolve_job(args.job)
    job_id = job.get("_id", "")
    data = client.get(f"/jobs/{job_id}/runs")
    runs: list[dict] = data if isinstance(data, list) else data.get("runs", [])
    # Most recent first; cap at --limit
    runs = list(reversed(runs))
    if args.limit:
        runs = runs[:args.limit]

    if args.json:
        print_json(runs)
        return

    rows = []
    for r in runs:
        rows.append({
            "run_id": (r.get("run_id") or r.get("_id") or "")[:16],
            "status": fmt_status(r.get("status")),
            "started": fmt_ts(r.get("start_ts")),
            "duration": fmt_duration(_run_duration(r)),
            "worker": (r.get("worker_id") or "—")[:20],
        })
    print(f"Runs for: {job.get('name')}")
    print_table(rows, [
        ("run_id", "RUN ID"),
        ("status", "STATUS"),
        ("started", "STARTED"),
        ("duration", "DURATION"),
        ("worker", "WORKER"),
    ])


# ── runs ──────────────────────────────────────────────────────────────────────

def cmd_runs_list(client: HydraClient, args: argparse.Namespace) -> None:
    data = client.get("/history/")
    runs: list[dict] = data if isinstance(data, list) else data.get("runs", [])
    if args.limit:
        runs = runs[:args.limit]

    if args.json:
        print_json(runs)
        return

    rows = []
    for r in runs:
        rows.append({
            "run_id": (r.get("run_id") or r.get("_id") or "")[:16],
            "job": (r.get("job_id") or "")[:24],
            "status": fmt_status(r.get("status")),
            "started": fmt_ts(r.get("start_ts")),
            "duration": fmt_duration(_run_duration(r)),
        })
    print_table(rows, [
        ("run_id", "RUN ID"),
        ("job", "JOB"),
        ("status", "STATUS"),
        ("started", "STARTED"),
        ("duration", "DURATION"),
    ])


def cmd_runs_show(client: HydraClient, args: argparse.Namespace) -> None:
    r = client.get(f"/runs/{args.run_id}")
    if args.json:
        print_json(r)
        return

    print(f"Run ID:   {r.get('id') or r.get('_id', '')}")
    print(f"Job:      {r.get('job_id', '')}")
    print(f"Domain:   {r.get('domain', '')}")
    print(f"Status:   {fmt_status(r.get('status'))}")
    print(f"Worker:   {r.get('worker_id') or '—'}")
    print(f"Started:  {fmt_ts(r.get('start_ts'))}")
    print(f"Ended:    {fmt_ts(r.get('end_ts'))}")
    print(f"Duration: {fmt_duration(_run_duration(r))}")
    if r.get("returncode") is not None:
        print(f"Exit:     {r['returncode']}")


def cmd_runs_logs(client: HydraClient, args: argparse.Namespace) -> None:
    run = client.get(f"/runs/{args.run_id}")
    status = run.get("status", "")

    if status == "running":
        _stream_sse_logs(client, args.run_id)
        return

    # Completed run — print captured output
    stdout = (run.get("stdout_tail") or run.get("stdout") or "").rstrip()
    stderr = (run.get("stderr") or "").rstrip()
    if stdout:
        print(stdout)
    if stderr:
        print("--- stderr ---", file=sys.stderr)
        print(stderr, file=sys.stderr)
    if not stdout and not stderr:
        print(f"(no output captured for run {args.run_id})")


def _stream_sse_logs(client: HydraClient, run_id: str) -> None:
    url = f"{client.base}/runs/{run_id}/stream"
    headers = {**client.headers, "Accept": "text/event-stream"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            for raw_line in resp:
                line = raw_line.decode(errors="replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                payload_str = line[5:].strip()
                if not payload_str:
                    continue
                try:
                    payload = json.loads(payload_str)
                    text = payload.get("line") or payload.get("data") or ""
                    if text:
                        print(text, end="" if text.endswith("\n") else "\n")
                except json.JSONDecodeError:
                    print(payload_str)
    except (urllib.error.HTTPError, urllib.error.URLError):
        # Stream unavailable — fall back to tail already stored
        pass


def cmd_runs_kill(client: HydraClient, args: argparse.Namespace) -> None:
    if not args.yes:
        try:
            confirm = input(f"Kill run {args.run_id}? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            sys.exit(0)
    result = client.post(f"/runs/{args.run_id}/kill")
    if args.json:
        print_json(result)
        return
    print(f"Kill signal sent to run {args.run_id}.")


# ── workers ───────────────────────────────────────────────────────────────────

def cmd_workers_list(client: HydraClient, args: argparse.Namespace) -> None:
    data = client.get("/workers/")
    workers: list[dict] = data if isinstance(data, list) else data.get("workers", [])

    if args.json:
        print_json(workers)
        return

    rows = []
    for w in workers:
        running = w.get("running_jobs") or []
        rows.append({
            "id": w.get("worker_id", ""),
            "state": w.get("state", "—"),
            "running": str(len(running)),
            "tags": ", ".join(w.get("tags") or []) or "—",
            "connected": fmt_bool(w.get("connected")),
        })
    print_table(rows, [
        ("id", "WORKER ID"),
        ("state", "STATE"),
        ("running", "RUNNING"),
        ("tags", "TAGS"),
        ("connected", "CONNECTED"),
    ])


def cmd_workers_show(client: HydraClient, args: argparse.Namespace) -> None:
    data = client.get("/workers/")
    workers: list[dict] = data if isinstance(data, list) else data.get("workers", [])

    wid = args.worker_id
    matches = [w for w in workers
               if w.get("worker_id") == wid or (w.get("worker_id") or "").startswith(wid)]
    if not matches:
        print(f"error: worker '{wid}' not found", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        ids = ", ".join(w.get("worker_id", "?") for w in matches)
        print(f"error: '{wid}' is ambiguous — matches: {ids}", file=sys.stderr)
        sys.exit(1)

    w = matches[0]
    if args.json:
        print_json(w)
        return

    running = w.get("running_jobs") or []
    print(f"Worker:       {w.get('worker_id', '')}")
    print(f"State:        {w.get('state', '—')}")
    print(f"Connected:    {fmt_bool(w.get('connected'))}")
    print(f"Running jobs: {len(running)}")
    for r in running:
        print(f"  - job={r.get('job_id', '?')}  run={str(r.get('run_id', '?'))[:12]}")
    if w.get("tags"):
        print(f"Tags:         {', '.join(w['tags'])}")
    if w.get("capabilities"):
        print(f"Capabilities: {', '.join(w['capabilities'])}")
    if w.get("os"):
        print(f"OS:           {w['os']}")
    if w.get("max_concurrency"):
        print(f"Concurrency:  {w['max_concurrency']}")


def cmd_workers_state(client: HydraClient, args: argparse.Namespace) -> None:
    valid = ("online", "draining", "offline")
    if args.new_state not in valid:
        print(f"error: state must be one of {valid}", file=sys.stderr)
        sys.exit(2)
    result = client.post(f"/workers/{args.worker_id}/state", body={"state": args.new_state})
    if args.json:
        print_json(result)
        return
    print(f"Worker '{args.worker_id}' → {args.new_state}.")


# ── overview ──────────────────────────────────────────────────────────────────

def cmd_overview(client: HydraClient, args: argparse.Namespace) -> None:
    stats = client.get("/overview/statistics")
    health = client.get("/health")

    if args.json:
        print_json({"statistics": stats, "health": health})
        return

    print(f"Domain:        {client.domain}")
    print(f"Workers:       {health.get('worker_count', 0)} active")
    print(f"Pending:       {health.get('pending_jobs', 0)} jobs in queue")
    total = stats.get("total_jobs", 0)
    enabled = stats.get("enabled_jobs", 0)
    print(f"Jobs:          {total} total  ({enabled} enabled)")
    runs_today = stats.get("runs_today", stats.get("total_runs_today", "—"))
    print(f"Runs today:    {runs_today}")
    sr = stats.get("success_rate")
    if sr is not None:
        try:
            print(f"Success rate:  {float(sr):.0%}")
        except (ValueError, TypeError):
            print(f"Success rate:  {sr}")


def cmd_overview_queue(client: HydraClient, args: argparse.Namespace) -> None:
    data = client.get("/overview/queue")
    items: list[dict] = (
        data if isinstance(data, list)
        else data.get("queue", data.get("jobs", []))
    )
    if args.limit:
        items = items[:args.limit]

    if args.json:
        print_json(items)
        return

    rows = []
    for item in items:
        rows.append({
            "job": (item.get("name") or item.get("job_id") or "")[:30],
            "reason": item.get("reason", "—"),
            "next": fmt_ts(item.get("next_run_at") or item.get("scheduled_at")),
            "priority": fmt_nullable(item.get("priority")),
        })
    print_table(rows, [
        ("job", "JOB"),
        ("reason", "REASON"),
        ("next", "NEXT RUN"),
        ("priority", "PRIORITY"),
    ])


# ── utilities ─────────────────────────────────────────────────────────────────

def _run_duration(run: dict) -> float | None:
    start = run.get("start_ts")
    end = run.get("end_ts")
    if not start or not end:
        return None
    try:
        from datetime import datetime as _dt

        def _parse(s: str) -> _dt:
            if isinstance(s, _dt):
                return s
            s = str(s)
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return _dt.fromisoformat(s)

        return (_parse(end) - _parse(start)).total_seconds()
    except Exception:
        return None


# ── argparse tree ─────────────────────────────────────────────────────────────

def _jobs_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("jobs", help="Job management (list, trigger, enable/disable, runs)")
    js = p.add_subparsers(dest="jobs_cmd", metavar="SUBCOMMAND")
    js.required = True

    # list
    pl = js.add_parser("list", parents=[_shared], help="List jobs in the domain")
    pl.add_argument("--search", metavar="TEXT", help="Filter by name")
    pl.add_argument("--tags", metavar="t1,t2", help="Filter by tag (comma-separated)")

    # show
    ps = js.add_parser("show", parents=[_shared], help="Show job definition")
    ps.add_argument("job", metavar="NAME-OR-ID")

    # trigger
    pt = js.add_parser("trigger", parents=[_shared], help="Queue a manual run now")
    pt.add_argument("job", metavar="NAME-OR-ID")
    pt.add_argument("--param", metavar="key=value", action="append",
                    help="Runtime parameter (repeatable)")

    # enable / disable
    pe = js.add_parser("enable", parents=[_shared], help="Enable job schedule")
    pe.add_argument("job", metavar="NAME-OR-ID")

    pd = js.add_parser("disable", parents=[_shared], help="Disable job schedule")
    pd.add_argument("job", metavar="NAME-OR-ID")

    # runs
    pr = js.add_parser("runs", parents=[_shared], help="List runs for a job")
    pr.add_argument("job", metavar="NAME-OR-ID")
    pr.add_argument("--limit", metavar="N", type=int, default=20,
                    help="Max runs to show (default: 20)")


def _runs_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("runs", help="Run management (list, show, logs, kill)")
    rs = p.add_subparsers(dest="runs_cmd", metavar="SUBCOMMAND")
    rs.required = True

    pl = rs.add_parser("list", parents=[_shared], help="List recent runs across all jobs")
    pl.add_argument("--limit", metavar="N", type=int, default=20,
                    help="Max runs to show (default: 20)")

    ps = rs.add_parser("show", parents=[_shared], help="Show run metadata and outcome")
    ps.add_argument("run_id", metavar="RUN-ID")

    plo = rs.add_parser("logs", parents=[_shared],
                        help="Print logs; streams live if run is still active")
    plo.add_argument("run_id", metavar="RUN-ID")

    pk = rs.add_parser("kill", parents=[_shared], help="Kill a running execution")
    pk.add_argument("run_id", metavar="RUN-ID")
    pk.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")


def _workers_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("workers", help="Worker management (list, show, set state)")
    ws = p.add_subparsers(dest="workers_cmd", metavar="SUBCOMMAND")
    ws.required = True

    ws.add_parser("list", parents=[_shared], help="List workers and their status")

    psh = ws.add_parser("show", parents=[_shared], help="Show worker details")
    psh.add_argument("worker_id", metavar="WORKER-ID")

    pst = ws.add_parser("state", parents=[_shared], help="Set worker state")
    pst.add_argument("worker_id", metavar="WORKER-ID")
    pst.add_argument("new_state", metavar="online|draining|offline")


def _overview_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("overview", parents=[_shared],
                       help="Domain summary: job counts, run stats, worker health")
    ov = p.add_subparsers(dest="overview_cmd", metavar="SUBCOMMAND")

    pq = ov.add_parser("queue", parents=[_shared], help="Show pending and upcoming jobs")
    pq.add_argument("--limit", metavar="N", type=int, default=20,
                    help="Max items to show (default: 20)")


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="hydra-ctl",
        description="Command-line interface for the Hydra scheduler.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
environment variables:
  API_TOKEN      Domain API token (required)
  DOMAIN         Target domain    (default: prod)
  HYDRA_API_URL  Scheduler URL    (default: http://localhost:8000)

examples:
  hydra-ctl jobs list
  hydra-ctl jobs list --search nightly
  hydra-ctl jobs trigger my-daily-job --param date=2026-01-01
  hydra-ctl jobs runs my-daily-job --limit 5
  hydra-ctl runs logs <run-id>
  hydra-ctl workers list
  hydra-ctl overview
  hydra-ctl overview queue
""",
    )
    # Global flags on the main parser so 'hydra-ctl --json jobs list' also works
    parser.add_argument("--token", metavar="TOKEN", help="Domain API token [env: API_TOKEN]")
    parser.add_argument("--domain", metavar="DOMAIN", help="Target domain [env: DOMAIN]")
    parser.add_argument("--api-url", metavar="URL", dest="api_url",
                        help="Scheduler URL [env: HYDRA_API_URL]")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    _jobs_parser(sub)
    _runs_parser(sub)
    _workers_parser(sub)
    _overview_parser(sub)

    args = parser.parse_args(argv)
    client = _build_client(args)

    if args.command == "jobs":
        {
            "list": cmd_jobs_list,
            "show": cmd_jobs_show,
            "trigger": cmd_jobs_trigger,
            "enable": cmd_jobs_enable,
            "disable": cmd_jobs_disable,
            "runs": cmd_jobs_runs,
        }[args.jobs_cmd](client, args)

    elif args.command == "runs":
        {
            "list": cmd_runs_list,
            "show": cmd_runs_show,
            "logs": cmd_runs_logs,
            "kill": cmd_runs_kill,
        }[args.runs_cmd](client, args)

    elif args.command == "workers":
        {
            "list": cmd_workers_list,
            "show": cmd_workers_show,
            "state": cmd_workers_state,
        }[args.workers_cmd](client, args)

    elif args.command == "overview":
        if getattr(args, "overview_cmd", None) == "queue":
            cmd_overview_queue(client, args)
        else:
            cmd_overview(client, args)


if __name__ == "__main__":
    main()

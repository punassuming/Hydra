#!/usr/bin/env python3
"""
hydra-apply — GitOps-style job upsert tool for Hydra Jobs.

Reads a YAML or JSON file of job definitions and creates or updates them
via the Hydra scheduler API.  Matches jobs by name within the target domain.

Usage:
    python scripts/hydra-apply.py --file jobs.yaml --token $API_TOKEN [options]

    # Dry-run (no changes made):
    python scripts/hydra-apply.py --file jobs.yaml --token $API_TOKEN --dry-run

    # Target a specific domain:
    python scripts/hydra-apply.py --file jobs.yaml --token $API_TOKEN --domain prod

    # Point at a non-default scheduler:
    python scripts/hydra-apply.py --file jobs.yaml --token $API_TOKEN \\
        --api-url https://hydra.internal:8000

Exit codes:
    0  — all jobs applied successfully (or --dry-run completed)
    1  — one or more HTTP errors or file parse errors
    2  — usage / configuration error

YAML format example (jobs.yaml):
    - name: daily-report
      user: default
      timeout: 300
      executor:
        type: shell
        shell: bash
        script: |
          python /opt/reports/run.py
      schedule:
        mode: cron
        cron: "0 8 * * *"
        enabled: true
      affinity:
        os: [linux]
      completion:
        exit_codes: [0]

    - name: health-check
      executor:
        type: http
        url: https://api.example.com/health
        method: GET
        expected_status: 200
      timeout: 30
      schedule:
        mode: interval
        interval_seconds: 300
        enabled: true
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _load_file(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read()

    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
    except ImportError:
        # yaml not installed; fall back to JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            sys.exit(f"[hydra-apply] ERROR: Could not parse file as JSON (yaml not installed): {exc}")

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        sys.exit("[hydra-apply] ERROR: File must contain a list (or single object) of job definitions.")
    return data


def _api(method: str, path: str, api_url: str, token: str, domain: str, body: dict | None = None) -> dict:
    url = f"{api_url.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "x-api-key": token,
            "x-domain": domain,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason} — {body_text}") from exc


def _find_job_by_name(name: str, domain: str, api_url: str, token: str) -> dict | None:
    path = f"/jobs/?search={urllib.parse.quote(name)}&domain={urllib.parse.quote(domain)}"
    results = _api("GET", path, api_url, token, domain)
    for job in results:
        if job.get("name") == name and job.get("domain") == domain:
            return job
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply Hydra job definitions from a YAML/JSON file (create or update by name).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", "-f", required=True, help="Path to YAML or JSON file containing job definitions.")
    parser.add_argument("--token", "-t", default=os.getenv("API_TOKEN"), help="Domain API token (or set API_TOKEN env var).")
    parser.add_argument("--api-url", default=os.getenv("API_BASE_URL", "http://localhost:8000"), help="Scheduler base URL.")
    parser.add_argument("--domain", default=os.getenv("DOMAIN", "prod"), help="Target domain (default: prod).")
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions without making any changes.")
    args = parser.parse_args()

    if not args.token:
        print("[hydra-apply] ERROR: --token / API_TOKEN is required.", file=sys.stderr)
        return 2

    jobs = _load_file(args.file)
    print(f"[hydra-apply] Loaded {len(jobs)} job definition(s) from {args.file}")
    if args.dry_run:
        print("[hydra-apply] DRY-RUN mode — no changes will be made.")

    created = updated = errors = 0

    for job_def in jobs:
        name = job_def.get("name")
        if not name:
            print("[hydra-apply] WARNING: skipping entry with no 'name' field.", file=sys.stderr)
            errors += 1
            continue

        # Ensure domain is set on the payload
        job_def = dict(job_def)
        job_def.setdefault("domain", args.domain)

        try:
            existing = _find_job_by_name(name, args.domain, args.api_url, args.token)
        except RuntimeError as exc:
            print(f"[hydra-apply] ERROR looking up '{name}': {exc}", file=sys.stderr)
            errors += 1
            continue

        if existing:
            job_id = existing.get("_id") or existing.get("id")
            if args.dry_run:
                print(f"  would update  {name}  (id={job_id})")
            else:
                try:
                    _api("PUT", f"/jobs/{job_id}", args.api_url, args.token, args.domain, job_def)
                    print(f"  updated       {name}  (id={job_id})")
                    updated += 1
                except RuntimeError as exc:
                    print(f"[hydra-apply] ERROR updating '{name}': {exc}", file=sys.stderr)
                    errors += 1
        else:
            if args.dry_run:
                print(f"  would create  {name}")
            else:
                try:
                    result = _api("POST", "/jobs/", args.api_url, args.token, args.domain, job_def)
                    new_id = result.get("_id") or result.get("id", "?")
                    print(f"  created       {name}  (id={new_id})")
                    created += 1
                except RuntimeError as exc:
                    print(f"[hydra-apply] ERROR creating '{name}': {exc}", file=sys.stderr)
                    errors += 1

    if args.dry_run:
        print(f"\n[hydra-apply] Dry-run complete: {len(jobs)} job(s) would be processed.")
    else:
        print(f"\n[hydra-apply] Done. created={created}  updated={updated}  errors={errors}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

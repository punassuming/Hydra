"""Output formatting helpers for hydra-ctl.

Pure stdlib — no third-party dependencies.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


# ── JSON ─────────────────────────────────────────────────────────────────────

def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


# ── Tables ───────────────────────────────────────────────────────────────────

def print_table(rows: list[dict], columns: list[tuple[str, str]]) -> None:
    """Print rows as a plain-text table.

    columns is a list of (key, header) pairs.  Values are extracted from each
    row dict by key and coerced to str.
    """
    if not rows:
        print("(no results)")
        return

    keys = [k for k, _ in columns]
    headers = [h for _, h in columns]

    # Collect string values
    str_rows: list[list[str]] = []
    for row in rows:
        str_rows.append([str(row.get(k) if row.get(k) is not None else "") for k in keys])

    # Compute column widths
    widths = [len(h) for h in headers]
    for r in str_rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for r in str_rows:
        print(fmt.format(*r))


# ── Formatters ───────────────────────────────────────────────────────────────

def fmt_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def fmt_ts(value: Any) -> str:
    """Format an ISO timestamp or datetime to a short local-time string."""
    if value is None:
        return "—"
    if isinstance(value, datetime):
        dt = value
    else:
        iso = str(value)
        if not iso:
            return "—"
        try:
            if iso.endswith("Z"):
                iso = iso[:-1] + "+00:00"
            dt = datetime.fromisoformat(iso)
        except ValueError:
            return str(value)[:16]
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M")


_STATUS_SYMBOLS = {
    "success": "✓",
    "failed": "✗",
    "timed_out": "⏱",
    "running": "⟳",
    "killed": "⊘",
    "pending": "○",
    "dispatched": "→",
    "skipped": "⊖",
}


def fmt_status(status: str | None) -> str:
    if not status:
        return "—"
    sym = _STATUS_SYMBOLS.get(status, "?")
    return f"{sym} {status}"


def fmt_bool(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "—"


def fmt_nullable(value: Any) -> str:
    return str(value) if value is not None else "—"

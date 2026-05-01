"""Thin HTTP client for the Hydra scheduler API.

Uses only Python stdlib (urllib) so the CLI can be installed on any machine
without pulling in third-party HTTP libraries.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class HydraClient:
    def __init__(self, api_url: str, token: str, domain: str) -> None:
        self.base = api_url.rstrip("/")
        self.domain = domain
        self.headers: dict[str, str] = {
            "x-api-key": token,
            "x-domain": domain,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ── low-level ────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, params: dict | None = None,
                 body: Any = None, ok_404: bool = False) -> Any:
        url = self.base + path
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                url += "?" + urllib.parse.urlencode(filtered)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            if ok_404 and e.code == 404:
                return None
            body_text = e.read().decode(errors="replace")
            try:
                detail = json.loads(body_text).get("detail", body_text)
            except Exception:
                detail = body_text
            # detail may be a list (FastAPI validation errors)
            if isinstance(detail, list):
                detail = "; ".join(
                    d.get("msg", str(d)) if isinstance(d, dict) else str(d)
                    for d in detail
                )
            print(f"error: HTTP {e.code} — {detail}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"error: could not connect to {self.base} — {e.reason}", file=sys.stderr)
            sys.exit(1)

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def get_or_none(self, path: str) -> Any:
        """GET that returns None on 404 instead of exiting."""
        return self._request("GET", path, ok_404=True)

    def post(self, path: str, body: Any = None) -> Any:
        return self._request("POST", path, body=body)

    def put(self, path: str, body: Any = None) -> Any:
        return self._request("PUT", path, body=body)

    # ── helpers ──────────────────────────────────────────────────────────────

    def resolve_job(self, name_or_id: str) -> dict:
        """Return the job dict for name_or_id.

        Tries a direct ID lookup first (fast path), then falls back to a
        name-based search so callers can use either the UUID or the job name.
        """
        # Fast path: treat as ID
        job = self.get_or_none(f"/jobs/{urllib.parse.quote(name_or_id, safe='')}")
        if job:
            return job

        # Name search
        results = self.get("/jobs/", params={"search": name_or_id})
        jobs_list: list[dict] = results if isinstance(results, list) else results.get("jobs", [])

        # Prefer exact name match
        exact = [j for j in jobs_list if j.get("name") == name_or_id]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            _ambiguous_exit(name_or_id, exact)

        # Accept partial name match if unambiguous
        partial = [j for j in jobs_list if name_or_id.lower() in (j.get("name") or "").lower()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            _ambiguous_exit(name_or_id, partial)

        print(f"error: job '{name_or_id}' not found", file=sys.stderr)
        sys.exit(1)


def _ambiguous_exit(name_or_id: str, matches: list[dict]) -> None:
    names = ", ".join(j.get("name", j.get("_id", "?")) for j in matches[:5])
    print(f"error: '{name_or_id}' is ambiguous — matches: {names}", file=sys.stderr)
    sys.exit(1)

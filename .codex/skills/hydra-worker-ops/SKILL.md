---
name: hydra-worker-ops
description: Start or scale Hydra workers for a domain across Docker, Kubernetes, or bare-metal using DOMAIN/API_TOKEN/REDIS_PASSWORD. Use this when operators ask to bring workers online quickly, rotate domain credentials, or produce deployment-ready worker env settings.
---

# Hydra Worker Ops

Use this skill when the user wants to:
- start workers for a domain
- scale worker count
- rotate domain worker credentials before rollout
- produce environment values for non-Docker platforms

## Primary workflow

1. Ensure `ADMIN_TOKEN` is available.
2. Run:
```bash
ADMIN_TOKEN=<admin_token> ./scripts/start-domain-workers.sh <domain> [scale]
```
3. Select backend with `WORKER_BACKEND`:
- `docker` (default): docker compose deployment
- `k8s`: updates secret + deployment env + replicas
- `bare`: prints/exports env and optionally runs `BARE_START_CMD`
- `print`: only emits env values

## Key env knobs

- `API_BASE_URL` (default `http://localhost:8000`)
- `WORKER_BACKEND=docker|k8s|bare|print`
- Kubernetes:
  - `K8S_NAMESPACE`
  - `K8S_DEPLOYMENT`
  - `K8S_SECRET_PREFIX`
- Bare-metal:
  - `BARE_START_CMD`

## Output expectations

After running, report:
- generated domain credentials (`DOMAIN/API_TOKEN/REDIS_PASSWORD` flow)
- deployment actions taken for selected backend
- scheduler worker visibility summary from `/workers/?domain=<domain>`

## Guardrails

- Do not reintroduce `WORKER_DOMAIN` or `WORKER_DOMAIN_TOKEN`.
- Keep examples consistent with `DOMAIN`, `API_TOKEN`, `REDIS_PASSWORD`.
- If rollout fails, immediately run domain diagnostics skill (`hydra-domain-triage`).

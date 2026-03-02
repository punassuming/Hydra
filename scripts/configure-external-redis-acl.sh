#!/usr/bin/env bash
set -euo pipefail

# Configure a domain-scoped worker ACL user directly on an external Redis server.
#
# Examples:
#   REDIS_URL=rediss://redis.example.com:6379 \
#   REDIS_ADMIN_USERNAME=default REDIS_ADMIN_PASSWORD=secret \
#   DOMAIN=prod ./scripts/configure-external-redis-acl.sh
#
#   REDIS_URL=redis://127.0.0.1:6379 REDIS_ADMIN_PASSWORD=secret \
#   DOMAIN=prod WORKER_PASSWORD=my_pass ./scripts/configure-external-redis-acl.sh

REDIS_URL="${REDIS_URL:-}"
REDIS_HOST="${REDIS_HOST:-}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DB="${REDIS_DB:-0}"
REDIS_TLS="${REDIS_TLS:-false}"
REDIS_ADMIN_USERNAME="${REDIS_ADMIN_USERNAME:-}"
REDIS_ADMIN_PASSWORD="${REDIS_ADMIN_PASSWORD:-}"

DOMAIN="${DOMAIN:-${1:-}}"
WORKER_USERNAME="${WORKER_USERNAME:-}"
WORKER_PASSWORD="${WORKER_PASSWORD:-}"

if ! command -v redis-cli >/dev/null 2>&1; then
  echo "redis-cli is required"
  exit 1
fi

if [[ -z "${DOMAIN}" ]]; then
  echo "DOMAIN is required (env or first arg)"
  exit 1
fi

if [[ -z "${REDIS_URL}" && -z "${REDIS_HOST}" ]]; then
  echo "Either REDIS_URL or REDIS_HOST must be set"
  exit 1
fi

if [[ -z "${REDIS_ADMIN_PASSWORD}" ]]; then
  echo "REDIS_ADMIN_PASSWORD is required"
  exit 1
fi

if [[ -z "${WORKER_USERNAME}" ]]; then
  WORKER_USERNAME="${DOMAIN}"
fi

if [[ -z "${WORKER_PASSWORD}" ]]; then
  WORKER_PASSWORD="$(openssl rand -hex 24 2>/dev/null || head -c 48 /dev/urandom | xxd -p -c 48)"
fi

cli=(redis-cli --no-auth-warning)
if [[ -n "${REDIS_URL}" ]]; then
  cli+=(-u "${REDIS_URL}")
else
  cli+=(-h "${REDIS_HOST}" -p "${REDIS_PORT}" -n "${REDIS_DB}")
fi
if [[ "${REDIS_TLS}" == "true" ]]; then
  cli+=(--tls)
fi
if [[ -n "${REDIS_ADMIN_USERNAME}" ]]; then
  cli+=(--user "${REDIS_ADMIN_USERNAME}")
fi
cli+=(-a "${REDIS_ADMIN_PASSWORD}")

key_patterns=(
  "~job_queue:${DOMAIN}:*"
  "~workers:${DOMAIN}:*"
  "~worker_heartbeats:${DOMAIN}"
  "~worker_running_set:${DOMAIN}:*"
  "~job_running:${DOMAIN}:*"
  "~worker_metrics:${DOMAIN}:*"
  "~log_stream:${DOMAIN}:*"
  "~run_events:${DOMAIN}"
  "~worker_ops:${DOMAIN}:*"
)
channel_patterns=("&log_stream:${DOMAIN}:*")
commands=(
  "+ping"
  "+exists"
  "+blpop"
  "+hset"
  "+hincrby"
  "+zadd"
  "+sadd"
  "+srem"
  "+rpush"
  "+ltrim"
  "+expire"
  "+del"
  "+publish"
)

"${cli[@]}" ACL SETUSER "${WORKER_USERNAME}" reset on ">${WORKER_PASSWORD}" \
  "${key_patterns[@]}" "${channel_patterns[@]}" "${commands[@]}" >/dev/null

echo "Configured worker ACL user for domain ${DOMAIN}"
echo "REDIS_PASSWORD=${WORKER_PASSWORD}"
echo ""
echo "Worker env example:"
echo "DOMAIN=${DOMAIN}"
echo "WORKER_REQUIRE_REDIS_ACL=true"
echo "REDIS_URL=${REDIS_URL:-redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}}"
echo "# REDIS_USERNAME is derived from DOMAIN by worker runtime"
echo "REDIS_PASSWORD=${WORKER_PASSWORD}"

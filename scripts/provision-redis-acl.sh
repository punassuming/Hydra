#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
DOMAIN_FILTER="${1:-}"

if [[ -z "${ADMIN_TOKEN}" ]]; then
  echo "ADMIN_TOKEN is required"
  echo "Usage: ADMIN_TOKEN=<admin_token> $0 [domain]"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required"
  exit 1
fi

auth_headers=(-H "x-api-key: ${ADMIN_TOKEN}" -H "Content-Type: application/json")

domains_json="$(curl -sS "${auth_headers[@]}" "${API_BASE_URL}/admin/domains?domain=prod")"
domains=()
if [[ -n "${DOMAIN_FILTER}" ]]; then
  domains=("${DOMAIN_FILTER}")
else
  while IFS= read -r d; do
    [[ -n "$d" ]] && domains+=("$d")
  done < <(printf "%s" "${domains_json}" | jq -r '.domains[].domain')
fi

if [[ "${#domains[@]}" -eq 0 ]]; then
  echo "No domains found"
  exit 0
fi

echo "Provisioning worker Redis ACL users via ${API_BASE_URL}"
for domain in "${domains[@]}"; do
  resp="$(curl -sS "${auth_headers[@]}" -X POST "${API_BASE_URL}/admin/domains/${domain}/redis_acl/rotate?domain=${domain}" -d '{}')"
  user="$(printf "%s" "${resp}" | jq -r '.worker_redis_acl.username')"
  pass="$(printf "%s" "${resp}" | jq -r '.worker_redis_acl.password')"
  if [[ -z "${user}" || "${user}" == "null" || -z "${pass}" || "${pass}" == "null" ]]; then
    echo "Failed provisioning ACL for domain ${domain}: ${resp}"
    continue
  fi
  env_file="/tmp/hydra-redis-acl-${domain}.env"
  {
    echo "WORKER_DOMAIN=${domain}"
    echo "WORKER_REQUIRE_REDIS_ACL=true"
    echo "REDIS_USERNAME=${user}"
    echo "REDIS_PASSWORD=${pass}"
  } > "${env_file}"
  echo "domain=${domain} user=${user} password=<redacted> env=${env_file}"
done

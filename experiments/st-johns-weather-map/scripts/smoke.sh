#!/usr/bin/env bash
# Truth-boundary smoke test against a running Compose stack.
#
# The point is not that endpoints respond. It is that they respond HONESTLY:
# that a live deployment never returns a fixture number, that readiness is not
# claimed without a live store, and that the catalogue is the real registry.
set -euo pipefail

API="http://127.0.0.1:${WEATHER_API_PORT:-8000}/api/experiments/weather/v0"
POINT="latitude=47.5615&longitude=-52.7126"
fails=0

check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  ok    %s\n' "$label"
  else
    printf '  FAIL  %s\n' "$label"
    fails=$((fails + 1))
  fi
}

json() { curl -fsS "$1"; }

echo "== reachability =="
check "health responds"            curl -fsS "${API}/health"
check "ready responds"             curl -fsS "${API}/ready"
check "timeline responds"          curl -fsS "${API}/timeline"

echo "== truth boundary =="
mode=$(json "${API}/point?${POINT}" | jq -r '.data_mode')
printf '  point data_mode = %s\n' "$mode"
if [[ "$mode" != "live" && "$mode" != "unavailable" && "$mode" != "mixed" ]]; then
  printf '  FAIL  a live deployment returned data_mode=%s\n' "$mode"; fails=$((fails + 1))
fi

# operational must be false on every response, without exception.
# NOTE: jq's `//` alternative operator treats `false` as falsy, so
# `.operational // "absent"` always yields "absent" for a correct false
# response - it can never observe the real value. Use has()/type instead.
operational_fails=0
for path in "health" "ready" "timeline" "layers" "catalog" "sources/status" "point?${POINT}"; do
  value=$(json "${API}/${path}" | jq -r 'if has("operational") then (.operational | tostring) else "absent" end')
  if [[ "$value" != "false" ]]; then
    printf '  FAIL  /%s reported operational=%s\n' "$path" "$value"
    fails=$((fails + 1))
    operational_fails=$((operational_fails + 1))
  fi
done
if [[ "$operational_fails" -eq 0 ]]; then
  printf '  ok    operational=false on every endpoint\n'
fi

echo "== canonical catalogue =="
count=$(json "${API}/catalog" | jq '.sources | length')
printf '  catalog sources = %s (registry has 59; 6 means the fixture catalogue is still wired)\n' "$count"
[[ "$count" -gt 6 ]] || { printf '  FAIL  catalog is still the fixture list\n'; fails=$((fails + 1)); }

# No source may report active without live evidence behind it.
actives=$(json "${API}/sources/status" | jq -r '[.statuses[] | select(.state == "active")] | length')
retrieved=$(json "${API}/sources/status" | jq -r '[.statuses[] | select(.last_retrieval != null)] | length')
printf '  active=%s with last_retrieval=%s\n' "$actives" "$retrieved"
[[ "$actives" -le "$retrieved" ]] || { printf '  FAIL  a source is active with no recorded retrieval\n'; fails=$((fails + 1)); }

echo "== fail-closed on storage outage =="
if docker compose ps --status running --services 2>/dev/null | grep -qx minio; then
  docker compose stop minio >/dev/null 2>&1
  sleep 3
  outage=$(json "${API}/point?${POINT}" | jq -r '.data_mode')
  nulls=$(json "${API}/point?${POINT}" | jq -r '[.fields[] | select(.value != null)] | length')
  docker compose start minio >/dev/null 2>&1
  printf '  outage data_mode = %s, non-null field values = %s\n' "$outage" "$nulls"
  if [[ "$outage" == "fixture" || "$nulls" -gt 0 ]]; then
    printf '  FAIL  storage outage produced values; this is the fixture fallthrough\n'; fails=$((fails + 1))
  else
    printf '  ok    outage returns unavailable with no values\n'
  fi
else
  printf '  skip  minio is not running under compose\n'
fi

echo
if [[ "$fails" -gt 0 ]]; then
  echo "smoke FAILED: ${fails} check(s)"; exit 1
fi
echo "smoke passed"

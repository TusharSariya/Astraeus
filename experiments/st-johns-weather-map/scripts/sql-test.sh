#!/usr/bin/env bash
# Prove the storage-integrity invariants against a real PostgreSQL.
#
# The mocked Python tests assert which statements the store SENDS. They cannot
# assert what the database DOES with them, and "a partial run can never become
# visible" is a property of the database, not of the caller. This spins up a
# disposable postgis container, loads both migrations in order, and runs
# infra/postgres/tests/publication_invariants.sql against them.
set -euo pipefail

CONTAINER="${WEATHER_SQL_TEST_CONTAINER:-wx-sql-proof}"
IMAGE="ghcr.io/baosystems/postgis:17-3.5"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "starting disposable postgres..."
docker run -d --name "$CONTAINER" \
  -e POSTGRES_PASSWORD=proof -e POSTGRES_DB=weather -e POSTGRES_USER=weather \
  "$IMAGE" >/dev/null

# The postgis entrypoint starts a TEMPORARY server to run its own init, then
# shuts it down and restarts for real. pg_isready happily passes against that
# temporary server, and the next command then dies with "the database system is
# shutting down". Require several consecutive successful queries so a restart
# in the middle resets the count.
ready=0
for _ in $(seq 1 90); do
  if docker exec "$CONTAINER" psql -U weather -d weather -tAc 'SELECT 1' >/dev/null 2>&1; then
    ready=$((ready + 1))
    [ "$ready" -ge 4 ] && break
  else
    ready=0
  fi
  sleep 1
done
if [ "$ready" -lt 4 ]; then
  echo "postgres never became stably available" >&2
  docker logs "$CONTAINER" 2>&1 | tail -20 >&2
  exit 1
fi

# Migrations load in filename order, exactly as the compose init directory does.
for migration in "$ROOT"/infra/postgres/init/*.sql; do
  echo "loading $(basename "$migration")"
  docker cp "$migration" "$CONTAINER:/tmp/migration.sql" >/dev/null
  docker exec "$CONTAINER" psql -U weather -d weather -v ON_ERROR_STOP=1 -q -f /tmp/migration.sql
done

# Every proof in the directory, in filename order, each in its own psql run.
# A proof states its own final assertion; reaching the end of the file is not
# the same as having asserted anything, so the sentinel is required.
for proof in "$ROOT"/infra/postgres/tests/*.sql; do
  name="$(basename "$proof")"
  echo
  echo "running $name"
  docker cp "$proof" "$CONTAINER:/tmp/proof.sql" >/dev/null

  # Captured rather than piped: on failure the whole psql transcript is the
  # useful artifact, and a pipeline would discard it.
  output=$(docker exec "$CONTAINER" psql -U weather -d weather -v ON_ERROR_STOP=1 -f /tmp/proof.sql 2>&1) || {
    echo "$output"
    echo "SQL INVARIANTS FAILED: $name"
    exit 1
  }

  echo "$output" | grep -E "PASS|FAIL|ERROR" | sed -E 's/^psql:[^ ]+ (NOTICE:  )?//' || true

  if ! echo "$output" | grep -qE "ALL [A-Z ]+ INVARIANTS HOLD"; then
    echo "$output"
    echo "SQL INVARIANTS FAILED: $name did not reach its final assertion"
    exit 1
  fi
done

echo
echo "all storage invariants hold"

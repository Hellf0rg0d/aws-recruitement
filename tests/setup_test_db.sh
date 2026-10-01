#!/usr/bin/env bash
# Starts a THROWAWAY Postgres in Docker and builds the template database the tests clone for every test.
# Nothing here can reach Supabase: the container listens on 127.0.0.1 only and has its own empty data.
#   VISS_TEST_PG_NAME (default viss-race-test-pg)   VISS_TEST_PG_PORT (default 55432)
# Re-running is safe: an existing container is reused, and the template is rebuilt from supabase_schema.sql.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${VISS_TEST_PG_NAME:-viss-race-test-pg}"
PORT="${VISS_TEST_PG_PORT:-55432}"

if ! docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
  docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=test -p "127.0.0.1:${PORT}:5432" postgres:15-alpine >/dev/null
fi
until docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1; do sleep 0.5; done

# The test template can only be dropped/recreated while no test database is being cloned from it.
docker exec "$NAME" psql -U postgres -q -c "DROP DATABASE IF EXISTS viss_template WITH (FORCE)" -c "CREATE DATABASE viss_template"
docker exec -i "$NAME" psql -U postgres -d viss_template -q -v ON_ERROR_STOP=1 < supabase_schema.sql 2>&1 | grep -v NOTICE || true
echo "Test Postgres ready: container=$NAME  port=$PORT  (stop with: docker stop $NAME)"

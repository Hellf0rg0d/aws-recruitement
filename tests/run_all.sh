#!/usr/bin/env bash
# Runs every suite against the project's current code. Prerequisites: see tests/README.md
#   VISS_TEST_PG_PORT=55432 (default)
# Baselines (optional, should FAIL - proves the tests detect the original bugs):
#   ORIG_SERVER_PY=... ORIG_COMMAND_CENTER_PY=... ORIG_INDEX_HTML=... tests/run_all.sh baseline
set -uo pipefail
cd "$(dirname "$0")"
rc=0
if [ "${1:-}" = "baseline" ]; then
  echo "== BASELINE (pre-fix code): failures are EXPECTED =="
  [ -n "${ORIG_SERVER_PY:-}" ] && SERVER=orig python3 -m pytest -q -p no:cacheprovider test_server_races.py test_server_resilience.py
  [ -n "${ORIG_COMMAND_CENTER_PY:-}" ] && CC=orig python3 -m pytest -q -p no:cacheprovider test_command_center.py
  [ -n "${ORIG_INDEX_HTML:-}" ] && (cd client && INDEX_HTML="$ORIG_INDEX_HTML" node client_tests.js)
  exit 0
fi
echo "== server + command center (pytest) =="
python3 -m pytest -q -p no:cacheprovider test_server_races.py test_server_resilience.py test_command_center.py || rc=1
echo "== client (jsdom) =="
(cd client && { [ -d node_modules ] || npm install --silent --no-audit --no-fund; } && node client_tests.js | tee /tmp/viss_client_tests.out; grep -q " 0 failed" /tmp/viss_client_tests.out) || rc=1
exit $rc

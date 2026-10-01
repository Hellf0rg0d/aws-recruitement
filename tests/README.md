# VISS-2026 tests

Three suites that reproduce the race conditions and the "unresponsive" failure modes, and verify the fixes.
They are written so each test **fails on the pre-fix code and passes on the fixed code**.

| Suite | What it covers | Count |
|---|---|---|
| `test_server_races.py` | login / save / proctoring / finish / auto-submit worker / admin-unlock interleavings, atomic file writes. Timing-sensitive cases sweep many request schedules. | 56 |
| `test_server_resilience.py` | DB failure → 503 (not fake success/logout), pool exhaustion fails fast, health check sees a wedged DB, challenges cache, exam-end finish surge, body-size cap, pool supervisor, schema check, real startup/shutdown | 10 |
| `test_command_center.py` | Command Center reset is atomic; force-submit never grades a stale answer set | 7 |
| `client/client_tests.js` | The real `index.html` in jsdom: key-repeat flood, bounded logs, last-answer-before-finish, single finish, ordered saves, retries, reconnect, server-side lock | 11 |

## Safety model

* **Nothing here can reach Supabase.** Every test runs a *copy* of `server.py` / `command_center.py` from `tests/.scratch/`
  (a directory with no `.env`), forces `DATABASE_URL` to `127.0.0.1`, and asserts it before doing anything.
* Each server test gets its own database cloned from a template inside a throwaway Docker Postgres, so tests are isolated and can run in parallel.
* A small latency shim sleeps before each DB round trip (default 30 ms, like a remote pooler) so races interleave realistically.

## Run

```bash
pip install -r tests/requirements-test.txt            # + the app's requirements.txt
tests/setup_test_db.sh                                 # Docker Postgres on 127.0.0.1:55432 (VISS_TEST_PG_PORT / VISS_TEST_PG_NAME to change)
tests/run_all.sh                                       # server + command center + client (needs node for the client suite)
```

Individual pieces:

```bash
cd tests
python3 -m pytest -q -p no:cacheprovider test_server_races.py          # ~45 s
python3 -m pytest -q -p no:cacheprovider test_server_resilience.py     # ~10 s
python3 -m pytest -q -p no:cacheprovider test_command_center.py
(cd client && npm install && node client_tests.js)
```

## Proving the tests catch the original bugs (baseline)

Extract the pre-fix files from the original zip and point the tests at them; **failures are the expected result**:

```bash
unzip -j VISS-2026.zip server.py command_center.py index.html -d /tmp/viss-orig
ORIG_SERVER_PY=/tmp/viss-orig/server.py ORIG_COMMAND_CENTER_PY=/tmp/viss-orig/command_center.py \
ORIG_INDEX_HTML=/tmp/viss-orig/index.html  tests/run_all.sh baseline
```

Last measured baseline: server races 25–29 of 56 schedules fail (varies with timing, because the sweeps use real sleeps),
resilience 10 of 10 fail, command center 3 of 7 fail, client 10 of 11 fail (the one that passes is a regression guard).
Fixed code: everything passes.

## Notes

* `tests/.scratch/` and `tests/client/node_modules/` are generated; both are git-ignored.
* The container name/port are only used by these tests. `docker stop viss-race-test-pg` when finished.
* Do **not** point these tests at a shared or real database: they `CREATE`/`DROP` databases and truncate tables.

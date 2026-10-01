"""
Race-condition reproductions for VISS-2026 server.py.

Runs a COPY of the server's ASGI app in-process against a THROWAWAY local Postgres
(127.0.0.1:$VISS_TEST_PG_PORT, schema from supabase_schema.sql). Never touches Supabase.
See tests/README.md. Start the database first:  tests/setup_test_db.sh

Usage:  SERVER=fixed pytest -q tests/        (default: the project's server.py)
        SERVER=orig ORIG_SERVER_PY=/path/to/original/server.py pytest -q tests/   (baseline: should FAIL)
A latency shim sleeps before every DB round-trip so concurrent requests
interleave the way they do against a remote pooler.
"""
import asyncio, contextlib, importlib.util, json, os, shutil, sys, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRATCH = HERE / ".scratch"; SCRATCH.mkdir(exist_ok=True)
PG_PORT = os.environ.get("VISS_TEST_PG_PORT", "55432")
ADMIN_DSN = f"postgresql://postgres:test@127.0.0.1:{PG_PORT}/postgres"
LOCAL_DSN = f"postgresql://postgres:test@127.0.0.1:{PG_PORT}/viss_template"   # placeholder; real DB is created per harness()
LATENCY = float(os.environ.get("DB_LATENCY", "0.03"))

# Hard safety rails: never let the server see a real DSN.
os.environ["DATABASE_URL"] = LOCAL_DSN
os.environ["DB_PATH"] = str(SCRATCH / "scratch_submissions.json")
os.environ.pop("SUPABASE_URL", None); os.environ.pop("SUPABASE_KEY", None)

import asyncpg, httpx
import pytest

WHICH = os.environ.get("SERVER", "fixed")
# Tests always run a COPY of server.py from a scratch directory that has no .env, so nothing in the test path
# can read the project's .env (which points at the live database). DATABASE_URL is forced to the local container above.
if WHICH == "orig":
    if not os.environ.get("ORIG_SERVER_PY"):
        pytest.skip("SERVER=orig needs ORIG_SERVER_PY=<path to the pre-fix server.py> (e.g. unzip VISS-2026.zip server.py)", allow_module_level=True)
    _src_dir = SCRATCH / "orig_src"; _srcfile = Path(os.environ["ORIG_SERVER_PY"])
else:
    _src_dir = SCRATCH / "fixed_src"; _srcfile = ROOT / "server.py"
_src_dir.mkdir(exist_ok=True)
shutil.copy(_srcfile, _src_dir / "server.py")
shutil.copy(ROOT / "challenges.json", _src_dir / "challenges.json")
SRC = _src_dir / "server.py"
assert not (SRC.parent / ".env").exists(), "scratch copy must not contain a .env"
_real_sleep = asyncio.sleep

def load_server():
    spec = importlib.util.spec_from_file_location(f"viss_server_{WHICH}", SRC)
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert f"127.0.0.1:{PG_PORT}" in mod.DATABASE_URL, "refusing to run: DSN is not the local throwaway DB"
    mod.CLASSROOM_DB_FILE = SCRATCH / "scratch_classroom.json"
    mod.LOCAL_DB_FILE = SCRATCH / "scratch_submissions.json"
    return mod

class LatConn:
    def __init__(self, c): self._c = c
    def __getattr__(self, n):
        a = getattr(self._c, n)
        if n in ("fetch", "fetchrow", "fetchval", "execute"):
            async def w(*x, **k):
                await _real_sleep(LATENCY)
                return await a(*x, **k)
            return w
        return a
class LatAcquire:
    def __init__(self, p, timeout=None): self._cm = p.acquire(timeout=timeout)
    async def __aenter__(self): return LatConn(await self._cm.__aenter__())
    async def __aexit__(self, *e): return await self._cm.__aexit__(*e)
class LatPool:
    def __init__(self, p): self._p = p
    def acquire(self, timeout=None): return LatAcquire(self._p, timeout)
    async def close(self): await self._p.close()

@contextlib.asynccontextmanager
async def harness(latency=None, pool_max=25):
    global LATENCY
    if latency is not None: LATENCY = latency
    mod = load_server()
    dbname = "viss_t_" + uuid.uuid4().hex[:10]
    admin = await asyncpg.connect(ADMIN_DSN)
    await admin.execute(f'CREATE DATABASE {dbname} TEMPLATE viss_template')
    dsn = f"postgresql://postgres:test@127.0.0.1:{PG_PORT}/{dbname}"
    raw = await asyncpg.create_pool(dsn, min_size=2, max_size=pool_max, statement_cache_size=0)
    for p in (mod.LOCAL_DB_FILE, mod.CLASSROOM_DB_FILE):
        if p.exists(): p.unlink()
    mod.LOCAL_CANDIDATES.clear(); mod.LOCAL_SESSIONS.clear(); mod.LOCAL_ANSWERS.clear()
    mod.DB_POOL = LatPool(raw)
    mod.__test_dsn__ = dsn
    transport = httpx.ASGITransport(app=mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as cl:
        try:
            yield mod, cl, raw
        finally:
            mod.DB_POOL = None
            await raw.close()
            await admin.execute(f'DROP DATABASE IF EXISTS {dbname} WITH (FORCE)')
            await admin.close()

async def seed(raw, email="a@x.edu", sid=None, status="in_progress", fe=0, ts=0, minutes_ago=5, **kw):
    sid = sid or str(uuid.uuid4())
    await raw.execute(
        """INSERT INTO candidates (email,name,session_id,start_time,status,fullscreen_exits,tab_switches,
                                   challenge_id,set_name)
           VALUES ($1,'T',$2,$3,$4::candidate_status_enum,$5,$6,'set_a','SET A')""",
        email, sid, datetime.now(timezone.utc) - timedelta(minutes=minutes_ago), status, fe, ts)
    return sid

async def row(raw, sid):
    return dict(await raw.fetchrow("SELECT * FROM candidates WHERE session_id=$1", sid))

def H(sid): return {"x-session-id": sid}
OFFSETS = [0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.1, 0.13]
async def after(delay, coro):
    await _real_sleep(delay)
    return await coro
def run(coro): return asyncio.run(coro)

# ------------------------------------------------------------------ S1
def test_S1_concurrent_login_same_email_yields_one_session():
    async def go():
        async with harness() as (mod, cl, raw):
            body = {"email": "dup@x.edu", "name": "Dup", "usn": "1", "branch_sem": "CS"}
            rs = await asyncio.gather(*[cl.post("/api/login", json=body) for _ in range(6)])
            sids = {r.json()["session_id"] for r in rs if r.status_code == 200}
            sets = {r.json()["set_name"] for r in rs if r.status_code == 200}
            n = await raw.fetchval("SELECT count(*) FROM candidates WHERE email='dup@x.edu'")
            assert n == 1
            assert len(sids) == 1, f"{len(sids)} different session ids issued for one candidate"
            assert len(sets) == 1, f"candidate was assigned several sets: {sets}"
            # every issued session must exist in the DB (no phantom local-only sessions)
            for s in sids:
                assert await raw.fetchval("SELECT count(*) FROM candidates WHERE session_id=$1", s) == 1
    run(go())

# ------------------------------------------------------------------ S2
@pytest.mark.parametrize("off", OFFSETS)
@pytest.mark.parametrize("save_first", [True, False])
def test_S2_save_cannot_unlock_or_roll_back_a_proctoring_lock(off, save_first):
    async def go():
        async with harness() as (mod, cl, raw):
            sid = await seed(raw, fe=2)
            save = cl.post("/api/save", headers=H(sid), json={
                "question_id": "q1", "selected_option": "a",
                "telemetry": {"fullscreen_exits": 2, "tab_switches": 0, "copy_attempts": 0, "integrity_risk": "MEDIUM / SUSPICIOUS"}})
            procto = cl.post("/api/proctoring", headers=H(sid), json={"fullscreen_exits": 3, "tab_switches": 0, "integrity_risk": "HIGH / FLAGGED"})
            a, b = (save, after(off, procto)) if save_first else (procto, after(off, save))
            await asyncio.gather(a, b)
            r = await row(raw, sid)
            assert r["fullscreen_exits"] == 3, f"strike counter rolled back to {r['fullscreen_exits']}"
            assert r["status"] == "locked", f"candidate with 3 exits is '{r['status']}'"
            assert r["integrity_risk"].startswith("HIGH"), f"risk downgraded to {r['integrity_risk']}"
    run(go())

# ------------------------------------------------------------------ S3
def test_S3_out_of_order_beacons_never_decrease_counters():
    async def go():
        async with harness() as (mod, cl, raw):
            sid = await seed(raw)
            # beacon carrying exit #2 and a stale beacon carrying exit #1 race each other
            await asyncio.gather(
                cl.post("/api/proctoring", headers=H(sid), json={"fullscreen_exits": 2, "tab_switches": 1, "paste_attempts": 4}),
                cl.post("/api/proctoring", headers=H(sid), json={"fullscreen_exits": 1, "tab_switches": 0, "paste_attempts": 1}))
            r = await row(raw, sid)
            assert (r["fullscreen_exits"], r["tab_switches"], r["paste_attempts"]) == (2, 1, 4), \
                f"counters regressed to fe={r['fullscreen_exits']} ts={r['tab_switches']} paste={r['paste_attempts']}"
    run(go())

# ------------------------------------------------------------------ S4
def test_S4_concurrent_finish_submits_once():
    async def go():
        async with harness() as (mod, cl, raw):
            sid = await seed(raw)
            await raw.execute("INSERT INTO answers (candidate_email,question_id,selected_option) VALUES ('a@x.edu','q1','a')")
            rs = await asyncio.gather(*[cl.post("/api/finish", headers=H(sid)) for _ in range(5)])
            assert all(r.status_code == 200 for r in rs), [r.status_code for r in rs]
            if hasattr(mod, "backup_writer"): await mod.backup_writer.flush()   # backups are batched off-loop
            backups = json.loads(mod.LOCAL_DB_FILE.read_text()) if mod.LOCAL_DB_FILE.exists() else []
            assert len(backups) == 1, f"{len(backups)} backup records written for a single submission"
    run(go())

# ------------------------------------------------------------------ S5
@pytest.mark.parametrize("off", OFFSETS)
@pytest.mark.parametrize("finish_first", [True, False])
def test_S5_finish_cannot_overwrite_a_concurrent_lock(off, finish_first):
    async def go():
        async with harness() as (mod, cl, raw):
            sid = await seed(raw, fe=2)
            fin = cl.post("/api/finish", headers=H(sid))
            pro = cl.post("/api/proctoring", headers=H(sid), json={"fullscreen_exits": 3})
            a, b = (fin, after(off, pro)) if finish_first else (pro, after(off, fin))
            rs = await asyncio.gather(a, b)
            r = await row(raw, sid)
            assert not (r["status"] == "submitted" and r["fullscreen_exits"] >= 3), \
                f"3 recorded strikes but status is '{r['status']}' - the lock was overwritten by finish"
            fin_resp = rs[0] if finish_first else rs[1]
            if fin_resp.status_code == 200:   # told the candidate "submitted" -> DB must agree
                assert r["status"] == "submitted", f"finish said 200 but status is {r['status']}"
    run(go())

# ------------------------------------------------------------------ S6
@pytest.mark.parametrize("off", OFFSETS)
def test_S6_auto_submit_worker_cannot_overwrite_a_concurrent_lock(off):
    async def go():
        async with harness() as (mod, cl, raw):
            sid = await seed(raw, fe=2, minutes_ago=30)          # timer already expired
            await raw.execute("INSERT INTO answers (candidate_email,question_id,selected_option) VALUES ('a@x.edu','q1','a')")
            async def fast_sleep(d, *a, **k): return await _real_sleep(0.01 if d == 15 else d)
            asyncio.sleep = fast_sleep
            try:
                worker = asyncio.create_task(mod.auto_submit_expired_candidates_worker())
                await after(off, cl.post("/api/proctoring", headers=H(sid), json={"fullscreen_exits": 3}))
                await _real_sleep(0.6)
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError): await worker
            finally:
                asyncio.sleep = _real_sleep
            r = await row(raw, sid)
            assert not (r["status"] == "submitted" and r["fullscreen_exits"] >= 3), \
                f"3 recorded strikes but status is '{r['status']}' - the lock was overwritten by the worker"
    run(go())

# ------------------------------------------------------------------ S7
def test_S7_stale_save_after_admin_unlock_does_not_relock():
    async def go():
        async with harness() as (mod, cl, raw):
            sid = await seed(raw, status="unlocked", fe=3, ts=1)
            st = await cl.get("/api/state", headers=H(sid))          # candidate reloads -> counters reset
            assert st.json()["status"] == "in_progress"
            # in-flight save from the *pre-reload* page still carries the old counters
            await cl.post("/api/save", headers=H(sid), json={
                "question_id": "q1", "selected_option": "a",
                "telemetry": {"fullscreen_exits": 3, "tab_switches": 1}})
            r = await row(raw, sid)
            assert r["status"] == "in_progress" and r["fullscreen_exits"] == 0, \
                f"stale pre-reload save re-locked the freshly unlocked candidate: {r['status']} fe={r['fullscreen_exits']}"
    run(go())

# ------------------------------------------------------------------ S8
def test_S8_proctoring_does_not_resurrect_a_submitted_candidate():
    async def go():
        async with harness() as (mod, cl, raw):
            sid = await seed(raw, fe=1)
            assert (await cl.post("/api/finish", headers=H(sid))).status_code == 200
            await cl.post("/api/proctoring", headers=H(sid), json={"fullscreen_exits": 3, "tab_switches": 3})
            r = await row(raw, sid)
            assert r["status"] == "submitted", f"submitted candidate flipped to '{r['status']}' by a late beacon"
    run(go())

# ------------------------------------------------------------------ S9
def test_S9_local_json_persistence_is_atomic(tmp_path):
    mod = load_server()
    mod.CLASSROOM_DB_FILE = tmp_path / "c.json"
    mod.LOCAL_CANDIDATES.clear(); mod.LOCAL_CANDIDATES["x@y"] = {"email": "x@y"}
    import builtins, os as _os
    real_open = builtins.open
    seen = []
    def spy(f, mode="r", *a, **k):
        if str(f) == str(mod.CLASSROOM_DB_FILE) and "w" in mode: seen.append(f)
        return real_open(f, mode, *a, **k)
    builtins.open = spy
    try: mod.save_local_classroom_db()
    finally: builtins.open = real_open
    assert not seen, "state file is truncated in place; a crash mid-write corrupts the whole classroom DB"

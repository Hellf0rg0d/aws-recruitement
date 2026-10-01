"""Command Center admin actions vs. candidate traffic. CC=orig|fixed (scratch copies, no .env). Local throwaway DB only."""
import asyncio, importlib.util, json, os, sys
from pathlib import Path
import httpx, pytest
import shutil, pytest
from test_server_races import harness, seed, H, run, after, _real_sleep, HERE, ROOT, SCRATCH

CC = os.environ.get("CC", "fixed")        # CC=orig + ORIG_COMMAND_CENTER_PY=<pre-fix file> runs the baseline (should FAIL)
if CC == "orig":
    if not os.environ.get("ORIG_COMMAND_CENTER_PY"):
        pytest.skip("CC=orig needs ORIG_COMMAND_CENTER_PY=<path to the pre-fix command_center.py>", allow_module_level=True)
    _cc_file = Path(os.environ["ORIG_COMMAND_CENTER_PY"])
else:
    _cc_file = ROOT / "command_center.py"
_cc_dir = SCRATCH / f"cc_{CC}"; _cc_dir.mkdir(exist_ok=True)       # scratch copy: no .env can be read
shutil.copy(_cc_file, _cc_dir / "command_center.py"); shutil.copy(ROOT / "challenges.json", _cc_dir / "challenges.json")
CC_SRC = _cc_dir / "command_center.py"
assert not (CC_SRC.parent / ".env").exists()

def load_cc():
    spec = importlib.util.spec_from_file_location(f"cc_{CC}", CC_SRC)
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m)
    return m

CH = json.loads((ROOT / "challenges.json").read_text())["challenges"]["set_a"]["questions"]
A1, A2 = CH[0]["answer"], CH[1]["answer"]

class FailOnCandidateUpdate:
    """Pool whose connections fail any 'UPDATE candidates' - simulates the DB dropping mid-reset."""
    def __init__(self, inner): self._i = inner
    def acquire(self, timeout=None):
        outer = self
        class Ctx:
            def __init__(s): s.cm = outer._i.acquire(timeout=timeout)
            async def __aenter__(s):
                c = await s.cm.__aenter__()
                class P:
                    def __getattr__(p, n):
                        a = getattr(c, n)
                        if n == "execute":
                            async def ex(q, *args, **k):
                                if "UPDATE candidates" in q: raise RuntimeError("connection lost mid-reset")
                                return await a(q, *args, **k)
                            return ex
                        return a
                return P()
            async def __aexit__(s, *e): return await s.cm.__aexit__(*e)
        return Ctx()

def test_CC1_reset_is_all_or_nothing():
    async def go():
        async with harness() as (mod, cl, raw):
            cc = load_cc(); cc.DB_POOL = FailOnCandidateUpdate(mod.DB_POOL)
            sid = await seed(raw, email="r@x.edu")
            await raw.execute("INSERT INTO answers (candidate_email,question_id,selected_option) VALUES ('r@x.edu','q1','a'),('r@x.edu','q2','b')")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=cc.app), base_url="http://cc") as ccl:
                r = await ccl.post("/api/candidate/r@x.edu/reset")
            n = await raw.fetchval("SELECT count(*) FROM answers WHERE candidate_email='r@x.edu'")
            assert r.status_code == 500
            assert n == 2, f"reset failed half-way yet {2 - n} answer(s) were already deleted (not atomic)"
    run(go())

@pytest.mark.parametrize("off", [0, 0.02, 0.04, 0.06, 0.08, 0.1])
def test_CC2_force_submit_never_grades_a_stale_answer_set(off):
    async def go():
        async with harness() as (mod, cl, raw):
            cc = load_cc(); cc.DB_POOL = mod.DB_POOL
            sid = await seed(raw, email="f@x.edu")
            await raw.execute("INSERT INTO answers (candidate_email,question_id,selected_option) VALUES ('f@x.edu',$1,$2)", "q1", A1)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=cc.app), base_url="http://cc") as ccl:
                save = cl.post("/api/save", headers=H(sid), json={"question_id": "q2", "selected_option": A2})
                force = ccl.post("/api/candidate/f@x.edu/force-submit")
                s, f = await asyncio.gather(save, after(off, force))
            row = dict(await raw.fetchrow("SELECT status, score FROM candidates WHERE session_id=$1", sid))
            answers = {r[0]: r[1] for r in await raw.fetch("SELECT question_id, selected_option FROM answers WHERE candidate_email='f@x.edu'")}
            expected = sum(1 for q in CH if answers.get(q["id"], "").strip().lower() == str(q["answer"]).strip().lower())
            assert f.status_code == 200 and row["status"] == "submitted"
            assert row["score"] == expected, f"score {row['score']} but the stored answers are worth {expected} (answer saved={s.status_code}) - graded a stale snapshot"
    run(go())

import os
import sys
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("CommandCenter")

REPO_ROOT = Path(__file__).resolve().parent

# Load .env file
def load_env():
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v

load_env()

def resolve_database_url(url: str) -> str:
    if not url:
        return ""
    # Transform direct supabase.co URL to IPv4 connection pooler URL if needed
    if "supabase.co" in url and "pooler.supabase.com" not in url:
        import re
        match = re.search(r"://([^:]+):([^@]+)@db\.([a-z0-9]+)\.supabase\.co:5432/(.+)", url)
        if match:
            user, pwd, ref, db = match.groups()
            pooler_user = f"{user}.{ref}"
            return f"postgresql://{pooler_user}:{pwd}@aws-0-ap-southeast-1.pooler.supabase.com:5432/{db}"
    return url

# Load challenges configuration for scoring & audit
def load_challenges():
    c_path = REPO_ROOT / "challenges.json"
    if c_path.exists():
        with open(c_path, "r") as f:
            return json.load(f)
    return {"challenges": {}}

CHALLENGES_DATA = load_challenges()

DB_POOL: Optional[asyncpg.Pool] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global DB_POOL
    raw_url = os.environ.get("DATABASE_URL", "")
    db_url = resolve_database_url(raw_url)
    if not db_url:
        logger.error("[DATABASE] DATABASE_URL is not configured in .env!")
    else:
        try:
            DB_POOL = await asyncpg.create_pool(
                dsn=db_url,
                min_size=1,
                max_size=10,
                timeout=10.0,
                statement_cache_size=0
            )
            logger.info("[DATABASE] Command Center successfully connected to Supabase PostgreSQL Pool!")
        except Exception as e:
            logger.error(f"[DATABASE] Connection error: {e}")
    yield
    if DB_POOL:
        await DB_POOL.close()
        logger.info("[DATABASE] Supabase PostgreSQL pool closed.")

app = FastAPI(
    title="AWS Student Builder Group — Proctoring Command Center",
    description="Real-time live classroom proctoring, candidate tracking, and security administration console.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Request Models
class ExtendTimeRequest(BaseModel):
    seconds: Optional[int] = 300 # Default +5 minutes

# Helpers
def parse_iso_datetime(dt_val: Any) -> datetime:
    if not dt_val:
        return datetime.now(timezone.utc)
    if isinstance(dt_val, datetime):
        return dt_val if dt_val.tzinfo else dt_val.replace(tzinfo=timezone.utc)
    if isinstance(dt_val, (int, float)):
        return datetime.fromtimestamp(dt_val, tz=timezone.utc)
    try:
        dt_str = str(dt_val).replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)

def calculate_time_remaining(start_time_raw: Any, duration_seconds: int = 1500) -> int:
    start_dt = parse_iso_datetime(start_time_raw)
    now = datetime.now(timezone.utc)
    elapsed = int((now - start_dt).total_seconds())
    return max(0, duration_seconds - elapsed)

def get_challenge_set(challenge_id: str):
    c_key = (challenge_id or "set_a").lower().strip()
    challenges = CHALLENGES_DATA.get("challenges", {})
    if "set_b" in c_key:
        return challenges.get("set_b", challenges.get("set_a", {}))
    elif "set_c" in c_key:
        return challenges.get("set_c", challenges.get("set_a", {}))
    return challenges.get("set_a", {})

# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/health")
@app.get("/api/health")
async def health_check():
    connected = False
    latency_ms = None
    if DB_POOL:
        t0 = datetime.now(timezone.utc)
        try:
            async with DB_POOL.acquire() as conn:
                await conn.fetchval("SELECT 1")
            latency_ms = round((datetime.now(timezone.utc) - t0).total_seconds() * 1000, 1)
            connected = True
        except Exception as e:
            logger.error(f"Health ping error: {e}")
    return {
        "status": "healthy" if connected else "degraded",
        "service": "AWS Classroom Proctor Command Center",
        "database_connected": connected,
        "database_latency_ms": latency_ms,
        "active_pool": bool(DB_POOL)
    }

@app.get("/api/candidates")
async def get_all_candidates():
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")

    try:
        async with DB_POOL.acquire() as conn:
            # 1. Fetch all candidates
            candidates_query = """
                SELECT 
                    id, email, name, usn, branch_sem, session_id,
                    start_time, duration_seconds, challenge_id, set_name,
                    status, score, total_possible, integrity_risk,
                    device, fullscreen_exits, tab_switches, copy_attempts,
                    paste_attempts, ctrl_cmd_attempts, text_selection_attempts,
                    current_question, submitted_at, created_at
                FROM candidates
                ORDER BY 
                    CASE 
                        WHEN status = 'locked' THEN 1
                        WHEN status = 'in_progress' THEN 2
                        WHEN status = 'unlocked' THEN 3
                        WHEN status = 'submitted' THEN 4
                        ELSE 5
                    END,
                    score DESC,
                    start_time ASC;
            """
            c_rows = await conn.fetch(candidates_query)

            # 2. Fetch all answers
            a_rows = await conn.fetch("""
                SELECT candidate_email, question_id, selected_option, updated_at
                FROM answers
                ORDER BY updated_at ASC;
            """)

        answers_by_email: Dict[str, List[Dict[str, Any]]] = {}
        for a in a_rows:
            answers_by_email.setdefault(a["candidate_email"], []).append({
                "question_id": a["question_id"],
                "selected_option": a["selected_option"],
                "updated_at": a["updated_at"].isoformat() if a["updated_at"] else None
            })

        results = []
        for c in c_rows:
            c_dict = dict(c)
            email = c_dict["email"]
            c_answers = answers_by_email.get(email, [])
            
            # Format timestamps
            if c_dict.get("start_time"):
                c_dict["start_time_iso"] = c_dict["start_time"].isoformat()
            if c_dict.get("submitted_at"):
                c_dict["submitted_at_iso"] = c_dict["submitted_at"].isoformat()
            if c_dict.get("created_at"):
                c_dict["created_at_iso"] = c_dict["created_at"].isoformat()

            # Time remaining calculation
            duration = c_dict.get("duration_seconds") or 1500
            rem_sec = calculate_time_remaining(c_dict.get("start_time"), duration)
            c_dict["seconds_remaining"] = rem_sec
            c_dict["time_remaining_formatted"] = f"{rem_sec // 60:02d}:{rem_sec % 60:02d}"

            # Answers progress
            total_questions = 15
            answered_count = len(c_answers)
            c_dict["answered_count"] = answered_count
            c_dict["total_questions"] = total_questions
            c_dict["progress_pct"] = round((answered_count / total_questions) * 100) if total_questions else 0
            c_dict["answered_qids"] = [a["question_id"] for a in c_answers]
            c_dict["answers_map"] = {a["question_id"]: a["selected_option"] for a in c_answers}
            c_dict["latest_answer"] = c_answers[-1] if c_answers else None

            # Current question fallback
            if not c_dict.get("current_question") or c_dict["current_question"] == "general":
                c_dict["current_question"] = c_answers[-1]["question_id"] if c_answers else "q1"

            results.append(c_dict)

        return {
            "candidates": results,
            "total_count": len(results),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/candidate/{email}/audit")
async def get_candidate_audit(email: str):
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")

    clean_email = email.strip().lower()
    try:
        async with DB_POOL.acquire() as conn:
            cand = await conn.fetchrow("SELECT * FROM candidates WHERE email = $1", clean_email)
            if not cand:
                raise HTTPException(status_code=404, detail="Candidate not found.")
            
            ans_rows = await conn.fetch("""
                SELECT question_id, selected_option, updated_at
                FROM answers
                WHERE candidate_email = $1
                ORDER BY updated_at ASC;
            """, clean_email)

        cand_dict = dict(cand)
        answers_map = {r["question_id"]: r["selected_option"] for r in ans_rows}
        answers_timings = {r["question_id"]: (r["updated_at"].isoformat() if r["updated_at"] else None) for r in ans_rows}

        # Build detailed question audit sheet
        ch_set = get_challenge_set(cand_dict.get("challenge_id", "set_a"))
        questions_audit = []
        raw_questions = ch_set.get("questions", [])

        calculated_score = 0
        for idx, q in enumerate(raw_questions, start=1):
            qid = q.get("id")
            correct_opt = str(q.get("answer") or q.get("correct") or "").strip().lower()
            selected_opt = str(answers_map.get(qid) or "").strip().lower()

            is_answered = bool(selected_opt)
            is_correct = False
            if is_answered and correct_opt and selected_opt == correct_opt:
                is_correct = True
                calculated_score += 1

            questions_audit.append({
                "number": idx,
                "id": qid,
                "heading": q.get("heading") or f"Question {idx}",
                "category": q.get("category", "General"),
                "text": q.get("text", ""),
                "image": q.get("image"),
                "code": q.get("code"),
                "options": q.get("options", []),
                "correct_option": correct_opt,
                "selected_option": selected_opt or None,
                "is_answered": is_answered,
                "is_correct": is_correct,
                "answered_at": answers_timings.get(qid)
            })

        duration = cand_dict.get("duration_seconds") or 1500
        rem_sec = calculate_time_remaining(cand_dict.get("start_time"), duration)

        return {
            "candidate": {
                "name": cand_dict.get("name"),
                "email": cand_dict.get("email"),
                "usn": cand_dict.get("usn"),
                "branch_sem": cand_dict.get("branch_sem"),
                "set_name": cand_dict.get("set_name", "SET A"),
                "challenge_id": cand_dict.get("challenge_id", "set_a"),
                "status": cand_dict.get("status"),
                "score": cand_dict.get("score") if cand_dict.get("status") == "submitted" else calculated_score,
                "total_possible": len(raw_questions),
                "seconds_remaining": rem_sec,
                "fullscreen_exits": cand_dict.get("fullscreen_exits", 0),
                "tab_switches": cand_dict.get("tab_switches", 0),
                "copy_attempts": cand_dict.get("copy_attempts", 0),
                "current_question": cand_dict.get("current_question", "q1"),
                "device": cand_dict.get("device"),
                "integrity_risk": cand_dict.get("integrity_risk", "LOW / CLEAN"),
                "start_time": cand_dict["start_time"].isoformat() if cand_dict.get("start_time") else None,
                "submitted_at": cand_dict["submitted_at"].isoformat() if cand_dict.get("submitted_at") else None,
            },
            "questions": questions_audit,
            "calculated_score": calculated_score,
            "total_questions": len(raw_questions),
            "events": json.loads(cand_dict["events"]) if isinstance(cand_dict.get("events"), str) else (cand_dict.get("events") or []),
            "question_violations": json.loads(cand_dict["question_violations"]) if isinstance(cand_dict.get("question_violations"), str) else (cand_dict.get("question_violations") or {})
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Audit lookup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/candidate/{email}/unlock")
async def unlock_candidate(email: str):
    """
    Admin override: Unlocks candidate by setting status = 'unlocked' and zeroing strikes.
    """
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")
    
    clean_email = email.strip().lower()
    try:
        async with DB_POOL.acquire() as conn:
            res = await conn.execute("""
                UPDATE candidates 
                SET status = 'unlocked', fullscreen_exits = 0, tab_switches = 0
                WHERE email = $1;
            """, clean_email)
            if res == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Candidate not found.")
        logger.info(f"[COMMAND-CENTER] Candidate '{clean_email}' successfully unlocked by proctor.")
        return {"status": "success", "message": f"Candidate {clean_email} unlocked and proctoring strikes reset to 0."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unlock error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/candidate/{email}/lock")
async def lock_candidate(email: str):
    """
    Proctor manual action: Locks candidate session immediately.
    """
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")
    
    clean_email = email.strip().lower()
    try:
        async with DB_POOL.acquire() as conn:
            res = await conn.execute("""
                UPDATE candidates 
                SET status = 'locked'
                WHERE email = $1;
            """, clean_email)
            if res == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Candidate not found.")
        logger.info(f"[COMMAND-CENTER] Candidate '{clean_email}' manually locked by proctor.")
        return {"status": "success", "message": f"Candidate {clean_email} locked."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lock error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/candidate/{email}/extend-time")
async def extend_candidate_time(email: str, payload: ExtendTimeRequest):
    """
    Extends candidate's time allowance by N seconds (default 300s = 5m).
    """
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")
    
    clean_email = email.strip().lower()
    added_sec = max(60, payload.seconds or 300)
    try:
        async with DB_POOL.acquire() as conn:
            row = await conn.fetchrow("""
                UPDATE candidates 
                SET duration_seconds = duration_seconds + $2
                WHERE email = $1
                RETURNING duration_seconds, start_time;
            """, clean_email, added_sec)
            if not row:
                raise HTTPException(status_code=404, detail="Candidate not found.")
            
        rem = calculate_time_remaining(row["start_time"], row["duration_seconds"])
        logger.info(f"[COMMAND-CENTER] Extended time for '{clean_email}' by {added_sec}s. New remaining: {rem}s.")
        return {
            "status": "success",
            "message": f"Added {added_sec // 60}m {added_sec % 60}s to {clean_email}.",
            "new_seconds_remaining": rem
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Extend time error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/candidate/{email}/force-submit")
async def force_submit_candidate(email: str):
    """
    Forces submission and evaluation for a candidate.
    """
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")
    
    clean_email = email.strip().lower()
    try:
        async with DB_POOL.acquire() as conn:
            cand = await conn.fetchrow("SELECT * FROM candidates WHERE email = $1", clean_email)
            if not cand:
                raise HTTPException(status_code=404, detail="Candidate not found.")
            
            ans_rows = await conn.fetch("SELECT question_id, selected_option FROM answers WHERE candidate_email = $1", clean_email)
            answers_map = {r["question_id"]: r["selected_option"] for r in ans_rows}

            # Grade
            ch_set = get_challenge_set(cand.get("challenge_id", "set_a"))
            score = 0
            for q in ch_set.get("questions", []):
                corr = str(q.get("answer") or q.get("correct") or "").strip().lower()
                sel = str(answers_map.get(q.get("id")) or "").strip().lower()
                if sel and sel == corr:
                    score += 1

            total = len(ch_set.get("questions", [])) or 15
            now_utc = datetime.now(timezone.utc)

            await conn.execute("""
                UPDATE candidates 
                SET status = 'submitted', score = $2, total_possible = $3, submitted_at = $4
                WHERE email = $1;
            """, clean_email, score, total, now_utc)

        logger.info(f"[COMMAND-CENTER] Force submitted candidate '{clean_email}'. Final Score: {score}/{total}")
        return {
            "status": "success",
            "message": f"Assessment finalized for {clean_email}.",
            "score": score,
            "total_possible": total
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Force submit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/candidate/{email}/reset")
async def reset_candidate_session(email: str):
    """
    Danger Zone: Completely resets a candidate's session so they can re-take the test from scratch.
    """
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")
    
    clean_email = email.strip().lower()
    try:
        async with DB_POOL.acquire() as conn:
            # Delete answers
            await conn.execute("DELETE FROM answers WHERE candidate_email = $1;", clean_email)
            # Reset candidate
            res = await conn.execute("""
                UPDATE candidates 
                SET status = 'in_progress',
                    score = 0,
                    fullscreen_exits = 0,
                    tab_switches = 0,
                    copy_attempts = 0,
                    paste_attempts = 0,
                    ctrl_cmd_attempts = 0,
                    text_selection_attempts = 0,
                    start_time = NOW(),
                    duration_seconds = 1500,
                    submitted_at = NULL,
                    current_question = 'q1',
                    integrity_risk = 'LOW / CLEAN'
                WHERE email = $1;
            """, clean_email)
            if res == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Candidate not found.")

        logger.info(f"[COMMAND-CENTER] Candidate '{clean_email}' was completely reset.")
        return {"status": "success", "message": f"Session and answers for {clean_email} completely reset."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export-csv")
async def export_candidates_csv():
    if not DB_POOL:
        raise HTTPException(status_code=503, detail="Database connection pool unavailable.")

    import csv
    import io

    try:
        async with DB_POOL.acquire() as conn:
            cands = await conn.fetch("""
                SELECT 
                    id, email, name, usn, branch_sem, set_name, challenge_id,
                    status, score, total_possible, duration_seconds, start_time,
                    submitted_at, fullscreen_exits, tab_switches, copy_attempts,
                    integrity_risk, device
                FROM candidates
                ORDER BY score DESC, submitted_at ASC NULLS LAST;
            """)
            ans_rows = await conn.fetch("SELECT candidate_email, question_id, selected_option FROM answers;")

        ans_by_email = {}
        for a in ans_rows:
            ans_by_email.setdefault(a["candidate_email"], {})[a["question_id"]] = a["selected_option"]

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Rank", "Name", "Email", "USN", "Branch_Sem", "Set", "Status",
            "Score", "Total", "Percentage", "Questions_Answered",
            "Fullscreen_Exits", "Tab_Switches", "Copy_Attempts", "Integrity_Risk",
            "Start_Time_UTC", "Submitted_At_UTC", "Device", "Answers_JSON"
        ]
        writer.writerow(headers)

        for rank, c in enumerate(cands, start=1):
            email = c["email"]
            answers = ans_by_email.get(email, {})
            score = c["score"] or 0
            total = c["total_possible"] or 15
            pct = round((score / total) * 100, 1) if total else 0.0

            writer.writerow([
                rank,
                c["name"],
                c["email"],
                c.get("usn", ""),
                c.get("branch_sem", ""),
                c.get("set_name", "SET A"),
                c.get("status", "in_progress"),
                score,
                total,
                f"{pct}%",
                len(answers),
                c.get("fullscreen_exits", 0),
                c.get("tab_switches", 0),
                c.get("copy_attempts", 0),
                c.get("integrity_risk", "LOW / CLEAN"),
                c["start_time"].isoformat() if c.get("start_time") else "",
                c["submitted_at"].isoformat() if c.get("submitted_at") else "",
                c.get("device", ""),
                json.dumps(answers)
            ])

        output.seek(0)
        filename = f"classroom_assessment_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Serve Command Center HTML Dashboard
@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    html_file = REPO_ROOT / "templates" / "command_center.html"
    if not html_file.exists():
        return HTMLResponse("<h1>Command Center UI template not found. Please create templates/command_center.html</h1>", status_code=404)
    with open(html_file, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

if __name__ == "__main__":
    port = int(os.environ.get("COMMAND_CENTER_PORT", 8090))
    print(f"\n" + "="*70)
    print(f"🚀 AWS CLASSROOM PROCTOR COMMAND CENTER")
    print(f"📡 Real-Time Live Mission Control is running at:")
    print(f"👉 http://localhost:{port}")
    print(f"="*70 + "\n")
    uvicorn.run("command_center:app", host="0.0.0.0", port=port, reload=True)

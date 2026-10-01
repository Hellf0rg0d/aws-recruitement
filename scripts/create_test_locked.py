import asyncio
import asyncpg
from datetime import datetime, timezone, timedelta

async def setup_locked_candidate():
    db_url = 'postgresql://postgres.REDACTED_PROJECT_REF:REDACTED_PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres'
    conn = await asyncpg.connect(db_url)
    
    email = 'locked_test@student.edu'
    name = 'Test Locked Candidate'
    usn = '1VA21CS999'
    branch_sem = 'AIML - 6th Sem'
    session_id = 'session-locked-demo-001'
    start_time = datetime.now(timezone.utc) - timedelta(minutes=5) # 5 mins ago, 20 mins remaining
    
    # Clean up previous if exists
    await conn.execute('DELETE FROM answers WHERE candidate_email = $1', email)
    await conn.execute('DELETE FROM candidates WHERE email = $1', email)
    
    # Insert locked candidate
    insert_candidate_sql = """
        INSERT INTO candidates (
            email, name, usn, branch_sem, session_id,
            start_time, duration_seconds, challenge_id, set_name,
            status, score, total_possible, integrity_risk,
            fullscreen_exits, tab_switches, copy_attempts
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9,
            $10, $11, $12, $13,
            $14, $15, $16
        ) RETURNING *;
    """
    row = await conn.fetchrow(
        insert_candidate_sql,
        email, name, usn, branch_sem, session_id,
        start_time, 1500, 'set_a', 'SET A',
        'locked', 2, 15, 'CRITICAL / LOCKED',
        3, 3, 1
    )
    print("Inserted Candidate:")
    for k, v in dict(row).items():
        print(f"  {k}: {v}")
    
    # Insert 2 pre-answered questions
    insert_ans_sql = """
        INSERT INTO answers (candidate_email, question_id, selected_option)
        VALUES ($1, $2, $3), ($4, $5, $6);
    """
    await conn.execute(insert_ans_sql, email, 'q1', 'b', email, 'q2', 'a')
    print("\nInserted sample answers for q1 and q2.")
    
    # Verify view
    dash_row = await conn.fetchrow('SELECT * FROM classroom_proctoring_dashboard WHERE email = $1', email)
    print("\nDashboard View Row:")
    for k, v in dict(dash_row).items():
        print(f"  {k}: {v}")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(setup_locked_candidate())

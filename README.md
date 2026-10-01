# AWS Student Builder Group — Technical Recruitment Test (SET A)

Modern, secure, browser-based online assessment platform designed for the **AWS Student Builder Group Technical Recruitment Test**.

---

## 🚀 Features

- **Dynamic Question Loading:** Loads section-based assessments configured in [`challenges.json`](file:///challenges.json).
- **Sections & Questions:**
  - 📐 **Section A:** Elementary Math
  - 🧠 **Section B:** Aptitude & Reasoning
  - 💻 **Section C:** C Programming
  - 🧩 **Section D:** Puzzles
- **Strict Anti-Cheating & Proctoring:**
  - **Fullscreen Lock:** Enforces fullscreen mode with a 3-strike limit before auto-lockout.
  - **Focus & Tab Switch Detection:** Tracks `window.blur` and `visibilitychange` with real-time countdown warning modals (3-times limit).
  - **Ctrl & Cmd Key Logging:** Intercepts and records Ctrl/Command key strokes and unauthorized shortcuts (<kbd>Cmd+A</kbd>, <kbd>Cmd+F</kbd>, <kbd>Cmd+P</kbd>, <kbd>Cmd+S</kbd>, <kbd>Cmd+C</kbd>, etc.).
  - **Text Selection Prevention:** Blocks text selection (`selectstart` / `user-select: none`) and logs selection attempts with captured text lengths.
  - **Copy / Cut / Paste Blocking:** Disables clipboard actions inside exam questions.
  - **Per-Question Time Tracking:** Records the timestamp, elapsed test seconds, answer selection, and modification count for every question attempted.
- **Automated Submission:** Transmits responses, telemetry violations, and formatted event timelines to Google Apps Script / Google Sheets.

---

## 📁 Project Structure

```text
.
├── index.html                  # Assessment application frontend (self-contained UI, proctoring & telemetry)
├── server.py                   # High-speed Python HTTP server & database API (/api/submit, /health, /export)
├── challenges.json             # AWS Club questions (SET A - 15 MCQs)
├── submissions.json            # Local JSON candidate database with full telemetry & score records
├── render.yaml                 # Render Blueprint configuration (zero-config 1-click deployment)
├── Procfile                    # Render Web Service process definition
├── requirements.txt            # Python environment specification
├── runtime.txt                 # Python runtime version (3.11.9)
├── Dockerfile                  # Container deployment definition (optional Docker mode)
├── .dockerignore               # Docker ignore rules
├── scripts/
│   └── view_telemetry_logs.py  # Forensic audit & telemetry inspection CLI tool
├── tests/                      # Race-condition / resilience / client suites (see tests/README.md)
├── RACE_AND_STABILITY_HANDOFF.md  # What was fixed, how it was verified, what to do before deploying
└── .github/
    └── workflows/static.yml    # GitHub Pages deployment workflow
```

---

## ☁️ Deploying on Render

You can deploy this assessment platform to [Render](https://render.com/) in less than 2 minutes using either method below:

### Option 1: Automatic Blueprint (Recommended)
1. Push this repository to your **GitHub** or **GitLab** account.
2. Log into **[dashboard.render.com](https://dashboard.render.com/)**.
3. Click **New +** ➔ **Blueprint**.
4. Connect this repository. Render automatically reads [`render.yaml`](file:///render.yaml) and configures:
   - **Service Type:** Web Service
   - **Environment:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python3 server.py`
   - **Health Check Path:** `/health`
5. Click **Apply**. Your assessment URL will be live at `https://<your-service-name>.onrender.com`.

### Option 2: Manual Web Service Setup
1. On the Render Dashboard, click **New +** ➔ **Web Service**.
2. Select your repository.
3. Configure the following settings:
   - **Name:** `aws-recruitment-test`
   - **Runtime:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python3 server.py`
   - **Health Check Path:** `/health`
4. Click **Create Web Service**.

---

## 📊 Live Endpoints & Admin Tools

When hosted on Render (or locally):
- **Candidate Assessment Portal:** `https://<your-app>.onrender.com/`
- **Health Check Endpoint:** `https://<your-app>.onrender.com/health` (Returns `{"status": "healthy"}`)
- **Live Results API:** `https://<your-app>.onrender.com/api/results` (JSON array of all candidate submissions)
- **Export to CSV (Excel):** `https://<your-app>.onrender.com/api/export/csv` (Instant spreadsheet download)
- **Export Raw Database:** `https://<your-app>.onrender.com/api/export` (Download raw `submissions.json`)

---

## ⚙️ Reliability Settings (environment variables, all optional)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | – | Postgres/Supabase connection string. **Set this explicitly**; the server also contains a built-in fallback (see handoff doc, security notes). |
| `VISS_LOCAL_MODE` | off | `1` allows the in-memory/JSON offline store (local dev only). Without it a missing/failed database answers **HTTP 503** and clients retry, so candidate state never silently lives only in server memory. |
| `DB_ACQUIRE_TIMEOUT` | `5` | Seconds a request waits for a pooled connection before answering 503. |
| `HEALTH_FAIL_THRESHOLD` | `5` | Consecutive failed database probes before `/health` returns 503 (Render then restarts the instance). |
| `BACKUP_FLUSH_DELAY` | `1.0` | Seconds the `submissions.json` backup batches records before one off-loop write. |
| `MAX_REQUEST_BYTES` | `524288` | Request bodies larger than this are rejected with 413. |

## 💻 Local Development & Testing

> ⚠️ **`python3 server.py` connects to whatever `DATABASE_URL` points at, and falls back to a built-in Supabase URL when it is unset.**
> For local work, point `DATABASE_URL` at a local Postgres, or run with `VISS_LOCAL_MODE=1` and no database.
> Never start it against the live database during an exam.

1. Start the server locally. Setting `DATABASE_URL` to a local address also guarantees the built-in Supabase fallback
   is never used; with nothing listening there, `VISS_LOCAL_MODE=1` makes the server use its in-memory/JSON store:
   ```bash
   VISS_LOCAL_MODE=1 DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres python3 server.py
   ```
   (or run `tests/setup_test_db.sh` first and the same URL will reach a real throwaway Postgres.)
2. Open your browser and navigate to:
   ```text
   http://localhost:8080/
   ```
3. To inspect recorded candidate submissions and anti-cheat forensics in your terminal:
   ```bash
   python3 scripts/view_telemetry_logs.py
   ```

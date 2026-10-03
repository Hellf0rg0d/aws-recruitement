# Assessment & Proctoring Platform

A modern, high-concurrency, browser-based examination platform with real-time proctoring telemetry, crash-resilient session resumption, and a live proctor command center.

Designed for universities, student developer communities, and organizations conducting timed technical screenings and evaluations.

---

## 🚀 Key Capabilities

- **Dynamic Question Sets:** Configurable multi-section assessments via [`challenges.json`](file:///challenges.json) supporting MCQ, code comprehension, and math questions.
- **Strict Proctoring & Integrity Telemetry:**
  - **Fullscreen Enforcement:** Fullscreen lock with configurable strike limits before candidate lockout.
  - **Focus & Tab Switch Detection:** Tracks `window.blur` and `visibilitychange` with countdown warning modals.
  - **Keystroke & Shortcut Interception:** Detects unauthorized shortcuts (<kbd>Cmd+C</kbd>, <kbd>Cmd+V</kbd>, <kbd>Cmd+P</kbd>, <kbd>Cmd+F</kbd>, <kbd>Cmd+A</kbd>).
  - **Clipboard & Selection Guard:** Blocks text selection and clipboard events inside the exam window.
  - **Per-Question Time & Change Tracking:** Records timestamp, elapsed seconds, option choices, and edit counts per question.
- **Server-Authoritative State & Classroom Resumption:**
  - Server-calculated remaining duration prevents client clock tampering.
  - Automatic periodic answer saving and instant restore on browser crash or accidental refresh.
  - Row-level database locks ensure race-free submissions under high concurrency.
- **Live Proctor Command Center:**
  - Dedicated real-time dashboard ([`command_center.py`](file:///command_center.py)) to monitor all live students in a hall.
  - Live strike counts, question-by-question progression, time remaining, and instant remote lock/unlock controls.
- **Cloud & Offline Resilience:**
  - Built for PostgreSQL / Supabase connection pooling (port 6543 transaction pooler).
  - Graceful local JSON offline fallback for air-gapped environments or local development.

---

## 📁 Repository Structure

```text
.
├── index.html                  # Assessment application frontend (single-page test interface)
├── server.py                   # FastAPI assessment engine (/api/login, /api/save, /api/submit)
├── command_center.py           # Live proctor mission control console (proctor monitoring & unlock)
├── start_command_center.sh     # Quick-launch shell script for proctor command center
├── templates/
│   └── command_center.html     # Real-time proctor command center web UI
├── challenges.json             # Assessment question bank (template included)
├── supabase_schema.sql         # PostgreSQL database schema and live dashboard view
├── render.yaml                 # Render cloud deployment blueprint
├── requirements.txt            # Python dependencies
├── .env.example                # Template for environment variables
├── scripts/
│   ├── create_test_locked.py   # Development helper to simulate a locked candidate
│   ├── render_keepalive.sh     # Health-check ping script to prevent cloud idle sleep
│   └── view_telemetry_logs.py  # CLI forensic audit and telemetry inspection tool
└── tests/                      # Concurrency, race condition, and resilience test suites
```

---

## 🛠️ Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.11+
- (Optional) PostgreSQL or a free [Supabase](https://supabase.com) project

### 2. Installation
```bash
git clone git@github.com:Hellf0rg0d/aws-recruitement.git
cd aws-recruitement
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment
Copy the example environment file:
```bash
cp .env.example .env
```
Edit `.env` with your database credentials and configuration:
```ini
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<your-anon-or-service-key>
PORT=8080
ADMIN_KEY=your-secure-admin-key
```

> **Offline Mode:** If `DATABASE_URL` is omitted, the server automatically starts in offline mode using local JSON persistence.

### 4. Start the Assessment Server
```bash
python3 server.py
```
Open **[http://localhost:8080](http://localhost:8080)** in your browser.

---

## 🛰️ Running the Proctor Command Center

The Command Center provides a real-time grid of all active candidates, their strikes, current questions, and controls to unlock candidates:

```bash
chmod +x start_command_center.sh
./start_command_center.sh
```
Or run directly:
```bash
COMMAND_CENTER_PORT=8090 python3 command_center.py
```
Access the control dashboard at **[http://localhost:8090](http://localhost:8090)**.

---

## 🗄️ Database Setup (Supabase / PostgreSQL)

1. Create a new Supabase project or PostgreSQL database.
2. In the Supabase SQL Editor, execute the contents of [`supabase_schema.sql`](file:///supabase_schema.sql).
3. Copy your project's **Transaction Pooler Connection String** (port 6543) into `DATABASE_URL` in `.env`.

---

## 📝 Customizing Questions

Assessment questions and sections are defined in [`challenges.json`](file:///challenges.json).

Each test set contains a list of questions with options and an answer key:

```json
{
  "activeChallenge": "set_a",
  "challenges": {
    "set_a": {
      "title": "Technical Assessment (SET A)",
      "durationMinutes": 25,
      "sections": [
        { "id": "math", "title": "Section A: Math", "icon": "📐" },
        { "id": "code", "title": "Section B: Coding", "icon": "💻" }
      ],
      "questions": [
        {
          "id": "q1",
          "name": "q1_sample",
          "category": "math",
          "heading": "Question 1: Problem Title",
          "text": "What is the result of 2 + 2?",
          "type": "mcq",
          "options": [
            { "label": "a", "text": "3" },
            { "label": "b", "text": "4" },
            { "label": "c", "text": "5" }
          ],
          "answer": "b"
        }
      ]
    }
  }
}
```

The server automatically strips the `"answer"` field before serving questions to candidate browsers via `/challenges.json`.

---

## 🧪 Running Tests

A complete suite of race-condition, stress, and client-resilience tests is located in [`tests/`](file:///tests/):

```bash
# Run all automated test suites
bash tests/run_all.sh
```

---

## ☁️ Deployment

### Render Blueprint
1. Push this repository to GitHub or GitLab.
2. Go to [Render Dashboard](https://dashboard.render.com/) ➔ **New +** ➔ **Blueprint**.
3. Select your repository. Render reads [`render.yaml`](file:///render.yaml) automatically.
4. Set your `DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_KEY` in Render environment settings.

---

## 🤝 Contributing

Contributions to improve concurrency, expand proctoring capabilities, and enhance UI accessibility are welcome!

1. Fork the repository.
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "feat: add my feature"`
4. Push to branch: `git push origin feature/my-feature`
5. Open a Pull Request.

Ensure all tests pass (`bash tests/run_all.sh`) before submitting your PR.
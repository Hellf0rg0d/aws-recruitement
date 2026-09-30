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

## 💻 Local Development & Testing

1. Start the server locally:
   ```bash
   python3 server.py
   ```
2. Open your browser and navigate to:
   ```text
   http://localhost:8080/
   ```
3. To inspect recorded candidate submissions and anti-cheat forensics in your terminal:
   ```bash
   python3 scripts/view_telemetry_logs.py
   ```

#!/usr/bin/env python3
"""
AWS Student Builder Group Recruitment Test — Telemetry & Audit Inspector
Parses JSON session audit logs or exported spreadsheets using the Python standard library.
"""
import sys
import os
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def inspect_xlsx(xlsx_path):
    if not os.path.exists(xlsx_path):
        print(f"File not found: {xlsx_path}")
        return

    with zipfile.ZipFile(xlsx_path) as z:
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        shared_strings = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in sst.findall(".//" + ns + "si"):
                t = si.find(ns + "t")
                shared_strings.append(t.text if t is not None else "")

        sheet1 = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet1.findall(".//" + ns + "row"):
            cols = {}
            for c in row.findall(ns + "c"):
                coord = c.get("r")
                col_letter = "".join([ch for ch in coord if ch.isalpha()])
                is_elem = c.find(ns + "is")
                v = c.find(ns + "v")
                val = ""
                if is_elem is not None:
                    t_elem = is_elem.find(ns + "t")
                    if t_elem is not None:
                        val = t_elem.text
                elif v is not None:
                    if c.get("t") == "s" and shared_strings:
                        idx = int(v.text)
                        val = shared_strings[idx] if idx < len(shared_strings) else v.text
                    else:
                        val = v.text
                cols[col_letter] = val
            rows.append(cols)

    if not rows:
        print("Empty sheet.")
        return

    headers = rows[0]
    data_rows = rows[1:]
    print("=" * 60)
    print(f"ASSESSMENT RESULTS & TELEMETRY LOGS ({os.path.basename(xlsx_path)})")
    print("=" * 60)
    print(f"Total Candidate Rows: {len(data_rows)}")
    
    if not data_rows:
        print("No student submission rows currently recorded (DB / sheet is clean).")
        return

    # Check for known column mappings
    tot_tabs = 0
    tot_pastes = 0
    tot_copies = 0
    tot_exits = 0
    tot_shortcuts = 0
    violations = []

    for r in data_rows:
        usn = r.get("A", "")
        name = r.get("B", "")
        status = r.get("D", "not_started")
        score = r.get("R", "0")
        
        # Telemetry columns: T, U, V, W, X
        tabs = int(float(r.get("T", 0) or 0))
        pastes = int(float(r.get("U", 0) or 0))
        exits = int(float(r.get("V", 0) or 0))
        shortcuts = int(float(r.get("W", 0) or 0))
        copies = int(float(r.get("X", 0) or 0))

        tot_tabs += tabs
        tot_pastes += pastes
        tot_copies += copies
        tot_exits += exits
        tot_shortcuts += shortcuts

        if tabs > 0 or pastes > 0 or copies > 0 or exits > 0 or shortcuts > 0:
            violations.append({
                "usn": usn, "name": name, "status": status, "score": score,
                "tabs": tabs, "pastes": pastes, "copies": copies,
                "exits": exits, "shortcuts": shortcuts
            })

    print(f"Total Fullscreen Exits:  {tot_exits}")
    print(f"Total Tab Switches:      {tot_tabs}")
    print(f"Total Copy Attempts:     {tot_copies}")
    print(f"Total Paste Attempts:    {tot_pastes}")
    print(f"Total Blocked Shortcuts: {tot_shortcuts}")
    print(f"Candidates with Flags:   {len(violations)}")
    print("-" * 60)

    for v in violations:
        print(f"[{v['usn']}] {v['name']} ({v['status']}) - Score: {v['score']}")
        print(f"   Exits: {v['exits']} | Tabs: {v['tabs']} | Copies: {v['copies']} | Pastes: {v['pastes']} | Shortcuts: {v['shortcuts']}")

def print_single_candidate(data):
    print("=" * 75)
    print(f"CANDIDATE TEST RECORD: {data.get('name', 'N/A')} ({data.get('usn', 'N/A')})")
    print("=" * 75)
    cid = data.get('challengeId', 'set_a')
    set_name = 'SET B' if 'set_b' in cid.lower() or 'set b' in cid.lower() else ('SET C' if 'set_c' in cid.lower() or 'set c' in cid.lower() else 'SET A')
    print(f"Assessment Set: {set_name} ({cid})")
    print(f"Email: {data.get('email', 'N/A')} | Branch/Sem: {data.get('branch_sem', 'N/A')}")
    print(f"Submitted At: {data.get('timestamp') or data.get('submittedAt', 'N/A')}")
    if 'score' in data and 'totalPossible' in data:
        print(f"Score: {data.get('score')}/{data.get('totalPossible')}")
    print(f"Time Taken: {data.get('timeTakenSec', 'N/A')} seconds")
    print(f"Device: {data.get('device', 'N/A')}")

    # Integrity Risk Summary
    risk = data.get('integrityRisk')
    q_violations = data.get('questionViolations', {})
    if not risk:
        if any(v.get('riskLevel') == 'HIGH' for v in q_violations.values()) or data.get('copyAttempts', 0) > 0 or data.get('fullscreenExits', 0) >= 3 or data.get('tabSwitches', 0) >= 3:
            risk = "HIGH / FLAGGED"
        elif any(v.get('riskLevel') == 'MEDIUM' for v in q_violations.values()) or data.get('tabSwitches', 0) > 1:
            risk = "MEDIUM / SUSPICIOUS"
        else:
            risk = "LOW / CLEAN"

    risk_badge = f"\033[92m[{risk}]\033[0m" if "LOW" in risk else (f"\033[93m[{risk}]\033[0m" if "MEDIUM" in risk else f"\033[91m[{risk}]\033[0m")
    print(f"Integrity & Anti-Cheat Audit: {risk_badge}")
    print("-" * 75)
    print(f"Proctoring Metrics:")
    print(f"  • Fullscreen Exits:         {data.get('fullscreenExits', 0)} / 3")
    print(f"  • Tab Switches / Focus:     {data.get('tabSwitches', 0)} / 3")
    print(f"  • Ctrl/Cmd Modifier Keys:   {data.get('ctrlCmdAttempts', 0)}")
    print(f"  • Text Selection Attempts:  {data.get('textSelectionAttempts', 0)}")
    print(f"  • Copy Attempts Blocked:    {data.get('copyAttempts', 0)}")
    print(f"  • Paste Attempts Blocked:   {data.get('pasteAttempts', 0)}")
    
    # Per-Question Attempt Timings
    q_times = data.get('questionTimings', {})
    if q_times:
        print("-" * 75)
        print("PER-QUESTION ATTEMPT TIMELINE:")
        for q_id, info in q_times.items():
            q_num = info.get('questionNumber', q_id)
            print(f"  • Q{q_num} ({q_id}): First answered at {info.get('firstAttemptFormatted', '?')} ({info.get('firstAttemptAtSec', 0)}s) | Answer: {info.get('selectedAnswer', 'N/A')} | Changes: {info.get('changesCount', 1)}")

    # PER-QUESTION FORENSICS: ACCIDENTAL VS DELIBERATE MALPRACTICE
    print("-" * 75)
    print("PER-QUESTION FORENSICS (ACCIDENTAL VS. DELIBERATE MALPRACTICE):")
    if not q_violations:
        if data.get('fullscreenExits', 0) == 0 and data.get('tabSwitches', 0) == 0 and data.get('copyAttempts', 0) == 0 and data.get('textSelectionAttempts', 0) == 0 and data.get('ctrlCmdAttempts', 0) == 0:
            print("  ✓ Pristine Session: 0 proctoring violations recorded across all questions.")
        else:
            print("  ℹ️ Legacy record: Global telemetry flags logged (see Event Timeline below).")
    else:
        for q_id, qv in q_violations.items():
            level = qv.get('riskLevel', 'LOW')
            color = "\033[92m" if level == "LOW" else ("\033[93m" if level == "MEDIUM" else "\033[91m")
            q_title = f"Question {qv.get('questionNumber', '?')} ({q_id}): {qv.get('questionHeading', 'Question')}"
            print(f"\n  {color}▶ {q_title}\033[0m")
            print(f"    Risk Classification: {color}[{level}]\033[0m | Total Violations: {qv.get('violationsCount', len(qv.get('violations', [])))} | Away Time: {qv.get('totalAwaySec', 0)}s")
            print(f"    Forensic Verdict:    {qv.get('verdict', 'N/A')}")
            violations_list = qv.get('violations', [])
            if violations_list:
                print(f"    Violation Event Log:")
                for v in violations_list:
                    print(f"      - [{v.get('time', '?')}] {v.get('summary', v.get('type', '?'))}")

    events = data.get('events', [])
    if events:
        print("-" * 75)
        print(f"CHRONOLOGICAL EVENT LOG ({len(events)} events):")
        for ev in events:
            detail_str = ", ".join([f"{k}: {v}" for k, v in ev.get('detail', {}).items() if k not in ('reason',)])
            extra = f" | {detail_str}" if detail_str else ""
            print(f"  [{ev.get('timestamp', '?')}] ({ev.get('elapsedSec', 0)}s) {ev.get('type')} [Q:{ev.get('questionNumber', '-')}{extra}]")

def inspect_json(json_path):
    with open(json_path) as f:
        data = json.load(f)

    if isinstance(data, list):
        print("=" * 80)
        print(f"AWS RECRUITMENT TEST DATABASE ({os.path.basename(json_path)})")
        print("=" * 80)
        print(f"Total Submissions Recorded: {len(data)}")
        if not data:
            print("No submissions recorded yet.")
            return

        print(f"{'#':<3} {'USN':<12} {'Name':<18} {'Set':<7} {'Score':<7} {'Risk Status':<15} {'Exits':<6} {'Tabs':<6} {'Copies':<7}")
        print("-" * 88)
        for r in data:
            score_str = f"{r.get('score', 0)}/{r.get('totalPossible', 15)}"
            risk_str = r.get('integrityRisk', 'LOW / CLEAN')[:14]
            cid = r.get('challengeId', 'set_a')
            set_badge = 'SET B' if 'set_b' in cid.lower() or 'set b' in cid.lower() else ('SET C' if 'set_c' in cid.lower() or 'set c' in cid.lower() else 'SET A')
            print(f"{r.get('id', 1):<3} {r.get('usn', 'N/A')[:11]:<12} {r.get('name', 'N/A')[:17]:<18} {set_badge:<7} {score_str:<7} {risk_str:<15} {r.get('fullscreenExits', 0):<6} {r.get('tabSwitches', 0):<6} {r.get('copyAttempts', 0):<7}")
        
        # Also print detailed logs of the most recent submission
        print("\n" + "=" * 80)
        print("MOST RECENT CANDIDATE AUDIT & FORENSIC REPORT:")
        print_single_candidate(data[-1])
    else:
        print_single_candidate(data)

def main():
    db_file = REPO_ROOT / "submissions.json"
    if len(sys.argv) > 1:
        arg1 = sys.argv[1]
    elif db_file.exists():
        arg1 = str(db_file)
    else:
        # Check if any json logs exist in current directory or prompt usage
        json_files = list(REPO_ROOT.glob("*.json"))
        audit_files = [f for f in json_files if f.name != "challenges.json"]
        if audit_files:
            arg1 = str(audit_files[0])
        else:
            print("Usage: python3 scripts/view_telemetry_logs.py <path_to_audit_log.json | submissions.json>")
            print("No database submissions found yet.")
            return

    if arg1.endswith(".json"):
        inspect_json(arg1)
    else:
        inspect_xlsx(arg1)

if __name__ == "__main__":
    main()

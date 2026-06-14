#!/usr/bin/env python3
"""
Read run_state.json and send ONE summary email for the pipeline run.
Usage: send_summary.py <week|month> <yom|ping>
Exits 0 on overall success, 1 if any step failed or was not run.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).parent))
from utils import send_email_alert

EXPECTED_STEPS = {
    "week":  ["simulation", "import_basin_7days", "import_admin_7days",
              "import_basin_daily", "import_admin_daily"],
    "month": ["simulation", "import_basin_6months", "import_admin_6months",
              "import_basin_daily", "import_admin_daily"],
}

BASIN_LABELS = {"yom": "Yom", "ping": "Ping"}




def main(mode, basin):
    fore_dir = Path(__file__).parent
    state_file = fore_dir / basin / mode / "Logs" / "run_state.json"

    date_str = datetime.now().strftime("%Y-%m-%d")
    basin_label = BASIN_LABELS.get(basin, basin.title())
    mode_label = mode.title()

    if state_file.exists():
        steps_ran = {e["step"]: e for e in json.loads(state_file.read_text())}
    else:
        steps_ran = {}

    project_root = Path(__file__).parent.parent
    project_root_str = str(project_root) + "/"

    def _rel(text):
        return text.replace(project_root_str, "") if text else text

    expected = EXPECTED_STEPS[mode]
    overall_ok = True
    lines = []

    # Simulation row
    sim = steps_ran.get("simulation")
    if sim:
        if sim["success"]:
            sim_line = f"✓  {sim.get('sim_start', '?')} → {sim.get('sim_end', '?')}"
        else:
            sim_line = f"✗  {_rel(sim.get('error', 'Unknown error'))}"
            overall_ok = False
    else:
        sim_line = "–  NOT RUN"
        overall_ok = False

    lines.append(f"SIMULATION      {sim_line}")
    lines.append("")
    lines.append("DB IMPORT")

    last_log = None
    for step in expected:
        if step == "simulation":
            continue
        entry = steps_ran.get(step)
        label = step.replace("import_", "")
        if entry is None:
            lines.append(f"  {label:<18} –  NOT RUN")
            overall_ok = False
        elif entry.get("skipped"):
            lines.append(f"  {label:<18} –  SKIPPED (DB disabled)")
        elif entry["success"]:
            lines.append(f"  {label:<18} ✓")
            for t in entry.get("tables", []):
                lines.append(f"      {t['table']}: {t['rows']} rows")
        else:
            error = entry.get("error", "Unknown error")
            failed_at = entry.get("failed_at", "")
            lines.append(f"  {label:<18} ✗  FAILED at {failed_at}: {_rel(error)}")
            if entry.get("log_file"):
                last_log = entry["log_file"]
            overall_ok = False

    if last_log:
        try:
            rel = Path(last_log).relative_to(project_root)
        except ValueError:
            rel = last_log
        lines.append("")
        lines.append(f"Log: {rel}")

    status = "SUCCESS" if overall_ok else "FAILED"
    subject = f"[SWAT {basin.upper()} {mode.upper()}] {status} – {date_str}"
    body = f"{basin_label} {mode_label} Pipeline – {date_str}\n\n" + "\n".join(lines)

    send_email_alert(subject, body)
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("week", "month") or sys.argv[2] not in ("yom", "ping"):
        print(f"Usage: {sys.argv[0]} <week|month> <yom|ping>")
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])

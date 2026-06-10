import logging
import sys
import os
import smtplib
import ssl
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# =====================================================================
# GLOBAL LOGGING CONFIGURATION
# =====================================================================
def setup_colored_logger(log_file=None):
    logger = logging.getLogger("SWAT_Weekly_Pipeline")
    logger.setLevel(logging.INFO)
    
    if logger.hasHandlers(): 
        logger.handlers.clear()
        
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    class ColorFormatter(logging.Formatter):
        GREEN, YELLOW, RED, RESET = "\033[92m", "\033[93m", "\033[91m", "\033[0m"
        def format(self, record):
            msg = record.getMessage()
            color = self.RED if record.levelno >= logging.ERROR or "FAILED" in msg else \
                    self.YELLOW if record.levelno == logging.WARNING or "NOT EXECUTED" in msg else \
                    self.GREEN if "SUCCESS" in msg else ""
            return f"{color}{super().format(record)}{self.RESET}" if color else super().format(record)

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ColorFormatter(log_format, datefmt=date_format))
    logger.addHandler(ch)
    
    # File Handler
    if log_file:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        logger.addHandler(fh)
        
    logger.propagate = False
    return logger

# =====================================================================
# UTILITIES & EMAIL ALERT FUNCTIONS
# =====================================================================
def send_email_alert(subject, body_text):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    receivers = [r.strip() for r in os.getenv("ALERT_EMAIL", "").split(",") if r.strip()]

    if not receivers:
        print("No ALERT_EMAIL configured, skipping email alert.")
        return

    message = MIMEMultipart()
    message["From"]    = smtp_user
    message["To"]      = ", ".join(receivers)
    message["Subject"] = subject
    message.attach(MIMEText(body_text, "plain"))

    try:
        context = ssl.create_default_context()
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, receivers, message.as_string())
        server.quit()
    except Exception as e:
        print(f"Failed to send email alert. Error: {e}")
        
def generate_email_alert(state_tracker: dict, output_path: str, phase_name: str = "SWAT Process"):
    counts = {"SUCCESS": 0, "FAILED": 0, "WARNING": 0, "NOT EXECUTED": 0}
    lines = [f"Subject: [ALERT] {phase_name} Summary – {datetime.now().strftime('%Y-%m-%d')}", f"\n{phase_name} Status:"]
    
    for task_name, details in state_tracker.items():
        status = details.get("status", "NOT EXECUTED")
        error_msg = details.get("error", "")
        if status in counts: counts[status] += 1
        lines.append(f"{task_name} → {status} ({error_msg})" if error_msg else f"{task_name} → {status}")

    lines.extend([
        "\nSummary:",
        f"SUCCESS: {counts['SUCCESS']} items",
        f"WARNING: {counts['WARNING']} items",
        f"FAILED: {counts['FAILED']} items",
        f"NOT EXECUTED: {counts['NOT EXECUTED']} items",
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ])
    
    output_dir = os.path.dirname(str(output_path))
    if output_dir: os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f: f.write("\n".join(lines))
    if counts["FAILED"] > 0: send_email_alert(f"[SWAT FAILED] Phase: {phase_name}", "\n".join(lines))
    return "\n".join(lines)

def _date_to_julian(date_val):
    d = datetime.strptime(str(int(date_val)), '%Y%m%d')
    return f"{d.year}{d.timetuple().tm_yday:03d}"

def load_basin_mapping(json_file) -> dict:
    if not os.path.exists(json_file):
        raise FileNotFoundError(f"Mapping file '{json_file}' does not exist.")
    with open(json_file, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
        return {int(k): int(v) for k, v in mapping.items()}

def get_mode_or_mean(series):
    clean = series.dropna()
    if clean.empty: return np.nan
    modes = clean.mode()
    return modes.iloc[0] if len(modes) == 1 else clean.mean()

def update_state(state_tracker, process_name, status, error_msg=None):
    state_tracker[process_name]["status"] = status
    if error_msg: 
        state_tracker[process_name]["error"] = error_msg
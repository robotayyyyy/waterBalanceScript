"""Shared DB helpers for all import scripts."""

import csv
import io
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

try:
    import psycopg2
except ImportError:
    raise SystemExit("Missing dependency: pip install psycopg2-binary")

DB = {
    "host":     os.getenv("DATABASE_HOST"),
    "port":     int(os.getenv("DATABASE_PORT")),
    "user":     os.getenv("DATABASE_USER"),
    "password": os.getenv("DATABASE_PASSWORD"),
    "dbname":   os.getenv("DATABASE_NAME"),
}

LOGGER_NAME = "SWAT_Weekly_Pipeline"


def _setup_logger(log_file=None):
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if logger.hasHandlers():
        logger.handlers.clear()

    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    class ColorFormatter(logging.Formatter):
        GREEN, YELLOW, RED, RESET = "\033[92m", "\033[93m", "\033[91m", "\033[0m"
        def format(self, record):
            msg = record.getMessage()
            color = self.RED    if record.levelno >= logging.ERROR or "FAILED" in msg else \
                    self.YELLOW if record.levelno == logging.WARNING or "NOT EXECUTED" in msg else \
                    self.GREEN  if "SUCCESS" in msg else ""
            return f"{color}{super().format(record)}{self.RESET}" if color else super().format(record)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ColorFormatter(log_format, datefmt=date_format))
    logger.addHandler(ch)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        logger.addHandler(fh)

    logger.propagate = False
    return logger


def _append_state(state_file: Path, entry: dict):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(state_file.read_text()) if state_file.exists() else []
    existing.append(entry)
    state_file.write_text(json.dumps(existing, indent=2))


def read_csv(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    headers = [h.strip() for h in next(reader)]
    rows = [row for row in reader if any(c.strip() for c in row)]
    return headers, rows


def year_mon_to_date(year: str, mon: str) -> str:
    return f"{int(year):04d}-{int(mon):02d}-01"


def parse_date(s: str) -> str:
    return datetime.strptime(s.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")


def zero_pad_mb(v: str) -> str:
    return v.strip().zfill(2)


def zero_pad_sb(v: str) -> str:
    return v.strip().zfill(4)


def to_num(v: str):
    v = v.strip()
    return v if v else None


def to_int(v: str):
    v = v.strip()
    return int(float(v)) if v else None


def copy_insert(cur, table: str, columns, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        writer.writerow(['' if v is None else v for v in row])
    buf.seek(0)
    cur.copy_from(buf, table, columns=columns, sep='\t', null='')


def run(importers, log_dir=None, script_name=None):
    """Connect to DB, run each importer(cur), commit on success. Writes result to run_state.json."""
    log_file = None

    # Log file: always uses log_dir
    if log_dir and script_name:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M")
        log_file = Path(log_dir) / f"{script_name}_{ts}.log"

    # State file: SWAT_LOG_DIR env var overrides log_dir (used by Makefile for month targets)
    _state_dir = os.getenv("SWAT_LOG_DIR") or (str(log_dir) if log_dir else None)
    state_file = Path(_state_dir) / "run_state.json" if _state_dir else None

    logger = _setup_logger(log_file=str(log_file) if log_file else None)
    label = script_name or "import"
    log_path = str(log_file) if log_file else None

    # Feature flag: SWAT_SAVE_DB=false skips DB entirely (for teammates without a DB)
    if os.getenv("SWAT_SAVE_DB", "true").strip().lower() == "false":
        logger.info("DB saving disabled (SWAT_SAVE_DB=false), skipping import.")
        entry = {"step": label, "success": True, "skipped": True, "tables": [], "log_file": log_path}
        if state_file:
            _append_state(state_file, entry)
        return entry

    step = "DB connection"
    conn = None
    tables = []
    logger.info("Connecting to DB...")
    try:
        conn = psycopg2.connect(**DB)
        conn.autocommit = False
        cur = conn.cursor()
        for fn in importers:
            step = fn.__name__
            result = fn(cur)
            if result:
                if isinstance(result, list):
                    tables.extend(result)
                else:
                    tables.append(result)
        conn.commit()
        logger.info("SUCCESS: All tables imported.")
        entry = {"step": label, "success": True, "tables": tables, "log_file": log_path}
        if state_file:
            _append_state(state_file, entry)
        return entry
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"FAILED at {step}: {e}")
        entry = {"step": label, "success": False, "error": str(e), "failed_at": step, "log_file": log_path}
        if state_file:
            _append_state(state_file, entry)
        raise
    finally:
        if conn:
            conn.close()

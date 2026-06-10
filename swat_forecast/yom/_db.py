"""Shared DB helpers for all import scripts."""

import csv
import io
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

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


def run(importers):
    """Connect to DB, run each importer(cur), commit on success."""
    print("Connecting to DB...")
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        for fn in importers:
            fn(cur)
        conn.commit()
        print("\nDone.\n")
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()

"""Shared DB helpers for all import scripts."""

import csv
import io
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


def stream_csv(path: Path):
    """Open a CSV lazily. Returns (headers, row_iterator) without loading the whole file."""
    f = open(path, encoding="utf-8-sig", newline="")
    try:
        reader = csv.reader(f)
        headers = [h.strip() for h in next(reader)]
    except Exception:
        f.close()
        raise

    def _rows():
        try:
            for row in reader:
                if any(c.strip() for c in row):
                    yield row
        finally:
            f.close()

    return headers, _rows()


def copy_insert(cur, table: str, columns, rows):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
    for row in rows:
        writer.writerow(['' if v is None else v for v in row])
    buf.seek(0)
    cur.copy_from(buf, table, columns=columns, sep='\t', null='')


def copy_insert_stream(cur, table: str, columns, row_iter, chunk_size=50_000):
    """Bulk-insert from an iterator in chunks to limit peak memory usage. Returns row count."""
    total = 0
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
    count = 0
    for row in row_iter:
        writer.writerow(['' if v is None else v for v in row])
        count += 1
        if count >= chunk_size:
            buf.seek(0)
            cur.copy_from(buf, table, columns=columns, sep='\t', null='')
            total += count
            buf = io.StringIO()
            writer = csv.writer(buf, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
            count = 0
    if count:
        buf.seek(0)
        cur.copy_from(buf, table, columns=columns, sep='\t', null='')
        total += count
    return total


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

#!/usr/bin/env python3
import os
import sys
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

try:
    conn = psycopg2.connect(**DB)
    conn.close()
    print(f"OK: connected to {DB['dbname']} at {DB['host']}:{DB['port']}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

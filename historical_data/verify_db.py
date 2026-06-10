#!/usr/bin/env python3
"""Print row counts and date ranges per basin for all 24 DB tables."""

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
    "host":     os.getenv("DATABASE_HOST",     "localhost"),
    "port":     int(os.getenv("DATABASE_PORT", "5432")),
    "user":     os.getenv("DATABASE_USER",     "postgres"),
    "password": os.getenv("DATABASE_PASSWORD", "postgres"),
    "dbname":   os.getenv("DATABASE_NAME",     "postgres"),
}

TABLES = [
    "basin_watershed_7days", "basin_subbasin_l1_7days", "basin_subbasin_l2_7days",
    "basin_watershed_6months", "basin_subbasin_l1_6months", "basin_subbasin_l2_6months",
    "basin_watershed_daily_7days", "basin_watershed_daily_6months",
    "basin_subbasin_l1_daily_7days", "basin_subbasin_l1_daily_6months",
    "basin_subbasin_l2_daily_7days", "basin_subbasin_l2_daily_6months",
    "forecast_province_7days", "forecast_amphoe_7days", "forecast_tambon_7days",
    "forecast_province_6months", "forecast_amphoe_6months", "forecast_tambon_6months",
    "forecast_province_daily_7days", "forecast_province_daily_6months",
    "forecast_amphoe_daily_7days", "forecast_amphoe_daily_6months",
    "forecast_tambon_daily_7days", "forecast_tambon_daily_6months",
]

BASINS = [("Ping", "06"), ("Yom", "08")]


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    print(f"\n{'Table':<40} {'Basin':<6} {'Rows':>6}  {'Min date':<12}  {'Max date':<12}")
    print("-" * 82)
    for table in TABLES:
        for name, mb_code in BASINS:
            cur.execute(
                f"SELECT COUNT(*), MIN(date_sim), MAX(date_sim) FROM {table} WHERE mb_code = %s",
                (mb_code,)
            )
            count, min_d, max_d = cur.fetchone()
            print(f"{table:<40} {name:<6} {count:>6}  {str(min_d):<12}  {str(max_d):<12}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

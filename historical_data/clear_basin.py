#!/usr/bin/env python3
"""Delete all rows for one basin from all 24 DB tables.

Usage: python3 clear_basin.py [ping|yom]
"""

import sys
from _db import run

BASIN_CODES = {"ping": "06", "yom": "08"}

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


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in BASIN_CODES:
        print("Usage: python3 clear_basin.py [ping|yom]", file=sys.stderr)
        sys.exit(1)

    basin = sys.argv[1]
    mb_code = BASIN_CODES[basin]

    confirm = input(f"Delete ALL {basin.upper()} (mb_code={mb_code}) rows from all 24 tables? [y/N] ")
    if confirm.lower() != "y":
        print("Aborted.")
        sys.exit(0)

    def clear(cur):
        for table in TABLES:
            cur.execute(f"DELETE FROM {table} WHERE mb_code = %s", (mb_code,))
            print(f"  cleared {table}")

    run([clear])


if __name__ == "__main__":
    main()

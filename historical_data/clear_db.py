#!/usr/bin/env python3
"""Delete all rows for both basins from all 24 DB tables."""

from pathlib import Path
from _db import run

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


def clear_all(cur):
    for table in TABLES:
        cur.execute(f"DELETE FROM {table} WHERE mb_code IN ('06', '08')")
        print(f"  cleared {table}")


if __name__ == "__main__":
    run([clear_all])

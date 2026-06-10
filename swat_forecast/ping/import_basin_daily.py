#!/usr/bin/env python3
"""
Import daily SWAT results into DB (basin_*_daily_* tables).

Week model reads from:  week/Results/
  Bonwr_Daily.csv   → basin_watershed_daily_7days
  Sbonwr_Daily.csv  → basin_subbasin_l1_daily_7days

Month model reads from:  month/Results/
  Bonwr_Daily.csv   → basin_watershed_daily_6months
  Sbonwr_Daily.csv  → basin_subbasin_l1_daily_6months
"""

from pathlib import Path
from _db import copy_insert, parse_date, read_csv, run, to_int, to_num, zero_pad_mb, zero_pad_sb

ROOT = Path(__file__).parent

MODELS = {
    "7days":   ROOT / "week/Results",
    "6months": ROOT / "month/Results",
}

MB_CODES = ["06"]


def import_watershed(cur):
    for suffix, results_dir in MODELS.items():
        table = f"basin_watershed_daily_{suffix}"
        path = results_dir / "Bonwr_Daily.csv"
        print(f"\n  Bonwr_Daily.csv → {table}")
        if not path.exists():
            print(f"    SKIP: {path} not found")
            continue
        columns = ["date_sim", "mb_code", "mb_name_t",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        headers, raw = read_csv(path)
        rows = []
        for r in raw:
            row = dict(zip(headers, r))
            rows.append([
                parse_date(row["DateSim"]),
                zero_pad_mb(row["MB_CODE"]),
                row.get("MB_NAME_T")    or None,
                row.get("Rainfall")     or None,
                row.get("Reservoir")    or None,
                row.get("WaterSupply")  or None,
                row.get("WaterDemand")  or None,
                row.get("WaterBalance") or None,
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        cur.execute(f"DELETE FROM {table} WHERE mb_code = ANY(%s)", (MB_CODES,))
        copy_insert(cur, table, columns, rows)
        print(f"    ✓ {len(rows)} rows inserted")


def import_subbasin_l1(cur):
    for suffix, results_dir in MODELS.items():
        table = f"basin_subbasin_l1_daily_{suffix}"
        path = results_dir / "Sbonwr_Daily.csv"
        print(f"\n  Sbonwr_Daily.csv → {table}")
        if not path.exists():
            print(f"    SKIP: {path} not found")
            continue
        columns = ["date_sim", "sb_code", "sb_name_t", "mb_code", "mb_name_t",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        headers, raw = read_csv(path)
        if not raw:
            print(f"    SKIP: file is empty")
            continue
        rows = []
        for r in raw:
            row = dict(zip(headers, r))
            rows.append([
                parse_date(row["DateSim"]),
                zero_pad_sb(row["SB_CODE"]),
                row.get("SB_NAME_T")    or None,
                zero_pad_mb(row["MB_CODE"]),
                row.get("MB_NAME_T")    or None,
                row.get("Rainfall")     or None,
                row.get("Reservoir")    or None,
                row.get("WaterSupply")  or None,
                row.get("WaterDemand")  or None,
                row.get("WaterBalance") or None,
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        cur.execute(f"DELETE FROM {table} WHERE mb_code = ANY(%s)", (MB_CODES,))
        copy_insert(cur, table, columns, rows)
        print(f"    ✓ {len(rows)} rows inserted")


def import_subbasin_l2(cur):
    for suffix, results_dir in MODELS.items():
        table = f"basin_subbasin_l2_daily_{suffix}"
        path = results_dir / "Analysis_Sbswat.csv"
        print(f"\n  Analysis_Sbswat.csv → {table}")
        if not path.exists():
            print(f"    SKIP: {path} not found")
            continue
        columns = ["date_sim", "sbswat", "mb_code", "mb_name_t",
                   "rainfall", "reservoir", "watersupply",
                   "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
        headers, raw = read_csv(path)
        rows = []
        for r in raw:
            row = dict(zip(headers, r))
            rows.append([
                parse_date(row["DateSim"]),
                int(row["Sbswat"]),
                zero_pad_mb(row["MB_CODE"]),
                row.get("MB_NAME_T")    or None,
                row.get("Rainfall")     or None,
                row.get("Reservoir")    or None,
                row.get("WaterSupply")  or None,
                row.get("WaterDemand")  or None,
                row.get("WaterBalance") or None,
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        cur.execute(f"DELETE FROM {table} WHERE mb_code = ANY(%s)", (MB_CODES,))
        copy_insert(cur, table, columns, rows)
        print(f"    ✓ {len(rows)} rows inserted")


if __name__ == "__main__":
    run([import_watershed, import_subbasin_l1, import_subbasin_l2])

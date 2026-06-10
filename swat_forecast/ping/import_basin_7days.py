#!/usr/bin/env python3
"""
Import weekly SWAT results into DB (basin_*_7days tables).

Reads from:  week/Results/
  Bonwr_Weekly.csv           → basin_watershed_7days
  Sbonwr_Weekly.csv          → basin_subbasin_l1_7days
  Analysis_Sbswat_Weekly.csv → basin_subbasin_l2_7days
"""

from pathlib import Path
from _db import copy_insert, parse_date, read_csv, run, to_int, to_num, zero_pad_mb, zero_pad_sb

ROOT = Path(__file__).parent

BASINS = {
    "Ping": {"results_dir": ROOT / "week/Results", "mb_code": "06"},
}

MB_CODES = [cfg["mb_code"] for cfg in BASINS.values()]


def import_watershed(cur):
    print("\n[1/3] Bonwr_Weekly.csv → basin_watershed_7days")
    columns = ["date_sim", "mb_code", "mb_name_t",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Bonwr_Weekly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
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
        print(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM basin_watershed_7days WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "basin_watershed_7days", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


def import_subbasin_l1(cur):
    print("\n[2/3] Sbonwr_Weekly.csv → basin_subbasin_l1_7days")
    columns = ["date_sim", "sb_code", "sb_name_t", "mb_code", "mb_name_t",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Sbonwr_Weekly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        if not raw:
            print(f"  SKIP {basin}: file is empty")
            continue
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
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
        print(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM basin_subbasin_l1_7days WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "basin_subbasin_l1_7days", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


def import_subbasin_l2(cur):
    print("\n[3/3] Analysis_Sbswat_Weekly.csv → basin_subbasin_l2_7days")
    columns = ["date_sim", "sbswat", "mb_code", "mb_name_t",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Analysis_Sbswat_Weekly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
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
        print(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM basin_subbasin_l2_7days WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "basin_subbasin_l2_7days", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


if __name__ == "__main__":
    run([import_watershed, import_subbasin_l1, import_subbasin_l2])

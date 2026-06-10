#!/usr/bin/env python3
"""
Import weekly admin forecast CSVs into DB (forecast_*_7days tables).

Reads from:  week/Results/
  Province_Weekly.csv  → forecast_province_7days
  Amphoe_Weekly.csv    → forecast_amphoe_7days
  Tambol_Weekly.csv    → forecast_tambon_7days
"""

from pathlib import Path
from _db import copy_insert, parse_date, read_csv, run, to_int, to_num

ROOT = Path(__file__).parent

BASINS = {
    "Yom": {"results_dir": ROOT / "week/Results", "mb_code": "08"},
    # "Ping": {"results_dir": ROOT.parent / "ping/week/Results", "mb_code": "06"},
}

MB_CODES = [cfg["mb_code"] for cfg in BASINS.values()]


def import_province(cur):
    print("\n[1/3] Province_Weekly.csv → forecast_province_7days")
    columns = ["date_sim", "mb_code", "province_id", "province",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Province_Weekly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                parse_date(row["DateSim"]),
                cfg["mb_code"],
                str(row["Province_ID"]).strip(),
                row.get("Province") or None,
                to_num(row.get("Rainfall", "")),
                to_num(row.get("Reservoir", "")),
                to_num(row.get("WaterSupply", "")),
                to_num(row.get("WaterDemand", "")),
                to_num(row.get("WaterBalance", "")),
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        print(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM forecast_province_7days WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "forecast_province_7days", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


def import_amphoe(cur):
    print("\n[2/3] Amphoe_Weekly.csv → forecast_amphoe_7days")
    columns = ["date_sim", "mb_code", "amphoe_id", "amphoe", "province_id", "province",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Amphoe_Weekly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                parse_date(row["DateSim"]),
                cfg["mb_code"],
                str(row["Amphoe_ID"]).strip(),
                row.get("Amphoe") or None,
                str(row["Province_ID"]).strip(),
                row.get("Province") or None,
                to_num(row.get("Rainfall", "")),
                to_num(row.get("Reservoir", "")),
                to_num(row.get("WaterSupply", "")),
                to_num(row.get("WaterDemand", "")),
                to_num(row.get("WaterBalance", "")),
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        print(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM forecast_amphoe_7days WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "forecast_amphoe_7days", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


def import_tambon(cur):
    print("\n[3/3] Tambol_Weekly.csv → forecast_tambon_7days")
    columns = ["date_sim", "mb_code", "tambon_id", "tambon", "amphoe_id", "amphoe",
               "province_id", "province",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Tambol_Weekly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                parse_date(row["DateSim"]),
                cfg["mb_code"],
                str(row["Tambol_ID"]).strip(),
                row.get("Tambol") or None,
                str(row["Amphoe_ID"]).strip(),
                row.get("Amphoe") or None,
                str(row["Province_ID"]).strip(),
                row.get("Province") or None,
                to_num(row.get("Rainfall", "")),
                to_num(row.get("Reservoir", "")),
                to_num(row.get("WaterSupply", "")),
                to_num(row.get("WaterDemand", "")),
                to_num(row.get("WaterBalance", "")),
                to_int(row.get("DroughtIndex", "")),
                to_int(row.get("RunoffIndex", "")),
                to_num(row.get("WB_level", "")),
            ])
        print(f"  {basin}: {len(raw)} rows")

    cur.execute("DELETE FROM forecast_tambon_7days WHERE mb_code = ANY(%s)", (MB_CODES,))
    copy_insert(cur, "forecast_tambon_7days", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


if __name__ == "__main__":
    run([import_province, import_amphoe, import_tambon])

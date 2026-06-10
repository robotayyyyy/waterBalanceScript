#!/usr/bin/env python3
"""
Import monthly admin forecast CSVs into DB (forecast_*_6months tables).

Reads from:  yom/Results/ and ping/Results/
  Province_Monthly.csv → forecast_province_6months
  Amphoe_Monthly.csv   → forecast_amphoe_6months
  Tambol_Monthly.csv   → forecast_tambon_6months
"""

from pathlib import Path
from _db import copy_insert, read_csv, run, to_int, to_num, year_mon_to_date

ROOT = Path(__file__).parent
DATA_DIR = Path(__file__).parent

BASINS = {
    "Ping": {"results_dir": DATA_DIR / "ping", "mb_code": "06"},
    "Yom":  {"results_dir": DATA_DIR / "yom" , "mb_code": "08"},
}


def import_province(cur):
    print("\n[1/3] Province_Monthly.csv → forecast_province_6months")
    columns = ["date_sim", "mb_code", "province_id", "province",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Province_Monthly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                year_mon_to_date(row["YEAR"], row["MON"]),
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

    copy_insert(cur, "forecast_province_6months", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


def import_amphoe(cur):
    print("\n[2/3] Amphoe_Monthly.csv → forecast_amphoe_6months")
    columns = ["date_sim", "mb_code", "amphoe_id", "amphoe", "province_id", "province",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Amphoe_Monthly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                year_mon_to_date(row["YEAR"], row["MON"]),
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

    copy_insert(cur, "forecast_amphoe_6months", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


def import_tambon(cur):
    print("\n[3/3] Tambol_Monthly.csv → forecast_tambon_6months")
    columns = ["date_sim", "mb_code", "tambon_id", "tambon", "amphoe_id", "amphoe",
               "province_id", "province",
               "rainfall", "reservoir", "watersupply",
               "water_demand", "water_balance", "drought_index", "runoff_index", "wb_level"]
    all_rows = []

    for basin, cfg in BASINS.items():
        path = cfg["results_dir"] / "Tambol_Monthly.csv"
        if not path.exists():
            print(f"  SKIP {basin}: {path} not found")
            continue
        headers, raw = read_csv(path)
        for r in raw:
            row = dict(zip(headers, r))
            all_rows.append([
                year_mon_to_date(row["YEAR"], row["MON"]),
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

    copy_insert(cur, "forecast_tambon_6months", columns, all_rows)
    print(f"  ✓ {len(all_rows)} total rows inserted")


if __name__ == "__main__":
    run([import_province, import_amphoe, import_tambon])

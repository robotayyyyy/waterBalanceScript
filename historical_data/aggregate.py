#!/usr/bin/env python3
"""
Aggregate historical CSV chunks into master ping/ and yom/ directories.

Any subdir of historical_data/ that contains a ping/ or yom/ subdir is treated
as a chunk. All chunks are merged, sorted by date, deduplicated, and written to
the master historical_data/ping/ and historical_data/yom/ dirs.

Supports two date layouts found in SWAT outputs:
  - DateSim column  (DD/MM/YYYY)  — Daily and Weekly files
  - YEAR + MON columns            — Monthly files
"""

import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
BASINS = ["ping", "yom"]


def _sort_key(headers: list[str], row: list[str]):
    if "DateSim" in headers:
        idx = headers.index("DateSim")
        return datetime.strptime(row[idx].strip(), "%d/%m/%Y")
    if "YEAR" in headers and "MON" in headers:
        yi, mi = headers.index("YEAR"), headers.index("MON")
        return (int(row[yi]), int(row[mi]))
    return row[0]  # fallback: sort by first column as string


def find_chunk_dirs() -> list[Path]:
    return sorted(
        d for d in ROOT.iterdir()
        if d.is_dir()
        and d.name not in BASINS
        and any((d / b).is_dir() for b in BASINS)
    )


def aggregate():
    chunk_dirs = find_chunk_dirs()
    if not chunk_dirs:
        print("No chunk directories found — nothing to aggregate.")
        return

    print(f"Chunk dirs: {[d.name for d in chunk_dirs]}")

    for basin in BASINS:
        master_dir = ROOT / basin
        master_dir.mkdir(exist_ok=True)

        all_filenames: set[str] = set()
        for chunk in chunk_dirs:
            basin_dir = chunk / basin
            if basin_dir.is_dir():
                all_filenames.update(f.name for f in basin_dir.glob("*.csv"))

        if not all_filenames:
            continue

        print(f"\n  {basin}:")
        for filename in sorted(all_filenames):
            headers = None
            all_rows: list[list[str]] = []

            for chunk in chunk_dirs:
                path = chunk / basin / filename
                if not path.exists():
                    continue
                with open(path, encoding="utf-8-sig", newline="") as f:
                    reader = csv.reader(f)
                    file_headers = [h.strip() for h in next(reader)]
                    if headers is None:
                        headers = file_headers
                    for row in reader:
                        if any(c.strip() for c in row):
                            all_rows.append(row)

            if not all_rows or headers is None:
                continue

            all_rows.sort(key=lambda r: _sort_key(headers, r))

            seen: set[tuple] = set()
            unique_rows: list[list[str]] = []
            for row in all_rows:
                key = tuple(row)
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)

            out_path = master_dir / filename
            with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(unique_rows)

            n_chunks = sum(1 for c in chunk_dirs if (c / basin / filename).exists())
            print(f"    {filename}: {len(unique_rows)} rows from {n_chunks} chunk(s)")

    print("\nAggregation complete.")


if __name__ == "__main__":
    aggregate()

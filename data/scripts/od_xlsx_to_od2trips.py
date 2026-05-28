"""
Convert the hourly OD matrix produced by the OD-matrix pipeline
(OD-matrix-main/outputs/hourly_od_<City>.xlsx) into VISUM "O-format" matrix
files that SUMO's od2trips can read -- one file per hour, each carrying its own
time window.

The xlsx has one sheet per hour ("hour_0" .. "hour_23"). Each sheet is an
origin x destination matrix whose row index and column header are the TAZ ids
Z0..Zn-1 -- the SAME ids as the grid TAZ in larissa.taz.xml. Rows are origins,
columns are destinations.

Each output file looks like:

    $OR;D2
    * From-Time  To-Time
    8.00 9.00
    * Factor
    1.00
    Z0 Z1 3.50
    ...

Usage
-----
    python data/scripts/od_xlsx_to_od2trips.py \
        --xlsx OD-matrix-main/outputs/hourly_od_Larissa.xlsx \
        --out-dir data/od \
        --prefix larissa

"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def write_o_format(path: Path, matrix: pd.DataFrame, hour: int,
                   factor: float, drop_intrazonal: bool) -> int:
    """Write one hourly matrix as a VISUM O-format file. Returns #relations."""
    lines = [
        "$OR;D2",
        "* From-Time  To-Time",
        f"{hour:.2f} {hour + 1:.2f}",
        "* Factor",
        f"{factor:.2f}",
        "* Origin Dest Count",
    ]

    n_rel = 0
    origins = matrix.index.tolist()
    dests = matrix.columns.tolist()
    for o in origins:
        row = matrix.loc[o]
        for d in dests:
            if drop_intrazonal and o == d:
                continue
            amount = float(row[d])
            if amount <= 0.0:
                continue
            lines.append(f"{o} {d} {amount:.4f}")
            n_rel += 1

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n_rel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True, help="hourly_od_<City>.xlsx")
    parser.add_argument("--out-dir", required=True, help="Output directory for .od files.")
    parser.add_argument("--prefix", default="larissa", help="Output filename prefix.")
    parser.add_argument("--factor", type=float, default=1.0,
                        help="Global scaling factor written into each file.")
    parser.add_argument("--drop-intrazonal", action="store_true",
                        help="Skip origin==destination (within-zone) trips.")
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.exists():
        raise FileNotFoundError(f"xlsx not found: {xlsx_path}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    xls = pd.ExcelFile(xlsx_path)
    written = []
    grand_total = 0.0
    for hour in range(24):
        sheet = f"hour_{hour}"
        if sheet not in xls.sheet_names:
            print(f"  (skip {sheet}: not in workbook)")
            continue

        matrix = pd.read_excel(xls, sheet_name=sheet, index_col=0)
        out_path = out_dir / f"{args.prefix}_hour_{hour}.od"
        n_rel = write_o_format(out_path, matrix, hour, args.factor, args.drop_intrazonal)
        grand_total += matrix.values.sum()
        written.append(out_path)
        print(f"  {sheet}: {n_rel} OD relations -> {out_path.name}")

    if not written:
        raise RuntimeError("No hour_* sheets found in the workbook.")

    print(f"\nWrote {len(written)} O-format files. Matrix grand total "
          f"(all hours, before factor): {grand_total:,.0f} trips")
    print("\nFeed them to od2trips (PowerShell):")
    print(f'  $ods = ((0..23) | ForEach-Object {{ "{out_dir}\\{args.prefix}_hour_$_.od" }}) -join ","')
    print('  & "$env:SUMO_HOME\\bin\\od2trips.exe" '
          '-n data\\taz\\larissa.taz.xml -d $ods '
          '-o data\\routes\\larissa.odtrips.xml --ignore-errors')


if __name__ == "__main__":
    main()
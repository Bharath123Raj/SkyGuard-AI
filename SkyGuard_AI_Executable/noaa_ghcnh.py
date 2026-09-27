"""Prepare NOAA GHCNh Indian station PSV records for SkyGuard.

Example: python noaa_ghcnh.py --input GHCNh_INI0000VIDD_2024.psv
         --input GHCNh_INI0000VIDD_2025.psv --out noaa_safdarjung
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

COLS = {"temperature": "temperature", "pressure": "sea_level_pressure",
        "humidity": "relative_humidity"}
LIMITS = {"temperature": (-60, 60), "pressure": (850, 1100), "humidity": (0, 100)}
# NOAA's source 223 uses 1=good; any explicit other QC or derived-input flag
# is withheld from the candidate training/calibration reference sets.


def prepare(paths, out, station, train_end, cal_end, interval_minutes=180):
    if not 0 < interval_minutes < 1440 or 1440 % interval_minutes:
        raise ValueError("interval_minutes must divide 1440 (e.g. 180)")
    out = Path(out)
    parts = [pd.read_csv(path, sep="|", low_memory=False, dtype={"STATION": str}) for path in paths]
    data = pd.concat(parts, ignore_index=True)
    required = {"STATION", "DATE", *COLS.values(),
                *(name + "_Quality_Code" for name in COLS.values()),
                "relative_humidity_Measurement_Code"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"Missing NOAA PSV columns: {sorted(missing)}")
    data = data[data["STATION"] == station].copy()
    if data.empty:
        raise ValueError(f"No rows for {station}")
    data["timestamp"] = pd.to_datetime(data["DATE"], utc=True, errors="raise")
    # Keep the scheduled three-hour synoptic grid; interim reports have a
    # different reporting pattern and break the baseline detector's cadence.
    minute_of_day = data.timestamp.dt.hour * 60 + data.timestamp.dt.minute
    on_grid = minute_of_day.mod(interval_minutes).eq(0) & data.timestamp.dt.second.eq(0)
    off_grid_count = int((~on_grid).sum())
    data = data[on_grid].sort_values("timestamp")
    duplicates = int(data.timestamp.duplicated().sum())
    data = data.drop_duplicates("timestamp", keep="first")

    obs = pd.DataFrame({"timestamp": data.timestamp.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "station_id": station})
    for dest, source in COLS.items():
        obs[dest] = pd.to_numeric(data[source], errors="coerce").values
    bounds_ok = pd.Series(True, index=data.index)
    for dest, (minimum, maximum) in LIMITS.items():
        bounds_ok &= obs[dest].between(minimum, maximum).to_numpy()
    qc_ok = pd.Series(True, index=data.index)
    for source in COLS.values():
        flags = data[source + "_Quality_Code"].astype("string").str.strip()
        # Empty flag: no source flag. NOAA source 223 numeric code 1 = good.
        qc_ok &= (flags.isna() | flags.isin(["1", "1.0"]))
    rh_derived = data["relative_humidity_Measurement_Code"].astype("string").eq("D").fillna(False)
    train_cutoff = pd.Timestamp(train_end, tz="UTC")
    cal_cutoff = pd.Timestamp(cal_end, tz="UTC")
    if train_cutoff >= cal_cutoff:
        raise ValueError("train_end must precede cal_end")
    periods = {"train": data.timestamp < train_cutoff,
               "calibration": (data.timestamp >= train_cutoff) & (data.timestamp < cal_cutoff),
               "held_out": data.timestamp >= cal_cutoff}
    out.mkdir(parents=True, exist_ok=True)
    report = {"dataset": "NOAA GHCNh", "station_id": station,
              "input_files": [str(p) for p in paths], "interval_minutes": interval_minutes,
              "train_end_exclusive_utc": train_end, "calibration_end_exclusive_utc": cal_end,
              "off_grid_excluded": off_grid_count, "duplicate_timestamps_excluded": duplicates,
              "relative_humidity_derived_rows": int(rh_derived.sum()), "splits": {}}
    for name, mask in periods.items():
        # The held-out replay retains missing, implausible and NOAA-flagged
        # observations for inspection. These are NOT verified fault labels.
        selected = mask if name == "held_out" else mask & bounds_ok & qc_ok
        piece = obs.loc[selected.values].copy()
        piece.to_csv(out / f"{name}.csv", index=False)
        report["splits"][name] = {"raw_on_grid": int(mask.sum()),
                                  "written": int(len(piece)),
                                  "incomplete_or_outside_range": int((mask & ~bounds_ok).sum()),
                                  "noaa_qc_flagged": int((mask & ~qc_ok).sum()),
                                  "rh_derived": int((mask & rh_derived).sum())}
    (out / "audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("noaa_safdarjung"))
    parser.add_argument("--station", default="INI0000VIDD")
    parser.add_argument("--train-end", default="2025-01-01")
    parser.add_argument("--cal-end", default="2025-07-01")
    parser.add_argument("--interval-minutes", type=int, default=180)
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.out, args.station, args.train_end,
                             args.cal_end, args.interval_minutes), indent=2))


if __name__ == "__main__":
    main()

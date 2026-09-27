"""Check imported station coverage and candidate split dates before model training."""
import argparse
import json

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--interval-minutes", type=float, default=60)
    args = parser.parse_args()
    frame = pd.read_csv(args.input, dtype={"station_id": str})
    expected = {"timestamp", "station_id", "temperature", "pressure", "humidity", "qc_flags"}
    if not expected.issubset(frame.columns):
        parser.error(f"Input needs {sorted(expected)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values(["station_id", "timestamp"])
    reports = []
    for station, rows in frame.groupby("station_id"):
        values = rows[["temperature", "pressure", "humidity"]]
        valid = values.notna().all(axis=1) & rows["qc_flags"].fillna("").eq("")
        gaps = rows["timestamp"].diff().dt.total_seconds().div(60)
        reports.append({"station_id": station, "rows": len(rows),
                        "from_utc": rows["timestamp"].min().isoformat(),
                        "to_utc": rows["timestamp"].max().isoformat(),
                        "complete_and_in_range": int(valid.sum()),
                        "incomplete_or_out_of_range": int((~valid).sum()),
                        "gaps_over_1_5_intervals": int((gaps > 1.5*args.interval_minutes).sum()),
                        "median_interval_minutes": float(gaps.median()) if gaps.notna().any() else None})
    print(json.dumps({"source": args.input, "stations": reports,
                      "note": "Range/coverage checks cannot prove that training observations are fault-free."}, indent=2))


if __name__ == "__main__":
    main()

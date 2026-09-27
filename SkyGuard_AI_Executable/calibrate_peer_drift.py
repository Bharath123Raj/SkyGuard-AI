"""Calibrate a paired-station 24-hour drift check using prior reference dates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def load(path, expected_station):
    data = pd.read_csv(path)
    if set(data.station_id.dropna()) != {expected_station}:
        raise ValueError(f"Expected only station {expected_station} in {path}")
    data["ts"] = pd.to_datetime(data.timestamp, utc=True)
    return data.drop_duplicates("ts").sort_values("ts")


def calibrate(target_path, peer_path, model_path, output, target_station, peer_station):
    target = load(target_path, target_station)
    peer = load(peer_path, peer_station)
    bundle = joblib.load(model_path)  # use only a trusted locally generated model
    lag_count = int(round(24*60/bundle["interval_minutes"]))
    if lag_count < 2 or lag_count*bundle["interval_minutes"] != 24*60:
        raise ValueError("Expected cadence must divide 24 hours")
    joined = target.merge(peer, on="ts", suffixes=("_target", "_peer"))
    cutoffs = {}
    counts = {}
    valid_span = joined.ts.diff(lag_count).eq(pd.Timedelta(hours=24))
    for sensor in ("temperature", "pressure"):
        offset = joined[f"{sensor}_target"]-joined[f"{sensor}_peer"]
        diff = (offset-offset.shift(lag_count)).abs()[valid_span].dropna()
        if len(diff) < 200:
            raise ValueError(f"Insufficient paired reference changes for {sensor}")
        cutoffs[sensor] = float(np.quantile(diff, .999))
        counts[sensor] = len(diff)
    rule = {"target_station_id": target_station, "peer_station_id": peer_station,
            "lag_readings": lag_count, "offset_change_cutoffs": cutoffs,
            "reference_pairs": counts, "reference_quantile": .999,
            "reference_start_utc": joined.ts.min().isoformat(),
            "reference_end_utc": joined.ts.max().isoformat(),
            "method": "Absolute 24-hour change in simultaneous target-minus-peer value"}
    bundle["peer_drift_rule"] = rule
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output)
    return rule


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target-reference", required=True, type=Path)
    p.add_argument("--peer-reference", required=True, type=Path)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--output-model", required=True, type=Path)
    p.add_argument("--target-station", required=True)
    p.add_argument("--peer-station", required=True)
    a = p.parse_args()
    print(json.dumps(calibrate(a.target_reference, a.peer_reference, a.model, a.output_model,
                               a.target_station, a.peer_station), indent=2))


if __name__ == "__main__":
    main()

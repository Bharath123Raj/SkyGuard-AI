"""SkyGuard: causal, bounded-state quality control for three AWS measurements."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

SENSORS = ("temperature", "pressure", "humidity")
BOUNDS = {"temperature": (-60, 60), "pressure": (850, 1100), "humidity": (0, 100)}
FEATURES = [f"{s}_{v}" for s in SENSORS for v in ("delta", "six", "long")]
FEATURES += ["temperature_humidity_change", "temperature_pressure_change",
             "hour_sin", "hour_cos", "day_sin", "day_cos"]


def parse_time(value):
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("timestamp is missing")
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset, e.g. 2025-01-01T00:00:00Z")
    return timestamp.tz_convert("UTC")


def number(value):
    try:
        result = float(value)
        return result if np.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def normalize(row):
    timestamp = parse_time(row["timestamp"])
    return {"timestamp": timestamp, "station_id": str(row.get("station_id", "AWS-001")),
            **{s: number(row.get(s)) for s in SENSORS}}


@dataclass
class Station:
    history: deque = field(default_factory=lambda: deque(maxlen=144))
    last_time: object = None
    repeats: dict = field(default_factory=lambda: {s: 0 for s in SENSORS})
    recent_alerts: deque = field(default_factory=lambda: deque(maxlen=144))


def vector(row, history, scales):
    if len(history) < 6:
        return None
    out = []
    recent = list(history)[-6:]
    changes = {}
    for sensor in SENSORS:
        now = row[sensor]
        if now is None:
            return None
        lag = recent[-1][sensor]
        mid = float(np.median([item[sensor] for item in recent]))
        change = (now - lag) / scales[sensor]
        changes[sensor] = change
        long_mean = float(np.mean([item[sensor] for item in list(history)[-36:]]))
        out.extend([change, (now - mid) / scales[sensor], (now - long_mean) / scales[sensor]])
    out.extend([changes["temperature"] * changes["humidity"],
                changes["temperature"] * changes["pressure"]])
    ts = row["timestamp"]
    hour = ts.hour + ts.minute / 60
    day = ts.dayofyear
    out.extend([np.sin(2*np.pi*hour/24), np.cos(2*np.pi*hour/24),
                np.sin(2*np.pi*day/365.25), np.cos(2*np.pi*day/365.25)])
    return out


def read_csv(path):
    frame = pd.read_csv(path)
    required = {"timestamp", *SENSORS}
    if not required.issubset(frame.columns):
        raise ValueError(f"CSV must contain {sorted(required)}")
    rows = [normalize(row) for row in frame.to_dict("records")]
    rows.sort(key=lambda row: (row["station_id"], row["timestamp"]))
    return rows


def clean_vectors(rows, scales):
    histories = {}
    features = []
    for row in rows:
        state = histories.setdefault(row["station_id"], Station())
        valid = all(row[s] is not None and BOUNDS[s][0] <= row[s] <= BOUNDS[s][1] for s in SENSORS)
        contiguous = state.last_time is None or (row["timestamp"] - state.last_time) <= pd.Timedelta(minutes=20)
        if not contiguous:
            state.history.clear()
        if valid:
            v = vector(row, state.history, scales)
            if v is not None:
                features.append(v)
            state.history.append(row)
        else:
            state.history.clear()
        state.last_time = row["timestamp"]
    return np.asarray(features, dtype=float).reshape(-1, len(FEATURES))


def train(train_path, calibration_path, model_path):
    training = read_csv(train_path)
    calibration = read_csv(calibration_path)
    if not training or not calibration:
        raise ValueError("training and calibration files must contain observations")
    if max(r["timestamp"] for r in training) >= min(r["timestamp"] for r in calibration):
        raise ValueError("calibration must follow training in time")
    scales = {}
    for sensor in SENSORS:
        diffs = []
        prev = {}
        for row in training:
            old = prev.get(row["station_id"])
            if old and row[sensor] is not None and old[sensor] is not None and (row["timestamp"]-old["timestamp"]) <= pd.Timedelta(minutes=20):
                diffs.append(abs(row[sensor] - old[sensor]))
            prev[row["station_id"]] = row
        scales[sensor] = max(float(np.percentile(diffs, 90)) if diffs else 0, {"temperature": .15, "pressure": .08, "humidity": .8}[sensor])
    x_train = clean_vectors(training, scales)
    x_cal = clean_vectors(calibration, scales)
    if min(len(x_train), len(x_cal)) < 50:
        raise ValueError("need >=50 contiguous clean feature rows in each split")
    model = IsolationForest(n_estimators=120, max_samples=min(256, len(x_train)),
                            contamination="auto", random_state=42, n_jobs=-1).fit(x_train)
    # Quantile is chosen exclusively on subsequent clean reference observations.
    scores = -model.score_samples(x_cal)
    bundle = {"model": model, "scales": scales, "threshold": float(np.quantile(scores, .999)),
              "features": FEATURES, "calibration_rows": len(x_cal), "version": 1}
    joblib.dump(bundle, model_path)
    print(json.dumps({"model": str(model_path), "training_rows": len(x_train),
                      "calibration_rows": len(x_cal), "reference_score_threshold": bundle["threshold"]}, indent=2))


class Detector:
    def __init__(self, bundle, interval_minutes=10):
        if bundle.get("features") != FEATURES or bundle.get("version") != 1:
            raise ValueError("incompatible model bundle")
        self.bundle = bundle
        self.interval = pd.Timedelta(minutes=interval_minutes)
        self.stations = {}

    def process(self, raw, peers=None):
        row = normalize(raw)
        state = self.stations.setdefault(row["station_id"], Station())
        ts = row["timestamp"]
        if state.last_time is not None and ts <= state.last_time:
            raise ValueError("timestamps must increase strictly within each station")
        reasons = []
        sensors = []
        gap = state.last_time is not None and ts-state.last_time > 1.5*self.interval
        if gap:
            reasons.append("communication_gap")
            state.history.clear()
            state.repeats = {s: 0 for s in SENSORS}
        for s in SENSORS:
            v = row[s]
            if v is None:
                reasons.append(f"{s}:missing_or_nonfinite")
                sensors.append(s)
            elif not BOUNDS[s][0] <= v <= BOUNDS[s][1]:
                reasons.append(f"{s}:outside_physical_range")
                sensors.append(s)
        previous = state.history[-1] if state.history else None
        for s in SENSORS:
            v = row[s]
            state.repeats[s] = state.repeats[s]+1 if previous is not None and v is not None and v == previous[s] else 0
            if state.repeats[s] >= 5:
                reasons.append(f"{s}:frozen_6_readings")
                sensors.append(s)

        feature = vector(row, state.history, self.bundle["scales"]) if not gap else None
        score = float(-self.bundle["model"].score_samples([feature])[0]) if feature is not None else None
        threshold = self.bundle["threshold"]
        if score is not None and score > threshold:
            reasons.append("unusual_multivariate_temporal_pattern")
        residuals = {}
        if len(state.history) >= 6:
            for s in SENSORS:
                if row[s] is not None:
                    expected = float(np.median([h[s] for h in list(state.history)[-6:]]))
                    z = abs(row[s] - expected)/self.bundle["scales"][s]
                    residuals[s] = round(z, 2)
                    if z > 8 and score is not None and score > threshold:
                        reasons.append(f"{s}:abrupt_change")
                        sensors.append(s)
        # Optional peer observations are a separate input; only comparable readings count.
        peer_support = []
        if peers:
            for s in SENSORS:
                values = [number(p.get(s)) for p in peers if isinstance(p, dict)]
                values = [v for v in values if v is not None]
                if row[s] is not None and len(values) >= 2 and abs(row[s]-float(np.median(values))) <= 3*self.bundle["scales"][s]:
                    peer_support.append(s)
        hard = gap or any(":missing" in reason or ":outside" in reason or ":frozen" in reason for reason in reasons)
        large = [s for s, z in residuals.items() if z > 8]
        weather = len(large) >= 2 and all(s in peer_support for s in large) and not hard
        if weather:
            reasons.append("peer_corroborated_weather_change")
        elif len(large) >= 2 and not hard:
            reasons.append("coherent_change_unverified")
        fault = hard or (score is not None and score > threshold and not weather)
        classification = "normal"
        if fault:
            if gap:
                classification = "communication_gap"
            elif any(":missing" in r for r in reasons):
                classification = "missing_data"
            elif any(":outside" in r for r in reasons):
                classification = "invalid_reading"
            elif any(":frozen" in r for r in reasons):
                classification = "frozen_sensor"
            elif any(":abrupt_change" in r for r in reasons):
                classification = "spike_or_shift"
            else:
                classification = "unusual_pattern"
        elif weather:
            classification = "plausible_weather_event"
        affected = sorted(set(sensors))
        if fault and not affected:
            affected = large or list(SENSORS)
        suggestions = {}
        if fault and len(state.history) >= 6:
            for s in affected:
                suggestions[s] = round(float(np.median([h[s] for h in list(state.history)[-6:]])), 3)
        state.recent_alerts.append(int(fault))
        rate = sum(state.recent_alerts)/len(state.recent_alerts)
        health = "needs_inspection" if len(state.recent_alerts) >= 12 and rate >= .25 else "monitor" if fault else "healthy"
        severity = "high" if hard else "medium" if fault else "info"
        evidence_strength = round(min(.99, .5 + .08*len(reasons) + .03*max(residuals.values(), default=0)), 2) if fault else 0.0
        result = {"timestamp": ts.isoformat(), "station_id": row["station_id"],
                  **{s: row[s] for s in SENSORS}, "alert": fault, "classification": classification,
                  "severity": severity, "evidence_strength": evidence_strength,
                  "reasons": reasons, "affected_sensors": affected, "residual_scale_units": residuals,
                  "anomaly_score": round(score, 5) if score is not None else None,
                  "score_threshold": round(threshold, 5), "peer_support": peer_support,
                  "sensor_health": health, "suggested_values": suggestions}
        # Exclude invalid readings from future context; retain valid faults to detect sustained changes.
        if all(row[s] is not None and BOUNDS[s][0] <= row[s] <= BOUNDS[s][1] for s in SENSORS):
            state.history.append(row)
        else:
            state.history.clear()
        state.last_time = ts
        return result


def make_demo(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    n = 31*24*6
    t = np.arange(n)
    day = 2*np.pi*(t % 144)/144
    slow = 2*np.pi*t/(144*9)
    frame = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=n, freq="10min", tz="UTC").astype(str),
                          "station_id": "AWS-DEMO",
                          "temperature": 24 + 5*np.sin(day-.8) + 1.5*np.sin(slow) + rng.normal(0,.22,n),
                          "pressure": 1007 + 2*np.sin(slow+.4) + .35*np.sin(day+1) + rng.normal(0,.09,n),
                          "humidity": 66 - 13*np.sin(day-.8) + 4*np.sin(slow+1) + rng.normal(0,1.0,n)})
    train_end, cal_end = 20*144, 25*144
    frame.iloc[:train_end].to_csv(destination/"train.csv", index=False)
    frame.iloc[train_end:cal_end].to_csv(destination/"calibration.csv", index=False)
    test = frame.iloc[cal_end:].copy().reset_index(drop=True)
    test["injected_fault"] = False
    # Evaluation is illustrative: these synthetic faults must not be presented as real-world accuracy.
    for i, col, val in [(40,"temperature",18),(78,"humidity",130),(110,"pressure",-13),
                        (180,"humidity",np.nan),(280,"temperature",22)]:
        test.loc[i, col] = val
        test.loc[i,"injected_fault"] = True
    test.loc[350:357,"pressure"] = test.loc[349,"pressure"]
    test.loc[350:357,"injected_fault"] = True
    test.to_csv(destination/"replay.csv", index=False)
    print(f"Wrote train.csv, calibration.csv, replay.csv to {destination}")


def replay(detector, path, output):
    records = []
    for raw in pd.read_csv(path).to_dict("records"):
        out = detector.process(raw)
        if "injected_fault" in raw:
            out["injected_fault"] = bool(raw["injected_fault"])
        records.append(out)
    frame = pd.DataFrame(records)
    frame.to_csv(output, index=False)
    if "injected_fault" in frame:
        labels = frame["injected_fault"].astype(bool)
        alarms = frame["alert"].astype(bool)
        tp, fp, fn, tn = (int((alarms & labels).sum()), int((alarms & ~labels).sum()),
                          int((~alarms & labels).sum()), int((~alarms & ~labels).sum()))
        print(json.dumps({"type": "synthetic_demo_only", "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                          "precision": tp/(tp+fp) if tp+fp else 0, "recall": tp/(tp+fn) if tp+fn else 0,
                          "reference_false_alert_rate": fp/(fp+tn) if fp+tn else 0}, indent=2))
    print(f"Saved {len(frame)} observations to {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("generate-demo")
    demo.add_argument("--out", default="demo_data")
    fit = commands.add_parser("train")
    fit.add_argument("--train", required=True)
    fit.add_argument("--calibration", required=True)
    fit.add_argument("--model", default="skyguard.joblib")
    run = commands.add_parser("replay")
    run.add_argument("--input", required=True)
    run.add_argument("--model", default="skyguard.joblib")
    run.add_argument("--output", default="alerts.csv")
    live = commands.add_parser("stream")
    live.add_argument("--model", default="skyguard.joblib")
    args = parser.parse_args()
    if args.command == "generate-demo":
        make_demo(args.out)
    elif args.command == "train":
        train(args.train, args.calibration, args.model)
    else:
        detector = Detector(joblib.load(args.model))  # load only your own trusted model file
        if args.command == "replay":
            replay(detector, args.input, args.output)
        else:
            for line in sys.stdin:
                if line.strip():
                    try:
                        message = json.loads(line)
                        print(json.dumps(detector.process(message, message.get("peers"))), flush=True)
                    except (ValueError, KeyError, TypeError) as exc:
                        print(json.dumps({"error": str(exc)}), flush=True)


if __name__ == "__main__":
    main()

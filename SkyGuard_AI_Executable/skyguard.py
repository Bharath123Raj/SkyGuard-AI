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
from sklearn.linear_model import HuberRegressor

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
    last_rule_sensors: set = field(default_factory=set)
    peer_history: dict = field(default_factory=dict)
    peer_alert_timestamps: deque = field(default_factory=lambda: deque(maxlen=144))


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


def clean_vectors(rows, scales, interval_minutes=10):
    histories = {}
    features = []
    for row in rows:
        state = histories.setdefault(row["station_id"], Station())
        valid = all(row[s] is not None and BOUNDS[s][0] <= row[s] <= BOUNDS[s][1] for s in SENSORS)
        contiguous = state.last_time is None or (row["timestamp"] - state.last_time) <= pd.Timedelta(minutes=1.5*interval_minutes)
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


def contiguous_changes(rows, interval_minutes):
    """Use only valid, consecutive observations from the same station."""
    previous = {}
    changes = []
    for row in rows:
        old = previous.get(row["station_id"])
        if old is not None and row["timestamp"]-old["timestamp"] == pd.Timedelta(minutes=interval_minutes):
            if all(row[s] is not None and old[s] is not None and
                   BOUNDS[s][0] <= row[s] <= BOUNDS[s][1] and
                   BOUNDS[s][0] <= old[s] <= BOUNDS[s][1] for s in SENSORS):
                changes.append([row[s]-old[s] for s in SENSORS])
        previous[row["station_id"]] = row
    return np.asarray(changes, dtype=float).reshape(-1, len(SENSORS))


def calibrate_quality_rules(training, calibration, interval_minutes):
    """Fit coupling on training; set conservative cutoffs on later reference data."""
    train_changes = contiguous_changes(training, interval_minutes)
    cal_changes = contiguous_changes(calibration, interval_minutes)
    if min(len(train_changes), len(cal_changes)) < 50:
        raise ValueError("need >=50 contiguous changes to calibrate quality rules")
    coupling = HuberRegressor().fit(train_changes[:, [0]], train_changes[:, 2])
    rh_residual = cal_changes[:, 2] - coupling.predict(cal_changes[:, [0]])
    return {"pressure_step_hpa": float(np.quantile(abs(cal_changes[:, 1]), .999)),
            "temperature_humidity_residual_pp": float(np.quantile(abs(rh_residual), .999)),
            "humidity_delta_per_temperature_delta": float(coupling.coef_[0]),
            "humidity_delta_intercept": float(coupling.intercept_),
            "calibration_pairs": len(cal_changes), "reference_quantile": .999}


def train(train_path, calibration_path, model_path, interval_minutes=10):
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
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
            if old and row[sensor] is not None and old[sensor] is not None and (row["timestamp"]-old["timestamp"]) <= pd.Timedelta(minutes=1.5*interval_minutes):
                diffs.append(abs(row[sensor] - old[sensor]))
            prev[row["station_id"]] = row
        scales[sensor] = max(float(np.percentile(diffs, 90)) if diffs else 0, {"temperature": .15, "pressure": .08, "humidity": .8}[sensor])
    x_train = clean_vectors(training, scales, interval_minutes)
    x_cal = clean_vectors(calibration, scales, interval_minutes)
    if min(len(x_train), len(x_cal)) < 50:
        raise ValueError("need >=50 contiguous clean feature rows in each split")
    model = IsolationForest(n_estimators=120, max_samples=min(256, len(x_train)),
                            contamination="auto", random_state=42, n_jobs=-1).fit(x_train)
    # Quantile is chosen exclusively on subsequent clean reference observations.
    scores = -model.score_samples(x_cal)
    bundle = {"model": model, "scales": scales, "threshold": float(np.quantile(scores, .999)),
              "features": FEATURES, "calibration_rows": len(x_cal), "version": 1,
              "interval_minutes": interval_minutes,
              "quality_rules": calibrate_quality_rules(training, calibration, interval_minutes)}
    joblib.dump(bundle, model_path)
    print(json.dumps({"model": str(model_path), "training_rows": len(x_train),
                      "calibration_rows": len(x_cal), "reference_score_threshold": bundle["threshold"]}, indent=2))


class Detector:
    def __init__(self, bundle, interval_minutes=None):
        if bundle.get("features") != FEATURES or bundle.get("version") != 1:
            raise ValueError("incompatible model bundle")
        self.bundle = bundle
        self.interval = pd.Timedelta(minutes=interval_minutes or bundle.get("interval_minutes", 10))
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
        # Independent checks: a high model score is not required for an alert.
        # Coupling flags inconsistent changes but cannot identify which sensor
        # is faulty, especially when humidity is derived from temperature.
        rule_sensors = []
        rules = self.bundle.get("quality_rules")
        if rules and previous is not None and ts-previous["timestamp"] == self.interval:
            if all(row[s] is not None and previous[s] is not None and
                   BOUNDS[s][0] <= row[s] <= BOUNDS[s][1] and
                   BOUNDS[s][0] <= previous[s] <= BOUNDS[s][1] for s in SENSORS):
                p_change = row["pressure"]-previous["pressure"]
                if abs(p_change) > rules["pressure_step_hpa"]:
                    reasons.append("pressure:unusual_step")
                    rule_sensors.append("pressure")
                t_change = row["temperature"]-previous["temperature"]
                h_change = row["humidity"]-previous["humidity"]
                expected_h_change = (rules["humidity_delta_per_temperature_delta"]*t_change +
                                     rules["humidity_delta_intercept"])
                if abs(h_change-expected_h_change) > rules["temperature_humidity_residual_pp"]:
                    reasons.append("temperature_humidity:inconsistent_change")
                    rule_sensors.extend(["temperature", "humidity"])
                # A one-reading spike often returns to the prior trajectory on
                # the next sample. Report that return as context, not a second
                # incident, if the two-step net change fits the reference.
                if len(state.history) >= 2 and state.last_rule_sensors:
                    before_spike = state.history[-2]
                    if ts-before_spike["timestamp"] == 2*self.interval:
                        if "pressure" in rule_sensors and "pressure" in state.last_rule_sensors:
                            if abs(row["pressure"]-before_spike["pressure"]) <= rules["pressure_step_hpa"]:
                                rule_sensors.remove("pressure")
                                reasons.remove("pressure:unusual_step")
                                reasons.append("pressure:return_after_previous_alert")
                        if ("temperature" in rule_sensors and
                                {"temperature", "humidity"} <= state.last_rule_sensors):
                            net_t = row["temperature"]-before_spike["temperature"]
                            net_h = row["humidity"]-before_spike["humidity"]
                            net_expected = (rules["humidity_delta_per_temperature_delta"]*net_t +
                                            2*rules["humidity_delta_intercept"])
                            if abs(net_h-net_expected) <= rules["temperature_humidity_residual_pp"]:
                                rule_sensors = [s for s in rule_sensors if s not in ("temperature", "humidity")]
                                reasons.remove("temperature_humidity:inconsistent_change")
                                reasons.append("temperature_humidity:return_after_previous_alert")
        # Optional peer observations are a separate input; only comparable readings count.
        peer_support = []
        if peers:
            for s in SENSORS:
                values = [number(p.get(s)) for p in peers if isinstance(p, dict)]
                values = [v for v in values if v is not None]
                if row[s] is not None and len(values) >= 2 and abs(row[s]-float(np.median(values))) <= 3*self.bundle["scales"][s]:
                    peer_support.append(s)
        # Compare the change in target-minus-peer over a full 24-hour cycle.
        # Require an identified, same-time peer and the paired prior readings;
        # un-timestamped peers are only eligible for the older review cue.
        peer_rule_sensors = []
        peer_rule = self.bundle.get("peer_drift_rule")
        current_peer = None
        if peer_rule and row["station_id"] == peer_rule["target_station_id"] and peers:
            for item in peers:
                if not isinstance(item, dict) or item.get("station_id") != peer_rule["peer_station_id"]:
                    continue
                try:
                    candidate = normalize(item)
                except (ValueError, KeyError, TypeError):
                    continue
                if candidate["timestamp"] == ts and all(
                        candidate[s] is not None and BOUNDS[s][0] <= candidate[s] <= BOUNDS[s][1]
                        for s in SENSORS):
                    current_peer = candidate
                    break
            lag = pd.Timedelta(minutes=self.interval.total_seconds()/60*peer_rule["lag_readings"])
            old_target = next((h for h in reversed(state.history)
                               if h["timestamp"] == ts-lag), None)
            old_peer = next((h for h in reversed(state.peer_history.get(peer_rule["peer_station_id"], ()))
                             if h["timestamp"] == ts-lag), None)
            # An alerting reading is an untrusted reference. Comparing to it
            # again 24 hours later would echo the same incident as a new alert.
            if (current_peer and old_target and old_peer and not gap and
                    old_target["timestamp"] not in state.peer_alert_timestamps):
                for s, cutoff in peer_rule["offset_change_cutoffs"].items():
                    if row[s] is not None and BOUNDS[s][0] <= row[s] <= BOUNDS[s][1]:
                        divergence = (row[s]-current_peer[s])-(old_target[s]-old_peer[s])
                        if abs(divergence) > cutoff:
                            peer_rule_sensors.append(s)
                            reasons.append(f"{s}:24h_peer_divergence")
        sensors.extend(peer_rule_sensors)
        if rule_sensors and all(s in peer_support for s in rule_sensors):
            reasons.append("peer_corroborated_unusual_change")
            rule_sensors.clear()
        sensors.extend(rule_sensors)
        hard = gap or any(":missing" in reason or ":outside" in reason or ":frozen" in reason for reason in reasons)
        large = [s for s, z in residuals.items() if z > 8]
        weather = len(large) >= 2 and all(s in peer_support for s in large) and not hard
        if weather:
            reasons.append("peer_corroborated_weather_change")
        elif len(large) >= 2 and not hard:
            reasons.append("coherent_change_unverified")
        fault = hard or bool(rule_sensors) or bool(peer_rule_sensors) or (score is not None and score > threshold and not weather)
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
            elif "temperature_humidity:inconsistent_change" in reasons and rule_sensors:
                classification = "cross_sensor_inconsistency"
            elif "pressure:unusual_step" in reasons and rule_sensors:
                classification = "spike_or_shift"
            elif peer_rule_sensors:
                classification = "peer_divergence_review"
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
        if fault and current_peer is not None:
            state.peer_alert_timestamps.append(ts)
        state.last_rule_sensors = set(rule_sensors) if fault else set()
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
        if current_peer is not None:
            state.peer_history.setdefault(peer_rule["peer_station_id"], deque(maxlen=144)).append(current_peer)
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


def peer_lookup(path):
    if path is None:
        return {}
    data = pd.read_csv(path)
    required = {"timestamp", "station_id", *SENSORS}
    if not required.issubset(data.columns):
        raise ValueError(f"Peer CSV must contain {sorted(required)}")
    data["timestamp"] = pd.to_datetime(data.timestamp, utc=True).map(lambda ts: ts.isoformat())
    if data.timestamp.duplicated().any():
        raise ValueError("Peer CSV must have one observation per timestamp")
    return dict(zip(data.timestamp, data.to_dict("records")))


def replay(detector, path, output, peer_path=None):
    if detector.bundle.get("peer_drift_rule") and peer_path is None:
        raise ValueError("This paired-station model requires --peer-input for replay")
    peers = peer_lookup(peer_path)
    records = []
    for raw in pd.read_csv(path).to_dict("records"):
        ts = parse_time(raw["timestamp"]).isoformat()
        out = detector.process(raw, [peers[ts]] if ts in peers else None)
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
    fit.add_argument("--interval-minutes", type=float, default=10,
                     help="Expected reporting cadence (e.g. 60 for hourly observations)")
    run = commands.add_parser("replay")
    run.add_argument("--input", required=True)
    run.add_argument("--model", default="skyguard.joblib")
    run.add_argument("--output", default="alerts.csv")
    run.add_argument("--peer-input", type=Path, help="Same-time peer observations for a calibrated paired-station check")
    live = commands.add_parser("stream")
    live.add_argument("--model", default="skyguard.joblib")
    args = parser.parse_args()
    if args.command == "generate-demo":
        make_demo(args.out)
    elif args.command == "train":
        train(args.train, args.calibration, args.model, args.interval_minutes)
    else:
        detector = Detector(joblib.load(args.model))  # load only your own trusted model file
        if args.command == "replay":
            replay(detector, args.input, args.output, args.peer_input)
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

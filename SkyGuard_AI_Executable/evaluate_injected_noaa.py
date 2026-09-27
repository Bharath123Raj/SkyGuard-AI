"""Reproducible injected-fault benchmark on held-out NOAA observations.

The model is loaded without retraining. Metrics describe injected faults on a
NOAA weather background; unmodified readings are nominal, not verified clean.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from skyguard import BOUNDS, Detector, SENSORS, parse_time, peer_lookup


FAULT_TYPES = (
    "temperature_spike", "pressure_spike", "humidity_spike",
    "temperature_drift", "pressure_bias", "temperature_frozen",
    "missing_humidity", "invalid_humidity", "multivariate_corruption",
    "communication_gap",
)
LENGTHS = {"temperature_drift": 8, "pressure_bias": 6,
           "temperature_frozen": 6, "communication_gap": 2}


def eligible_anchors(frame, cadence_minutes):
    ts = pd.to_datetime(frame.timestamp, utc=True)
    valid = pd.Series(True, index=frame.index)
    for sensor in SENSORS:
        valid &= pd.to_numeric(frame[sensor], errors="coerce").between(*BOUNDS[sensor])
    candidates = []
    for i in range(40, len(frame)-20):
        segment = slice(i-6, i+15)
        if valid.iloc[segment].all() and ts.iloc[segment].diff().iloc[1:].eq(pd.Timedelta(minutes=cadence_minutes)).all():
            candidates.append(i)
    return candidates


def choose_events(frame, seed, per_type, cadence_minutes):
    rng = np.random.default_rng(seed)
    choices = eligible_anchors(frame, cadence_minutes)
    if not choices:
        raise ValueError("No contiguous, valid windows for injection")
    ordered_kinds = rng.permutation(list(FAULT_TYPES)*per_type)
    anchors = []
    events = []
    for index, kind in enumerate(ordered_kinds, 1):
        available = [i for i in choices if all(abs(i-other) >= 22 for other in anchors)]
        if not available:
            raise ValueError("Cannot fit isolated events: lower --events-per-type")
        i = int(rng.choice(available))
        anchors.append(i)
        events.append({"event_id": f"E{index:03d}", "fault_type": str(kind), "anchor": i,
                       "length": LENGTHS.get(kind, 1),
                       "start_timestamp_utc": frame.loc[i, "timestamp"]})
    return events


def inject(frame, events):
    out = frame.copy()
    out["injected_fault"] = False
    out["fault_type"] = ""
    out["injected_event_id"] = ""
    dropped = set()
    for event in events:
        i, kind, length = event["anchor"], event["fault_type"], event["length"]
        affected = list(range(i, i+length))
        if kind == "temperature_spike":
            out.loc[i, "temperature"] += 12 if out.loc[i, "temperature"] <= 43 else -12
        elif kind == "pressure_spike":
            out.loc[i, "pressure"] += 12
        elif kind == "humidity_spike":
            out.loc[i, "humidity"] += 40 if out.loc[i, "humidity"] <= 60 else -40
        elif kind == "temperature_drift":
            out.loc[affected, "temperature"] += np.arange(1, length+1, dtype=float)
        elif kind == "pressure_bias":
            out.loc[affected, "pressure"] += 5
        elif kind == "temperature_frozen":
            out.loc[affected, "temperature"] = out.loc[i-1, "temperature"]
        elif kind == "missing_humidity":
            out.loc[i, "humidity"] = np.nan
        elif kind == "invalid_humidity":
            out.loc[i, "humidity"] = 125.0
        elif kind == "multivariate_corruption":
            out.loc[i, "temperature"] += 10
            out.loc[i, "pressure"] += 8
            out.loc[i, "humidity"] += 35 if out.loc[i, "humidity"] <= 65 else -35
        elif kind == "communication_gap":
            # Missing scheduled observation has no row to score. Label the
            # following received observation, where the gap is first visible.
            dropped.add(i)
            affected = [i+1]
        else:
            raise ValueError(kind)
        out.loc[affected, "injected_fault"] = True
        out.loc[affected, "fault_type"] = kind
        out.loc[affected, "injected_event_id"] = event["event_id"]
        event["scored_timestamp_utc"] = frame.loc[affected[0], "timestamp"]
        event["last_labeled_timestamp_utc"] = frame.loc[affected[-1], "timestamp"]
        event["labeled_readings"] = len(affected)
        event["omitted_timestamp_utc"] = frame.loc[i, "timestamp"] if kind == "communication_gap" else ""
    out = out.drop(index=list(dropped)).reset_index(drop=True)
    return out


def process(frame, bundle, peers=None):
    detector = Detector(bundle)
    output = []
    for row in frame.to_dict("records"):
        ts = parse_time(row["timestamp"]).isoformat()
        result = detector.process(row, [peers[ts]] if peers and ts in peers else None)
        for key in ("injected_fault", "fault_type", "injected_event_id"):
            if key in row:
                result[key] = row[key]
        output.append(result)
    return pd.DataFrame(output)


def ratio(numerator, denominator):
    return float(numerator/denominator) if denominator else None


def evaluate(original, altered, events, bundle, peers=None):
    baseline = process(original, bundle, peers)
    trial = process(altered, bundle, peers)
    baseline_alerts = baseline.set_index("timestamp")["alert"]
    trial["baseline_alert_same_time"] = trial.timestamp.map(baseline_alerts).fillna(False).astype(bool)
    trial["new_alert_vs_baseline"] = trial.alert.astype(bool) & ~trial.baseline_alert_same_time
    label = trial.injected_fault.astype(bool)
    alarm = trial.alert.astype(bool)
    tp = int((label & alarm).sum())
    fp = int((~label & alarm).sum())
    fn = int((label & ~alarm).sum())
    tn = int((~label & ~alarm).sum())
    precision = ratio(tp, tp+fp)
    recall = ratio(tp, tp+fn)
    report = {"scope": "injected_faults_on_observed_NOAA_weather; NOT verified field accuracy",
              "nominal_negative_assumption": "Unmodified NOAA readings are treated as negative only for this benchmark; some could contain unknown faults or extreme weather.",
              "seed": None,
              "model_retrained": False,
              "confusion_matrix_nominal": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
              "point_metrics_nominal": {"accuracy": ratio(tp+tn, len(trial)),
                                        "precision": precision, "recall": recall,
                                        "f1": ratio(2*tp, 2*tp+fp+fn)},
              "baseline_alerts": int(baseline.alert.sum()),
              "baseline_alert_rate": ratio(int(baseline.alert.sum()), len(baseline)),
              "trial_non_injected_alerts": fp,
              "trial_non_injected_alert_rate": ratio(fp, int((~label).sum())),
              "trial_new_alerts_outside_injected_rows": int((~label & trial.new_alert_vs_baseline).sum()),
              "note": "Point accuracy is strongly affected by the many nominal negatives. Event recall and alert burden are also reported."}
    by_event = []
    for event in events:
        rows = trial[trial.injected_event_id == event["event_id"]]
        alarms = rows[rows.alert]
        attributable = rows[rows.new_alert_vs_baseline]
        start = pd.Timestamp(event["start_timestamp_utc"])
        by_event.append({**event, "detected": bool(len(alarms)),
                         "new_detection_vs_baseline": bool(len(attributable)),
                         "first_alert_delay_hours": round((pd.Timestamp(alarms.iloc[0].timestamp)-start).total_seconds()/3600, 2) if len(alarms) else None,
                         "first_new_alert_delay_hours": round((pd.Timestamp(attributable.iloc[0].timestamp)-start).total_seconds()/3600, 2) if len(attributable) else None,
                         "baseline_alerts_in_event": int(rows.baseline_alert_same_time.sum()),
                         "alerted_labeled_readings": int(rows.alert.sum())})
    event_frame = pd.DataFrame(by_event)
    report["events"] = {"total": int(len(event_frame)),
                        "detected": int(event_frame.detected.sum()),
                        "event_recall": ratio(int(event_frame.detected.sum()), len(event_frame)),
                        "new_detections_vs_baseline": int(event_frame.new_detection_vs_baseline.sum()),
                        "incremental_event_recall": ratio(int(event_frame.new_detection_vs_baseline.sum()), len(event_frame)),
                        "median_first_new_alert_delay_hours": float(event_frame.first_new_alert_delay_hours.median()) if event_frame.first_new_alert_delay_hours.notna().any() else None}
    report["fault_types"] = []
    for kind, group in event_frame.groupby("fault_type"):
        report["fault_types"].append({"fault_type": kind, "events": len(group),
                                      "detected": int(group.detected.sum()),
                                      "new_detections_vs_baseline": int(group.new_detection_vs_baseline.sum()),
                                      "median_new_delay_hours": float(group.first_new_alert_delay_hours.median()) if group.first_new_alert_delay_hours.notna().any() else None})
    return baseline, trial, event_frame, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--events-per-type", type=int, default=4)
    p.add_argument("--peer-input", type=Path, help="Same-time reference station CSV; required for paired-station model")
    a = p.parse_args()
    if a.events_per_type < 1:
        p.error("--events-per-type must be positive")
    original = pd.read_csv(a.input).reset_index(drop=True)
    bundle = joblib.load(a.model)  # load only a trusted local model
    if bundle.get("peer_drift_rule") and a.peer_input is None:
        p.error("--peer-input is required by this paired-station model")
    peers = peer_lookup(a.peer_input)
    cadence = int(bundle.get("interval_minutes", 180))
    events = choose_events(original, a.seed, a.events_per_type, cadence)
    trial_input = inject(original, events)
    baseline, trial, event_frame, report = evaluate(original, trial_input, events, bundle, peers)
    report["seed"] = a.seed
    report["model_path"] = str(a.model)
    report["source_replay_path"] = str(a.input)
    report["peer_input_path"] = str(a.peer_input) if a.peer_input else None
    a.output_dir.mkdir(parents=True, exist_ok=True)
    trial_input.to_csv(a.output_dir/"injected_replay.csv", index=False)
    baseline.to_csv(a.output_dir/"baseline_alerts.csv", index=False)
    trial.to_csv(a.output_dir/"injected_alerts.csv", index=False)
    event_frame.to_csv(a.output_dir/"events.csv", index=False)
    (a.output_dir/"metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(a.output_dir), "events": report["events"],
                      "point_metrics_nominal": report["point_metrics_nominal"]}, indent=2))


if __name__ == "__main__":
    main()

"""Describe unmodified NOAA alerts without assigning unverified fault labels."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

import pandas as pd


def category(reasons, row):
    if any(":missing" in reason or ":outside_physical_range" in reason for reason in reasons):
        return "incomplete_or_outside_range"
    if "communication_gap" in reasons:
        return "scheduled_report_gap"
    if "humidity:frozen_6_readings" in reasons and row.humidity == 100:
        return "repeated_100_percent_humidity"
    if any(":frozen_6_readings" in reason for reason in reasons):
        return "repeated_value_other"
    if any(":24h_peer_divergence" in reason for reason in reasons):
        return "peer_change_disagreement"
    if any(":unusual_step" in reason or ":inconsistent_change" in reason for reason in reasons):
        return "calibrated_change_check"
    if "unusual_multivariate_temporal_pattern" in reasons:
        return "isolation_forest_pattern"
    return "other"


def audit(alert_path, output_path):
    readings = pd.read_csv(alert_path)
    flagged = readings[readings.alert.astype(bool)].copy()
    flagged["review_category"] = [category(ast.literal_eval(row.reasons), row)
                                  for row in flagged.itertuples()]
    cols = ["timestamp", "station_id", "classification", "review_category",
            "temperature", "pressure", "humidity", "reasons", "anomaly_score"]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    flagged[cols].to_csv(output_path, index=False)
    counts = flagged.review_category.value_counts().to_dict()
    summary = {"source": str(alert_path), "observations": len(readings),
               "baseline_alerts": len(flagged), "baseline_alert_rate": len(flagged)/len(readings),
               "by_category": counts,
               "objective_data_quality_rows": counts.get("incomplete_or_outside_range", 0),
               "proven_sensor_faults": 0,
               "note": "Categories describe evidence for review, not confirmed fault labels. Unmodified NOAA rows are nominal negatives only in the injection benchmark. Missing values are objective data-quality problems; a report gap does not prove a communication hardware failure. Repeated 100% relative humidity may be genuine saturation."}
    output_path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alerts", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(audit(a.alerts, a.output), indent=2))


if __name__ == "__main__":
    main()

"""Aggregate deterministic injected-fault evaluations from multiple seeds."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd


def safe_div(a, b):
    return a/b if b else None


def summarize(directories, output_dir, target_station="Safdarjung", status=None, period="July–December 2025"):
    runs = [json.loads((Path(d)/"metrics.json").read_text(encoding="utf-8")) for d in directories]
    seeds = [run["seed"] for run in runs]
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be distinct")
    counts = Counter()
    for run in runs:
        counts.update(run["confusion_matrix_nominal"])
    tp, fp, fn, tn = (counts[x] for x in ("tp", "fp", "fn", "tn"))
    events = pd.concat([pd.read_csv(Path(d)/"events.csv").assign(seed=s)
                        for d, s in zip(directories, seeds)], ignore_index=True)
    by_type = []
    for name, group in events.groupby("fault_type"):
        by_type.append({"fault_type": name, "events": len(group),
                        "detected": int(group.detected.sum()),
                        "new_detections_vs_baseline": int(group.new_detection_vs_baseline.sum()),
                        "incremental_event_recall": safe_div(int(group.new_detection_vs_baseline.sum()),len(group))})
    status = status or ("Development comparison: July–December 2025 observations and earlier benchmark runs were examined before these checks were finalized. An untouched period is still needed.")
    summary = {"scope": f"Injected faults on {target_station} NOAA observations from {period} at three seeds; not field validation",
               "evaluation_status": status,
               "seeds": seeds, "runs": len(runs), "events": len(events),
               "event_recall": safe_div(int(events.detected.sum()),len(events)),
               "incremental_event_recall": safe_div(int(events.new_detection_vs_baseline.sum()),len(events)),
               "new_event_detections_vs_baseline": int(events.new_detection_vs_baseline.sum()),
               "confusion_matrix_pooled_nominal": dict(counts),
               "point_metrics_pooled_nominal": {
                   "accuracy": safe_div(tp+tn,tp+fp+fn+tn),
                   "always_normal_accuracy": safe_div(fp+tn,tp+fp+fn+tn),
                   "precision": safe_div(tp,tp+fp),
                   "recall": safe_div(tp,tp+fn),
                   "f1": safe_div(2*tp,2*tp+fp+fn)},
               "baseline_alert_rate_per_run": runs[0]["baseline_alert_rate"],
               "per_fault_type": by_type,
               "cautions": ["Unmodified NOAA rows are only nominal negatives, not verified healthy sensors.",
                            "Repeated seeds reuse the same station and dates; observations are not independent.",
                            "NOAA relative humidity at these stations is derived, so humidity-sensor faults cannot be field-validated.",
                            "These metrics apply to the fixed injected severities, not all possible faults."]}
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    rows=[f"# SkyGuard: {target_station} injected-fault comparison", "",
          f"**{status}** The Isolation Forest and temperature–humidity relation were fitted on 2024 Safdarjung observations. The model and peer-change cutoffs used January–June 2025 reference observations only. Three seeds place 40 known edits each on {period} observations at {target_station}. NOAA relative humidity is derived, not an independent sensor reading.", "",
          "## Results", "",
          "| Metric | Result | Meaning |", "| --- | ---: | --- |",
          f"| Incremental event recall | {summary['new_event_detections_vs_baseline']}/{summary['events']} = {summary['incremental_event_recall']:.1%} | An event caused at least one alert absent at that time in the unmodified replay |",
          f"| Point precision (nominal) | {summary['point_metrics_pooled_nominal']['precision']:.1%} | Of trial alerts, share at injected/marked readings; unmodified rows assumed normal |",
          f"| Point recall | {summary['point_metrics_pooled_nominal']['recall']:.1%} | Share of altered/marked readings alerted, including early steps of drift/frozen events |",
          f"| Point F1 (nominal) | {summary['point_metrics_pooled_nominal']['f1']:.1%} | Harmonic mean of nominal precision and point recall |",
          f"| Point accuracy (nominal) | {summary['point_metrics_pooled_nominal']['accuracy']:.1%} | Dominated by unmodified readings, not field accuracy |",
          f"| Always-normal accuracy | {summary['point_metrics_pooled_nominal']['always_normal_accuracy']:.1%} | Trivial comparator that never detects a fault |",
          f"| Unmodified background alert rate | {summary['baseline_alert_rate_per_run']:.2%} | Original NOAA readings alerted; true fault status unknown |",
          "", "## Event recall by injected fault", "",
          "| Fault type | New detections / injected events |", "| --- | ---: |"]
    rows += [f"| {f['fault_type']} | {f['new_detections_vs_baseline']}/{f['events']} |" for f in by_type]
    rows += ["", "**Interpretation:** Compare the per-fault rows rather than relying on pooled accuracy. Returns after an injected fault can cause additional alerts outside its labeled window; those remain in nominal false positives. A gap alert occurs on the next received reading, and does not prove a physical communications failure.", "",
             "NOAA relative humidity is derived from temperature and dew point, so injected edits can create an artificially inconsistent relation. The optional paired-station check compares simultaneous station readings with an earlier pair; peer disagreement needs human review and cannot identify the faulty station. Metrics on edited observations do not establish accuracy on real sensor failures.", "",
             "## Limits and next experiment", "",
             "Every injected location, magnitude, fault window and seed is recorded in each run's `events.csv`; `injected_replay.csv` and `injected_alerts.csv` allow reproduction. The nominal confusion matrix in `summary.json` treats unmodified records as negative despite unknown field truth. Different seeds share one period and are not independent station validation. Do not tune on these evaluation rows and then reuse them as a fresh test: for an improved detector, design changes on separate development data and reserve another untouched date range or station."]
    (output_dir/"INJECTED_EVAL.md").write_text("\n".join(rows)+"\n",encoding="utf-8")
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,action="append",required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--target-station",default="Safdarjung")
    p.add_argument("--period",default="July–December 2025")
    p.add_argument("--status",help="Exact evaluation status to show in dashboard and report")
    a=p.parse_args()
    result=summarize(a.run,a.output_dir,a.target_station,a.status,a.period)
    print(json.dumps({"events":result["events"],"incremental_event_recall":result["incremental_event_recall"],
                      "point_metrics_pooled_nominal":result["point_metrics_pooled_nominal"]},indent=2))


if __name__=="__main__":
    main()

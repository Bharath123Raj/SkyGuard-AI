"""Run with: python -m streamlit run dashboard.py"""
import argparse
import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATASETS = {
    "Observed NOAA · Safdarjung 2026": ROOT / "noaa_2026/safdarjung/alerts.csv",
    "Observed NOAA · Delhi airport 2026": ROOT / "noaa_2026/airport/alerts.csv",
    "Injected demonstration · Safdarjung seed 42": ROOT / "noaa_2026/safdarjung/injected_eval_seed42/injected_alerts.csv",
}
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--data", default=None, help="Optional server-side local CSV; never supplied by public visitors")
args, _ = parser.parse_known_args()

st.set_page_config(page_title="SkyGuard AI", page_icon="🌦️", layout="wide")
st.title("SkyGuard AI | Weather station quality monitor")
st.caption("Historical observation replay; this page is not a live AWS feed.")
available = {label: file for label, file in DATASETS.items() if file.is_file()}
requested = None
if args.data:
    supplied = Path(args.data).expanduser()
    requested = (supplied if supplied.is_absolute() else Path.cwd() / supplied).resolve()
    if requested.is_file() and requested not in {p.resolve() for p in available.values()}:
        available["Custom CSV supplied by server operator"] = requested
if not available:
    st.error("No observation replay files were found in this deployment.")
    st.stop()
default_label = next((label for label, file in available.items()
                      if requested is not None and file.resolve() == requested), next(iter(available)))
label = st.sidebar.selectbox("Dataset", list(available), index=list(available).index(default_label))
path = available[label]
if label.startswith("Injected demonstration") or (label.startswith("Custom") and "injected" in path.name):
    st.warning("This is an injected-fault demonstration: values were edited in software, not verified hardware failures.")
frame = pd.read_csv(path)
source_metadata = path.parent / "source.json"
if source_metadata.exists():
    source = json.loads(source_metadata.read_text(encoding="utf-8"))
    st.info(f"{source['source']} · {source['station_name']}. "
            "Relative humidity here is derived from temperature and dew point. "
            "Alerts have not been confirmed as sensor faults.")
frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
station = st.sidebar.selectbox("Station", sorted(frame["station_id"].unique()))
part = frame.loc[frame["station_id"] == station].sort_values("timestamp")
total, alerts = len(part), int(part["alert"].sum())
c1, c2, c3 = st.columns(3)
c1.metric("Observations", total)
c2.metric("Alerts", alerts)
c3.metric("Latest sensor health", str(part.iloc[-1]["sensor_health"]))
st.subheader("Measurements")
st.line_chart(part.set_index("timestamp")[["temperature", "pressure", "humidity"]])
st.subheader("Anomaly score and calibrated reference threshold")
st.line_chart(part.set_index("timestamp")[["anomaly_score", "score_threshold"]])
st.subheader("Alerts and evidence")
columns = ["timestamp", "classification", "severity", "evidence_strength", "affected_sensors",
           "reasons", "suggested_values", "sensor_health"]
st.dataframe(part.loc[part["alert"], columns].iloc[::-1], use_container_width=True)
if "injected_fault" in part.columns:
    st.subheader("Injected-fault replay")
    st.caption("Known software edits to NOAA readings. Labels identify injected rows only; unmodified readings are not verified healthy sensors.")
    marked = part.injected_fault.astype(str).str.lower().isin(["true", "1"])
    alarm = part.alert.astype(bool)
    m1, m2, m3 = st.columns(3)
    m1.metric("Injected or marked readings", int(marked.sum()))
    m2.metric("Injected readings alerted", int((marked & alarm).sum()))
    m3.metric("Alerts on unmodified readings", int((~marked & alarm).sum()))
    metric_path = Path(path).parent / "metrics.json"
    if metric_path.exists():
        run = json.loads(metric_path.read_text(encoding="utf-8"))
        event = run.get("events", {})
        st.caption(f"New event detections vs unmodified replay: {event.get('new_detections_vs_baseline', '?')}/{event.get('total', '?')}. This run uses seed {run.get('seed', '?')}.")
    demo_columns = [c for c in ["timestamp", "injected_event_id", "fault_type",
                                "injected_fault", "alert", "classification", "reasons"] if c in part.columns]
    st.dataframe(part.loc[marked | alarm, demo_columns], use_container_width=True)
audit_path = Path(path).parent / "alert_audit.summary.json"
if audit_path.exists():
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    st.subheader("Unmodified alert audit")
    st.caption(f"{audit['baseline_alerts']} alerts; {audit['objective_data_quality_rows']} involve a missing or out-of-range observation. Other categories need review; none are confirmed sensor-fault labels.")
    st.dataframe(pd.DataFrame([{"review_category": k, "alerts": v} for k, v in
                               audit["by_category"].items()]), use_container_width=True)
review_path = Path(path).parent / "alert_review.csv"
if review_path.exists():
    review = pd.read_csv(review_path)
    st.subheader("Nearby station context for review")
    st.caption("Peer agreement and NOAA quality flags help review alerts; they do not confirm sensor faults.")
    st.dataframe(review[["time_ist", "skyguard_classification", "station_temperature_c",
                         "peer_temperature_c", "station_sea_level_pressure_hpa",
                         "peer_sea_level_pressure_hpa", "station_relative_humidity_pct",
                         "peer_relative_humidity_pct", "review_note"]],
                 use_container_width=True)
benchmark_path = Path(path).parent / "injected_benchmark" / "summary.json"
if benchmark_path.exists():
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    st.subheader("Injected-fault benchmark")
    if benchmark.get("evaluation_status"):
        st.warning(benchmark["evaluation_status"])
    st.caption("Three seeds on one NOAA station and the same held-out dates. Unmodified readings are nominal negatives, not verified fault-free observations. These are not field-accuracy metrics.")
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Newly detected events", f"{benchmark['new_event_detections_vs_baseline']}/{benchmark['events']}")
    b2.metric("Event recall", f"{benchmark['incremental_event_recall']:.1%}")
    b3.metric("Nominal point precision", f"{benchmark['point_metrics_pooled_nominal']['precision']:.1%}")
    b4.metric("Point recall", f"{benchmark['point_metrics_pooled_nominal']['recall']:.1%}")
    st.caption(f"Nominal point accuracy: {benchmark['point_metrics_pooled_nominal']['accuracy']:.1%}; always predicting normal: {benchmark['point_metrics_pooled_nominal']['always_normal_accuracy']:.1%}.")
    st.caption(f"Alerts on unmodified reference replay: {benchmark['baseline_alert_rate_per_run']:.2%} of rows. These alerts are not independently labeled as sensor faults.")
    st.dataframe(pd.DataFrame(benchmark["per_fault_type"]), use_container_width=True)
st.caption("Evidence strength is a heuristic severity cue, not a calibrated probability. Suggested values do not replace raw measurements.")

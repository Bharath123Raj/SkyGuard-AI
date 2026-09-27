"""Run with: streamlit run dashboard.py -- --data alerts.csv"""
import argparse
from pathlib import Path

import pandas as pd
import streamlit as st

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--data", default=str(Path(__file__).resolve().parent / "alerts.csv"))
args, _ = parser.parse_known_args()

st.set_page_config(page_title="SkyGuard AI", page_icon="🌦️", layout="wide")
st.title("SkyGuard AI | Weather station quality monitor")
path = st.sidebar.text_input("Alert CSV", args.data)
if not Path(path).exists():
    st.info("Run the replay command first, then enter the path to its alerts.csv output.")
    st.stop()
frame = pd.read_csv(path)
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
st.caption("Evidence strength is a heuristic severity cue, not a calibrated probability. Suggested values do not replace raw measurements.")

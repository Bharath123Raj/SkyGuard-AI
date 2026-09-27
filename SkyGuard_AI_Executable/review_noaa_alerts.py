"""Join SkyGuard alerts to original NOAA QC and a nearby GHCNh station.

This produces review evidence, NOT true fault labels or precision/recall.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

FIELDS = ("temperature", "sea_level_pressure", "relative_humidity")


def load_station(path):
    d = pd.read_csv(path, sep="|", low_memory=False)
    d["ts"] = pd.to_datetime(d.DATE, utc=True)
    return d.drop_duplicates("ts").set_index("ts").sort_index()


def value(row, name):
    if row is None:
        return None
    v = row.get(name)
    return float(v) if pd.notna(v) else None


def change(now, before, name):
    a, b = value(now, name), value(before, name)
    return round(a - b, 2) if a is not None and b is not None else None


def agrees(a, b, minimum):
    return a is not None and b is not None and abs(a) >= minimum and abs(b) >= minimum and a*b > 0


def build(alerts_path, station_path, peer_path, output):
    alerts = pd.read_csv(alerts_path)
    alerts["ts"] = pd.to_datetime(alerts.timestamp, utc=True)
    alerts = alerts.set_index("ts").sort_index()
    station = load_station(station_path)
    peer = load_station(peer_path)
    rows = []
    for ts, hit in alerts[alerts.alert].iterrows():
        prev_ts = ts - pd.Timedelta(hours=3)
        here = station.loc[ts] if ts in station.index else None
        there = peer.loc[ts] if ts in peer.index else None
        prev_here = station.loc[prev_ts] if prev_ts in station.index else None
        prev_there = peer.loc[prev_ts] if prev_ts in peer.index else None
        # Original PSV values, not provisional values suggested by SkyGuard.
        item = {"timestamp_utc": ts.isoformat(), "time_ist": ts.tz_convert("Asia/Kolkata").isoformat(),
                "skyguard_classification": hit.classification,
                "skyguard_reasons": hit.reasons,
                "station_previous_3h_present": prev_here is not None,
                "peer_same_time_present": there is not None,
                "peer_previous_3h_present": prev_there is not None}
        for name, short in (("temperature", "temperature_c"),
                            ("sea_level_pressure", "sea_level_pressure_hpa"),
                            ("relative_humidity", "relative_humidity_pct")):
            item["station_"+short] = value(here, name)
            item["peer_"+short] = value(there, name)
            item["station_change_3h_"+short] = change(here, prev_here, name)
            item["peer_change_3h_"+short] = change(there, prev_there, name)
            item["station_"+name+"_qc"] = str(here[name+"_Quality_Code"]) if here is not None and pd.notna(here[name+"_Quality_Code"]) else ""
            item["peer_"+name+"_qc"] = str(there[name+"_Quality_Code"]) if there is not None and pd.notna(there[name+"_Quality_Code"]) else ""
        t = agrees(item["station_change_3h_temperature_c"], item["peer_change_3h_temperature_c"], 2)
        rh = agrees(item["station_change_3h_relative_humidity_pct"],
                    item["peer_change_3h_relative_humidity_pct"], 5)
        item["peer_correlated_temperature_and_rh_change"] = bool(t and rh)
        item["station_rh_derived"] = bool(here is not None and here.get("relative_humidity_Measurement_Code") == "D")
        if hit.classification == "communication_gap":
            item["review_note"] = "Scheduled station report absent before this row; check archive and transmission logs."
        elif hit.classification == "missing_data":
            item["review_note"] = "Station RH absent; check source dew point/temperature and QC."
        elif t and rh:
            item["review_note"] = "Both sites changed in the same temperature/RH directions; review weather and local differences."
        else:
            item["review_note"] = "Review local observation, peer and weather context."
        rows.append(item)
    frame = pd.DataFrame(rows)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    summary = {"alerts": int(len(frame)),
               "classifications": frame.skyguard_classification.value_counts().to_dict(),
               "peer_same_time_available": int(frame.peer_same_time_present.sum()),
               "unusual_pattern_with_correlated_peer_temp_and_rh": int((frame.skyguard_classification.eq("unusual_pattern") & frame.peer_correlated_temperature_and_rh_change).sum()),
               "confirmed_fault_labels": 0}
    output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--alerts", required=True)
    p.add_argument("--station", required=True, help="Original Safdarjung NOAA PSV file")
    p.add_argument("--peer", required=True, help="Original airport NOAA PSV file")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    print(json.dumps(build(a.alerts, a.station, a.peer, a.output), indent=2))


if __name__ == "__main__":
    main()

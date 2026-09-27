# Paired-station drift check and 2026 evaluation

## Design and data separation

The revised detector retains the Safdarjung 2024 Isolation Forest and its
January–June 2025 calibration. Its optional peer check measures the 24-hour
change in the target-minus-peer temperature or sea-level pressure. Cutoffs
(99.9th percentile) were calculated on paired, quality-filtered Safdarjung
and Delhi airport records from January–June 2025: **5.1408 °C** and
**4.8944 hPa**, respectively. The peer reading must have a matching timestamp
and station ID. Peer disagreement prompts review; it does not establish which
station is faulty. The single-station model still runs without a peer, but
will not gain the new drift check in that case.

The airport served as a new target for the July–December 2025 benchmark, but
its observations had already appeared in peer review on those same dates.
After that run, a fault echo was found: an alerting observation could be used
as the comparison reference 24 hours later and create another alert. The
detector now excludes already alerted observations from that paired reference.
On that **development rerun**, the airport's nominal point precision changed
from **49.8% to 70.7%**, with point recall **67.9%**. These are development
figures and cannot be presented as untouched validation.

After freezing that fix, both stations' **January 1–September 24, 2026** NOAA
files were downloaded and replayed without changing the model or cutoffs.
Three recorded seeds inject 40 events each into copies of each target station.
The same two stations share regional weather; seeds also share dates, so these
are not independent fault histories.

| First frozen-model 2026 result | Safdarjung | Delhi airport |
| --- | ---: | ---: |
| New injected events detected | 116/120 (96.7%) | 115/120 (95.8%) |
| Temperature drift events | 12/12 | 12/12 |
| Pressure bias events | 12/12 | 12/12 |
| Nominal point precision | 45.6% | 39.6% |
| Point recall | 71.6% | 66.0% |
| Nominal point accuracy | 94.0% | 93.1% |
| Always-predict-normal accuracy | 94.8% | 94.9% |
| Alerts on unmodified 2026 observations | 89/2,069 (4.30%) | 99/2,125 (4.66%) |

**Conclusion:** Peer comparison improves gradual-fault *event detection* for
the injected severities. The unchanged 2026 data produced many more ordinary
alerts than the 2025 development period; the detector did **not** achieve 80%
point precision or 80% point recall. In fact, nominal accuracy is lower than
the always-normal comparator in both 2026 replays. Changing thresholds using
these results and then presenting the same 2026 rows as fresh validation would
be misleading.

An audit of the unmodified-data alerts explains part of the nominal precision
burden without relabeling the benchmark. See [`ALERT_AUDIT.md`](ALERT_AUDIT.md)
and each station's per-alert `alert_audit.csv`.

Point precision is **nominal**: the evaluation marks unmodified NOAA rows as
negative despite no technician-confirmed fault labels. Artificial edits can
break relationships that do not represent real faults. NOAA relative humidity
here is derived from temperature and dew point, not an independent humidity
sensor. These data are three-hourly archived observations, not direct IMD AWS
measurements. The 2026 files and SHA-256 hashes are in each station's
`source.json`; raw files remain in `raw/`. Peer observations used in detection
were exactly aligned by timestamp and recorded in each run's `metrics.json`.

## Open the observed-data dashboard on Windows

From `SkyGuard_AI_Executable` after `python -m pip install -r requirements.txt`:

```powershell
python -m streamlit run dashboard.py -- --data noaa_2026/safdarjung/alerts.csv
```

To see the airport as the target, replace the final data path with
`noaa_2026/airport/alerts.csv`. Both show the 2026 benchmark with an evaluation
status message. To reproduce a baseline replay with the paired input:

```powershell
python skyguard.py replay --input noaa_2026/safdarjung/held_out.csv --model noaa_safdarjung/skyguard_noaa_v3_peer.joblib --peer-input noaa_2026/airport/held_out.csv --output noaa_2026/safdarjung/alerts.csv
```

Keep the 2026 results fixed as a recorded test. For a stronger SIH claim,
obtain independent AWS records with confirmed faults and simultaneous
same-unit neighboring station values; reserve another untouched period or
network for any subsequent rule changes.

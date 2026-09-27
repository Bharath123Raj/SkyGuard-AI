# SkyGuard AI — executable AWS anomaly detector

For the included observed Indian station data and runnable replay, start with
[NOAA_DATA.md](NOAA_DATA.md). For future authorized IMD AWS imports, see
[REAL_DATA.md](REAL_DATA.md).

SkyGuard monitors **temperature (°C), atmospheric pressure (hPa), relative humidity (%)** per Automatic Weather Station. It combines a clean-history Isolation Forest with calibrated pressure-step and temperature–humidity change checks, plus physical-range, missing-reading, exact-repeat and communication-gap checks. It emits a JSON evidence record for every observation, including an alert, tentative fault type, severity, sensor health and optional reversible suggested values. It supports an optional peer-station check and a Streamlit dashboard.

The paired-station development and the later, frozen-model 2026 evaluation are
documented in [noaa_2026/PEER_DIVERGENCE_EVAL.md](noaa_2026/PEER_DIVERGENCE_EVAL.md).
For a short walkthrough using the observed and injected 2026 replays, see
[DEMO_GUIDE.md](DEMO_GUIDE.md).
For GitHub and Streamlit Community Cloud, see
[DEPLOY_GITHUB.md](DEPLOY_GITHUB.md). The hosted app defaults to observed
2026 Safdarjung records; the injected replay is an explicitly labeled option.

## Quick start

Use Python 3.10+ in a terminal (Windows PowerShell commands shown):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python skyguard.py generate-demo --out demo_data
python skyguard.py train --train demo_data/train.csv --calibration demo_data/calibration.csv --model skyguard.joblib
python skyguard.py replay --input demo_data/replay.csv --model skyguard.joblib --output alerts.csv
streamlit run dashboard.py -- --data alerts.csv
```

On macOS/Linux, use `python3 -m venv .venv`, `source .venv/bin/activate` and `python` for the rest. The dashboard prints a local URL. Replay writes one row per observation; its summary prints a **synthetic demonstration** confusion matrix, precision, recall, and false-alert rate.

## Your own data

Supply `train.csv`, `calibration.csv`, and optionally `replay.csv` with `timestamp,station_id,temperature,pressure,humidity`. Timestamps require UTC offsets; e.g. `2025-01-01T00:00:00Z`. Training and calibration should contain clean observations at approximately 10-minute intervals. Calibration must be strictly later than training. Each contiguous partition needs at least 56 observations; use substantially more across seasons in practice. Never train or calibrate on the evaluation period. `station_id` can be omitted for a single station.

```csv
timestamp,station_id,temperature,pressure,humidity
2025-01-01T00:00:00Z,AWS-001,24.1,1008.2,61.0
```

CSV replay is ordered by station and time. For a live feed, pipe one JSON object per line into `python skyguard.py stream --model skyguard.joblib`:

```json
{"timestamp":"2025-02-01T00:00:00Z","station_id":"AWS-001","temperature":26.1,"pressure":1007.3,"humidity":70.2,"peers":[{"temperature":25.9,"pressure":1007.4,"humidity":71},{"temperature":26.3,"pressure":1007.2,"humidity":69}]}
```

Stream mode writes one JSON result per line. It maintains bounded in-memory state per station. A process restart clears recent context, so allow six readings to warm up the model again; range and missing checks work immediately. Configure the upstream source to report lost intervals: the gap is flagged on the *next* received reading. Upstream ingestion, durable state, authentication, hardware interface, and ESP32 deployment are beyond this Python prototype.

## How decisions are made

The Isolation Forest learns temporal changes from the training split. A later candidate clean calibration split determines the 99.9th percentile reference score cutoff. New models also fit a robust temperature–humidity change relation on training data and calibrate independent pressure-step and cross-sensor residual cutoffs on that same later reference split. Those checks can alert below the Isolation Forest cutoff. A cross-sensor discrepancy alone cannot identify which of the two measurements is faulty. The alert policy also checks missing/nonfinite values, broad physical limits, a fixed value for six readings, and communication gaps. The optional 24-hour paired-station check compares change in target-minus-peer values using identified, same-time peer observations; it flags disagreement for review rather than proving which station failed. Two nearby peers with comparable values for each changed sensor can support a plausible meteorological event; this is a simple optional corroboration rule, not a spatially trained model. No peer input means there is no proof that a sudden coherent change is real weather.

`evidence_strength` is a bounded heuristic derived from reasons and change magnitude; **it is not a calibrated confidence probability**. `suggested_values` are medians of the last six local valid readings, appropriate as provisional placeholders for isolated faults, not for fast-changing weather. Keep originals and require review before using an estimate downstream. `sensor_health` moves to `needs_inspection` when >=25% of at least 12 recent observations alerted. This is a maintenance cue, not a validated remaining-life prediction. The rule `frozen_6_readings` assumes a 10-minute cadence; quiet physical sensors can naturally repeat with low-precision readings. Tune to actual instrument resolution.

## Evaluation and limitations

The generated test set contains injected spikes, invalid/missing readings and a frozen segment. It is deliberately separate in time from training and calibration, but shares the same simulated weather generator. Its metrics are **not operational field accuracy**, not an unbiased benchmark for all faults, and not a guarantee of 95% precision. To make a real claim, reserve untouched dates and stations, collect genuine technician-confirmed faults and true severe weather, report event-level recall and delay by fault type, false alarms per station-day, and results on Indian AWS stations. Domain shift from Jena or simulated weather to Indian locations must be evaluated independently. For a known station with a very different local climate, train and calibrate an appropriate separate model. You can replace the standalone Isolation Forest with the existing Step-8 bundle once its feature schema and stream parity are verified; this example makes no claim to reproduce that benchmark.

See [USE_CASES.md](USE_CASES.md) for example behavior and [skyguard.py](skyguard.py) for the complete implementation.

# SkyGuard on observed Indian station data

## Included observations

This package includes 2024 and 2025 NOAA GHCNh records for **Safdarjung,
India** (`INI0000VIDD`; 28.5845 N, 77.2058 E). The unchanged downloaded
pipe-separated source files are in `noaa_safdarjung/raw/`. Their source URLs,
retrieval date, and SHA-256 hashes are recorded in `noaa_safdarjung/source.json`.
NOAA's [GHCNh product page](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly)
and [format documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf)
describe this collection. NOAA timestamps are UTC. `temperature` is °C,
`sea_level_pressure` is hPa, and `relative_humidity` is a whole percent.

**Critical distinction:** This is observed weather-station data collected from
multiple sources, not a verified feed of raw IMD AWS sensor signals. At this
station, the RH measurement code is `D`: NOAA derives RH from air temperature
and dew point. Consequently, this replay cannot measure detection accuracy for
humidity-sensor faults. Do not describe its RH as an independent sensor input.

The station reports predominantly every **three hours**. We selected the 00,
03, 06, 09, 12, 15, 18, and 21 UTC reporting grid and set the detector interval
to 180 minutes. The importer preserved original PSV files and wrote:

| File | Period and use |
| --- | --- |
| `noaa_safdarjung/train.csv` | 2024, quality-filtered candidate reference |
| `noaa_safdarjung/calibration.csv` | January–June 2025, quality-filtered reference |
| `noaa_safdarjung/held_out.csv` | July–December 2025, scheduled-grid replay observations |
| `noaa_safdarjung/skyguard_noaa.joblib` | Model fitted on the first two files |
| `noaa_safdarjung/alerts.csv` | Replay output for the held-out period |
| `noaa_safdarjung/audit.json` | Split counts, missing/range checks and NOAA QC exclusions |
| `noaa_safdarjung/alert_review.csv` | Per-alert Safdarjung and nearby airport values, QC flags and three-hour changes |

The training and calibration filter excludes incomplete readings, broad
out-of-range values, and rows where NOAA supplied a quality code other than
blank or `1` for the three inputs. This is a conservative **candidate clean**
reference, not proof every retained reading is fault-free. The held-out CSV
retains flagged or missing observations and has **no fault labels**. Do not
calculate precision or recall by treating NOAA's flags as confirmed sensor
failures.

## Run in Windows PowerShell

Extract the ZIP. In PowerShell, change to its inner `SkyGuard_AI_Executable`
folder, then install dependencies and open the included real-observation replay:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run dashboard.py -- --data noaa_safdarjung/alerts.csv
```

To reproduce the conversion, train the **revised** model, and replay from the bundled NOAA PSV files:

```powershell
python noaa_ghcnh.py --input noaa_safdarjung/raw/GHCNh_INI0000VIDD_2024.psv --input noaa_safdarjung/raw/GHCNh_INI0000VIDD_2025.psv --out noaa_safdarjung
python skyguard.py train --train noaa_safdarjung/train.csv --calibration noaa_safdarjung/calibration.csv --model noaa_safdarjung/skyguard_noaa_v2.joblib --interval-minutes 180
python skyguard.py replay --input noaa_safdarjung/held_out.csv --model noaa_safdarjung/skyguard_noaa_v2.joblib --output noaa_safdarjung/improved/alerts.csv
python -m streamlit run dashboard.py -- --data noaa_safdarjung/improved/alerts.csv
```

The original `skyguard_noaa.joblib` and its benchmark are retained as a baseline.
Current `skyguard.py train` creates the revised model; do not overwrite the baseline
file if you want to reproduce the original comparison.

The 2025 held-out replay contains **1,434** readings and **21 alerts**:
9 communication gaps, 2 missing-data alerts, and 10 unusual-pattern alerts.
These are model/rule outputs only. We have not established how many are genuine
faults or severe meteorological events. Each reported `evidence_strength` is a
heuristic, not a probability.

See [`noaa_safdarjung/ALERT_REVIEW.md`](noaa_safdarjung/ALERT_REVIEW.md) for
the first peer-station review. The peer file is bundled under `peer_raw/`;
its source URL and checksum are in `source.json`. The review does not assign
fault labels or alter detector thresholds.

## Injected-fault benchmark

The next step is included in [`noaa_safdarjung/injected_benchmark/INJECTED_EVAL.md`](noaa_safdarjung/injected_benchmark/INJECTED_EVAL.md).
It **loads the already-trained model** and edits only copies of the July–December
2025 replay. Ten fault types are placed four times each for three recorded seeds.
It keeps baseline NOAA alerts separate so that a pre-existing alert does not
automatically count as evidence that an injection was detected. Results and
per-fault counts appear in the dashboard below the peer review table.

To reproduce the default seed from the existing model:

```powershell
python evaluate_injected_noaa.py --input noaa_safdarjung/held_out.csv --model noaa_safdarjung/skyguard_noaa.joblib --output-dir noaa_safdarjung/injected_eval --seed 42 --events-per-type 4
```

Additional runs in the ZIP use seeds `3101` and `2026`; their folders include
`events.csv`, `injected_replay.csv`, `injected_alerts.csv`, and `metrics.json`.
The aggregate `summary.json` identifies its assumptions. **An injected value
is a known modification, but an unmodified archived reading is not a
confirmed healthy sensor.** Thus benchmark accuracy and precision are
conditional on nominal negative labels and are not verified real-world fault
accuracy. The humidity data are derived, so humidity injections test software
behavior, not physical humidity sensor detection.

## Next validation step

The optional paired-station drift check and its later 2026 frozen-model test
are reported in [`noaa_2026/PEER_DIVERGENCE_EVAL.md`](noaa_2026/PEER_DIVERGENCE_EVAL.md).
The 2026 test caught most injected events but **did not reach 80% nominal point
precision or recall**. The 2026 source files, conversion outputs, calibrated
peer bundles and both dashboards are included. When running a paired model,
provide `--peer-input` for same-time observations from its configured peer.

The development comparison and commands for the revised detector are in
[`noaa_safdarjung/improved/IMPROVEMENTS.md`](noaa_safdarjung/improved/IMPROVEMENTS.md).
The July–December 2025 replay had already been examined when these checks were
added, so its revised results are **development metrics**, not an untouched
final test. Temperature drift is still a known gap.

Review alert times against station logs, maintenance records, independent
stations and reports of extreme weather. Obtain an authorized IMD AWS history
with directly measured temperature, pressure and humidity plus technician
confirmed incidents to test sensor-fault classification. Keep the NOAA model
separate: its station, observation sources and three-hour cadence differ from
the intended live IMD AWS network.

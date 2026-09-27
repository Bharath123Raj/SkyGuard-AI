# SkyGuard: development comparison on injected NOAA faults

**Development result, not a fresh held-out result.** The July–December 2025 background and original benchmark were already inspected before the new checks were designed. An independent period or station is still needed. The Isolation Forest was trained on 2024 Safdarjung observations. Both its threshold and the new independent step/change checks were calibrated on January–June 2025, with temperature–humidity coupling fitted on 2024. Three fixed seeds place 40 known events each on July–December 2025.

## Results

| Metric | Result | Meaning |
| --- | ---: | --- |
| Incremental event recall | 102/120 = 85.0% | An event caused at least one alert absent at that time in the unmodified replay |
| Point precision (nominal) | 59.5% | Of trial alerts, share at injected/marked readings; unmodified rows assumed normal |
| Point recall | 37.7% | Share of altered/marked readings alerted, including early steps of drift/frozen events |
| Point F1 (nominal) | 46.1% | Harmonic mean of nominal precision and point recall |
| Point accuracy (nominal) | 93.4% | Dominated by unmodified readings, not field accuracy |
| Always-normal accuracy | 92.4% | Trivial comparator that never detects a fault |
| Unmodified background alert rate | 1.60% | Original NOAA readings alerted; true fault status unknown |

## Event recall by injected fault

| Fault type | New detections / injected events |
| --- | ---: |
| communication_gap | 12/12 |
| humidity_spike | 12/12 |
| invalid_humidity | 11/12 |
| missing_humidity | 12/12 |
| multivariate_corruption | 12/12 |
| pressure_bias | 7/12 |
| pressure_spike | 12/12 |
| temperature_drift | 0/12 |
| temperature_frozen | 12/12 |
| temperature_spike | 12/12 |

**Interpretation:** The independent calibrated rules improve spike detection in this development comparison. Temperature drift remains a blind spot. A return to normal after a one-reading spike can itself trigger an additional alert outside the labeled injection window; those alerts remain in the nominal false-positive count. The gap alert occurs on the *next received reading*, not at the missing timestamp. Source gaps do not prove a physical communication fault.

Safdarjung NOAA relative humidity is calculated from temperature and dew point; injected temperature/humidity changes can break that derived relationship in ways real sensor faults may not. This benchmark measures response to software edits, not actual humidity-sensor faults. The airport peer review is separate and did not change these decisions.

## Limits and next experiment

Every injected location, magnitude, fault window and seed is recorded in each run's `events.csv`; `injected_replay.csv` and `injected_alerts.csv` allow reproduction. The nominal confusion matrix in `summary.json` treats unmodified records as negative despite unknown field truth. Different seeds share one period and are not independent station validation. Do not tune on these evaluation rows and then reuse them as a fresh test: for an improved detector, design changes on separate development data and reserve another untouched date range or station.

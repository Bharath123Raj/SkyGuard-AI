# SkyGuard: injected faults on observed NOAA weather

The Isolation Forest model was trained on 2024 Safdarjung observations and calibrated on January–June 2025. It was **not retrained** for these tests. The replay background is July–December 2025. Three fixed seeds place 40 known injected events each (120 placements total) on the same background.

## Results

| Metric | Result | Meaning |
| --- | ---: | --- |
| Incremental event recall | 62/120 = 51.7% | An event caused at least one alert absent at that time in the unmodified replay |
| Point precision (nominal) | 56.1% | Of trial alerts, share at injected/marked readings; unmodified rows assumed normal |
| Point recall | 24.1% | Share of altered/marked readings alerted, including early steps of drift/frozen events |
| Point F1 (nominal) | 33.7% | Harmonic mean of nominal precision and point recall |
| Point accuracy (nominal) | 92.8% | Dominated by unmodified readings, not field accuracy |
| Always-normal accuracy | 92.4% | Trivial comparator that never detects a fault |
| Unmodified background alert rate | 1.46% | 21/1,434 original NOAA readings alerted; true fault status unknown |

## Event recall by injected fault

| Fault type | New detections / injected events |
| --- | ---: |
| communication_gap | 12/12 |
| humidity_spike | 0/12 |
| invalid_humidity | 11/12 |
| missing_humidity | 12/12 |
| multivariate_corruption | 11/12 |
| pressure_bias | 2/12 |
| pressure_spike | 0/12 |
| temperature_drift | 0/12 |
| temperature_frozen | 12/12 |
| temperature_spike | 2/12 |

**Interpretation:** The rules reliably expose missing values, invalid humidity, frozen temperature and omitted scheduled records at these injection severities. The model misses many ordinary single-sensor spikes, pressure bias and temperature drift. The gap alert occurs on the *next received reading*, not at the missing timestamp. Source gaps do not prove a physical communication fault.

The Safdarjung NOAA source contains derived relative humidity. Humidity injections here test the software's response to edited values, not detection of real humidity-sensor failures. The airport peer review is separate and did not change detector decisions.

## Limits and next experiment

Every injected location, magnitude, fault window and seed is recorded in each run's `events.csv`; `injected_replay.csv` and `injected_alerts.csv` allow reproduction. The nominal confusion matrix in `summary.json` treats unmodified records as negative despite unknown field truth. Different seeds share one period and are not independent station validation. Do not tune on these evaluation rows and then reuse them as a fresh test: for an improved detector, design changes on separate development data and reserve another untouched date range or station.

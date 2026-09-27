# SkyGuard: Airport injected-fault comparison

**First airport-as-target evaluation with the initial paired-station implementation. Airport observations were previously used for Safdarjung peer review on the same dates, so this is not fully independent validation.** The Isolation Forest and temperature–humidity relation were fitted on 2024 Safdarjung observations. The model and peer-change cutoffs used January–June 2025 reference observations only. Three seeds place 40 known edits each on July–December 2025 observations at Airport. NOAA relative humidity is derived, not an independent sensor reading.

## Results

| Metric | Result | Meaning |
| --- | ---: | --- |
| Incremental event recall | 120/120 = 100.0% | An event caused at least one alert absent at that time in the unmodified replay |
| Point precision (nominal) | 49.8% | Of trial alerts, share at injected/marked readings; unmodified rows assumed normal |
| Point recall | 67.9% | Share of altered/marked readings alerted, including early steps of drift/frozen events |
| Point F1 (nominal) | 57.4% | Harmonic mean of nominal precision and point recall |
| Point accuracy (nominal) | 92.4% | Dominated by unmodified readings, not field accuracy |
| Always-normal accuracy | 92.5% | Trivial comparator that never detects a fault |
| Unmodified background alert rate | 1.46% | Original NOAA readings alerted; true fault status unknown |

## Event recall by injected fault

| Fault type | New detections / injected events |
| --- | ---: |
| communication_gap | 12/12 |
| humidity_spike | 12/12 |
| invalid_humidity | 12/12 |
| missing_humidity | 12/12 |
| multivariate_corruption | 12/12 |
| pressure_bias | 12/12 |
| pressure_spike | 12/12 |
| temperature_drift | 12/12 |
| temperature_frozen | 12/12 |
| temperature_spike | 12/12 |

**Interpretation:** Compare the per-fault rows rather than relying on pooled accuracy. Returns after an injected fault can cause additional alerts outside its labeled window; those remain in nominal false positives. A gap alert occurs on the next received reading, and does not prove a physical communications failure.

NOAA relative humidity is derived from temperature and dew point, so injected edits can create an artificially inconsistent relation. The optional paired-station check compares simultaneous station readings with an earlier pair; peer disagreement needs human review and cannot identify the faulty station. Metrics on edited observations do not establish accuracy on real sensor failures.

## Limits and next experiment

Every injected location, magnitude, fault window and seed is recorded in each run's `events.csv`; `injected_replay.csv` and `injected_alerts.csv` allow reproduction. The nominal confusion matrix in `summary.json` treats unmodified records as negative despite unknown field truth. Different seeds share one period and are not independent station validation. Do not tune on these evaluation rows and then reuse them as a fresh test: for an improved detector, design changes on separate development data and reserve another untouched date range or station.

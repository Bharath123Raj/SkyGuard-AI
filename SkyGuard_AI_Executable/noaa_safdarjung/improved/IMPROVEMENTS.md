# Revised SkyGuard detector: development comparison

The original 2024 Safdarjung Isolation Forest is retained. The revised bundle
adds two independent checks: an unusually large pressure step and a change in
relative humidity inconsistent with the accompanying temperature change. A
robust temperature–humidity relation is fitted on 2024; cutoffs use the 99.9th
percentile of eligible January–June 2025 observations. A return to the previous
trajectory immediately after a flagged one-reading change is recorded as
context rather than counted as a second rule alert. Missing, out-of-range,
repeated and gap checks remain available. The new checks can alert even when
the Isolation Forest score is below its threshold.

**These are development results.** We inspected the July–December 2025 data
and original benchmark before designing these checks. The same 2025 dates and
injection seeds were reused to compare software behavior; this is not an
independent final evaluation or measured sensor-fault accuracy.

| Measure | Original | Revised |
| --- | ---: | ---: |
| New injected events detected | 62/120 (51.7%) | 102/120 (85.0%) |
| Nominal point precision | 56.1% | 59.5% |
| Point recall | 24.1% | 37.7% |
| Nominal point F1 | 33.7% | 46.1% |
| Baseline alerts on 1,434 unmodified readings | 21 (1.46%) | 23 (1.60%) |

| Injected fault | Original events | Revised events |
| --- | ---: | ---: |
| Humidity spike | 0/12 | 12/12 |
| Pressure spike | 0/12 | 12/12 |
| Temperature spike | 2/12 | 12/12 |
| Pressure bias | 2/12 | 7/12 |
| Temperature drift | 0/12 | 0/12 |
| Remaining types combined | 58/60 | 59/60 |

The point metrics treat every unmodified NOAA record as nominally normal,
although its true fault status is unknown. Repeated seeds reuse one station
and period, so 120 placements are not 120 independent station conditions.
The return to baseline after an injection can still produce an additional
alert outside the marked fault window; these remain counted in nominal
precision. Data gaps are report absences, not confirmed transmission failures.

NOAA relative humidity at this station is **derived from temperature and dew
point**. Editing only one of these columns can manufacture a broken relation,
which may make this check easier to score than on a real independently measured
humidity sensor. A cross-sensor alert does not identify the faulty sensor, and
peer context in this dashboard is still a separate review, not a verified
weather/fault decision. Drift needs a separate design and a new validation set.

Run the revised dashboard from the `SkyGuard_AI_Executable` folder:

```powershell
python -m streamlit run dashboard.py -- --data noaa_safdarjung/improved/alerts.csv
```

For a fresh run, use the command sequence in `NOAA_DATA.md`. Each of the three
`injected_eval_seed*` folders records injection positions, alerts and metrics;
`injected_benchmark/summary.json` and `INJECTED_EVAL.md` contain the aggregate.
Reserve a period or another station that has not been inspected for final
testing, and collect confirmed AWS sensor faults before claiming field accuracy.

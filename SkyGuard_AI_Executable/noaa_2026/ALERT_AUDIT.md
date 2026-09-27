# Review of alerts on unmodified 2026 NOAA observations

The injected-fault benchmark treats **all unmodified readings** as nominal
negative examples. That assumption is convenient for a repeatable software
test, but it does not establish that every source reading is healthy. This
audit inspects the detector's **unmodified** 2026 replay without changing
the model, injection labels or reported precision.

| Primary review category | Safdarjung | Delhi airport | What it establishes |
| --- | ---: | ---: | --- |
| Missing or out-of-range value | 10 | 56 | An objective data-quality problem in the received observation; physical sensor cause unknown |
| Scheduled report gap | 18 | 8 | A report was absent from the selected three-hour grid; hardware cause unknown |
| Repeated 100% relative humidity | 14 | 0 | Repeated derived humidity at saturation, which may be real weather |
| Other repeated reading | 1 | 2 | Needs source and instrument review |
| Peer change disagreement | 18 | 19 | Nearby stations differ in their 24-hour change; either station or local weather may explain it |
| Isolation Forest pattern | 20 | 7 | Unusual relative to the training distribution, with no confirmed fault label |
| Calibrated change check | 8 | 7 | Unusual pressure or temperature–humidity change; cause unverified |
| **Total alerts** | **89/2,069 (4.30%)** | **99/2,125 (4.66%)** | **Zero technician-confirmed fault labels supplied** |

At the airport, missing or invalid pressure accounts for **56** alerts on
unmodified rows; **47** airport alerts occur in March 2026. At Safdarjung,
all **14** humidity-repetition alerts listed above have derived RH exactly
100%. These observations show why a benchmark that calls every alert on an
unmodified row a *false positive* cannot establish field precision. They do
**not** justify removing any of the benchmark's nominal false positives after
seeing the test. Reported injected-fault precision stays **45.6%** for
Safdarjung and **39.6%** for the airport.

Per-alert timestamps, observed values, reasons and review categories are in
each station's `alert_audit.csv`. The accompanying `alert_audit.summary.json`
feeds the dashboard. Categories are evidence cues, not fault labels.

## Next validation decision

1. Obtain original automatic-weather-station observations with the three
   independent measurements, exact timestamps and sensor/maintenance logs.
   An authorized export is suitable; the IMD API route previously returned
   HTTP 401 and cannot be treated as available here.
2. Have a domain reviewer label observed faults and genuine rapid weather
   changes, recording evidence and unknown cases separately. Cross-check
   reporting gaps against archive and transmission logs.
3. Design changes using a development split, then evaluate once on a new
   station or later untouched dates. Report event recall and delay **alongside**
   confirmed-fault precision and alerts per station-day.

Until those labels exist, demonstrate the working pipeline and its strong
injected-*event* detection while describing precision as **nominal**. Do not
claim 80% real-world sensor-fault precision from these NOAA results.

# Safdarjung alert review: July–December 2025

**Status:** Initial evidence review; no fault labels assigned. The full
21-row evidence table is `alert_review.csv`, produced by
`review_noaa_alerts.py`. Timestamps and the two stations' original NOAA
readings are kept separate from SkyGuard's classifications.

| SkyGuard alert | Count | Evidence gathered | What remains unknown |
| --- | ---: | --- | --- |
| Communication gap | 9 | A scheduled 3-hour Safdarjung observation is absent before the next report; the nearby airport reports at all nine alert times. | Whether the gap was a sensor, transmission, archive, or scheduling issue. |
| Missing data | 2 | Safdarjung's derived RH is missing; the airport has RH at both times. | Whether an input measurement, quality process, or feed caused the missing value. |
| Unusual pattern | 10 | The airport has same-time data for every event. Both stations' temperature and RH change in the same directions over the preceding three hours. | Whether each event is weather, local microclimate, instrument behavior, or a model false alert. |

Nine of the ten unusual-pattern alerts occur at **06:00 UTC (11:30 IST)**
between October and December; the other is at 15:00 UTC in July. This time
concentration suggests that the detector may be sensitive to the local morning
transition. It is an inference from the alerts and peer changes, not a proven
cause. For example, on 2025-07-09 at 15:00 UTC, Safdarjung changed by
−7.5 °C, +28 percentage points RH and +6.5 hPa from three hours earlier;
the airport changed by −7.5 °C, +31 points and +6.8 hPa. On 2025-12-03 at
06:00 UTC, Safdarjung warmed 13.0 °C and its derived RH fell 52 points;
the airport warmed 6.8 °C and its derived RH fell 27 points. The magnitude
differs, so these comparisons do not rule out a station-specific issue.

**Measurement caution:** At both sites, GHCNh source 223 has RH measurement
code `D`, meaning RH is derived from temperature and dew point. Agreement
between the two RH series does not independently validate humidity sensors.
NOAA quality flags and a nearby station provide review evidence, not
technician-confirmed truth. Missing scheduled observations in this archive
must not automatically be described as communication failures.

## Reproduce the table

Run from `SkyGuard_AI_Executable`:

```powershell
python review_noaa_alerts.py --alerts noaa_safdarjung/alerts.csv --station noaa_safdarjung/raw/GHCNh_INI0000VIDD_2025.psv --peer noaa_safdarjung/peer_raw/GHCNh_INI0000VIDP_2025.psv --output noaa_safdarjung/alert_review.csv
```

Review each row against weather reports and maintenance/source logs before
assigning a fault label. Any detector changes based on this review require a
new, untouched test period or station for an unbiased evaluation.

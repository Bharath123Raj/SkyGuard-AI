# SkyGuard AI use cases and output guide

| Situation | Observed evidence | Expected response | Action |
| --- | --- | --- | --- |
| Single temperature spike | Unusual temporal score and abrupt temperature change | `spike_or_shift` alert; medium severity; provisional median temperature | Inspect thermometer and raw record; avoid automatically replacing genuine heat extremes. |
| Humidity above 100% | Physical range violated | `invalid_reading` alert; high severity | Flag sensor/data transmission; retain the raw measurement. |
| Missing pressure value | Null, blank, nonnumeric or nonfinite input | `missing_data` alert; high severity | Check transmission and sensor; show a provisional value only with its provenance. |
| Pressure frozen for six 10-minute samples | Exact repetition | `frozen_sensor` alert; high severity | Inspect firmware, communications and quantization precision. |
| Lost reporting interval | Timestamp gap >15 minutes on next arrival | `communication_gap` evidence; model history resets | Investigate link/power and missing interval; add upstream silence timers for immediate detection. |
| Abrupt coherent regional event | Strong changes corroborated by at least two peers per changed parameter | `plausible_weather_event`; no ML alert if values pass hard checks | Keep raw readings; send to meteorologist if consequential. |
| Long-term degradation | Frequent recent alerts | `needs_inspection` health state after >=12 observations and >=25% alerts | Schedule maintenance; do not infer remaining life without labeled history. |

## Input and output

The input uses UTC timestamps, station ID and **only the three specified measured variables**. Peer input may include other stations' values for those same variables. Example JSON alert fields: `alert`, `classification`, `severity`, `evidence_strength`, `reasons`, `affected_sensors`, `anomaly_score`, `score_threshold`, `peer_support`, `sensor_health`, `suggested_values`. For every result, the raw values remain present. `evidence_strength` expresses rule strength and is not a probability.

## Workflow

1. Gather clean historical station data, mark invalid points, and hold out a later normal period for calibration.
2. Train the model with `train`, then replay a distinct period or stream JSON objects.
3. Inspect alerts, sensor traces, reason codes and health in the dashboard.
4. Have an operator confirm faults before acting on suggestions. Log actual weather events as well as faults for subsequent blinded evaluation.

## Design boundaries

This prototype is suitable for a laptop or server demonstration. It is not ESP32 firmware or an edge energy benchmark. The Isolation Forest score does not give a root-cause diagnosis; the displayed fault types come from transparent rules plus trend evidence. Peer corroboration requires time-aligned nearby stations and appropriate altitude correction in a production system. The simple median placeholder can be wrong for sustained drift and fast weather fronts. A real deployment needs persistence, alert deduplication, observability, data security, monitoring for model drift, and station-specific thresholds.

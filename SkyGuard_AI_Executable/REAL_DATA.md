# SkyGuard real observation phase

The demo CSV and model are synthetic. Keep `demo_data/`, `alerts.csv`, and
`skyguard.joblib` labeled as demo artifacts. A real observation import does not
establish that any row is an actual sensor fault.

## First station source: IMD AWS/ARG

IMD documents `https://api.imd.gov.in/api/v1/aws_data`, `?id=NDL`, and a
station mapping endpoint. Its sample AWS record contains `DATE`, `TIME`, `ID`,
`CURR_TEMP` (°C), `MSLP` (hPa), and `RH` (%). See the [IMD API reference](https://api.imd.gov.in/public/api_reference.html)
under **AWS/ARG Data**.
`MSLP` is mean sea level pressure. Do not mix it with station-level pressure
without an explicit conversion and station elevation.

The live endpoint returned HTTP 401 from the development environment, so this
package does **not** contain a downloaded IMD history. Confirm your access and
the timezone of `DATE`/`TIME` with the provider. The API reference shows sample
timestamps but does not define their timezone in its AWS/ARG section. The
timezone in the commands below is **an example only**: do not import observations
until you verify whether the actual feed uses IST or UTC.

Run from the inner `SkyGuard_AI_Executable` directory with your active Python:

```powershell
python -m pip install -r requirements.txt
python .\imd_ingest.py --input-json .\imd_sample_schema.json --source-tz Asia/Kolkata --output .\observations_example.csv
python .\audit_real.py --input .\observations_example.csv --interval-minutes 60
```

`imd_sample_schema.json` reproduces the **documentation example**, so the
result above only tests the importer. For authorized real observations saved as
JSON, substitute that file and output to a separate `real_observations.csv`.
For authorized endpoint access, use:

```powershell
python .\imd_ingest.py --url "https://api.imd.gov.in/api/v1/aws_data?id=NDL" --source-tz YOUR_CONFIRMED_IANA_TIMEZONE --output .\real_observations.csv
python .\audit_real.py --input .\real_observations.csv --interval-minutes 60
```

The importer accepts an optional `--bearer-env VARIABLE_NAME` for a token that
the data provider has issued. Never put a token in the repository. Polling must
run on a scheduled machine or service; the Streamlit dashboard does not execute
this command. Repeated polls skip observations with the same station ID and UTC
timestamp. A source correction at that key needs manual review, because the
first imported record is retained. Preserve the original JSON exports for an
audit trail if provider terms permit.

## Before fitting a real detector

1. Collect enough contiguous history from several Indian stations across
   weather regimes; `audit_real.py` reports the count, incomplete rows, gaps,
   and observed cadence. A single current snapshot is insufficient.
2. Confirm that `ID` identifies a stable physical station, the timestamp basis,
   MSLP units, sampling interval, and any feed quality flags. Check station
   moves and instrument changes. The importer marks broad range issues, but
   those checks do not certify the remaining data as clean.
3. Review candidate normal training and calibration periods manually. Set
   aside later dates and ideally entire stations for untouched evaluation.
   Exclude known faults and periods with missing/invalid measurements from the
   model fitting splits. Preserve genuine severe weather events in evaluation.
4. Write chronological `train.csv` and `calibration.csv` with the first five
   columns `timestamp,station_id,temperature,pressure,humidity`. Both need
   substantial uninterrupted data per station. Training refuses fewer than 50
   usable feature rows in either split. Fit using the confirmed cadence:

   ```powershell
   python .\skyguard.py train --train .\train.csv --calibration .\calibration.csv --model .\skyguard_real.joblib --interval-minutes 60
   python .\skyguard.py replay --input .\held_out.csv --model .\skyguard_real.joblib --output .\real_alerts.csv
   python -m streamlit run .\dashboard.py -- --data .\real_alerts.csv
   ```

   Use `--interval-minutes 10` if the actual station reports every 10 minutes.
   `replay` prints synthetic confusion metrics **only if** an `injected_fault`
   column is supplied. Do not add a made-up label to real observations.
5. Ask domain reviewers to verify actual fault events and genuine abrupt
   weather, then measure false alerts per station-day, recall by fault type,
   detection delay, and results by season and station. Injected faults may
   supplement this review but cannot establish operational accuracy.

The current model reports an anomaly score and heuristic reasons. It has not
been recalibrated to Indian station data. A single real snapshot should be
ingested and audited first; retraining and online alerting follow after enough
verified history is available.

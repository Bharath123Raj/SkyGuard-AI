# SkyGuard: 3-minute SIH demo

Run these from the extracted `SkyGuard_AI_Executable` directory in PowerShell.

## 1. Start with unmodified observed weather

```powershell
python -m streamlit run .\dashboard.py
```

Show the temperature, pressure and humidity timeline, then the alert audit.
State that the **89** Safdarjung alerts are signals for review, not 89
confirmed sensor failures. Ten contain an objectively missing or out-of-range
measurement; others include reporting gaps and repeated 100% derived humidity.

## 2. Show a labeled fault-injection replay

In Streamlit's sidebar, select **Injected demonstration · Safdarjung seed 42**
from **Dataset**. The default option is the unmodified observed replay.

The new **Injected-fault replay** section shows the injected event ID, fault
type, which readings were edited, and the detector's alert beside each row.
This seed placed 40 events; **39/40** produced a new alert compared with the
unmodified replay. Search the table for these example IDs:

| Event | Start time (UTC) | What to point out |
| --- | --- | --- |
| `E012` temperature spike | 2026-07-27 06:00 | A new alert at the edited reading |
| `E023` temperature drift | 2026-05-12 15:00 | Gradual fault; the first new alert comes 15 hours after it starts |
| `E003` scheduled report gap | 2026-04-30 15:00 | The omitted row has no result; the next received report raises the alert three hours later |

To rerun the injection from the original NOAA background rather than using
the saved seed-42 replay:

```powershell
python .\evaluate_injected_noaa.py --input .\noaa_2026\safdarjung\held_out.csv --model .\noaa_safdarjung\skyguard_noaa_v3_peer.joblib --peer-input .\noaa_2026\airport\held_out.csv --output-dir .\demo_seed42 --seed 42
```

The tool writes `events.csv` and `metrics.json` so the injected times and
counts can be checked independently. To open the newly generated file, stop
Streamlit with `Ctrl+C` and restart with:

```powershell
python -m streamlit run .\dashboard.py -- --data .\demo_seed42\injected_alerts.csv
```

The new file appears as **Custom CSV supplied by server operator** in the
dataset selector, with an injected-demonstration notice.

## 3. Give the correct conclusion

Across three seeds on Safdarjung 2026, new injected-event recall was
**116/120 (96.7%)**. Nominal point precision was **45.6%** and point recall
**71.6%**. Always predicting normal has a higher nominal accuracy than the
detector on this background. The NOAA relative humidity value is derived, and
there are no technician-confirmed real sensor-fault labels in this archive.
The benchmark demonstrates software response to known edits; it does not
establish real-world fault precision or claim 80% precision and recall.

If asked about nearby stations, show the second stream
`noaa_2026/airport/alerts.csv` and explain that the 24-hour pairwise change
check flags station disagreement for review. Disagreement alone cannot prove
which station is faulty.

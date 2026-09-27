# Publish the SkyGuard replay dashboard

## Which CSV should the hosted app open?

**Default:** `noaa_2026/safdarjung/alerts.csv` is the detector output from
unmodified NOAA observations. The Streamlit sidebar also offers the airport
observations and the clearly labeled seed-42 **injected demonstration**. Never
make an `injected_alerts.csv` the default observed feed or describe it as live
sensor data. The root `alerts.csv` in this package is an older synthetic demo;
it is not the default and should not be the deployed source.

The hosted Streamlit app is a **historical replay dashboard**, not a live IMD
AWS ingestion service. Local models and reproducible evaluation scripts are
included in the full project, but the public page reads packaged CSV outputs.

## GitHub from Windows PowerShell

Use the *updated extracted package*. Start in its `SkyGuard_AI_Executable`
folder so `$source` below points to the right directory. Because an earlier
push from the existing checkout was rejected, use a fresh clone rather than
force-pushing over changes on GitHub:

```powershell
$source = (Get-Location).Path
Set-Location "$env:USERPROFILE\Downloads"
git clone https://github.com/Bharath123Raj/SkyGuard-AI.git SkyGuard-AI-Deploy-2026
$repo = "$env:USERPROFILE\Downloads\SkyGuard-AI-Deploy-2026"
$target = Join-Path $repo 'SkyGuard_AI_Executable'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force
Set-Location $repo
git status --short
git add .\SkyGuard_AI_Executable\
git diff --cached --stat
git commit -m "Add observed NOAA replay and labeled fault demo"
git push origin main
```

Review `git status` and the staged file list before committing. If another
commit reaches GitHub after you clone, fetch and integrate it first; do not
force-push. If your repo uses a branch other than `main`, replace `main` with
that branch's name. Do not commit your virtual environment or any credentials.

## Streamlit Community Cloud

At [share.streamlit.io](https://share.streamlit.io), create an app using:

| Setting | Value |
| --- | --- |
| Repository | `Bharath123Raj/SkyGuard-AI` |
| Branch | `main` |
| Main file | `SkyGuard_AI_Executable/dashboard.py` |
| Dependencies | `SkyGuard_AI_Executable/requirements.txt` (auto-discovered beside main file) |

Open the resulting URL. The default selection must say **Observed NOAA ·
Safdarjung 2026**. Use the dataset selector to switch to **Injected
demonstration · Safdarjung seed 42** when demonstrating known software edits.
Show the 2026 evaluation status and nominal metrics alongside the replay.

Before sending the public link, confirm that observed and injected selections
both load and that the injected demonstration is visibly marked. Your
precision/recall numbers are based on injected edits and nominal negatives;
the archive does not have technician-confirmed sensor-fault labels.

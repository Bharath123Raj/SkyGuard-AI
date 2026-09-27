"""Import IMD AWS JSON snapshots into SkyGuard's observation CSV.

The public IMD API reference documents /api/v1/aws_data. Actual access may
require authorization; --input-json works with an authorized saved response.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS = ("timestamp", "station_id", "temperature", "pressure", "humidity",
          "source", "station_name", "latitude", "longitude", "qc_flags")
NUMBERS = {"temperature": "CURR_TEMP", "pressure": "MSLP", "humidity": "RH"}
LIMITS = {"temperature": (-60, 60), "pressure": (850, 1100), "humidity": (0, 100)}


def records(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "DATA", "results", "result"):
            if isinstance(payload.get(key), list):
                return payload[key]
        if "DATE" in payload:
            return [payload]
    raise ValueError("Expected an IMD observation or an array of IMD observations")


def measurement(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def convert(source, source_tz):
    if not isinstance(source, dict):
        raise ValueError("Each observation must be an object")
    station = str(source.get("ID") or source.get("CALL_SIGN") or "").strip()
    if not station:
        raise ValueError("Missing IMD station ID")
    try:
        naive = datetime.fromisoformat(f"{source['DATE']}T{source['TIME']}")
        observed = naive if naive.tzinfo else naive.replace(tzinfo=ZoneInfo(source_tz))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid DATE/TIME for station {station}: {exc}") from exc
    row = {"timestamp": observed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
           "station_id": station,
           "source": "IMD_AWS_ARG", "station_name": str(source.get("STATION") or ""),
           "latitude": measurement(source.get("Latitude")),
           "longitude": measurement(source.get("Longitude"))}
    flags = []
    for name, field in NUMBERS.items():
        row[name] = measurement(source.get(field))
        if row[name] is None:
            flags.append(f"{name}:missing")
        elif not LIMITS[name][0] <= row[name] <= LIMITS[name][1]:
            flags.append(f"{name}:outside_range")
    row["qc_flags"] = "|".join(flags)
    return row


def load_existing(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Existing CSV has an incompatible schema; use a new output path")
        return {(row["station_id"], row["timestamp"]): row for row in reader}


def import_payload(payload, output, source_tz):
    output = Path(output)
    existing = load_existing(output)
    added = duplicate = 0
    for item in records(payload):
        row = convert(item, source_tz)
        key = row["station_id"], row["timestamp"]
        if key in existing:
            # Repeated polling is safe. Preserve the first snapshot, including
            # an original missing value, rather than silently revising history.
            duplicate += 1
            continue
        existing[key] = row
        added += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        for key in sorted(existing, key=lambda k: (k[0], k[1])):
            writer.writerow(existing[key])
    os.replace(temp, output)
    return {"added": added, "duplicates_skipped": duplicate,
            "total": len(existing), "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-json", type=Path, help="An authorized saved IMD AWS JSON response")
    source.add_argument("--url", help="Authorized IMD AWS endpoint URL")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-tz", required=True,
                        help="Timezone of IMD DATE/TIME, confirmed with the provider (e.g. Asia/Kolkata)")
    parser.add_argument("--bearer-env", help="Environment variable containing an optional access token")
    args = parser.parse_args()
    ZoneInfo(args.source_tz)  # Reject invalid timezone before reading or writing data.
    if args.input_json:
        payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    else:
        headers = {"Accept": "application/json", "User-Agent": "SkyGuardAI/real-data-import"}
        if args.bearer_env:
            token = os.environ.get(args.bearer_env)
            if not token:
                parser.error(f"Environment variable {args.bearer_env} is unset")
            headers["Authorization"] = f"Bearer {token}"
        try:
            with urllib.request.urlopen(urllib.request.Request(args.url, headers=headers), timeout=20) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            parser.error(f"HTTP {exc.code} from source; check access with the data provider")
    print(json.dumps(import_payload(payload, args.output, args.source_tz), indent=2))


if __name__ == "__main__":
    main()

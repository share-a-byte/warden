#!/usr/bin/env python3
"""Run the official EnergyPlus refrigerated warehouse example and export GuardFleet telemetry.

Requires Python 3.9+ and a separately installed EnergyPlus v26.2 executable.
No third-party Python packages are required.

Original, unchanged upstream model:
https://raw.githubusercontent.com/NatLabRockies/EnergyPlus/v26.2.0/testfiles/RefrigeratedWarehouse.idf
Typical-year Chicago weather file:
https://raw.githubusercontent.com/NatLabRockies/EnergyPlus/v26.2.0/weather/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw

The resulting values are PHYSICS-BASED SIMULATION OUTPUTS, not facility measurements.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.request import Request, urlopen

BASE = "https://raw.githubusercontent.com/NatLabRockies/EnergyPlus/v26.2.0"
MODEL_URL = BASE + "/testfiles/RefrigeratedWarehouse.idf"
WEATHER_URL = BASE + "/weather/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
MODEL_NAME = "RefrigeratedWarehouse.idf"
WEATHER_NAME = "Chicago_TMY3.epw"

# These are output variables explicitly requested by the upstream model.
# Each is re-requested at TimeStep frequency (15 min for the original model).
VARIABLES = {
    "Site Outdoor Air Drybulb Temperature": "outdoor_temperature_c",
    "Zone Mean Air Temperature": "zone_temperature_c",
    "Zone Air Relative Humidity": "zone_relative_humidity_pct",
    "Refrigeration Zone Air Chiller Total Electricity Rate": "air_chiller_electric_power_w",
    "Refrigeration Zone Air Chiller Coil Defrost Electricity Rate": "defrost_electric_power_w",
    "Refrigeration Zone Air Chiller Total Cooling Rate": "air_chiller_cooling_rate_w",
    "Refrigeration Air Chiller System Total Compressor Electricity Rate": "compressor_electric_power_w",
    "Refrigeration Air Chiller System Compressor Runtime Fraction": "compressor_runtime_fraction",
    "Refrigeration Air Chiller System Condensing Temperature": "condensing_temperature_c",
    "Refrigeration Air Chiller System Evaporating Temperature": "evaporating_temperature_c",
    "Refrigeration Air Chiller System Estimated Refrigerant Mass Flow Rate": "refrigerant_mass_flow_kg_s",
}

HEADER = ["simulated_at", "facility_id", "asset_id", "metric", "value", "unit", "source", "is_attack", "energyplus_key"]


def fetch(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"Using existing: {dest}")
        return dest
    print(f"Fetching: {url}")
    req = Request(url, headers={"User-Agent": "GuardFleet-EnergyPlus-Example/1.0"})
    try:
        with urlopen(req, timeout=60) as resp, dest.open("wb") as out:
            shutil.copyfileobj(resp, out)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest


def create_telemetry_idf(original: Path, modified: Path) -> None:
    text = original.read_text(encoding="utf-8-sig")
    if not re.search(r"(?im)^\s*Version\s*,\s*26\.2\s*;", text):
        raise ValueError("This runner expects the official EnergyPlus version 26.2 IDF")
    # Avoid duplicate / mixed-frequency variables and keep outputs manageable.
    text, count = re.subn(r"(?im)^\s*Output:Variable\s*,[^\n;]*;[^\S\n]*(?:\n|$)", "", text)
    if not count:
        raise ValueError("The model didn't contain the expected Output:Variable requests")
    block = "\n\n! GuardFleet: time-step telemetry only; original model saved separately.\n"
    block += "\n".join(f"Output:Variable,*,{name},Timestep;" for name in VARIABLES)
    modified.write_text(text.rstrip() + block + "\n", encoding="utf-8")
    print(f"Prepared {modified.name} ({count} previous report requests replaced)")


def parse_ep_datetime(s: str) -> str:
    """Parse EnergyPlus month/day hh:mm, including 24:00 at the end of a day.

    Uses an arbitrary, clearly labeled synthetic reference year (2025) because
    weather files are typical meteorological years, not current telemetry.
    """
    match = re.search(r"\s*(\d{1,2})\s*/\s*(\d{1,2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if not match:
        raise ValueError(f"Unrecognized EnergyPlus time: {s!r}")
    month, day, hour, minute = map(int, match.group(1, 2, 3, 4))
    second = int(match.group(5) or 0)
    if hour > 24 or (hour == 24 and (minute != 0 or second != 0)):
        raise ValueError(f"Invalid EnergyPlus time: {s!r}")
    stamp = datetime(2025, month, day) + timedelta(hours=hour, minutes=minute, seconds=second)
    return stamp.isoformat(timespec="seconds")


def asset_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.casefold()).strip("_") or "unknown"


def convert_csv(energyplus_csv: Path, output_csv: Path, facility_id: str = "guardfleet_warehouse") -> tuple[int, int]:
    metrics_found = set()
    rows = 0
    timestamps = set()
    with energyplus_csv.open(newline="", encoding="utf-8-sig") as src, output_csv.open("w", newline="", encoding="utf-8") as dest:
        reader = csv.DictReader(src)
        if reader.fieldnames is None:
            raise ValueError("Empty EnergyPlus CSV")
        time_header = next((col for col in reader.fieldnames if col.strip().casefold() in ("date/time", "date / time")), None)
        if not time_header:
            raise ValueError(f"No Date/Time column found. First five: {reader.fieldnames[:5]}")
        mapped = []
        for col in reader.fieldnames:
            if col == time_header or ":" not in col:
                continue
            key, remainder = col.split(":", 1)
            var = remainder.split("[", 1)[0].strip()
            metric = VARIABLES.get(var)
            if not metric:
                continue
            unit_match = re.search(r"\[([^]]+)\]", remainder)
            unit = unit_match.group(1) if unit_match else "dimensionless"
            mapped.append((col, key.strip(), metric, unit))
            metrics_found.add(metric)
        if not mapped:
            raise ValueError("No requested refrigeration columns were found in EnergyPlus output")
        writer = csv.writer(dest)
        writer.writerow(HEADER)
        for row in reader:
            simulated_at = parse_ep_datetime(row[time_header])
            timestamps.add(simulated_at)
            for col, key, metric, unit in mapped:
                raw = row.get(col, "")
                if raw is None or not raw.strip():
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                writer.writerow([simulated_at, facility_id, asset_id(key), metric, format(val, ".9g"), unit, "energyplus_v26_2_simulation", 0, key])
                rows += 1
    print(f"Exported {rows:,} observations over {len(timestamps):,} time steps: {output_csv}")
    print(f"Exported metrics: {', '.join(sorted(metrics_found))}")
    if "zone_temperature_c" not in metrics_found or "compressor_electric_power_w" not in metrics_found:
        print("WARNING: Expected zone temperature or compressor power missing! Check the run .err and .rdd files.")
    return rows, len(timestamps)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--energyplus", default="energyplus", help="EnergyPlus v26.2 executable path (default: energyplus on PATH)")
    p.add_argument("--workdir", type=Path, default=Path("./guardfleet_eplus_output"), help="Output location")
    p.add_argument("--idf", type=Path, help="Optional local copy of the official v26.2 model")
    p.add_argument("--epw", type=Path, help="Optional local weather file")
    p.add_argument("--csv", type=Path, help="Convert an existing EnergyPlus eplusout.csv without running EnergyPlus")
    args = p.parse_args()
    work = args.workdir.expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    if args.csv:
        raw_csv = args.csv.resolve()
        if not raw_csv.is_file():
            p.error(f"No such EnergyPlus CSV: {raw_csv}")
    else:
        model = args.idf.resolve() if args.idf else fetch(MODEL_URL, work / MODEL_NAME)
        weather = args.epw.resolve() if args.epw else fetch(WEATHER_URL, work / WEATHER_NAME)
        patched = work / "GuardFleetRefrigeratedWarehouse.idf"
        create_telemetry_idf(model, patched)
        out = work / "simulation"
        out.mkdir(exist_ok=True)
        exe = args.energyplus
        if not Path(exe).exists() and shutil.which(exe) is None:
            p.error("EnergyPlus executable not found. Install EnergyPlus 26.2 and supply --energyplus /path/to/energyplus")
        print("Checking EnergyPlus version...")
        version = subprocess.run([exe, "--version"], capture_output=True, text=True, check=True)
        print((version.stdout or version.stderr).strip())
        if not re.search(r"26\.2", version.stdout + version.stderr):
            p.error("EnergyPlus 26.2 is required for this example. Match model and binary versions.")
        command = [exe, "-w", str(weather), "-r", "-d", str(out), str(patched)]
        print("Running:", " ".join(command))
        with (work / "energyplus_run.log").open("w") as log:
            run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        if run.returncode:
            print(f"EnergyPlus failed (exit={run.returncode}). Inspect {out / 'eplusout.err'} and {work / 'energyplus_run.log'}", file=sys.stderr)
            return run.returncode
        raw_csv = out / "eplusout.csv"
        if not raw_csv.exists():
            p.error(f"No {raw_csv}. Inspect {out / 'eplusout.err'}. Was ReadVarsESO installed?")
    convert_csv(raw_csv, work / "guardfleet_telemetry.csv")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

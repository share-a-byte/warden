"""Score daily metric samples and evaluate them against attack windows in warden-v2."""

import argparse
import json
import math
import subprocess
from datetime import date, timedelta

import pandas as pd

from anomaly_inference import AutoencoderDetector, evaluate, pivot_long
from spacetime_export import export_anomaly_detection_rows


DATABASE = "c20098cb596c05e6f8676a582d6c5564399eb1cc8c2d571be2574cbccf69fe44"
START_DAY = date.fromisoformat("2025-01-27")
END_DAY = date.fromisoformat("2025-01-28")  # Exclusive
MODEL_VERSION = "autoencoder-jan-v1"

# Set this to one scenario ID if the database contains windows from other scenarios.
SCENARIO_ID = None

# The model was trained with facility_id__asset_id__metric feature names.
# Add entries here if a site's ID differs from its facility ID in the training data.
FACILITY_ID_BY_SITE = {}

SAMPLE_COLUMNS = ["simulated_at", "site_id", "asset_id", "metric", "value"]
WINDOW_COLUMNS = [
    "window_key", "scenario_id", "attack_kind", "site_id", "asset_id", "metric",
    "start_iso", "end_iso", "multiplier", "offset",
]


def query_rows(query, columns):
    completed = subprocess.run(
        ["spacetime", "sql", "--server", "maincloud", "--format", "json", DATABASE, query],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"SpacetimeDB query failed:\n{completed.stderr or completed.stdout or query}"
        )
    response = json.loads(completed.stdout)
    return pd.DataFrame(response[0]["rows"], columns=columns)


def read_day(day, csv_path=None):
    """Read one UTC day from a CSV (including .csv.gz) or from SpacetimeDB."""
    if csv_path is not None:
        header = set(pd.read_csv(csv_path, nrows=0).columns)
        site_column = "site_id" if "site_id" in header else "facility_id"
        required = set(SAMPLE_COLUMNS) - {"site_id"} | {site_column}
        missing = required - header
        if missing:
            raise ValueError(f"{csv_path} lacks required columns: {sorted(missing)}")
        usecols = list(required | ({"is_attack"} if "is_attack" in header else set()))
        start = pd.Timestamp(day, tz="UTC")
        end = start + pd.Timedelta(days=1)
        matches = []
        for chunk in pd.read_csv(csv_path, usecols=usecols, chunksize=100_000):
            times = pd.to_datetime(chunk["simulated_at"], format="mixed", errors="coerce", utc=True)
            if times.isna().any():
                examples = chunk.loc[times.isna(), "simulated_at"].head(3).tolist()
                raise ValueError(f"Unparseable CSV timestamps: {examples}")
            selected = chunk.loc[(times >= start) & (times < end)].copy()
            if not selected.empty:
                if site_column == "facility_id":
                    selected["site_id"] = selected["facility_id"]
                selected = selected[SAMPLE_COLUMNS + (["is_attack"] if "is_attack" in header else [])]
                matches.append(selected)
        return (pd.concat(matches, ignore_index=True) if matches
                else pd.DataFrame(columns=SAMPLE_COLUMNS + (["is_attack"] if "is_attack" in header else [])))

    next_day = day + timedelta(days=1)
    query = f"""
        SELECT {", ".join(SAMPLE_COLUMNS)}
        FROM energyplus_metric_samples
        WHERE simulated_at >= '{day.isoformat()}'
          AND simulated_at < '{next_day.isoformat()}'
    """
    return query_rows(query, SAMPLE_COLUMNS)


def read_attack_windows(day, scenario_id=None):
    next_day = day + timedelta(days=1)
    if scenario_id is None:
        scenario_id = SCENARIO_ID
    scenario_filter = ""
    if scenario_id is not None:
        escaped_scenario = scenario_id.replace("'", "''")
        scenario_filter = f" AND scenario_id = '{escaped_scenario}'"
    query = f"""
        SELECT {", ".join(WINDOW_COLUMNS)}
        FROM energyplus_attack_windows
        WHERE start_iso < '{next_day.isoformat()}'
          AND end_iso > '{day.isoformat()}'
          {scenario_filter}
    """
    return query_rows(query, WINDOW_COLUMNS)


def apply_attack_windows(raw, windows):
    """Replace matching baseline rows with one derived attacked row apiece.

    Assumes each window changes its matching values to value * multiplier + offset.
    An attack window includes start_iso and excludes end_iso.
    """
    raw = raw.copy()
    raw["value"] = pd.to_numeric(raw["value"], errors="raise")
    attacked = pd.Series(False, index=raw.index)
    replacement_values = pd.Series(index=raw.index, dtype="float64")
    groups = raw.groupby(["site_id", "asset_id", "metric"], sort=False).groups

    for window in windows.itertuples(index=False):
        key = (window.site_id, window.asset_id, window.metric)
        indices = groups.get(key)
        if indices is None:
            continue
        start = pd.to_datetime(window.start_iso, utc=True).tz_localize(None)
        end = pd.to_datetime(window.end_iso, utc=True).tz_localize(None)
        if end <= start:
            raise ValueError(f"Invalid attack window: {key}, {window.start_iso} to {window.end_iso}")
        times = raw.loc[indices, "simulated_at"]
        matching = times.index[(times >= start) & (times < end)]
        if len(matching) == 0:
            continue
        if attacked.loc[matching].any():
            raise ValueError(
                f"Overlapping attack windows for {key} at {times.loc[matching[0]]}. "
                "Select a single scenario with --scenario-id, or define how overlaps combine."
            )
        multiplier, offset = float(window.multiplier), float(window.offset)
        if not math.isfinite(multiplier) or not math.isfinite(offset):
            raise ValueError(f"Non-finite attack parameters in window {window.window_key}")
        replacement_values.loc[matching] = raw.loc[matching, "value"] * multiplier + offset
        attacked.loc[matching] = True

    labels = attacked.groupby(raw["simulated_at"]).max().astype(int)
    # Keep all unaffected samples; remove each overlapping baseline sample and
    # insert its derived attacked value exactly once at the same feature/time.
    unaffected = raw.loc[~attacked]
    replacements = raw.loc[attacked].copy()
    replacements["value"] = replacement_values.loc[attacked].to_numpy()
    combined = pd.concat([unaffected, replacements], ignore_index=True)
    assert len(combined) == len(raw)
    return combined, labels, len(replacements)


def csv_attack_labels(raw):
    values = raw["is_attack"]
    if values.dtype == object:
        values = values.astype(str).str.strip().str.lower().map(
            {"0": 0, "1": 1, "false": 0, "true": 1}
        )
    else:
        values = pd.to_numeric(values, errors="coerce")
    if values.isna().any() or not values.isin([0, 1]).all():
        raise ValueError("CSV is_attack must contain only 0/1 or true/false")
    return values.groupby(raw["simulated_at"]).max().astype(int)


def main(csv_path=None, upload=True, scenario_id=None):
    detector = AutoencoderDetector("outputs")
    all_results = []
    all_labels = []
    context = None
    print(f"Reading metric samples from {csv_path if csv_path is not None else 'warden-v2'}")

    day = START_DAY
    while day < END_DAY:
        raw = read_day(day, csv_path=csv_path)
        if raw.empty:
            print(f"{day}: no metric samples in the selected source")
            context = None
            day += timedelta(days=1)
            continue

        # Treat naive ISO timestamps as UTC and compare all times on the same clock.
        raw["simulated_at"] = pd.to_datetime(raw["simulated_at"], utc=True).dt.tz_localize(None)
        raw["facility_id"] = raw["site_id"].map(FACILITY_ID_BY_SITE).fillna(raw["site_id"])
        if "is_attack" in raw:
            labels = csv_attack_labels(raw)
        else:
            windows = read_attack_windows(day, scenario_id=scenario_id)
            raw, labels, attacked_rows = apply_attack_windows(raw, windows)
            print(f"{day}: applied {len(windows)} attack windows; "
                  f"excluded {attacked_rows} overlapping baseline samples and "
                  f"inserted {attacked_rows} attacked replacements")

        wide = pivot_long(raw)
        missing = set(detector.features) - set(wide.columns)
        if missing:
            raise ValueError(
                f"{len(missing)} model features are absent from the day's samples; "
                f"first missing features: {sorted(missing)[:5]}. "
                "Check FACILITY_ID_BY_SITE and the input metric coverage."
            )

        # Carry the autoencoder's prior timesteps across midnight, as the notebook
        # does when it scores a continuous test CSV rather than separate days.
        scoring_wide = pd.concat([context, wide]) if context is not None else wide
        scoring_wide = scoring_wide[~scoring_wide.index.duplicated(keep="last")].sort_index()
        context = scoring_wide.tail(detector.window - 1)
        rule = detector.meta.get("resample_rule")
        available_steps = len(scoring_wide.resample(rule).mean()) if rule else len(scoring_wide)
        if available_steps < detector.window:
            print(f"{day}: {len(raw)} samples, only {available_steps} timesteps; awaiting model context")
            day += timedelta(days=1)
            continue

        result = detector.score(scoring_wide)
        result = result.loc[(result.index >= pd.Timestamp(day))
                            & (result.index < pd.Timestamp(day + timedelta(days=1)))]

        all_results.append(result)
        all_labels.append(labels)
        print(f"{day}: {len(raw)} samples, {int(result.alert.sum())} alerts, "
              f"{int(labels.sum())} attacked timestamps")
        print(f"{day} evaluation: {evaluate(detector, result, labels)}")
        print(result.loc[result.alert, ["score", "top_features"]].head(10))

        if upload:
            count = export_anomaly_detection_rows(
                raw,
                result,
                model_version=MODEL_VERSION,
                resample_rule=detector.meta.get("resample_rule"),
                batch_size=1,
            )
            print(f"{day}: uploaded {count} anomaly detections")
        day += timedelta(days=1)

    if all_results:
        combined_result = pd.concat(all_results).sort_index()
        combined_labels = pd.concat(all_labels).groupby(level=0).max().sort_index()
        print("Overall evaluation:", evaluate(detector, combined_result, combined_labels))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="read metric samples from this CSV or .csv.gz file")
    parser.add_argument("--no-upload", action="store_true", help="evaluate without uploading detections")
    parser.add_argument("--scenario-id", help="apply only attack windows from this scenario")
    args = parser.parse_args()
    main(csv_path=args.csv, upload=not args.no_upload, scenario_id=args.scenario_id)

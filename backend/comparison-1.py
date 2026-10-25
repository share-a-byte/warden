"""Compare one day's CSV samples and labels with warden-v2. Read-only."""

import argparse
import json
import subprocess
from datetime import date, timedelta

import numpy as np
import pandas as pd

DATABASE = "c20098cb596c05e6f8676a582d6c5564399eb1cc8c2d571be2574cbccf69fe44"
SAMPLE_COLUMNS = ["simulated_at", "site_id", "asset_id", "metric", "value"]
DB_COLUMNS = ["row_key", *SAMPLE_COLUMNS]
WINDOW_COLUMNS = [
    "window_key", "scenario_id", "attack_kind", "site_id", "asset_id", "metric",
    "start_iso", "end_iso", "multiplier", "offset",
]
KEYS = ["simulated_at", "site_id", "asset_id", "metric"]


def query_rows(query, columns):
    completed = subprocess.run(
        ["spacetime", "sql", "--server", "maincloud", "--format", "json", DATABASE, query],
        capture_output=True, text=True,
    )
    if completed.returncode:
        raise RuntimeError(f"SpacetimeDB query failed:\n{completed.stderr or completed.stdout}")
    return pd.DataFrame(json.loads(completed.stdout)[0]["rows"], columns=columns)


def read_day_csv(day, csv_path):
    header = set(pd.read_csv(csv_path, nrows=0).columns)
    site_column = "site_id" if "site_id" in header else "facility_id"
    required = (set(SAMPLE_COLUMNS) - {"site_id"}) | {site_column}
    if required - header:
        raise ValueError(f"CSV lacks columns: {sorted(required - header)}")
    columns = list(required | ({"is_attack"} if "is_attack" in header else set()))
    start = pd.Timestamp(day, tz="UTC")
    end = start + pd.Timedelta(days=1)
    selected = []
    row_offset = 0
    for chunk in pd.read_csv(csv_path, usecols=columns, chunksize=100_000):
        chunk = chunk.reset_index(drop=True)
        times = pd.to_datetime(chunk["simulated_at"], format="mixed", errors="coerce", utc=True)
        if times.isna().any():
            raise ValueError(f"Unparseable CSV timestamps: {chunk.loc[times.isna(), 'simulated_at'].head(3).tolist()}")
        matching = chunk.loc[(times >= start) & (times < end)].copy()
        if not matching.empty:
            matching["csv_line"] = matching.index + row_offset + 2  # 1-based, including header
            if site_column == "facility_id":
                matching["site_id"] = matching["facility_id"]
            selected.append(matching[SAMPLE_COLUMNS + (["is_attack"] if "is_attack" in header else [])
                                     + ["csv_line"]])
        row_offset += len(chunk)
    return (pd.concat(selected, ignore_index=True) if selected else
            pd.DataFrame(columns=SAMPLE_COLUMNS + (["is_attack"] if "is_attack" in header else [])
                         + ["csv_line"]))


def read_day_db(day):
    next_day = day + timedelta(days=1)
    return query_rows(f"""
        SELECT {", ".join(DB_COLUMNS)} FROM energyplus_metric_samples
        WHERE simulated_at >= '{day.isoformat()}'
          AND simulated_at < '{next_day.isoformat()}'
    """, DB_COLUMNS)


def read_attack_windows(day):
    next_day = day + timedelta(days=1)
    return query_rows(f"""
        SELECT {", ".join(WINDOW_COLUMNS)} FROM energyplus_attack_windows
        WHERE start_iso < '{next_day.isoformat()}'
          AND end_iso > '{day.isoformat()}'
    """, WINDOW_COLUMNS)


def csv_attack_labels(csv):
    labels = csv["is_attack"].astype(str).str.strip().str.lower().map(
        {"0": 0, "1": 1, "false": 0, "true": 1}
    )
    if labels.isna().any():
        raise ValueError("CSV is_attack must contain only 0/1 or true/false")
    return labels.groupby(csv["simulated_at"]).max().astype(int)


def attack_labels(database, windows):
    attacked = pd.Series(False, index=database.index)
    groups = database.groupby(["site_id", "asset_id", "metric"], sort=False).groups
    for window in windows.itertuples(index=False):
        indices = groups.get((window.site_id, window.asset_id, window.metric))
        if indices is None:
            continue
        start = pd.to_datetime(window.start_iso, utc=True).tz_localize(None)
        end = pd.to_datetime(window.end_iso, utc=True).tz_localize(None)
        if end <= start:
            raise ValueError(f"Invalid attack window: {window}")
        times = database.loc[indices, "simulated_at"]
        attacked.loc[indices] |= (times >= start) & (times < end)
    return attacked.groupby(database["simulated_at"]).max().astype(int)


def reconstructed_values(database, windows):
    """Try the same value * multiplier + offset interpretation as inference."""
    reconstructed = database.copy()
    applied = pd.Series(False, index=database.index)
    groups = database.groupby(["site_id", "asset_id", "metric"], sort=False).groups
    for window in windows.itertuples(index=False):
        indices = groups.get((window.site_id, window.asset_id, window.metric))
        if indices is None:
            continue
        start = pd.to_datetime(window.start_iso, utc=True).tz_localize(None)
        end = pd.to_datetime(window.end_iso, utc=True).tz_localize(None)
        times = database.loc[indices, "simulated_at"]
        matching = times.index[(times >= start) & (times < end)]
        if applied.loc[matching].any():
            raise ValueError("Overlapping windows; select a single scenario before reconstructing")
        reconstructed.loc[matching, "value"] = (
            reconstructed.loc[matching, "value"] * float(window.multiplier) + float(window.offset)
        )
        applied.loc[matching] = True
    return reconstructed


def normalize(frame):
    frame = frame.copy()
    frame["simulated_at"] = pd.to_datetime(
        frame["simulated_at"], format="mixed", errors="raise", utc=True
    ).dt.tz_localize(None)
    frame["value"] = pd.to_numeric(frame["value"], errors="raise")
    return frame


def compare(day, csv_path, output_path=None, site_id=None):
    csv = normalize(read_day_csv(day, csv_path))
    database = read_day_db(day)
    database["stored_simulated_at"] = database["simulated_at"]
    database = normalize(database)
    if site_id is not None:
        csv = csv.loc[csv["site_id"] == site_id].copy().reset_index(drop=True)
        database = database.loc[database["site_id"] == site_id].copy().reset_index(drop=True)
    print(f"{day}: CSV rows={len(csv):,}; warden-v2 rows={len(database):,}")
    if csv.empty or database.empty:
        print("One source is empty. Check the date, CSV path, and database selection.")
        # An empty source can still have missing rows worth exporting.

    for name, frame in (("CSV", csv), ("warden-v2", database)):
        print(f"  {name}: {frame.simulated_at.min()} to {frame.simulated_at.max()}; "
              f"sites={frame.site_id.unique()[:5].tolist()}")

    # Duplicate keys are counted separately; the notebook pivots duplicates by mean.
    csv_values = csv.groupby(KEYS, dropna=False, sort=False).agg(
        csv_value=("value", "mean"), csv_rows=("value", "size"), csv_line=("csv_line", "first")
    ).reset_index()
    db_values = database.groupby(KEYS, dropna=False, sort=False).agg(
        db_value=("value", "mean"), db_rows=("value", "size"), db_row_key=("row_key", "first")
    ).reset_index()
    merged = csv_values.merge(db_values, on=KEYS, how="outer", indicator=True,
                              validate="one_to_one")
    csv_only = merged.loc[merged["_merge"] == "left_only"]
    db_only = merged.loc[merged["_merge"] == "right_only"]
    both = merged.loc[merged["_merge"] == "both"].copy()
    both["absolute_difference"] = (both["csv_value"] - both["db_value"]).abs()
    different = both.loc[~np.isclose(both["csv_value"], both["db_value"],
                                     rtol=1e-6, atol=1e-6)]
    duplicate_count_diff = both.loc[both["csv_rows"] != both["db_rows"]]

    if output_path is not None:
        merged["difference_type"] = None
        merged.loc[csv_only.index, "difference_type"] = "csv_only"
        merged.loc[db_only.index, "difference_type"] = "db_only"
        merged.loc[duplicate_count_diff.index, "difference_type"] = "duplicate_count_mismatch"
        merged.loc[different.index, "difference_type"] = "value_mismatch"
        merged["absolute_difference"] = (merged["csv_value"] - merged["db_value"]).abs()
        fields = ["difference_type", *KEYS, "csv_line", "db_row_key", "csv_value",
                  "db_value", "absolute_difference", "csv_rows", "db_rows"]
        differences = merged.loc[merged["difference_type"].notna(), fields]
        differences.to_csv(output_path, index=False)
        print(f"  wrote {len(differences):,} differing metric keys to {output_path}")

    print(f"  matched metric keys={len(both):,}; CSV-only={len(csv_only):,}; "
          f"DB-only={len(db_only):,}")
    print(f"  differing values={len(different):,} (tolerance 1e-6 relative/absolute); "
          f"different duplicate counts={len(duplicate_count_diff):,}")
    if not both.empty:
        print(f"  maximum absolute value difference={both.absolute_difference.max():.9g}")
    for name, frame, columns in (
        ("CSV-only keys", csv_only, KEYS),
        ("DB-only keys", db_only, KEYS),
        ("largest value differences", different.sort_values("absolute_difference", ascending=False),
         KEYS + ["csv_value", "db_value", "absolute_difference"]),
    ):
        if not frame.empty:
            print(f"  {name} (up to 5):\n{frame[columns].head(5).to_string(index=False)}")
    if not different.empty:
        example = different.sort_values("absolute_difference", ascending=False).iloc[0]
        csv_match = pd.Series(True, index=csv.index)
        db_match = pd.Series(True, index=database.index)
        for column in KEYS:
            csv_match &= csv[column].eq(example[column])
            db_match &= database[column].eq(example[column])
        print(f"  raw CSV rows for largest difference "
              f"(CSV group size={int(example.csv_rows)}):\n"
              f"{csv.loc[csv_match, ['simulated_at', 'value']].head(10).to_string(index=False)}")
        print(f"  raw warden-v2 rows for largest difference "
              f"(DB group size={int(example.db_rows)}):\n"
              f"{database.loc[db_match, ['row_key', 'stored_simulated_at', 'value']].head(10).to_string(index=False)}")

    if "is_attack" in csv:
        windows = read_attack_windows(day)
        print(f"  attack windows={len(windows):,}; "
              f"scenario IDs={windows.scenario_id.dropna().unique()[:10].tolist()}")
        csv_labels = csv_attack_labels(csv)
        window_labels = attack_labels(database, windows)
        common_times = csv_labels.index.intersection(window_labels.index)
        mismatches = pd.DataFrame({
            "csv_is_attack": csv_labels.reindex(common_times),
            "db_attack_window": window_labels.reindex(common_times),
        })
        mismatches = mismatches.loc[
            mismatches["csv_is_attack"] != mismatches["db_attack_window"]
        ]
        print(f"  common timestamps={len(common_times):,}; "
              f"CSV attacked={int(csv_labels.sum()):,}; "
              f"window attacked={int(window_labels.sum()):,}; "
              f"label disagreements={len(mismatches):,}")
        if not mismatches.empty:
            print("  first label disagreements:\n" + mismatches.head(5).to_string())
        try:
            reconstructed = reconstructed_values(database, windows)
        except ValueError as exc:
            print(f"  could not compare reconstructed attack values: {exc}")
        else:
            reconstructed_values_by_key = reconstructed.groupby(KEYS, dropna=False)["value"].mean()
            reconstructed_matches = merged.loc[merged["_merge"] == "both", KEYS + ["csv_value"]].copy()
            reconstructed_matches = reconstructed_matches.join(
                reconstructed_values_by_key.rename("reconstructed_value"), on=KEYS
            )
            disagrees = reconstructed_matches.loc[
                ~np.isclose(reconstructed_matches["csv_value"],
                            reconstructed_matches["reconstructed_value"], rtol=1e-6, atol=1e-6)
            ]
            print(f"  differing values AFTER applying windows={len(disagrees):,} "
                  f"out of {len(reconstructed_matches):,} matched metric keys")
            if not disagrees.empty:
                print("  first reconstructed differences:\n" + disagrees.head(5).to_string(index=False))
    else:
        print("  CSV has no is_attack column; ground-truth labels were not compared")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="local CSV or .csv.gz to compare")
    parser.add_argument("--day", required=True, type=date.fromisoformat,
                        help="UTC date in YYYY-MM-DD format")
    parser.add_argument("--site-id", help="limit both sources to one site")
    parser.add_argument("--output", help="CSV for the full list of missing/different rows")
    args = parser.parse_args()
    compare(args.day, args.csv, output_path=args.output or
            f"metric_differences_{args.day.isoformat()}.csv", site_id=args.site_id)

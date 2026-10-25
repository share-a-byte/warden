#!/usr/bin/env python3
"""Combine the guardfleet_attacked_v2 day files into one CSV, in time order.

Keep this script in the same folder as the part files. Each part is one
simulated day and already includes the CSV header:

    guardfleet_attacked_v2_YYYY-MM-DD.csv.gz

From that folder:

    python3 combine_guardfleet_attacked_v2.py

That writes guardfleet_attacked_v2.csv beside the parts. To check that every
part arrived, the checksums match, and simulated_at never moves backward:

    python3 combine_guardfleet_attacked_v2.py --check-only

You can also pass the folder and an output path:

    python3 combine_guardfleet_attacked_v2.py /path/to/parts -o /path/to/guardfleet_attacked_v2.csv

Parts are joined from the earliest day to the latest. Rows that share a
timestamp stay in their original order. Python 3 is enough; no extra packages.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import sys
from pathlib import Path


class CombineError(Exception):
    pass


def part_day(path: Path) -> str | None:
    name = path.name
    prefix = "guardfleet_attacked_v2_"
    if not name.startswith(prefix):
        return None
    rest = name[len(prefix):]
    day = rest[:10]
    if len(day) != 10 or day[4] != "-" or day[7] != "-":
        return None
    if not day.replace("-", "").isdigit():
        return None
    if rest[10:] not in (".csv", ".csv.gz"):
        return None
    return day


def discover(directory: Path) -> list[Path]:
    by_day: dict[str, list[Path]] = {}
    for path in directory.iterdir():
        if not path.is_file():
            continue
        day = part_day(path)
        if day is None:
            continue
        by_day.setdefault(day, []).append(path)
    chosen: list[Path] = []
    for day in sorted(by_day):
        options = by_day[day]
        compressed = [p for p in options if p.name.endswith(".csv.gz")]
        plain = [p for p in options if p.name.endswith(".csv") and not p.name.endswith(".csv.gz")]
        if compressed and plain:
            print(f"Both .csv and .csv.gz exist for {day}; using the .csv.gz file.", file=sys.stderr)
        pick = sorted(compressed or plain, key=lambda p: p.name)
        if len(pick) != 1:
            raise CombineError(f"More than one part file for {day}: {[p.name for p in pick]}")
        chosen.append(pick[0])
    return chosen


def open_part(path: Path):
    if path.name.endswith(".gz"):
        return gzip.open(path, "rb")
    return path.open("rb")


def read_manifest(directory: Path) -> list[dict[str, str]] | None:
    path = directory / "manifest.csv"
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise CombineError("manifest.csv is empty")
    header = lines[0].split(",")
    expected = [
        "filename",
        "rows",
        "first_simulated_at",
        "last_simulated_at",
        "uncompressed_sha256",
    ]
    if header != expected:
        raise CombineError("manifest.csv does not have the expected columns")
    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cols = line.split(",")
        if len(cols) != len(expected):
            raise CombineError(f"Bad manifest row: {line}")
        rows.append(dict(zip(expected, cols)))
    return rows


def timestamp_of(line: bytes, filename: str) -> bytes:
    comma = line.find(b",")
    if comma <= 0:
        raise CombineError(f"A data row in {filename} has no simulated_at value")
    return line[:comma]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine guardfleet_attacked_v2 day files in time order."
    )
    parser.add_argument(
        "parts_dir",
        nargs="?",
        help="Folder containing the day files. Defaults to this script's folder.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Combined CSV path. Defaults to guardfleet_attacked_v2.csv in the parts folder.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check parts, checksums, and time order without writing the CSV.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    parts_dir = Path(args.parts_dir).expanduser().resolve() if args.parts_dir else script_dir
    if not parts_dir.is_dir():
        raise CombineError(f"Parts folder not found: {parts_dir}")

    parts = discover(parts_dir)
    if not parts:
        raise CombineError(
            f"No guardfleet_attacked_v2_YYYY-MM-DD.csv.gz files in {parts_dir}"
        )

    manifest_rows = read_manifest(parts_dir)
    if manifest_rows is None:
        print(
            "No manifest.csv found. Combining every day file in date order. "
            "A missing day can still look time-ordered, so send manifest.csv "
            "and original_sha256.txt with the parts.",
            file=sys.stderr,
        )
        manifest_by_name = None
    else:
        expected_names = [row["filename"] for row in manifest_rows]
        actual_names = [path.name for path in parts]
        if actual_names != expected_names:
            missing = [name for name in expected_names if name not in actual_names]
            extra = [name for name in actual_names if name not in expected_names]
            raise CombineError(
                "The files in the folder do not match manifest.csv.\n"
                f"Missing: {missing or 'none'}\n"
                f"Extra: {extra or 'none'}"
            )
        manifest_by_name = {row["filename"]: row for row in manifest_rows}

    output = None
    out_tmp = None
    out_fh = None
    committed = False
    if not args.check_only:
        output = (
            Path(args.output).expanduser().resolve()
            if args.output
            else parts_dir / "guardfleet_attacked_v2.csv"
        )
        if output.exists():
            raise CombineError(f"Output already exists: {output}")
        out_tmp = output.with_name(output.name + ".partial")
        if out_tmp.exists():
            raise CombineError(f"Remove the leftover partial file first: {out_tmp}")
        out_fh = out_tmp.open("wb")

    whole = hashlib.sha256()
    previous_ts = None
    first_ts = None
    last_ts = None
    total_rows = 0
    header = None

    try:
        for path in parts:
            part_hash = hashlib.sha256()
            rows = 0
            part_first = None
            part_last = None
            with open_part(path) as src:
                part_header = src.readline()
                if not part_header:
                    raise CombineError(f"{path.name} is empty")
                part_hash.update(part_header)
                if header is None:
                    header = part_header
                    whole.update(part_header)
                    if out_fh is not None:
                        out_fh.write(part_header)
                elif part_header != header:
                    raise CombineError(f"{path.name} has a different header")

                while True:
                    line = src.readline()
                    if not line:
                        break
                    if line in (b"\n", b"\r\n"):
                        raise CombineError(f"Blank line in {path.name}")
                    ts = timestamp_of(line, path.name)
                    if previous_ts is not None and ts < previous_ts:
                        raise CombineError(
                            "Time order is broken.\n"
                            f"Previous: {previous_ts.decode()}\n"
                            f"Next: {ts.decode()} in {path.name}"
                        )
                    previous_ts = ts
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts
                    if part_first is None:
                        part_first = ts
                    part_last = ts
                    rows += 1
                    part_hash.update(line)
                    whole.update(line)
                    if out_fh is not None:
                        out_fh.write(line)

            if rows == 0 or part_first is None or part_last is None:
                raise CombineError(f"{path.name} has no data rows")

            info = manifest_by_name.get(path.name) if manifest_by_name else None
            if info is not None:
                if int(info["rows"]) != rows:
                    raise CombineError(
                        f"{path.name}: manifest lists {info['rows']} rows, file has {rows}"
                    )
                if info["first_simulated_at"] != part_first.decode():
                    raise CombineError(f"{path.name}: first timestamp differs from manifest.csv")
                if info["last_simulated_at"] != part_last.decode():
                    raise CombineError(f"{path.name}: last timestamp differs from manifest.csv")
                if info["uncompressed_sha256"] != part_hash.hexdigest():
                    raise CombineError(
                        f"{path.name}: checksum differs from manifest.csv. "
                        "The file may have changed in transit."
                    )

            total_rows += rows
            print(
                f"{path.name}: {rows} rows, {part_first.decode()} -> {part_last.decode()}"
            )

        digest = whole.hexdigest()
        sha_path = parts_dir / "original_sha256.txt"
        if sha_path.exists():
            recorded = sha_path.read_text(encoding="utf-8").split()[0].strip()
            if recorded != digest:
                raise CombineError(
                    "Combined checksum differs from original_sha256.txt.\n"
                    f"Expected {recorded}\n"
                    f"Got      {digest}"
                )
            print("Checksum matches the original file.")
        else:
            print(f"Combined sha256: {digest}")

        if out_fh is not None and out_tmp is not None and output is not None:
            out_fh.close()
            out_fh = None
            out_tmp.replace(output)
            committed = True
            print(f"Wrote {output}")

        print(f"Rows: {total_rows}")
        if first_ts is not None and last_ts is not None:
            print(f"Time span: {first_ts.decode()} -> {last_ts.decode()}")
        if args.check_only:
            print("Check only: parts are complete and in time order.")
    finally:
        if out_fh is not None:
            out_fh.close()
        if out_tmp is not None and not committed and out_tmp.exists():
            out_tmp.unlink()


if __name__ == "__main__":
    try:
        main()
    except CombineError as exc:
        sys.exit(str(exc))

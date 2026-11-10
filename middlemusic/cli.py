import argparse
import sys
from pathlib import Path
from typing import Dict

from .config import LIBRARY_PATH
from .converter import BITRATES, MAPPED_FIELDS, convert_rows, parse_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert local music files listed in a CSV to tagged MP3 files."
    )
    parser.add_argument("csv_file", type=Path, help="CSV file containing local music paths")
    parser.add_argument("--library", type=Path, default=LIBRARY_PATH, help="Root of the local music library")
    parser.add_argument("--output", type=Path, required=True, help="Directory for converted MP3 files")
    parser.add_argument("--bitrate", choices=sorted(BITRATES), default="192k")
    for field in MAPPED_FIELDS:
        default = "source" if field == "source" else ""
        parser.add_argument(
            f"--{field.replace('_', '-')}-column",
            default=default,
            help=f"CSV heading to use for {field.replace('_', ' ')}",
        )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    mapping: Dict[str, str] = {
        field: getattr(args, f"{field}_column")
        for field in MAPPED_FIELDS
    }

    try:
        rows = parse_csv(args.csv_file.read_bytes(), mapping)
        total = len(rows)

        def report_progress(completed, _total, result):
            name = result.get("output") or result.get("source") or "row"
            print(f"[{completed}/{total}] {result['status']}: {name}", file=sys.stderr)

        outputs, errors = convert_rows(rows, args.library, args.output, args.bitrate, report_progress)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))

    print(f"Converted {len(outputs)} of {total} file(s) to {args.output}")
    if errors:
        print(f"{len(errors)} file(s) could not be converted:", file=sys.stderr)
        for error in errors:
            print(
                f"  CSV line {error['line_number']}: {error['source']}: {error['message']}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

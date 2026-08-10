from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json

from .config import SERVICE_ROOT
from .dataset import build_point_in_time_datasets, read_event_table, save_point_in_time_datasets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build point-in-time-correct retrieval and ranking datasets"
    )
    parser.add_argument(
        "--impressions",
        type=str,
        default=str(SERVICE_ROOT / "data" / "artifacts" / "synthetic_impressions.parquet"),
    )
    parser.add_argument(
        "--interactions",
        type=str,
        default=str(SERVICE_ROOT / "data" / "artifacts" / "synthetic_interactions.parquet"),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(SERVICE_ROOT / "data" / "datasets"),
    )
    parser.add_argument("--as-of", type=str, default=None)
    parser.add_argument("--attribution-hours", type=float, default=24.0)
    parser.add_argument("--max-history", type=int, default=20)
    args = parser.parse_args()

    from pathlib import Path

    result = build_point_in_time_datasets(
        read_event_table(Path(args.impressions)),
        read_event_table(Path(args.interactions)),
        as_of=datetime.fromisoformat(args.as_of) if args.as_of else None,
        attribution_window=timedelta(hours=args.attribution_hours),
        max_history=args.max_history,
    )
    save_point_in_time_datasets(result, Path(args.output_dir))
    print(json.dumps(result.report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

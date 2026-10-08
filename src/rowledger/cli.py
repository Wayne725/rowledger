import argparse
import csv
import json
import shutil
import sys
import zipfile
from importlib.resources import files
from pathlib import Path

from .engine import apply_review, reconcile
from .export import export_bundle
from .rules import Rules


def _json_file(path):
    with Path(path).open("rb") as handle:
        content = handle.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError("Rules or review file exceeds 1 MiB.")
    return json.loads(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline, source-linked reconciliation. No uploads or API keys.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Reconcile two CSV/XLSX files into a new report directory.")
    run.add_argument("orders", type=Path)
    run.add_argument("payments", type=Path)
    run.add_argument("--rules", type=Path)
    run.add_argument("--review", type=Path, help="Apply decisions exported from the same input snapshot.")
    run.add_argument("--out", type=Path, required=True)
    demo = commands.add_parser("demo", help="Create a complete synthetic example and report.")
    demo.add_argument("--out", type=Path, default=Path("runs/demo"))
    studio = commands.add_parser("studio", help="Open a persistent, local browser workspace.")
    studio.add_argument("--workspace", type=Path, default=Path("runs/studio"))
    studio.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "studio":
            if not 0 <= args.port <= 65535:
                raise ValueError("Port must be between 0 and 65535.")
            from .studio_server import serve
            serve(args.workspace, args.port)
            return 0
        elif args.command == "demo":
            examples = files("rowledger").joinpath("examples")
            result = reconcile(examples.joinpath("orders.csv"), examples.joinpath("payments.csv"))
            output = export_bundle(result, args.out)
            source_dir = output / "inputs"
            source_dir.mkdir()
            for name in ("orders.csv", "payments.csv", "rules.json"):
                shutil.copyfile(examples.joinpath(name), source_dir / name)
        else:
            rules = Rules.from_dict(_json_file(args.rules)) if args.rules else Rules()
            result = reconcile(args.orders, args.payments, rules)
            if args.review:
                result = apply_review(result, _json_file(args.review))
            output = export_bundle(result, args.out)
    except (ValueError, OSError, csv.Error, zipfile.BadZipFile) as error:
        print(f"rowledger: {error}", file=sys.stderr)
        return 2
    print(f"{result['summary']['matched_pairs']} matched pairs; {result['summary']['needs_attention']} source records need attention.")
    print(f"Report: {output / 'report.html'}")
    print(f"Snapshot: {result['run_id']}")
    return 0

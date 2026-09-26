"""The GridLock command-line interface."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from .contract import export_contract, validate_payload
from .ingestion.documents import IngestionError, ingest_plans
from .settings.loader import ConfigError, load_settings


def _default_config_path() -> Path:
    configured = os.environ.get("GRIDLOCK_CONFIG")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "config" / "gridlock.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gridlock")
    parser.add_argument("--config", type=Path, default=_default_config_path())
    commands = parser.add_subparsers(dest="command", required=True)
    config_parser = commands.add_parser("config", help="inspect resolved configuration")
    config_parser.add_argument("action", choices=["show"])
    contract_parser = commands.add_parser("contract", help="export or validate the API contract")
    contract_parser.add_argument("action", choices=["export", "validate"])
    contract_parser.add_argument("payload", type=Path, nargs="?")
    ingest_parser = commands.add_parser("ingest", help="ingest configured public sources")
    ingest_parser.add_argument("source", choices=["plans"])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "config" and args.action == "show":
        try:
            bundle = load_settings(args.config)
        except ConfigError as error:
            print(f"Configuration error: {error}")
            return 2
        print(json.dumps(bundle.summary(), indent=2, sort_keys=True))
        return 0
    if args.command == "contract" and args.action == "export":
        repository_root = Path(__file__).resolve().parents[3]
        schema_path, types_path = export_contract(repository_root)
        print(f"Wrote {schema_path}")
        print(f"Wrote {types_path}")
        return 0
    if args.command == "contract" and args.action == "validate":
        if args.payload is None:
            print("contract validate requires a payload path")
            return 2
        try:
            validate_payload(args.payload)
        except (OSError, ValueError) as error:
            print(f"Contract validation error: {error}")
            return 2
        print(f"Valid: {args.payload}")
        return 0
    if args.command == "ingest" and args.source == "plans":
        try:
            bundle = load_settings(args.config)
            report = ingest_plans(bundle, Path(__file__).resolve().parents[3])
        except (ConfigError, IngestionError) as error:
            print(f"Ingestion error: {error}")
            return 2
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

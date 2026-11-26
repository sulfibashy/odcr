"""Command line interface: `odcr <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from . import __version__
from .adapters import get_adapter
from .config import Config, ConfigError, load_config
from .contract import ContractError, load_contract
from .lint import lint
from .meta import ensure_meta, table_name
from .observe import checkpoint, trace
from .reconcile import load_reconciliation, run_reconciliation
from .runner import run_contract

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
TEMPLATES = {
    "contract.odcs.yaml": "contracts/orders.odcs.yaml",
    "odcr.yaml": "odcr.yaml",
    "reconciliation.yaml": "reconciliations/orders.recon.yaml",
}


def _adapter(config: Config, name: str):
    return get_adapter(config.connection(name))


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.directory)
    written = []
    for src, dest in TEMPLATES.items():
        target = root / dest
        if target.exists() and not args.force:
            print(f"skip   {target} (exists, use --force to overwrite)")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(resources.files("odcr.templates").joinpath(src).read_text(encoding="utf-8"),
                          encoding="utf-8")
        written.append(target)
        print(f"create {target}")
    print("\nNext: edit odcr.yaml connections, then run\n  odcr lint contracts/orders.odcs.yaml\n"
          "  odcr run contracts/orders.odcs.yaml --connection postgres-dev")
    return EXIT_OK


def cmd_lint(args: argparse.Namespace) -> int:
    code = EXIT_OK
    for path in args.contracts:
        res = lint(path, use_datacontract_cli=args.datacontract_cli)
        print(f"{'OK  ' if res.ok else 'FAIL'} {path}")
        for p in res.problems:
            print(f"  error:   {p}")
        for w in res.warnings:
            print(f"  warning: {w}")
        if res.datacontract_cli:
            print("  datacontract lint:\n    " + res.datacontract_cli.replace("\n", "\n    "))
        if not res.ok:
            code = EXIT_FAIL
    return code


def cmd_meta_init(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with _adapter(config, args.connection) as a:
        ensure_meta(a, config.meta_schema)
    print(f"Meta tables ready in schema '{config.meta_schema}' on connection '{args.connection}'")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    contract = load_contract(args.contract)
    with _adapter(config, args.connection) as a:
        result = run_contract(contract, a, config, batch_id=args.batch_id, where=args.where,
                              objects=args.object or None, pipeline=args.pipeline, stage=args.stage,
                              send_notifications=not args.no_notify)
    _print(result.to_dict() if args.json else result.summary(), args.json)
    if result.status == "fail" or (args.fail_on_warn and result.status == "warn"):
        return EXIT_FAIL
    return EXIT_OK


def cmd_reconcile(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    recon = load_reconciliation(args.spec)
    src_name = args.source or recon.source.connection
    tgt_name = args.target or recon.target.connection
    if not src_name or not tgt_name:
        raise ConfigError("source and target connections are required (in the spec or via --source/--target)")
    contacts = []
    if args.contract:
        contacts = load_contract(args.contract).contacts
    with _adapter(config, src_name) as s, _adapter(config, tgt_name) as t:
        result = run_reconciliation(recon, s, t, config, batch_id=args.batch_id, pipeline=args.pipeline,
                                    contacts=contacts, send_notifications=not args.no_notify)
    if args.json:
        _print({"run_id": result.run_id, "recon_id": result.recon_id, "status": result.status,
                "batch_id": result.batch_id, "results": [r.__dict__ for r in result.results]}, True)
    else:
        print(result.summary())
    return EXIT_OK if result.passed else EXIT_FAIL


def cmd_checkpoint(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with _adapter(config, args.connection) as a:
        event_id = checkpoint(a, pipeline=args.pipeline, stage=args.stage, batch_id=args.batch_id,
                              row_count=args.rows, object_name=args.object, where=args.where, mode=args.mode,
                              status=args.status, config=config)
    print(f"checkpoint {event_id}: {args.pipeline}/{args.stage} batch={args.batch_id}")
    return EXIT_OK


def cmd_trace(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with _adapter(config, args.connection) as a:
        steps = trace(a, pipeline=args.pipeline, batch_id=args.batch_id, config=config, tolerance=args.tolerance)
    if args.json:
        _print([s.__dict__ for s in steps], True)
    else:
        if not steps:
            print(f"No events for pipeline '{args.pipeline}' batch '{args.batch_id}'")
        for s in steps:
            change = "" if s.change is None else f" ({s.change:+d})"
            flag = f"  <-- {s.flag}" if s.flag else ""
            print(f"{s.stage:<12} {str(s.row_count):>10} rows{change:<10} {s.mode:<10} {s.status:<6} "
                  f"{s.object_name or ''}{flag}")
    return EXIT_FAIL if any(s.flag for s in steps) else EXIT_OK


def cmd_history(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with _adapter(config, args.connection) as a:
        ensure_meta(a, config.meta_schema)
        t = table_name(a, config.meta_schema, "validation_runs")
        sql = (f"SELECT started_at, contract_id, contract_version, object_name, batch_id, status, rows_checked, "
               f"checks_failed, checks_warned FROM {t}")
        params: list[Any] = []
        if args.contract_id:
            sql += f" WHERE contract_id = {a.placeholder}"
            params.append(args.contract_id)
        rows = a.fetchall(a.limit(sql + " ORDER BY started_at DESC", args.limit), params or None)
    if args.json:
        keys = ["started_at", "contract_id", "version", "object", "batch_id", "status", "rows", "failed", "warned"]
        _print([dict(zip(keys, r)) for r in rows], True)
    else:
        for r in rows:
            print(f"{r[0]}  {r[1]} v{r[2]}  {r[3]}  batch={r[4]}  {str(r[5]).upper():<4}  rows={r[6]} "
                  f"failed={r[7]} warned={r[8]}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="odcr", description="Open Data Contract Runtime: enforce ODCS contracts, "
                                "reconcile source and target, trace batches end to end.")
    p.add_argument("--version", action="version", version=f"odcr {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser, connection: bool = True) -> None:
        sp.add_argument("--config", "-c", help="config file (default: ./odcr.yaml)")
        if connection:
            sp.add_argument("--connection", "-C", required=True, help="connection name from the config")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    sp = sub.add_parser("init", help="create starter contract, config and reconciliation files")
    sp.add_argument("directory", nargs="?", default=".")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("lint", help="validate contract files")
    sp.add_argument("contracts", nargs="+")
    sp.add_argument("--datacontract-cli", action="store_true", help="also run `datacontract lint` if installed")
    sp.set_defaults(func=cmd_lint)

    sp = sub.add_parser("meta-init", help="create the meta schema and tables on a connection")
    common(sp)
    sp.set_defaults(func=cmd_meta_init)

    sp = sub.add_parser("run", help="check a table or batch against a contract")
    sp.add_argument("contract")
    common(sp)
    sp.add_argument("--batch-id", help="id of the batch / micro-batch / offset range being checked")
    sp.add_argument("--where", help="SQL filter selecting the batch, e.g. \"load_id = '42'\"")
    sp.add_argument("--object", action="append", help="only check this schema object (repeatable)")
    sp.add_argument("--pipeline", help="pipeline name, to record an end-to-end checkpoint")
    sp.add_argument("--stage", help="stage name for the checkpoint, e.g. ingestion, bronze, gold")
    sp.add_argument("--fail-on-warn", action="store_true", help="exit 1 on warnings too")
    sp.add_argument("--no-notify", action="store_true")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("reconcile", help="compare source and target for a batch")
    sp.add_argument("spec")
    common(sp, connection=False)
    sp.add_argument("--source", help="override source connection")
    sp.add_argument("--target", help="override target connection")
    sp.add_argument("--batch-id")
    sp.add_argument("--pipeline")
    sp.add_argument("--contract", help="contract file, to notify its source team")
    sp.add_argument("--no-notify", action="store_true")
    sp.set_defaults(func=cmd_reconcile)

    sp = sub.add_parser("checkpoint", help="record that a stage processed a batch")
    common(sp)
    sp.add_argument("--pipeline", required=True)
    sp.add_argument("--stage", required=True)
    sp.add_argument("--batch-id", required=True)
    sp.add_argument("--rows", type=int, help="row count (otherwise counted from --object)")
    sp.add_argument("--object", help="table to count rows from")
    sp.add_argument("--where")
    sp.add_argument("--mode", default="batch", choices=["batch", "streaming", "cdc", "queue", "microbatch"])
    sp.add_argument("--status", default="ok")
    sp.set_defaults(func=cmd_checkpoint)

    sp = sub.add_parser("trace", help="show a batch's journey through every stage")
    common(sp)
    sp.add_argument("--pipeline", required=True)
    sp.add_argument("--batch-id", required=True)
    sp.add_argument("--tolerance", type=int, default=0, help="allowed row change between stages")
    sp.set_defaults(func=cmd_trace)

    sp = sub.add_parser("history", help="recent validation runs")
    common(sp)
    sp.add_argument("--contract-id")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_history)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ContractError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        for prob in getattr(exc, "problems", []) or []:
            print(f"  - {prob}", file=sys.stderr)
        return EXIT_USAGE
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

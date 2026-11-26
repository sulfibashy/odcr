"""Command line interface: `odcr <command>`. Run `odcr --help` or `odcr <command> --help`."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from . import __version__, samples
from .adapters import ADAPTERS, driver_installed, get_adapter, resolve
from .adapters.base import Adapter
from .config import Config, ConfigError, load_config
from .contract import Contract, ContractError, load_contract
from .lint import lint
from .observe import checkpoint, trace
from .reconcile import load_reconciliation, run_reconciliation
from .repository import ContractRepository
from .runner import run_contract

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2


def _print(obj: Any, as_json: bool = False) -> None:
    print(json.dumps(obj, indent=2, default=str) if as_json else obj)


def _adapters(config: Config, name: str, stack: ExitStack) -> tuple[Adapter, Adapter]:
    """The data adapter and the meta adapter (the same one unless meta.connection is set)."""
    data = stack.enter_context(get_adapter(config.connection(name)))
    if config.meta_connection and config.meta_connection != name:
        return data, stack.enter_context(get_adapter(config.connection(config.meta_connection)))
    return data, data


def _contract(args: argparse.Namespace, config: Config) -> Contract:
    if getattr(args, "contract", None):
        return load_contract(args.contract)
    repo = ContractRepository.from_config(config)
    if getattr(args, "contract_id", None):
        return repo.get(args.contract_id)
    if getattr(args, "for_object", None):
        hits = repo.find_by_object(args.for_object)
        if not hits:
            raise ContractError(f"No contract in {repo.root} describes '{args.for_object}'")
        if len({c.id for c, _ in hits}) > 1:
            raise ContractError(f"Several contracts describe '{args.for_object}': {sorted({c.id for c, _ in hits})}")
        return hits[0][0]
    raise ContractError("Give a contract file, --contract-id or --for-object")


# ---------------------------------------------------------------------------------------- commands
def cmd_init(args: argparse.Namespace) -> int:
    from .scaffold import scaffold

    interactive = not args.no_input and sys.stdin.isatty()
    target = Path(args.directory)
    files = scaffold(target, name=args.name, adapter=args.adapter or "duckdb", meta_schema=args.meta_schema,
                     platform_channel=args.alerts, force=args.force, interactive=interactive)
    for f in files:
        print(f"  create {f}")
    info = resolve(next(line.split(":", 1)[1].strip() for line in (target / "odcr.yaml").read_text().splitlines()
                        if line.strip().startswith("type:")))
    extra = f'"odcr[{info.extra}]"' if info.extra else "odcr"
    print(f"\nCreated an odcr project for {info.title} in {target}\n\nNext steps:\n"
          f"  cd {target}\n  pip install {extra}\n  cp .env.example .env      # then fill in the connection\n"
          "  odcr doctor -C main\n  odcr meta-init -C main\n  odcr seed -C main          # optional sample data\n"
          "  odcr run --contract-id orders -C main\n")
    return EXIT_OK


def cmd_adapters(args: argparse.Namespace) -> int:
    rows = []
    for info in ADAPTERS.values():
        rows.append({"adapter": info.name, "platform": info.title, "category": info.category, "where": info.clouds,
                     "install": f'pip install "odcr[{info.extra}]"' if info.extra else "pip install odcr",
                     "driver_installed": driver_installed(info),
                     "tested": "CI end-to-end" if info.tested == "ci" else "end-to-end with credentials",
                     "aliases": list(info.aliases)})
    if args.json:
        _print(rows, True)
        return EXIT_OK
    print(f"{'adapter':<11} {'installed':<10} {'platform':<30} install")
    for r in rows:
        print(f"{r['adapter']:<11} {'yes' if r['driver_installed'] else 'no':<10} {r['platform']:<30} {r['install']}")
    print("\nCreate a project: odcr init my_project --adapter <adapter>")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    opts = config.connection(args.connection)
    info = resolve(opts.get("type", ""))
    print(f"odcr {__version__} on Python {sys.version.split()[0]} ({sys.platform})")
    print(f"connection '{args.connection}': {info.title}")
    adapter = get_adapter(opts)
    print(f"  driver:      {adapter.driver_version()}")
    ok = True
    try:
        adapter.connect()
        adapter.ping()
        print("  connect:     ok")
        print(f"  schema:      {adapter.current_schema()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  connect:     FAILED: {exc}")
        return EXIT_FAIL
    try:
        adapter.meta_ensure(config.meta_schema)
        print(f"  meta tables: ok ({config.meta_schema})")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"  meta tables: FAILED: {exc}\n    (grant create rights, or set meta.connection to another platform)")
    finally:
        adapter.close()
    try:
        repo = ContractRepository.from_config(config)
        print(f"  contracts:   {len(repo.contracts)} valid, {len(repo.errors)} invalid in {repo.root}")
        ok = ok and not repo.errors
    except (ConfigError, ContractError) as exc:
        print(f"  contracts:   {exc}")
    return EXIT_OK if ok else EXIT_FAIL


def cmd_seed(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with get_adapter(config.connection(args.connection)) as a:
        target = args.table or ("landing/orders/orders_sample.parquet" if a.dialect == "files" else "orders")
        a.create_sample(target, samples.COLUMNS, samples.ROWS)
    print(f"Loaded {len(samples.ROWS)} sample rows into {target} (batch-001 is clean, batch-002 breaks the contract)")
    return EXIT_OK


def cmd_lint(args: argparse.Namespace) -> int:
    paths = list(args.paths)
    if not paths:
        config = load_config(args.config)
        paths = [str(ContractRepository.from_config(config).root)]
    code = EXIT_OK
    for p in paths:
        if Path(p).is_dir():
            repo = ContractRepository.load(p)
            for c in repo.contracts.values():
                code = max(code, _lint_one(c.path or "", args.datacontract_cli))
            for f, problems in repo.errors.items():
                print(f"FAIL {f}")
                for prob in problems:
                    print(f"  error:   {prob}")
                code = EXIT_FAIL
            print(f"\n{len(repo.contracts)} valid contracts, {len(repo.errors)} invalid in {p}")
        else:
            code = max(code, _lint_one(p, args.datacontract_cli))
    return code


def _lint_one(path: str, dc_cli: bool) -> int:
    res = lint(path, use_datacontract_cli=dc_cli)
    print(f"{'OK  ' if res.ok else 'FAIL'} {path}")
    for p in res.problems:
        print(f"  error:   {p}")
    for w in res.warnings:
        print(f"  warning: {w}")
    if res.datacontract_cli:
        print("  datacontract lint:\n    " + res.datacontract_cli.replace("\n", "\n    "))
    return EXIT_OK if res.ok else EXIT_FAIL


def cmd_contracts(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    repo = ContractRepository.from_config(config)
    rows = [{"id": c.id, "version": c.version, "domain": c.domain, "owner": c.owner,
             "objects": [o.physical_name for o in c.schema], "file": c.path} for c in repo.contracts.values()]
    if args.json:
        _print(rows, True)
    else:
        for r in rows:
            print(f"{r['id']:<24} v{r['version']:<8} {', '.join(r['objects']):<40} {r['file']}")
        print(f"\n{len(rows)} contracts in {repo.root}" + (f", {len(repo.errors)} invalid" if repo.errors else ""))
    return EXIT_OK


def cmd_meta_init(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with ExitStack() as stack:
        _, meta = _adapters(config, args.connection, stack)
        meta.meta_ensure(config.meta_schema)
    print(f"Meta tables ready in '{config.meta_schema}'")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    contract = _contract(args, config)
    with ExitStack() as stack:
        data, meta = _adapters(config, args.connection, stack)
        result = run_contract(contract, data, config, batch_id=args.batch_id, where=args.where,
                              objects=args.object or None, pipeline=args.pipeline, stage=args.stage,
                              send_notifications=not args.no_notify, meta=meta)
    _print(result.to_dict() if args.json else result.summary(), args.json)
    if result.status == "fail" or (args.fail_on_warn and result.status == "warn"):
        return EXIT_FAIL
    return EXIT_OK


def cmd_watch(args: argparse.Namespace) -> int:
    from .watch import watch

    config = load_config(args.config)
    contract = _contract(args, config)
    failed = 0

    def report(event: Any) -> None:
        nonlocal failed
        failed += event.result.status == "fail"
        print(f"{event.result.status.upper():<5} {event.object_name} batch={event.batch_id}")

    with ExitStack() as stack:
        data, meta = _adapters(config, args.connection, stack)
        print(f"Watching {contract.id} on '{args.connection}'" + ("" if args.once else f" every {args.interval}s"))
        watch(contract, data, config, interval=args.interval, on_event=report, max_cycles=1 if args.once else None,
              batch_column=args.batch_column, meta=meta, pipeline=args.pipeline,
              send_notifications=not args.no_notify)
    return EXIT_FAIL if failed else EXIT_OK


def cmd_reconcile(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    recon = load_reconciliation(args.spec)
    src_name = args.source or recon.source.connection
    tgt_name = args.target or recon.target.connection
    if not src_name or not tgt_name:
        raise ConfigError("source and target connections are required (in the spec or via --source/--target)")
    contacts = load_contract(args.contract).contacts if args.contract else []
    with ExitStack() as stack:
        s = stack.enter_context(get_adapter(config.connection(src_name)))
        t = stack.enter_context(get_adapter(config.connection(tgt_name)))
        meta = stack.enter_context(get_adapter(config.connection(config.meta_connection))) \
            if config.meta_connection else t
        result = run_reconciliation(recon, s, t, config, batch_id=args.batch_id, pipeline=args.pipeline,
                                    contacts=contacts, send_notifications=not args.no_notify, meta=meta)
    if args.json:
        _print({"run_id": result.run_id, "recon_id": result.recon_id, "status": result.status,
                "batch_id": result.batch_id, "results": [r.__dict__ for r in result.results]}, True)
    else:
        print(result.summary())
    return EXIT_OK if result.passed else EXIT_FAIL


def cmd_checkpoint(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with ExitStack() as stack:
        data, meta = _adapters(config, args.connection, stack)
        event_id = checkpoint(data, pipeline=args.pipeline, stage=args.stage, batch_id=args.batch_id,
                              row_count=args.rows, object_name=args.object, where=args.where, mode=args.mode,
                              status=args.status, config=config, meta=meta)
    print(f"checkpoint {event_id}: {args.pipeline}/{args.stage} batch={args.batch_id}")
    return EXIT_OK


def cmd_trace(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    with ExitStack() as stack:
        _, meta = _adapters(config, args.connection, stack)
        steps = trace(meta, pipeline=args.pipeline, batch_id=args.batch_id, config=config, tolerance=args.tolerance)
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
    cols = ["started_at", "contract_id", "contract_version", "object_name", "batch_id", "status", "rows_checked",
            "checks_failed", "checks_warned"]
    with ExitStack() as stack:
        _, meta = _adapters(config, args.connection, stack)
        meta.meta_ensure(config.meta_schema)
        rows = meta.meta_select(config.meta_schema, "validation_runs", cols,
                                {"contract_id": args.contract_id} if args.contract_id else None,
                                order_by="started_at", limit=args.limit)
    if args.json:
        _print(rows, True)
    else:
        for r in rows:
            print(f"{r['started_at']}  {r['contract_id']} v{r['contract_version']}  {r['object_name']}  "
                  f"batch={r['batch_id']}  {str(r['status']).upper():<4}  rows={r['rows_checked']} "
                  f"failed={r['checks_failed']} warned={r['checks_warned']}")
    return EXIT_OK


# ---------------------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="odcr", description="Open Data Contract Runtime: enforce ODCS data contracts "
                                "where data lands, reconcile source and target, trace batches end to end.")
    p.add_argument("--version", action="version", version=f"odcr {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    def common(sp: argparse.ArgumentParser, connection: bool = True) -> None:
        sp.add_argument("--config", "-c", help="config file (default: ./odcr.yaml)")
        if connection:
            sp.add_argument("--connection", "-C", default="main", help="connection name from the config (default: main)")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    def contract_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("contract", nargs="?", help="contract file (or use --contract-id / --for-object)")
        sp.add_argument("--contract-id", help="contract id in the contract repository")
        sp.add_argument("--for-object", help="find the contract describing this table / collection / path")

    sp = sub.add_parser("init", help="create a new odcr project (like dbt init)")
    sp.add_argument("directory", nargs="?", default="odcr_project")
    sp.add_argument("--adapter", "-a", help="platform, e.g. postgres, snowflake, databricks (see: odcr adapters)")
    sp.add_argument("--name", help="project name (default: the directory name)")
    sp.add_argument("--meta-schema", default="odcr_meta")
    sp.add_argument("--alerts", default="email", choices=["slack", "teams", "email", "none"],
                    help="platform team alert channel")
    sp.add_argument("--no-input", action="store_true", help="do not ask questions; use the options and defaults")
    sp.add_argument("--force", action="store_true", help="write into a non-empty directory")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("adapters", help="list supported platforms and how to install each")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_adapters)

    sp = sub.add_parser("doctor", help="check a connection, its driver, the meta tables and the contracts")
    common(sp)
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("seed", help="load the sample orders data into a connection")
    common(sp)
    sp.add_argument("--table", help="target table / collection / file path (default: orders)")
    sp.set_defaults(func=cmd_seed)

    sp = sub.add_parser("lint", help="validate contract files or folders (default: the contract repository)")
    sp.add_argument("paths", nargs="*")
    sp.add_argument("--config", "-c")
    sp.add_argument("--datacontract-cli", action="store_true", help="also run `datacontract lint` if installed")
    sp.set_defaults(func=cmd_lint)

    sp = sub.add_parser("contracts", help="list the contracts in the contract repository")
    common(sp, connection=False)
    sp.set_defaults(func=cmd_contracts)

    sp = sub.add_parser("meta-init", help="create the meta schema and tables")
    common(sp)
    sp.set_defaults(func=cmd_meta_init)

    sp = sub.add_parser("run", help="check a table, file or batch against its contract")
    contract_args(sp)
    common(sp)
    sp.add_argument("--batch-id", help="id of the batch / micro-batch / CDC transaction / file")
    sp.add_argument("--where", help="filter selecting the batch: SQL, or JSON for MongoDB")
    sp.add_argument("--object", action="append", help="only check this schema object (repeatable)")
    sp.add_argument("--pipeline", help="pipeline name, to record an end-to-end checkpoint")
    sp.add_argument("--stage", help="stage name for the checkpoint, e.g. landing, bronze, gold")
    sp.add_argument("--fail-on-warn", action="store_true", help="exit 1 on warnings too")
    sp.add_argument("--no-notify", action="store_true")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("watch", help="check every new file or batch the moment it lands")
    contract_args(sp)
    common(sp)
    sp.add_argument("--batch-column", help="column identifying a batch in a table (e.g. load_id)")
    sp.add_argument("--interval", type=float, default=60.0, help="seconds between polls (default 60)")
    sp.add_argument("--once", action="store_true", help="check what is new, then exit (for schedulers)")
    sp.add_argument("--pipeline", help="pipeline name (default: watch:<contract id>)")
    sp.add_argument("--no-notify", action="store_true")
    sp.set_defaults(func=cmd_watch)

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
    sp.add_argument("--object", help="table / collection / path to count rows from")
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
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles
        except Exception:  # noqa: BLE001
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ContractError, ConfigError, FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        for prob in getattr(exc, "problems", []) or []:
            print(f"  - {prob}", file=sys.stderr)
        return EXIT_USAGE
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

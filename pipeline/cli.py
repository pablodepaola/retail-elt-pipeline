"""Orchestration entrypoint (the 'task graph' GitHub Actions calls).

    python -m pipeline.cli run                 # incremental daily run
    python -m pipeline.cli backfill --start ... --end ...
    python -m pipeline.cli extract|load|quality|dbt|status|publish

The full `run`/`backfill` path is: extract -> load -> Great Expectations gate ->
dbt build (+tests) -> record run audit -> publish to Oracle -> advance watermark.
The watermark advances ONLY on success, so failed/partial runs are safely
re-runnable with no double counting.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import uuid

from . import config, dbt_runner, extract, load, oracle_publish, quality_ge, state


def _setup_logging(verbose: bool = True) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)-14s %(message)s",
        datefmt="%H:%M:%S",
    )


def _parse_date(s: str | None) -> dt.date | None:
    return dt.datetime.strptime(s, "%Y-%m-%d").date() if s else None


def _pipeline(mode: str, use_sample: bool, start, end, target: str,
              publish: bool, dry_run: bool) -> int:
    log = logging.getLogger("elt.run")
    run_id = uuid.uuid4().hex[:12]
    started = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    wm = state.load_watermark()

    status = "FAIL"
    tests = {"passed": 0, "failed": 0, "errored": 0}
    ext = {"days": [], "rows": {}, "high_water": None}
    try:
        # 1) EXTRACT (incremental, idempotent, immutable raw)
        ext = extract.run_extract(wm, use_sample, start=start, end=end)
        if not ext["days"]:
            log.info("watermark up to date; nothing to do")
            return 0

        # 2) LOAD (mirror raw lake -> DuckDB raw schema)
        con = load.connect()
        load.load_raw(con)
        con.close()

        # 3) DATA QUALITY GATE at raw boundary (Great Expectations)
        quality_ge.validate_raw()

        # 4) TRANSFORM + TEST (dbt build: seeds, models, snapshots, tests)
        tests = dbt_runner.build(target=target)

        status = "PASS"
    finally:
        rows_total = sum(ext["rows"].values()) if ext["rows"] else 0
        con = load.connect()
        load.record_run(
            con,
            {
                "run_id": run_id,
                "run_started_at": started,
                "run_finished_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                "mode": mode,
                "window_start": ext["days"][0] if ext["days"] else None,
                "window_end": ext["days"][-1] if ext["days"] else None,
                "rows_extracted": rows_total,
                "dbt_tests_passed": tests.get("passed", 0),
                "dbt_tests_failed": tests.get("failed", 0) + tests.get("errored", 0),
                "status": status,
            },
        )
        con.close()

    # 5) SERVE: publish marts to Oracle (or CSV dry-run)
    if dry_run:
        oracle_publish.export_csv()
    elif publish:
        oracle_publish.publish()

    # 6) Advance watermark ONLY on success
    if ext["high_water"]:
        state.save_watermark(state.advance(wm, _parse_date(ext["high_water"])
                                           if isinstance(ext["high_water"], str)
                                           else ext["high_water"]))
    log.info("RUN %s status=%s rows=%d tests(pass=%d fail=%d)",
             run_id, status, rows_total, tests.get("passed", 0),
             tests.get("failed", 0) + tests.get("errored", 0))
    return 0


def cmd_run(a) -> int:
    return _pipeline("incremental", a.sample, None, None, a.target, a.publish, a.dry_run)


def cmd_backfill(a) -> int:
    return _pipeline("backfill", a.sample, _parse_date(a.start), _parse_date(a.end),
                     a.target, a.publish, a.dry_run)


def cmd_extract(a) -> int:
    wm = state.load_watermark()
    res = extract.run_extract(wm, a.sample, _parse_date(a.start), _parse_date(a.end))
    if res["high_water"]:
        hw = res["high_water"]
        state.save_watermark(state.advance(wm, _parse_date(hw) if isinstance(hw, str) else hw))
    print(res)
    return 0


def cmd_load(a) -> int:
    con = load.connect()
    print(load.load_raw(con))
    con.close()
    return 0


def cmd_quality(a) -> int:
    quality_ge.validate_raw()
    return 0


def cmd_dbt(a) -> int:
    print(dbt_runner.build(target=a.target, select=a.select))
    return 0


def cmd_publish(a) -> int:
    if a.dry_run:
        print(oracle_publish.export_csv())
    else:
        print(oracle_publish.publish())
    return 0


def cmd_status(a) -> int:
    wm = state.load_watermark()
    print(f"watermark.last_loaded_date = {wm.last_loaded_date}")
    print(f"watermark.last_run_at      = {wm.last_run_at}")
    print(f"watermark.runs             = {wm.runs}")
    try:
        con = load.connect(read_only=True)
        rows = con.execute(
            "SELECT run_id, window_start, window_end, rows_extracted, "
            "dbt_tests_passed, dbt_tests_failed, status, run_finished_at "
            "FROM meta.pipeline_runs ORDER BY run_finished_at DESC LIMIT 5"
        ).fetchall()
        con.close()
        print("\nlast runs:")
        for r in rows:
            print(" ", r)
    except Exception as exc:
        print(f"(no run history yet: {exc})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline", description="Retail ELT orchestrator")
    p.add_argument("--sample", action="store_true",
                   help="use the committed demo data in data/sample (CI default)")
    p.add_argument("--target", default="dev", help="dbt target (dev|prod|ci)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="incremental daily run")
    r.add_argument("--publish", action="store_true", help="publish marts to Oracle")
    r.add_argument("--dry-run", action="store_true", help="export marts to CSV instead")
    r.set_defaults(func=cmd_run)

    b = sub.add_parser("backfill", help="process an explicit date range")
    b.add_argument("--start", required=True)
    b.add_argument("--end", required=True)
    b.add_argument("--publish", action="store_true")
    b.add_argument("--dry-run", action="store_true")
    b.set_defaults(func=cmd_backfill)

    e = sub.add_parser("extract")
    e.add_argument("--start")
    e.add_argument("--end")
    e.set_defaults(func=cmd_extract)

    sub.add_parser("load").set_defaults(func=cmd_load)
    sub.add_parser("quality").set_defaults(func=cmd_quality)

    d = sub.add_parser("dbt")
    d.add_argument("--select")
    d.set_defaults(func=cmd_dbt)

    pub = sub.add_parser("publish")
    pub.add_argument("--dry-run", action="store_true")
    pub.set_defaults(func=cmd_publish)

    sub.add_parser("status").set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    args = build_parser().parse_args(argv)
    # propagate top-level flags onto subcommand namespace
    for k in ("sample", "target"):
        if not hasattr(args, k):
            setattr(args, k, getattr(args, k, None))
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("elt").error("PIPELINE FAILED: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())

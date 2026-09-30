"""Thin wrapper around the dbt CLI so the orchestrator can run dbt and read back
structured test results (to surface 'tests passing' on the dashboard and to fail
the run on any failed/error test)."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from . import config

log = logging.getLogger("elt.dbt")

RUN_RESULTS = config.DBT_DIR / "target" / "run_results.json"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    # The dbt profile reads the warehouse path from this env var (see profiles.yml).
    env["DBT_DUCKDB_PATH"] = str(config.DUCKDB_PATH)
    return env


def run(args: list[str], target: str = "dev") -> int:
    cmd = [
        "dbt",
        *args,
        "--project-dir",
        str(config.DBT_DIR),
        "--profiles-dir",
        str(config.DBT_DIR),
        "--target",
        target,
    ]
    log.info("dbt %s", " ".join(args))
    proc = subprocess.run(cmd, env=_env())
    return proc.returncode


def parse_test_results(path: Path = RUN_RESULTS) -> dict:
    """Return {passed, failed, warned, errored} for test nodes in the last run."""
    summary = {"passed": 0, "failed": 0, "warned": 0, "errored": 0}
    if not path.exists():
        return summary
    data = json.loads(path.read_text())
    for r in data.get("results", []):
        if not r.get("unique_id", "").startswith("test."):
            continue
        status = r.get("status")
        if status == "pass":
            summary["passed"] += 1
        elif status == "fail":
            summary["failed"] += 1
        elif status == "warn":
            summary["warned"] += 1
        elif status == "error":
            summary["errored"] += 1
    return summary


def build(target: str = "dev", select: str | None = None) -> dict:
    """Run `dbt build` (seeds + models + snapshots + tests). Returns test summary.

    Raises on a non-zero dbt exit so failing quality checks fail the run.
    """
    args = ["build"]
    if select:
        args += ["--select", select]
    rc = run(args, target=target)
    summary = parse_test_results()
    summary["returncode"] = rc
    if rc != 0:
        raise RuntimeError(
            f"dbt build failed (exit {rc}); tests: {summary}. Run failed by design."
        )
    return summary

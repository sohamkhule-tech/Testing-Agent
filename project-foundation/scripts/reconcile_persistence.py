#!/usr/bin/env python3
"""
Persistence Reconciliation Utility

Compares data between filesystem and PostgreSQL backends.

Usage:
    # Compare all runs between filesystem and PostgreSQL
    python scripts/reconcile_persistence.py --mode compare --entity run

    # Compare a specific run
    python scripts/reconcile_persistence.py --mode compare --entity run --run-id <uuid>

    # Dry-run repair — shows what would be repaired
    python scripts/reconcile_persistence.py --mode repair --entity run --dry-run

    # Actually repair (requires --dry-run first and --repair flag)
    python scripts/reconcile_persistence.py --mode repair --entity run --repair

Safety:
    * Default mode is ``--dry-run`` — no data is ever modified.
    * ``--repair`` must be explicitly passed to perform writes.
    * Only filesystem → PostgreSQL writes are performed (FS is authoritative).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("reconcile")


# ===================================================================
# Data structures
# ===================================================================


@dataclass
class ComparisonResult:
    """Result of comparing one entity across backends."""

    entity_type: str
    entity_id: str
    in_filesystem: bool = False
    in_postgres: bool = False
    field_mismatches: list[dict] = field(default_factory=list)
    fs_data: dict | None = None
    pg_data: dict | None = None

    @property
    def is_consistent(self) -> bool:
        return self.in_filesystem == self.in_postgres and not self.field_mismatches


@dataclass
class ReconciliationReport:
    """Aggregate report for one entity type."""

    entity_type: str
    total_filesystem: int = 0
    total_postgres: int = 0
    consistent: int = 0
    missing_in_postgres: int = 0
    missing_in_filesystem: int = 0
    field_mismatches: int = 0
    details: list[ComparisonResult] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "total_filesystem": self.total_filesystem,
            "total_postgres": self.total_postgres,
            "consistent": self.consistent,
            "missing_in_postgres": self.missing_in_postgres,
            "missing_in_filesystem": self.missing_in_filesystem,
            "field_mismatches": self.field_mismatches,
            "consistency_pct": round(
                (self.consistent / max(self.total_filesystem, 1)) * 100, 2
            ),
            "duration_seconds": round(self.duration_seconds, 2),
        }


# ===================================================================
# Filesystem Reader
# ===================================================================


class FilesystemReader:
    """Read entities from the filesystem storage directory."""

    def __init__(self, storage_root: str | Path) -> None:
        self.storage_root = Path(storage_root)

    def list_run_ids(self) -> list[UUID]:
        """List all run IDs by scanning metadata directory."""
        metadata_dir = self.storage_root / "runs" / "metadata"
        if not metadata_dir.exists():
            logger.warning("Metadata directory not found: %s", metadata_dir)
            return []
        run_ids = []
        for f in sorted(metadata_dir.glob("*.json")):
            try:
                run_ids.append(UUID(f.stem))
            except ValueError:
                logger.warning("Invalid UUID filename: %s", f.name)
        return run_ids

    def get_run(self, run_id: UUID) -> dict | None:
        """Load a single run's metadata from filesystem."""
        path = self.storage_root / "runs" / "metadata" / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            data["_source"] = "filesystem"
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to read %s: %s", path, e)
            return None

    def get_run_count(self) -> int:
        """Count total run metadata files."""
        metadata_dir = self.storage_root / "runs" / "metadata"
        if not metadata_dir.exists():
            return 0
        return sum(1 for f in metadata_dir.glob("*.json") if f.suffix == ".json")


# ===================================================================
# PostgreSQL Reader
# ===================================================================


class PostgresReader:
    """Read entities from PostgreSQL via raw SQL."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            self._engine = create_engine(self.database_url.replace("+asyncpg", ""))
        return self._engine

    def list_run_ids(self) -> list[UUID]:
        """List all run IDs from the runs table."""
        query = "SELECT run_id FROM runs ORDER BY created_at"
        with self._get_engine().connect() as conn:
            rows = conn.execute(text(query)).fetchall()
        return [UUID(str(row[0])) for row in rows]

    def get_run(self, run_id: UUID) -> dict | None:
        """Fetch a single run from PostgreSQL."""
        query = """
            SELECT run_id, status, current_stage, progress_percent,
                   message, error, workspace_path, created_at, updated_at,
                   trigger_type, config::text as config_json,
                   node_execution::text as node_execution_json
            FROM runs WHERE run_id = :run_id
        """
        with self._get_engine().connect() as conn:
            row = conn.execute(text(query), {"run_id": str(run_id)}).fetchone()
        if row is None:
            return None
        return {
            "_source": "postgres",
            "run_id": str(row[0]),
            "status": row[1],
            "current_stage": row[2],
            "progress_percent": row[3],
            "message": row[4],
            "error": row[5],
            "workspace_path": row[6],
            "created_at": str(row[7]) if row[7] else None,
            "updated_at": str(row[8]) if row[8] else None,
            "trigger_type": row[9],
        }

    def get_run_count(self) -> int:
        """Count total runs in PostgreSQL."""
        with self._get_engine().connect() as conn:
            result = conn.execute(text("SELECT count(*) FROM runs"))
            return result.scalar() or 0

    def get_migration_version(self) -> str | None:
        """Return the current Alembic migration version."""
        try:
            with self._get_engine().connect() as conn:
                result = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                )
                row = result.fetchone()
                return row[0] if row else None
        except Exception:
            return None


# ===================================================================
# Comparator
# ===================================================================

COMPARISON_FIELDS_RUN = [
    "status",
    "current_stage",
    "progress_percent",
    "message",
    "error",
    "workspace_path",
]


def compare_run(fs_data: dict | None, pg_data: dict | None) -> ComparisonResult:
    """Compare a single run across filesystem and PostgreSQL."""
    entity_id = "unknown"
    if fs_data:
        entity_id = str(fs_data.get("run_id", fs_data.get("runId", "unknown")))
    elif pg_data:
        entity_id = str(pg_data.get("run_id", "unknown"))

    result = ComparisonResult(
        entity_type="run",
        entity_id=entity_id,
        in_filesystem=fs_data is not None,
        in_postgres=pg_data is not None,
        fs_data=fs_data,
        pg_data=pg_data,
    )

    if fs_data and pg_data:
        for field in COMPARISON_FIELDS_RUN:
            fs_val = fs_data.get(field)
            pg_val = pg_data.get(field)
            # Normalize for comparison
            if str(fs_val) != str(pg_val):
                result.field_mismatches.append({
                    "field": field,
                    "filesystem": str(fs_val),
                    "postgres": str(pg_val),
                })

    return result


# ===================================================================
# Repair
# ===================================================================


def repair_run(fs_data: dict) -> dict:
    """Prepare a run entity for writing to PostgreSQL.

    Only fields that differ are included in the repair payload.
    This is a no-op in dry-run mode.
    """
    return {
        "run_id": fs_data.get("run_id") or fs_data.get("runId"),
        "status": fs_data.get("status"),
        "current_stage": fs_data.get("currentStage") or fs_data.get("current_stage"),
        "progress_percent": fs_data.get("progressPercent",
                                         fs_data.get("progress_percent", 0)),
        "message": fs_data.get("message"),
        "error": fs_data.get("error"),
        "workspace_path": fs_data.get("workspacePath") or fs_data.get("workspace_path"),
    }


# ===================================================================
# Reconciliation
# ===================================================================


async def reconcile_runs(
    fs_reader: FilesystemReader,
    pg_reader: PostgresReader,
    specific_run_id: UUID | None = None,
    repair: bool = False,
    dry_run: bool = True,
) -> ReconciliationReport:
    """Reconcile Run entities between filesystem and PostgreSQL."""
    start = time.monotonic()
    report = ReconciliationReport(entity_type="run")

    # Collect IDs
    fs_ids = fs_reader.list_run_ids()
    pg_ids = pg_reader.list_run_ids()

    if specific_run_id:
        fs_ids = [sid for sid in fs_ids if sid == specific_run_id] or [specific_run_id]
        pg_ids = [pid for pid in pg_ids if pid == specific_run_id] or [specific_run_id]

    report.total_filesystem = len(fs_ids)
    report.total_postgres = len(pg_ids)

    all_ids = sorted(set(fs_ids) | set(pg_ids))
    logger.info("Reconciling %s run(s)...", len(all_ids))

    for run_id in all_ids:
        fs_data = fs_reader.get_run(run_id)
        pg_data = pg_reader.get_run(run_id)

        result = compare_run(fs_data, pg_data)
        report.details.append(result)

        if result.is_consistent:
            report.consistent += 1
        else:
            if not result.in_postgres:
                report.missing_in_postgres += 1
            if not result.in_filesystem:
                report.missing_in_filesystem += 1
            if result.field_mismatches:
                report.field_mismatches += len(result.field_mismatches)

            _log_mismatch(result)

            # Repair if enabled
            if repair and not dry_run and result.fs_data:
                _repair_run_in_pg(pg_reader, run_id, result)

    report.duration_seconds = time.monotonic() - start
    return report


def _log_mismatch(result: ComparisonResult) -> None:
    """Log a single mismatch detail."""
    if not result.in_filesystem:
        logger.warning("  [MISSING_FS] run_id=%s (in PG but not FS)", result.entity_id)
    elif not result.in_postgres:
        logger.warning("  [MISSING_PG] run_id=%s (in FS but not PG)", result.entity_id)
    for m in result.field_mismatches:
        logger.warning(
            "  [MISMATCH] run_id=%s field=%s fs=%s pg=%s",
            result.entity_id, m["field"], m["filesystem"], m["postgres"],
        )


def _repair_run_in_pg(
    pg_reader: PostgresReader, run_id: UUID, result: ComparisonResult
) -> None:
    """Write missing run data to PostgreSQL."""
    payload = repair_run(result.fs_data)
    query = """
        INSERT INTO runs (run_id, status, current_stage, progress_percent,
                          message, error, workspace_path)
        VALUES (:run_id, :status, :current_stage, :progress_percent,
                :message, :error, :workspace_path)
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            current_stage = EXCLUDED.current_stage,
            progress_percent = EXCLUDED.progress_percent,
            message = EXCLUDED.message,
            error = EXCLUDED.error,
            workspace_path = EXCLUDED.workspace_path
    """
    try:
        with pg_reader._get_engine().connect() as conn:
            conn.execute(text(query), payload)
            conn.commit()
        logger.info("  [REPAIRED] run_id=%s written to PostgreSQL", run_id)
    except Exception as e:
        logger.error("  [REPAIR_FAILED] run_id=%s error=%s", run_id, e)


# ===================================================================
# Display
# ===================================================================


def print_report(report: ReconciliationReport, json_output: bool = False) -> None:
    """Print the reconciliation report."""
    if json_output:
        print(json.dumps(report.summary, indent=2, default=str))
        if report.details:
            print("\nDetails:")
            for d in report.details:
                print(json.dumps({
                    "entity_id": d.entity_id,
                    "consistent": d.is_consistent,
                    "mismatches": d.field_mismatches,
                }, indent=2))
        return

    print()
    print("=" * 60)
    print(f"  Reconciliation Report: {report.entity_type}")
    print("=" * 60)
    print(f"  Filesystem:  {report.total_filesystem}")
    print(f"  PostgreSQL:  {report.total_postgres}")
    print(f"  Consistent:  {report.consistent}")
    print(f"  Missing in PG: {report.missing_in_postgres}")
    print(f"  Missing in FS: {report.missing_in_filesystem}")
    print(f"  Field mismatches: {report.field_mismatches}")
    print(f"  Consistency: {report.summary['consistency_pct']}%")
    print(f"  Duration:    {report.duration_seconds:.2f}s")
    print("=" * 60)

    if report.details:
        mismatches = [d for d in report.details if not d.is_consistent]
        if mismatches:
            print(f"\n  {len(mismatches)} entity(ies) with issues:")
            for d in mismatches:
                if not d.in_postgres:
                    print(f"    MISSING IN PG: {d.entity_id}")
                elif not d.in_filesystem:
                    print(f"    MISSING IN FS: {d.entity_id}")
                else:
                    print(f"    FIELD MISMATCH: {d.entity_id}")
                    for m in d.field_mismatches:
                        print(f"      {m['field']}: fs={m['filesystem']} pg={m['postgres']}")


async def check_environment(
    fs_reader: FilesystemReader, pg_reader: PostgresReader
) -> dict:
    """Check and report environment health."""
    env = {
        "filesystem_root": str(fs_reader.storage_root),
        "database_url": pg_reader.database_url[:50] + "...",
        "migration_version": pg_reader.get_migration_version(),
        "filesystem_run_count": fs_reader.get_run_count(),
        "postgres_run_count": pg_reader.get_run_count(),
    }
    return env


# ===================================================================
# CLI
# ===================================================================


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persistence Reconciliation Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["compare", "repair", "env"],
        default="compare",
        help="Operation mode (default: compare)",
    )
    parser.add_argument(
        "--entity",
        choices=["run", "all"],
        default="run",
        help="Entity type to reconcile (default: run)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Specific run UUID to reconcile (optional)",
    )
    parser.add_argument(
        "--storage-root",
        type=str,
        default=None,
        help="Filesystem storage root (default: from settings)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="PostgreSQL connection URL (default: from settings)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be done without modifying data (default: on)",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        default=False,
        help="Actually perform repairs (requires --dry-run to be disabled)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output in JSON format",
    )
    return parser.parse_args(argv)


async def main_async(argv: list[str] | None = None) -> int:
    """Async entry point."""
    args = parse_args(argv)

    # Load settings for default values
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from app.config import get_settings

        settings = get_settings()
        storage_root = args.storage_root or str(settings.storage.storage_base_path)
        db_url = args.database_url or settings.database.url
    except Exception as e:
        logger.error("Failed to load settings: %s", e)
        logger.error("Provide --storage-root and --database-url explicitly.")
        return 1

    # Convert asyncpg → psycopg2 for sync SQLAlchemy
    pg_url = db_url.replace("+asyncpg", "")

    fs_reader = FilesystemReader(storage_root)
    pg_reader = PostgresReader(pg_url)

    if args.mode == "env":
        env = await check_environment(fs_reader, pg_reader)
        print(json.dumps(env, indent=2, default=str))
        return 0

    # Resolve specific run ID
    specific_run_id = None
    if args.run_id:
        try:
            specific_run_id = UUID(args.run_id)
        except ValueError:
            logger.error("Invalid run-id: %s", args.run_id)
            return 1

    # Determine repair mode
    do_repair = args.mode == "repair"
    do_dry_run = args.dry_run if do_repair else True

    if do_repair and not do_dry_run:
        logger.warning("*** REPAIR MODE ENABLED — data will be written to PostgreSQL ***")
        confirm = input("Type 'REPAIR' to confirm: ")
        if confirm != "REPAIR":
            logger.info("Repair cancelled.")
            return 0

    report = await reconcile_runs(
        fs_reader=fs_reader,
        pg_reader=pg_reader,
        specific_run_id=specific_run_id,
        repair=do_repair,
        dry_run=do_dry_run,
    )

    print_report(report, json_output=args.json)

    # Return non-zero if any inconsistencies found
    if report.consistent != max(report.total_filesystem, report.total_postgres):
        return 2
    return 0


def main() -> None:
    """Sync entry point that runs the async main."""
    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

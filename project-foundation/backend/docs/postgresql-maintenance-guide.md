# PostgreSQL Long-Term Maintenance Guide

## Overview

This guide covers ongoing operational maintenance for the PostgreSQL
persistence layer after the initial rollout.

---

## 1. Vacuum Strategy

PostgreSQL's `VACUUM` reclaims storage and prevents transaction ID
wraparound.  Autovacuum handles most cases, but high-write tables
may need attention.

### Autovacuum Configuration

```ini
# postgresql.conf — already configured in baseline
autovacuum = on
autovacuum_vacuum_scale_factor = 0.01
autovacuum_analyze_scale_factor = 0.005
autovacuum_vacuum_threshold = 1000
```

### Manual Vacuum Schedule

| Table | Frequency | Command |
|-------|-----------|---------|
| `audit_log` | Weekly off-peak | `VACUUM ANALYZE audit_log;` |
| `test_results` | Weekly off-peak | `VACUUM ANALYZE test_results;` |
| `test_scenarios` | Weekly off-peak | `VACUUM ANALYZE test_scenarios;` |
| All others | Monthly | `VACUUM ANALYZE;` |

### Monitoring

```sql
-- Check dead tuple ratio — investigate if > 20%
SELECT relname,
       n_dead_tup,
       n_live_tup,
       round(n_dead_tup * 100.0 / nullif(n_live_tup + n_dead_tup, 0), 2) AS dead_pct
FROM pg_stat_user_tables
ORDER BY dead_pct DESC
LIMIT 10;
```

### Table-Level Tuning

For high-write tables, reduce autovacuum scale factor:

```sql
ALTER TABLE audit_log SET (autovacuum_vacuum_scale_factor = 0.005);
ALTER TABLE test_results SET (autovacuum_vacuum_scale_factor = 0.005);
```

---

## 2. Analyze Strategy

`ANALYZE` updates query planner statistics.  Stale statistics cause
poor query plans.

### Scheduled Analyzes

| Frequency | Scope | Command |
|-----------|-------|---------|
| Daily | High-write tables | `ANALYZE audit_log; ANALYZE test_results;` |
| Weekly | All tables | `ANALYZE;` |

### Monitoring

```sql
-- Check when tables were last analyzed
SELECT relname, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY last_analyze DESC NULLS LAST;
```

---

## 3. Index Maintenance

Indexes degrade over time due to page splits and bloat.

### Reindex Schedule

| Frequency | Scope | Command |
|-----------|-------|---------|
| Monthly | All indexes | `REINDEX DATABASE testing_platform;` |
| Weekly | High-write tables | `REINDEX TABLE audit_log;` |

### Unused Index Detection

```sql
-- Find indexes that have never been used
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY tablename;
```

Indexes with zero scans after 30 days should be reviewed for removal.

### Missing Index Detection

```sql
-- Find sequential scans on large tables (potential missing indexes)
SELECT relname, seq_scan, seq_tup_read, idx_scan
FROM pg_stat_user_tables
WHERE seq_scan > 1000 AND seq_tup_read > 10000
ORDER BY seq_tup_read DESC;
```

---

## 4. Backup Verification

### Backup Schedule

| Type | Frequency | Retention | Tool |
|------|-----------|-----------|------|
| WAL archiving | Continuous (60s) | 7 days | `archive_command` |
| Full backup | Daily | 30 days | `pg_dump --format=custom` |
| Weekly backup | Weekly | 90 days | `pg_dump --format=custom` |
| Monthly backup | Monthly | 365 days | `pg_dump --format=custom` |

### Restore Test Procedure

Monthly automated restore test:

```bash
#!/bin/bash
# 1. Create test database
createdb testing_platform_restore_test

# 2. Restore latest backup
pg_restore --dbname=testing_platform_restore_test \
           --format=custom \
           --clean \
           /backups/latest.dump

# 3. Run reconciliation
python scripts/reconcile_persistence.py --mode env

# 4. Run validation tests
pytest tests/persistence/test_orm_models.py -x

# 5. Clean up
dropdb testing_platform_restore_test
```

### Backup Verification Checklist

- [ ] Backup file exists and is non-empty
- [ ] Checksum matches expected value
- [ ] Restore completes without errors
- [ ] All 14 tables present after restore
- [ ] Row counts match between production and restored copy
- [ ] Application can start against restored database

---

## 5. Migration Review Process

### Schema Change Procedure

1. **Design review**: New ORM models reviewed by team
2. **Generate migration**: `alembic revision --autogenerate -m "description"`
3. **Review migration SQL**: Check `upgrade()` and `downgrade()` manually
4. **Test downgrade**: `alembic downgrade -1` then `alembic upgrade head`
5. **Code review**: PR with migration + model changes reviewed
6. **Stage deployment**: Apply migration to staging first
7. **Production deployment**: Apply during maintenance window

### Migration Naming Convention

```
{alembic_revision_id}_{short_description}.py
```

Examples:
- `a1b2c3d4_add_user_preferences_table.py`
- `e5f6g7h8_add_index_on_execution_status.py`

### Migration DOs and DON'Ts

| DO | DON'T |
|----|-------|
| Add columns as NULLABLE | Add NOT NULL columns to tables with data |
| Add indexes CONCURRENTLY | Run migrations in transactions that lock for hours |
| Test downgrade before deploy | Deploy untested downgrade |
| Add CHECK constraints separately | Mix data migration with schema changes |
| Use batch backfills for large tables | UPDATE all rows in a single transaction |

---

## 6. Data Retention

### Archival Policy

| Table | Retention | Destination | Method |
|-------|-----------|-------------|--------|
| `audit_log` | 365 days | Cold storage (Parquet) | Export + delete |
| `test_results` | 365 days | Cold storage (Parquet) | Export + delete |
| `runs` | 365 days | Cold storage (Parquet) | Export + delete |
| `artifacts` (metadata) | 365 days | Cold storage (Parquet) | Export + delete |
| All others | Indefinite | — | Keep |

### Archival Procedure

```sql
-- Export old audit_log entries
COPY (
    SELECT * FROM audit_log
    WHERE created_at < now() - interval '365 days'
) TO '/tmp/audit_log_archive.csv' CSV HEADER;

-- Delete exported entries
DELETE FROM audit_log
WHERE created_at < now() - interval '365 days';
```

### Table Size Monitoring

```sql
SELECT relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       pg_size_pretty(pg_relation_size(relid)) AS table,
       pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS indexes
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

---

## 7. Operational Health Dashboard

The following queries provide a quick health snapshot:

```sql
-- 1. Connection count
SELECT count(*) AS active_connections FROM pg_stat_activity;

-- 2. Database size
SELECT pg_size_pretty(pg_database_size('testing_platform'));

-- 3. Long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC
LIMIT 10;

-- 4. Lock contention
SELECT relation::regclass, mode, granted
FROM pg_locks
WHERE NOT granted
ORDER BY relation;

-- 5. Cache hit ratio
SELECT sum(heap_blks_hit) / nullif(sum(heap_blks_hit + heap_blks_read), 0) * 100 AS hit_ratio
FROM pg_statio_user_tables;

-- 6. Transaction rate
SELECT xact_commit + xact_rollback AS tps
FROM pg_stat_database
WHERE datname = 'testing_platform';
```

---

## 8. Recommended Monitoring Alerts

| Alert | Metric | Threshold | Severity |
|-------|--------|-----------|----------|
| Connection pool high | `pool_utilization` | > 80% for 5 min | P2 |
| PG down | `connectivity.status` | unhealthy | P1 |
| Dual-write failures | `dual_write_failures` | > 10 in 5 min | P2 |
| Write latency high | `pg_write_latency` | p99 > 1s | P3 |
| Table bloat | `n_dead_tup` | > 20% live rows | P3 |
| Backup failed | Backup exit code | non-zero | P1 |
| Disk space | Disk usage | > 80% | P2 |
| Replication lag | (if replica) | > 10s | P2 |

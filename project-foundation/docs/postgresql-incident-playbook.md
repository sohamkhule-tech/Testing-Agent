# PostgreSQL Persistence — Incident Response Playbook

## Overview

This playbook defines procedures for 7 incident scenarios involving
the PostgreSQL persistence layer.  Each scenario has:

- **Severity** (P0–P3)
- **Symptoms** (how to detect)
- **Impact** (what breaks)
- **Immediate actions** (what to do now)
- **Resolution steps** (how to fix)
- **Post-incident** (prevent recurrence)

---

## Incident 1: PostgreSQL Outage

**Severity**: P1 (if dual-write active) / P3 (if FS-only)

**Symptoms**:
- `GET /health/db` returns `connectivity.status: "unhealthy"`
- `pg_write_failed` log entries
- Connection pool exhaustion alerts
- Dual-write failure counter increases

**Impact**:
- Dual-write: FS continues, PG writes fail silently
- FS-only: no impact

**Immediate Actions**:
1. Verify FS is still operational: `GET /health/` returns `"storage": "healthy"`
2. If dual-write active, no urgent action needed — FS is authoritative
3. If PG reads enabled, disable immediately:
   ```bash
   PERSISTENCE_DATABASE_READ_ENABLED=false
   ```

**Resolution**:
1. Check PostgreSQL server logs: `docker logs postgres-container`
2. Verify network: `pg_isready -h <host> -p 5432`
3. Check disk space: `df -h` on PostgreSQL host
4. Restart PostgreSQL: `docker restart postgres-container`
5. Verify reconnection: `python -c "from app.infrastructure.database import check_database_health; import asyncio; print(asyncio.run(check_database_health()))"`

**Post-incident**:
- Add PG connection alert if not already configured
- Review connection pool settings
- Consider connection pooling (pgbouncer)

---

## Incident 2: Filesystem Outage

**Severity**: P0

**Symptoms**:
- `GET /health/` returns `"storage": "unhealthy"`
- FS write errors in logs
- Application errors on write operations

**Impact**:
- ALL writes fail — FS is authoritative
- PG writes never attempted (FS must succeed first)

**Immediate Actions**:
1. **STOP the application**: `docker-compose down`
2. **DO NOT enable PG as primary** — not yet validated for FS replacement
3. Assess filesystem damage

**Resolution**:
1. Check disk: `df -h` for storage volume
2. Check filesystem permissions on `./storage/`
3. Restore from backup if needed
4. Verify FS integrity: `python scripts/reconcile_persistence.py --mode env`
5. Restart application

**Post-incident**:
- Add disk space monitoring
- Ensure storage directory is on redundant volume
- Consider moving storage to managed volume (EBS, etc.)

---

## Incident 3: Dual-Write Failure

**Severity**: P2

**Symptoms**:
- `persistence_metrics.dual_write_failures` counter increasing
- `pg_write_failed` in logs
- Retry count increasing

**Impact**:
- FS writes succeed (authoritative)
- PG writes fail silently
- PG may be missing some records

**Immediate Actions**:
1. Check `/health/db` for rollout status and metrics
2. Verify PG is reachable: `pg_isready`
3. If failures persist > 5 minutes, disable dual-write:
   ```bash
   PERSISTENCE_DUAL_WRITE_ENABLED=false
   ```

**Resolution**:
1. Identify failure pattern from logs:
   ```bash
   grep "pg_write_failed" storage/logs/*.log | tail -50
   ```
2. Common causes:
   - Transient connection error → retry handles this
   - Constraint violation → data inconsistency
   - Timeout → increase `DATABASE_CONNECT_TIMEOUT`
3. Run reconciliation to identify missed records:
   ```bash
   python scripts/reconcile_persistence.py --mode compare --entity run
   ```
4. Re-enable dual-write after resolution

**Post-incident**:
- Add dual-write failure rate alert (> 1%)
- Review timeout settings
- Consider increasing pool size

---

## Incident 4: Migration Rollback

**Severity**: P1

**Symptoms**:
- Business decision to abort PostgreSQL rollout
- Unacceptable performance or reliability

**Impact**:
- Return to FS-only operations
- PG data becomes stale (no writes)

**Rollback Procedure**:
```bash
# Step 1: Disable all PG flags
PERSISTENCE_POSTGRES_ENABLED=false
PERSISTENCE_DUAL_WRITE_ENABLED=false
PERSISTENCE_DATABASE_READ_ENABLED=false

# Step 2: Restart application
docker-compose restart api

# Step 3: Verify FS-only mode
curl http://localhost:8000/health/ | jq .components

# Step 4: Optional — downgrade schema
# alembic downgrade base

# Step 5: Optional — drop database
# dropdb testing_platform
```

**Rollback time**: < 1 minute (config + restart).
**Data loss**: ZERO — FS was always written first.

---

## Incident 5: Connection Pool Exhaustion

**Severity**: P2

**Symptoms**:
- `persistence_metrics.pool_utilization` approaching 100%
- Connection timeout errors in logs
- Slow query responses

**Impact**:
- New connections wait or fail
- Existing connections continue working

**Immediate Actions**:
1. Check active connections:
   ```sql
   SELECT count(*) FROM pg_stat_activity WHERE datname = 'testing_platform';
   ```
2. Check pool settings: `GET /health/db` → `rollout.features`
3. Kill idle connections if needed:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity
   WHERE state = 'idle' AND state_change < now() - interval '10 minutes';
   ```

**Resolution**:
1. Increase pool size:
   ```bash
   DATABASE_POOL_SIZE=20
   DATABASE_MAX_OVERFLOW=40
   ```
2. Add pgbouncer for connection pooling
3. Review application connection usage

**Post-incident**:
- Set pool utilization alert at 80%
- Add pgbouncer to deployment
- Review connection leak patterns

---

## Incident 6: Unexpected Latency

**Severity**: P3

**Symptoms**:
- `GET /health/db` → `metrics.pg_write_latency` > 1s
- Slow API responses
- Increased p99 latency

**Impact**:
- Application response times degrade
- Users experience slowness
- Retries consume resources

**Immediate Actions**:
1. Check PG server load:
   ```sql
   SELECT count(*) FROM pg_stat_activity;
   SELECT count(*) FROM pg_locks WHERE NOT granted;
   ```
2. Check slow queries:
   ```sql
   SELECT query, calls, total_time / calls AS avg_time
   FROM pg_stat_statements
   ORDER BY avg_time DESC LIMIT 10;
   ```
3. Check for blocking queries:
   ```sql
   SELECT pid, wait_event, query FROM pg_stat_activity
   WHERE wait_event IS NOT NULL;
   ```

**Resolution**:
1. Kill long-running queries if needed
2. Check indexes: `SELECT * FROM pg_stat_user_indexes WHERE idx_scan = 0;`
3. Run `ANALYZE` to update statistics:
   ```sql
   ANALYZE;
   ```
4. Check if VACUUM is needed:
   ```sql
   SELECT relname, n_dead_tup FROM pg_stat_user_tables
   ORDER BY n_dead_tup DESC LIMIT 10;
   ```

**Post-incident**:
- Review query plans for missing indexes
- Add latency alert (P99 > 1s for 5 minutes)
- Schedule regular ANALYZE runs

---

## Incident 7: Data Mismatch

**Severity**: P0 (if detected in production) / P2 (if detected via reconciliation)

**Symptoms**:
- Reconciliation report shows field mismatches
- `scripts/reconcile_persistence.py` returns exit code 2
- Missing records in either backend

**Impact**:
- Inconsistent state between backends
- If PG reads are enabled, stale data may be served
- Dual-write: FS is authoritative, so PG mismatch is acceptable

**Immediate Actions**:
1. Run full reconciliation:
   ```bash
   python scripts/reconcile_persistence.py --mode compare --entity run --json
   ```
2. If PG reads are enabled and mismatches found, disable PG reads:
   ```bash
   PERSISTENCE_DATABASE_READ_ENABLED=false
   ```
3. Assess scope of mismatch

**Resolution**:
1. Run dry-run repair to see what would change:
   ```bash
   python scripts/reconcile_persistence.py --mode repair --entity run --dry-run
   ```
2. If repair looks correct, run actual repair:
   ```bash
   python scripts/reconcile_persistence.py --mode repair --entity run --repair
   ```
3. Run reconciliation again to verify:
   ```bash
   python scripts/reconcile_persistence.py --mode compare --entity run
   ```
4. Re-enable PG reads if previously disabled

**Post-incident**:
- Add scheduled reconciliation to cron (daily during rollout)
- Identify root cause of mismatch:
  - Dual-write failure → fix PG connection
  - Race condition → review transaction boundaries
  - Bug → file issue and fix
- Increase monitoring on mismatch counter

---

## Escalation Matrix

| Severity | Response Time | Escalation |
|----------|--------------|------------|
| P0 | Immediate (< 5 min) | Engineering Lead + SRE |
| P1 | < 15 min | Engineering Lead |
| P2 | < 1 hour | On-call engineer |
| P3 | < 24 hours | Team lead |

---

## Communication Template

```
INCIDENT: {severity} — {title}
SERVICE: Persistence Layer
TIME: {timestamp}
SYMPTOMS: {key symptoms}
IMPACT: {what is affected}
CURRENT STATUS: {investigating / mitigated / resolved}
ACTION: {what is being done}
NEXT UPDATE: {expected time}
```

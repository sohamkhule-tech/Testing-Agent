"""
Pre-migration metadata audit.

Verifies all tables, columns, constraints, FKs, and indexes
before generating the Alembic initial migration.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Trigger model registration
from app.models import orm  # noqa: F401
from app.infrastructure.database import metadata
from sqlalchemy import inspect as sa_inspect

# Re-import models for inspection
from app.models.orm.core import User, Project, Run
from app.models.orm.discovery import CrawlPackage, Inventory
from app.models.orm.design import TestPlan, TestScenario, HumanReview
from app.models.orm.generation import IRDocument, GeneratedProject
from app.models.orm.execution import Execution, TestResult
from app.models.orm.system import Artifact, AuditLog

ALL_MODELS = {
    "User": User,
    "Project": Project,
    "Run": Run,
    "CrawlPackage": CrawlPackage,
    "Inventory": Inventory,
    "TestPlan": TestPlan,
    "TestScenario": TestScenario,
    "HumanReview": HumanReview,
    "IRDocument": IRDocument,
    "GeneratedProject": GeneratedProject,
    "Execution": Execution,
    "TestResult": TestResult,
    "Artifact": Artifact,
    "AuditLog": AuditLog,
}

assert len(ALL_MODELS) == 14

print("=" * 72)
print("  PRE-MIGRATION METADATA AUDIT")
print("=" * 72)
print()

# --- 1. Table count ---
tables = metadata.tables
print(f"Total tables in metadata: {len(tables)}")
print()

# --- 2. Per-table detail ---
for name in sorted(tables):
    table = tables[name]
    print(f"[{name}]")

    # Columns
    cols = table.columns
    for col in cols:
        coltype = str(col.type)
        nullable = "NULL" if col.nullable else "NOT NULL"
        pk = "PK" if col.primary_key else ""
        fk = ""
        uq = " UQ" if col.unique else ""
        default = ""
        if col.server_default is not None:
            default = f" default={col.server_default.arg}"
        for fkc in col.foreign_keys:
            fk = f" FK->{fkc.column.table.name}.{fkc.column.name}"
        print(f"  {col.name:30s} {coltype:30s} {nullable:8s} {pk:2s}{uq:3s}{fk}{default}")

    # Indexes (from table metadata)
    for idx in table.indexes:
        cols_str = ", ".join(c.name for c in idx.columns)
        unique_str = " UNIQUE" if idx.unique else ""
        if idx.name:
            print(f"  INDEX {idx.name:30s} ({cols_str}){unique_str}")

    # Unique constraints not covered by indexes
    for con in table.constraints:
        if "UniqueConstraint" in type(con).__name__:
            cols_str = ", ".join(c.name for c in con.columns)
            if con.name:
                print(f"  UNIQUE {con.name:30s} ({cols_str})")

    print()

# --- 3. Model-level relationship audit ---
print("--- RELATIONSHIPS ---")
for model_name, model_cls in sorted(ALL_MODELS.items()):
    inst = sa_inspect(model_cls)
    rels = list(inst.relationships)
    if rels:
        print(f"{model_name}:")
        for r in rels:
            direction = "->" if r.direction.name == "MANYTOONE" else "1:N"
            if r.uselist is False and r.direction.name != "MANYTOONE":
                direction = "1:1"
            cascade = r.cascade
            print(f"  {r.key:30s} {direction} {r.mapper.class_.__name__:20s} cascade={cascade}")
    print()

# --- 4. Dependency order (topological sort based on FKs) ---
print("--- TABLE CREATION ORDER (topological) ---")
edges = []
for name, table in tables.items():
    for col in table.columns:
        for fk in col.foreign_keys:
            edges.append((fk.column.table.name, name))

def topological_sort(names, edges):
    from collections import defaultdict, deque
    graph = defaultdict(list)
    in_deg = defaultdict(int)
    for n in names:
        in_deg[n] = 0
    for src, dst in edges:
        if src != dst:
            graph[src].append(dst)
            in_deg[dst] += 1
    q = deque([n for n in names if in_deg[n] == 0])
    result = []
    while q:
        node = q.popleft()
        result.append(node)
        for nb in graph[node]:
            in_deg[nb] -= 1
            if in_deg[nb] == 0:
                q.append(nb)
    remaining = [n for n in names if n not in result]
    return result, remaining

order, remaining = topological_sort(list(tables.keys()), edges)
for i, name in enumerate(order, 1):
    print(f"  {i:2d}. {name}")
if remaining:
    print(f"  CIRCULAR/REMAINING: {remaining}")

print()
print("=" * 72)
print("  AUDIT COMPLETE")
print("=" * 72)

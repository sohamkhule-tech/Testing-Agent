"""
ORM model validation: table registration, relationships, constraints.
"""

import pytest
from sqlalchemy import inspect as sa_inspect
from app.models import orm  # noqa: F401 — register models
from app.infrastructure.database import metadata as db_metadata

EXPECTED_TABLES = {
    "users", "projects", "runs",
    "crawl_packages", "inventories",
    "test_plans", "test_scenarios", "human_reviews",
    "ir_documents", "generated_projects",
    "executions", "test_results",
    "artifacts", "audit_log",
}


class TestTableRegistration:
    def test_all_14_tables_registered(self):
        actual = set(db_metadata.tables.keys())
        missing = EXPECTED_TABLES - actual
        extra = actual - EXPECTED_TABLES
        assert not missing, f"Missing tables: {missing}"
        assert not extra, f"Unexpected tables: {extra}"
        assert len(actual) >= 14

    def test_every_table_has_primary_key(self):
        for name in EXPECTED_TABLES:
            table = db_metadata.tables[name]
            assert table.primary_key, f"{name} has no primary key"

    def test_users_has_soft_delete(self):
        users = db_metadata.tables["users"]
        assert "deleted_at" in [c.name for c in users.columns]

    def test_audit_log_bigserial_pk(self):
        al = db_metadata.tables["audit_log"]
        pk = list(al.primary_key.columns)
        assert pk[0].name == "id"
        assert "BigInteger" in str(type(pk[0].type))

    def test_runs_run_id_unique(self):
        runs = db_metadata.tables["runs"]
        assert runs.columns["run_id"].unique


class TestColumns:
    @pytest.mark.parametrize("table_name,expected_cols", [
        ("users", {"id", "email", "role", "status", "tenant_id", "created_at", "deleted_at"}),
        ("audit_log", {"id", "action", "entity_type", "entity_id", "created_at"}),
        ("runs", {"id", "run_id", "tenant_id", "status", "progress_percent", "workspace_path"}),
        ("crawl_packages", {"id", "run_id", "status", "pages_visited", "file_path"}),
        ("inventories", {"id", "run_id", "page_count", "pages_data", "elements_data"}),
        ("test_plans", {"id", "run_id", "version", "is_latest", "status"}),
        ("test_scenarios", {"id", "test_plan_id", "scenario_id", "title", "description"}),
        ("human_reviews", {"id", "run_id", "test_plan_id", "status", "reviewer_name"}),
        ("ir_documents", {"id", "test_plan_id", "run_id", "is_latest", "ir_path"}),
        ("generated_projects", {"id", "run_id", "status", "project_path", "files_data"}),
        ("executions", {"id", "run_id", "status", "browser", "started_at"}),
        ("test_results", {"id", "execution_id", "title", "status", "failure_data"}),
        ("artifacts", {"id", "run_id", "artifact_type", "file_path", "storage_backend"}),
        ("projects", {"id", "name", "base_url", "environment", "default_browser"}),
    ])
    def test_required_columns(self, table_name, expected_cols):
        table = db_metadata.tables[table_name]
        actual = {c.name for c in table.columns}
        missing = expected_cols - actual
        assert not missing, f"{table_name} missing columns: {missing}"

    @pytest.mark.parametrize("table_name,jsonb_col", [
        ("inventories", "pages_data"),
        ("inventories", "elements_data"),
        ("inventories", "navigation_data"),
        ("generated_projects", "files_data"),
        ("human_reviews", "decision_data"),
        ("test_results", "failure_data"),
        ("test_results", "retry_data"),
        ("runs", "config"),
        ("runs", "node_execution"),
        ("executions", "config"),
        ("executions", "metrics_data"),
        ("artifacts", "storage_config"),
        ("audit_log", "details"),
    ])
    def test_jsonb_columns(self, table_name, jsonb_col):
        table = db_metadata.tables[table_name]
        col = table.columns.get(jsonb_col)
        assert col is not None, f"{table_name} missing {jsonb_col}"
        assert "JSONB" in str(col.type) or "JSON" in str(col.type), \
            f"{table_name}.{jsonb_col} is not JSONB: {col.type}"


class TestForeignKeys:
    @pytest.mark.parametrize("table_name,expected_fk_count", [
        ("users", 0),
        ("audit_log", 1),
        ("projects", 1),
        ("runs", 2),
        ("crawl_packages", 1),
        ("inventories", 1),
        ("test_plans", 1),
        ("test_scenarios", 1),
        ("human_reviews", 3),
        ("ir_documents", 2),
        ("generated_projects", 2),
        ("executions", 3),
        ("test_results", 1),
        ("artifacts", 3),
    ])
    def test_foreign_key_count(self, table_name, expected_fk_count):
        table = db_metadata.tables[table_name]
        fks = set()
        for col in table.columns:
            for fk in col.foreign_keys:
                fks.add(f"{col.name} -> {fk.column.table.name}.{fk.column.name}")
        assert len(fks) == expected_fk_count, f"{table_name}: expected {expected_fk_count} FKs, got {len(fks)}: {fks}"


class TestNamingConvention:
    def test_fk_names_end_with_fkey(self):
        for name, table in db_metadata.tables.items():
            for fk in table.foreign_key_constraints:
                assert fk.name.endswith("_fkey"), f"{name} FK {fk.name} doesn't end with _fkey"

    def test_pk_names_end_with_pkey(self):
        for name, table in db_metadata.tables.items():
            assert table.primary_key.name.endswith("_pkey"), f"{name} PK doesn't end with _pkey"


class TestModelRelationships:
    def test_run_has_all_child_relationships(self):
        from app.models.orm.core import Run
        inst = sa_inspect(Run)
        rels = {r.key for r in inst.relationships}
        expected = {"crawl_packages", "inventories", "test_plans",
                     "human_reviews", "ir_documents", "generated_projects",
                     "executions", "artifacts", "project", "requester"}
        missing = expected - rels
        assert not missing, f"Run missing relationships: {missing}"

    def test_user_has_relationships(self):
        from app.models.orm.core import User
        inst = sa_inspect(User)
        rels = {r.key for r in inst.relationships}
        assert "projects_created" in rels
        assert "runs_requested" in rels
        assert "reviews_done" in rels

    def test_ir_document_11_generated_project(self):
        from app.models.orm.generation import IRDocument
        inst = sa_inspect(IRDocument)
        rels = {r.key: r for r in inst.relationships}
        assert rels["generated_project"].uselist is False

    @pytest.mark.parametrize("model_path,relation", [
        ("app.models.orm.core.Run", "test_plans"),
        ("app.models.orm.core.Run", "executions"),
        ("app.models.orm.design.TestPlan", "scenarios"),
        ("app.models.orm.design.TestPlan", "reviews"),
        ("app.models.orm.execution.Execution", "test_results"),
    ])
    def test_cascade_delete_orphan(self, model_path, relation):
        import importlib
        mod_path, cls_name = model_path.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        inst = sa_inspect(cls)
        rels = {r.key: r for r in inst.relationships}
        rel = rels[relation]
        assert "delete-orphan" in str(rel.cascade), \
            f"{cls_name}.{relation} missing delete-orphan cascade"


class TestEnumConsistency:
    def test_db_enums_match_app_constants(self):
        from app.models.enums import RunStatus as DbRunStatus
        from app.constants import RunStatus as AppRunStatus
        db_vals = sorted([e.value for e in DbRunStatus])
        app_vals = sorted([e.value for e in AppRunStatus])
        assert db_vals == app_vals, f"Mismatch: DB={db_vals} App={app_vals}"

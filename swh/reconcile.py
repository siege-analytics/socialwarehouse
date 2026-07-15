"""Schema reconciliation for ``swh reconcile`` (#334).

Compares live PostgreSQL schema against Django model definitions and
reports column-level diffs: missing columns, extra columns, type
mismatches, and constraint mismatches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiffKind(Enum):
    MISSING_IN_DB = "missing_in_db"
    EXTRA_IN_DB = "extra_in_db"
    TYPE_MISMATCH = "type_mismatch"
    NULLABLE_MISMATCH = "nullable_mismatch"
    MISSING_TABLE = "missing_table"
    EXTRA_TABLE = "extra_table"


@dataclass
class ColumnDiff:
    table: str
    column: str
    kind: DiffKind
    model_type: Optional[str] = None
    db_type: Optional[str] = None
    detail: str = ""


@dataclass
class TableDiff:
    table: str
    kind: DiffKind
    detail: str = ""


@dataclass
class ReconcileReport:
    table_diffs: list[TableDiff] = field(default_factory=list)
    column_diffs: list[ColumnDiff] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.table_diffs or self.column_diffs)

    @property
    def issue_count(self) -> int:
        return len(self.table_diffs) + len(self.column_diffs)


DJANGO_TO_PG_TYPES = {
    "AutoField": {"integer"},
    "BigAutoField": {"bigint"},
    "SmallAutoField": {"smallint"},
    "BooleanField": {"boolean"},
    "CharField": {"character varying"},
    "TextField": {"text"},
    "IntegerField": {"integer"},
    "BigIntegerField": {"bigint"},
    "SmallIntegerField": {"smallint"},
    "PositiveIntegerField": {"integer"},
    "PositiveBigIntegerField": {"bigint"},
    "PositiveSmallIntegerField": {"smallint"},
    "FloatField": {"double precision"},
    "DecimalField": {"numeric"},
    "DateField": {"date"},
    "DateTimeField": {"timestamp with time zone"},
    "TimeField": {"time without time zone"},
    "UUIDField": {"uuid"},
    "BinaryField": {"bytea"},
    "JSONField": {"jsonb"},
    "SlugField": {"character varying"},
    "URLField": {"character varying"},
    "EmailField": {"character varying"},
    "FilePathField": {"character varying"},
    "IPAddressField": {"character varying", "inet"},
    "GenericIPAddressField": {"character varying", "inet"},
    "ForeignKey": {"integer", "bigint"},
    "OneToOneField": {"integer", "bigint"},
    "MultiPolygonField": {"USER-DEFINED"},
    "PolygonField": {"USER-DEFINED"},
    "PointField": {"USER-DEFINED"},
    "LineStringField": {"USER-DEFINED"},
    "MultiPointField": {"USER-DEFINED"},
    "MultiLineStringField": {"USER-DEFINED"},
    "GeometryField": {"USER-DEFINED"},
    "GeometryCollectionField": {"USER-DEFINED"},
    "RasterField": {"USER-DEFINED"},
}

INTROSPECT_COLUMNS_SQL = """\
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = ANY(%s)
ORDER BY table_name, ordinal_position;
"""

INTROSPECT_TABLES_SQL = """\
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE';
"""


def _get_django_models():
    import django

    if not django.apps.apps.ready:
        django.setup()

    from django.apps import apps

    models = []
    for model in apps.get_models():
        if model._meta.managed is False:
            continue
        models.append(model)
    return models


def _model_columns(model) -> dict[str, dict]:
    columns = {}
    for f in model._meta.get_fields():
        if not hasattr(f, "column"):
            continue
        col_name = f.column
        field_type = type(f).__name__
        nullable = getattr(f, "null", False)
        columns[col_name] = {
            "field_type": field_type,
            "nullable": nullable,
        }
    return columns


def reconcile(dsn: str, *, sw_only: bool = True) -> ReconcileReport:
    import psycopg2

    report = ReconcileReport()
    models = _get_django_models()

    model_tables = {}
    for m in models:
        table = m._meta.db_table
        if sw_only and not table.startswith("sw_"):
            continue
        model_tables[table] = m

    conn = psycopg2.connect(dsn, connect_timeout=10)
    try:
        cur = conn.cursor()

        cur.execute(INTROSPECT_TABLES_SQL)
        db_tables = {row[0] for row in cur.fetchall()}

        for table in sorted(model_tables.keys()):
            if table not in db_tables:
                report.table_diffs.append(TableDiff(
                    table=table,
                    kind=DiffKind.MISSING_TABLE,
                    detail="defined in Django models but not in database",
                ))

        target_tables = [t for t in model_tables if t in db_tables]

        if sw_only:
            extra_sw_tables = {t for t in db_tables if t.startswith("sw_")} - set(model_tables.keys())
            for table in sorted(extra_sw_tables):
                report.table_diffs.append(TableDiff(
                    table=table,
                    kind=DiffKind.EXTRA_TABLE,
                    detail="exists in database but no Django model",
                ))

        if not target_tables:
            return report

        cur.execute(INTROSPECT_COLUMNS_SQL, (target_tables,))
        db_columns: dict[str, dict[str, dict]] = {}
        for table_name, col_name, data_type, is_nullable in cur.fetchall():
            db_columns.setdefault(table_name, {})[col_name] = {
                "data_type": data_type,
                "nullable": is_nullable == "YES",
            }

        for table, model in sorted(model_tables.items()):
            if table not in db_columns:
                continue

            model_cols = _model_columns(model)
            db_cols = db_columns[table]

            for col_name, col_info in model_cols.items():
                if col_name not in db_cols:
                    report.column_diffs.append(ColumnDiff(
                        table=table,
                        column=col_name,
                        kind=DiffKind.MISSING_IN_DB,
                        model_type=col_info["field_type"],
                        detail=f"Django field {col_info['field_type']} has no column in DB",
                    ))
                    continue

                db_col = db_cols[col_name]
                expected_types = DJANGO_TO_PG_TYPES.get(col_info["field_type"], set())
                if expected_types and db_col["data_type"] not in expected_types:
                    report.column_diffs.append(ColumnDiff(
                        table=table,
                        column=col_name,
                        kind=DiffKind.TYPE_MISMATCH,
                        model_type=col_info["field_type"],
                        db_type=db_col["data_type"],
                        detail=f"Django={col_info['field_type']} expects {expected_types}, DB={db_col['data_type']}",
                    ))

                if col_info["nullable"] != db_col["nullable"]:
                    if col_name == "id":
                        continue
                    report.column_diffs.append(ColumnDiff(
                        table=table,
                        column=col_name,
                        kind=DiffKind.NULLABLE_MISMATCH,
                        model_type=f"null={col_info['nullable']}",
                        db_type=f"nullable={db_col['nullable']}",
                        detail=f"Django null={col_info['nullable']}, DB nullable={db_col['nullable']}",
                    ))

            for col_name in db_cols:
                if col_name not in model_cols:
                    report.column_diffs.append(ColumnDiff(
                        table=table,
                        column=col_name,
                        kind=DiffKind.EXTRA_IN_DB,
                        db_type=db_cols[col_name]["data_type"],
                        detail=f"column exists in DB ({db_cols[col_name]['data_type']}) but no Django field",
                    ))
    finally:
        conn.close()

    return report

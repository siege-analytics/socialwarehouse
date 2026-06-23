"""Monitoring models for warehouse observability (#331).

Creates three tables:
- sw_monitoring_materialization: per-asset parity after PostGIS materialization
- sw_monitoring_replication_lag: logical replication slot lag over time
- sw_monitoring_parity_check: cross-tier row count reconciliation
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_warehouse", "0006_partition_fact_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="MaterializationRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("asset_key", models.CharField(db_index=True, max_length=256)),
                ("source_tier", models.CharField(max_length=16)),
                ("target_table", models.CharField(max_length=128)),
                ("source_row_count", models.BigIntegerField()),
                ("target_row_count", models.BigIntegerField()),
                ("is_parity", models.BooleanField()),
                ("duration_seconds", models.FloatField()),
                ("dagster_run_id", models.CharField(blank=True, default="", max_length=64)),
                ("materialized_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "sw_monitoring_materialization",
            },
        ),
        migrations.AddIndex(
            model_name="materializationrecord",
            index=models.Index(fields=["asset_key", "-materialized_at"], name="sw_monitori_asset_k_idx"),
        ),
        migrations.AddIndex(
            model_name="materializationrecord",
            index=models.Index(fields=["-materialized_at"], name="sw_monitori_materia_idx"),
        ),
        migrations.CreateModel(
            name="ReplicationLagSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slot_name", models.CharField(db_index=True, max_length=128)),
                ("lag_bytes", models.BigIntegerField()),
                ("replay_lag_seconds", models.FloatField(null=True)),
                ("captured_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "sw_monitoring_replication_lag",
            },
        ),
        migrations.AddIndex(
            model_name="replicationlagsnapshot",
            index=models.Index(fields=["slot_name", "-captured_at"], name="sw_monitori_slot_na_idx"),
        ),
        migrations.CreateModel(
            name="ParityCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_tier", models.CharField(max_length=16)),
                ("target_tier", models.CharField(max_length=16)),
                ("table_name", models.CharField(max_length=128)),
                ("source_count", models.BigIntegerField()),
                ("target_count", models.BigIntegerField()),
                ("is_match", models.BooleanField()),
                ("checked_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "sw_monitoring_parity_check",
            },
        ),
        migrations.AddIndex(
            model_name="paritycheck",
            index=models.Index(fields=["table_name", "-checked_at"], name="sw_monitori_table_n_idx"),
        ),
        migrations.AddIndex(
            model_name="paritycheck",
            index=models.Index(fields=["-checked_at"], name="sw_monitori_checked_idx"),
        ),
    ]

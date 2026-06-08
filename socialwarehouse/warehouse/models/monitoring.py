"""Warehouse observability models (#331).

Three monitoring surfaces:
- MaterializationRecord: per-asset parity after PostGIS materialization
- ReplicationLagSnapshot: logical replication slot lag over time
- ParityCheck: cross-tier row count reconciliation
"""

from django.db import models


class MaterializationRecord(models.Model):
    asset_key = models.CharField(max_length=256, db_index=True)
    source_tier = models.CharField(max_length=16)
    target_table = models.CharField(max_length=128)
    source_row_count = models.BigIntegerField()
    target_row_count = models.BigIntegerField()
    is_parity = models.BooleanField()
    duration_seconds = models.FloatField()
    dagster_run_id = models.CharField(max_length=64, blank=True, default="")
    materialized_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_monitoring_materialization"
        indexes = [
            models.Index(fields=["asset_key", "-materialized_at"]),
            models.Index(fields=["-materialized_at"]),
        ]

    def __str__(self):
        status = "PARITY" if self.is_parity else "MISMATCH"
        return f"{self.asset_key} {status} ({self.source_row_count}→{self.target_row_count})"


class ReplicationLagSnapshot(models.Model):
    slot_name = models.CharField(max_length=128, db_index=True)
    lag_bytes = models.BigIntegerField()
    replay_lag_seconds = models.FloatField(null=True)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_monitoring_replication_lag"
        indexes = [
            models.Index(fields=["slot_name", "-captured_at"]),
        ]

    def __str__(self):
        return f"{self.slot_name}: {self.lag_bytes} bytes"


class ParityCheck(models.Model):
    source_tier = models.CharField(max_length=16)
    target_tier = models.CharField(max_length=16)
    table_name = models.CharField(max_length=128)
    source_count = models.BigIntegerField()
    target_count = models.BigIntegerField()
    is_match = models.BooleanField()
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sw_monitoring_parity_check"
        indexes = [
            models.Index(fields=["table_name", "-checked_at"]),
            models.Index(fields=["-checked_at"]),
        ]

    def __str__(self):
        status = "MATCH" if self.is_match else "MISMATCH"
        return f"{self.source_tier}→{self.target_tier} {self.table_name}: {status}"

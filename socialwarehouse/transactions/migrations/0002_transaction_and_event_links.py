import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_events", "0002_event_canonicalization"),
        ("sw_transactions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="contribution",
            name="event",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical Event this transaction record rolls up to",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)s_records",
                related_query_name="%(class)s_record",
                to="sw_events.event",
            ),
        ),
        migrations.AddField(
            model_name="expenditure",
            name="event",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical Event this transaction record rolls up to",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)s_records",
                related_query_name="%(class)s_record",
                to="sw_events.event",
            ),
        ),
        migrations.AddField(
            model_name="transfer",
            name="event",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical Event this transaction record rolls up to",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)s_records",
                related_query_name="%(class)s_record",
                to="sw_events.event",
            ),
        ),
        migrations.AddField(
            model_name="obligationevent",
            name="event",
            field=models.ForeignKey(
                blank=True,
                help_text="Canonical Event this transaction record rolls up to",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="%(class)s_records",
                related_query_name="%(class)s_record",
                to="sw_events.event",
            ),
        ),
        migrations.CreateModel(
            name="Transaction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "transaction_subtype",
                    models.CharField(
                        choices=[
                            ("contribution", "Contribution"),
                            ("expenditure", "Expenditure"),
                            ("transfer", "Transfer"),
                            ("obligation", "Obligation"),
                        ],
                        db_index=True,
                        help_text="contribution / expenditure / transfer / obligation",
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "currency",
                    models.CharField(
                        default="USD",
                        help_text="ISO 4217 currency code",
                        max_length=3,
                    ),
                ),
                (
                    "transaction_date",
                    models.DateField(
                        db_index=True,
                        help_text="Financial event date (may equal Event.event_date)",
                    ),
                ),
                (
                    "source_transaction_uuid",
                    models.UUIDField(
                        blank=True,
                        db_index=True,
                        help_text="transaction_uuid of a related source record, if any",
                        null=True,
                    ),
                ),
                (
                    "transaction_group_uuid",
                    models.UUIDField(
                        blank=True,
                        db_index=True,
                        help_text="group_uuid of the TransactionGroup this belongs to, if any",
                        null=True,
                    ),
                ),
                (
                    "event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transaction_detail",
                        to="sw_events.event",
                    ),
                ),
            ],
            options={
                "verbose_name": "Transaction",
                "verbose_name_plural": "Transactions",
                "db_table": "sw_transaction",
                "indexes": [
                    models.Index(
                        fields=["transaction_subtype", "transaction_date"],
                        name="idx_txn_subtype_date",
                    )
                ],
            },
        ),
    ]

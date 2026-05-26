import socialwarehouse.core.mixins
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("sw_core", "0001_initial"),
    ]

    operations = [
        # Obligation (SourceAwareModel, no IdentifiableModel)
        migrations.CreateModel(
            name="Obligation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                ("obligation_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("obligation_type", models.CharField(choices=[("loan", "Loan"), ("account_payable", "Account Payable"), ("refund_payable", "Refund Payable")], db_index=True, max_length=20)),
                ("original_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("current_balance", models.DecimalField(decimal_places=2, max_digits=14)),
                ("status", models.CharField(choices=[("active", "Active"), ("paid", "Paid in Full"), ("forgiven", "Forgiven"), ("defaulted", "Defaulted"), ("written_off", "Written Off")], db_index=True, default="active", max_length=20)),
                ("counterparty_uuid", models.UUIDField(db_index=True, help_text="entity_uuid of the counterparty (lender, payee, etc.)")),
                ("counterparty_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("agent_uuid", models.UUIDField(db_index=True, help_text="entity_uuid of the agent owing the obligation")),
                ("agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("incurred_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Obligation",
                "verbose_name_plural": "Obligations",
                "db_table": "sw_obligation",
            },
        ),
        # Contribution (_TransactionBase = SourceAwareModel + transaction fields)
        migrations.CreateModel(
            name="Contribution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                ("transaction_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("transaction_type", models.CharField(choices=[("contribution", "Contribution"), ("expenditure", "Expenditure"), ("transfer", "Transfer"), ("obligation_event", "Obligation Event")], db_index=True, max_length=20)),
                ("from_agent_uuid", models.UUIDField(db_index=True)),
                ("from_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("to_agent_uuid", models.UUIDField(db_index=True)),
                ("to_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("transaction_date", models.DateField(db_index=True)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Contribution",
                "verbose_name_plural": "Contributions",
                "db_table": "sw_contribution",
            },
        ),
        # Expenditure
        migrations.CreateModel(
            name="Expenditure",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                ("transaction_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("transaction_type", models.CharField(choices=[("contribution", "Contribution"), ("expenditure", "Expenditure"), ("transfer", "Transfer"), ("obligation_event", "Obligation Event")], db_index=True, max_length=20)),
                ("from_agent_uuid", models.UUIDField(db_index=True)),
                ("from_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("to_agent_uuid", models.UUIDField(db_index=True)),
                ("to_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("transaction_date", models.DateField(db_index=True)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Expenditure",
                "verbose_name_plural": "Expenditures",
                "db_table": "sw_expenditure",
            },
        ),
        # Transfer
        migrations.CreateModel(
            name="Transfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                ("transaction_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("transaction_type", models.CharField(choices=[("contribution", "Contribution"), ("expenditure", "Expenditure"), ("transfer", "Transfer"), ("obligation_event", "Obligation Event")], db_index=True, max_length=20)),
                ("from_agent_uuid", models.UUIDField(db_index=True)),
                ("from_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("to_agent_uuid", models.UUIDField(db_index=True)),
                ("to_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("transaction_date", models.DateField(db_index=True)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Transfer",
                "verbose_name_plural": "Transfers",
                "db_table": "sw_transfer",
            },
        ),
        # ObligationEvent
        migrations.CreateModel(
            name="ObligationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_source", models.CharField(blank=True, db_index=True, default="", max_length=50)),
                ("jurisdiction_level", models.CharField(blank=True, default="", max_length=20)),
                ("jurisdiction_state", models.CharField(blank=True, default="", max_length=2)),
                ("source_record_id", models.CharField(blank=True, default="", max_length=100)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                ("transaction_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("transaction_type", models.CharField(choices=[("contribution", "Contribution"), ("expenditure", "Expenditure"), ("transfer", "Transfer"), ("obligation_event", "Obligation Event")], db_index=True, max_length=20)),
                ("from_agent_uuid", models.UUIDField(db_index=True)),
                ("from_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("to_agent_uuid", models.UUIDField(db_index=True)),
                ("to_agent_type", models.CharField(choices=[("person", "Person"), ("committee", "Committee"), ("organization", "Organization")], max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("transaction_date", models.DateField(db_index=True)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("obligation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="sw_transactions.obligation")),
                ("obligation_event_type", models.CharField(choices=[("drawdown", "Drawdown / Incurrence"), ("repayment", "Repayment"), ("forgiveness", "Forgiveness"), ("adjustment", "Adjustment")], db_index=True, max_length=20)),
            ],
            options={
                "verbose_name": "Obligation Event",
                "verbose_name_plural": "Obligation Events",
                "db_table": "sw_obligation_event",
            },
        ),
        # TransactionGroup
        migrations.CreateModel(
            name="TransactionGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("group_uuid", models.UUIDField(default=socialwarehouse.core.mixins.generate_entity_uuid4, editable=False, unique=True)),
                ("group_type", models.CharField(choices=[("jfc_distribution", "Joint Fundraising Committee Distribution"), ("bundled_contribution", "Bundled Contribution"), ("split_disbursement", "Split Disbursement"), ("other", "Other")], db_index=True, max_length=30)),
                ("description", models.TextField(blank=True, default="")),
                ("contributions", models.ManyToManyField(blank=True, related_name="groups", to="sw_transactions.contribution")),
                ("expenditures", models.ManyToManyField(blank=True, related_name="groups", to="sw_transactions.expenditure")),
                ("transfers", models.ManyToManyField(blank=True, related_name="groups", to="sw_transactions.transfer")),
                ("obligation_events", models.ManyToManyField(blank=True, related_name="groups", to="sw_transactions.obligationevent")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Transaction Group",
                "verbose_name_plural": "Transaction Groups",
                "db_table": "sw_transaction_group",
            },
        ),
        # Indexes for Obligation
        migrations.AddIndex(model_name="obligation", index=models.Index(fields=["agent_uuid", "obligation_type"], name="idx_oblig_agent_type")),
        migrations.AddIndex(model_name="obligation", index=models.Index(fields=["counterparty_uuid"], name="idx_oblig_counterparty")),
        migrations.AddIndex(model_name="obligation", index=models.Index(fields=["status"], name="idx_oblig_status")),
        # Indexes for Contribution
        migrations.AddIndex(model_name="contribution", index=models.Index(fields=["from_agent_uuid", "transaction_date"], name="idx_contrib_from_date")),
        migrations.AddIndex(model_name="contribution", index=models.Index(fields=["to_agent_uuid", "transaction_date"], name="idx_contrib_to_date")),
        migrations.AddIndex(model_name="contribution", index=models.Index(fields=["jurisdiction_state", "transaction_date"], name="idx_contrib_state_date")),
        # Indexes for Expenditure
        migrations.AddIndex(model_name="expenditure", index=models.Index(fields=["from_agent_uuid", "transaction_date"], name="idx_expend_from_date")),
        migrations.AddIndex(model_name="expenditure", index=models.Index(fields=["to_agent_uuid", "transaction_date"], name="idx_expend_to_date")),
        migrations.AddIndex(model_name="expenditure", index=models.Index(fields=["jurisdiction_state", "transaction_date"], name="idx_expend_state_date")),
        # Indexes for Transfer
        migrations.AddIndex(model_name="transfer", index=models.Index(fields=["from_agent_uuid", "transaction_date"], name="idx_xfer_from_date")),
        migrations.AddIndex(model_name="transfer", index=models.Index(fields=["to_agent_uuid", "transaction_date"], name="idx_xfer_to_date")),
        migrations.AddIndex(model_name="transfer", index=models.Index(fields=["jurisdiction_state", "transaction_date"], name="idx_xfer_state_date")),
        # Indexes for ObligationEvent
        migrations.AddIndex(model_name="obligationevent", index=models.Index(fields=["obligation", "transaction_date"], name="idx_oblev_oblig_date")),
        migrations.AddIndex(model_name="obligationevent", index=models.Index(fields=["obligation_event_type"], name="idx_oblev_type")),
    ]

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sw_core", "0003_attestation"),
        ("sw_events", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="canonical_attestation",
            field=models.ForeignKey(
                blank=True,
                help_text="Fast-lookup cache of the canonical attestation; truth is Attestation.is_canonical",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="canonical_for_events",
                to="sw_core.attestation",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="attestation_disagreement",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="True when source attestations for this event conflict",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="is_amended",
            field=models.BooleanField(
                default=False,
                help_text="True when this event has been amended by a later revision",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="amendment_count",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Number of amendments applied to this event",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="event_state",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("amended", "Amended"),
                    ("withdrawn", "Withdrawn"),
                    ("superseded", "Superseded"),
                ],
                db_index=True,
                default="active",
                help_text="active / amended / withdrawn / superseded",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="event",
            index=models.Index(
                fields=["event_type", "event_state"],
                name="idx_event_type_state",
            ),
        ),
    ]

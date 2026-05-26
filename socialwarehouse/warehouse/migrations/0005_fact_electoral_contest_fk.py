from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sw_warehouse", "0004_dimperson_ontology_mixins"),
        ("sw_political", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="factelectionresult",
            name="electoral_contest",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="election_results",
                to="sw_political.electoralcontest",
                help_text="Link to the specific electoral contest (nullable during backfill)",
            ),
        ),
        migrations.AddField(
            model_name="factprecinctresult",
            name="electoral_contest",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="precinct_results",
                to="sw_political.electoralcontest",
                help_text="Link to the specific electoral contest (nullable during backfill)",
            ),
        ),
        migrations.AddIndex(
            model_name="factelectionresult",
            index=models.Index(fields=["electoral_contest"], name="idx_fer_contest"),
        ),
        migrations.AddIndex(
            model_name="factprecinctresult",
            index=models.Index(fields=["electoral_contest"], name="idx_fpr_contest"),
        ),
    ]

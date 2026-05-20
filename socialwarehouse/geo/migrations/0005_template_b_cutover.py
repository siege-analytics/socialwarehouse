"""Template-readiness B PR #2 cutover: retarget ABP's `vintage` FK
from `CensusVintageConfig` to the polymorphic `Vintage` parent table;
drop `CensusVintageConfig`.

Sequence:
  1. Data migration: repoint each ABP row's `vintage_id` from a
     CensusVintageConfig.id to the equivalent Vintage.id (where the
     equivalent is the CensusDecadalVintage row with the matching
     `decade`; that vintage's `vintage_ptr_id` is the parent
     Vintage.id by Django multi-table inheritance convention).
  2. AlterField: change ABP.vintage's FK target to `Vintage`. The
     underlying integer column is unchanged; Django adjusts the
     foreign-key constraint to point at `sw_geo_vintage` instead of
     `sw_geo_census_vintage_config`.
  3. DeleteModel: drop `CensusVintageConfig`.

After this migration, the polymorphic Vintage is the canonical
vintage table for ABP and downstream consumers.
"""

from django.db import migrations, models


def _repoint_abp_vintages(apps, schema_editor):
    """For each ABP, map vintage_id from CensusVintageConfig.pk to the
    matching CensusDecadalVintage's parent Vintage.pk.
    """
    AddressBoundaryPeriod = apps.get_model("sw_geo", "AddressBoundaryPeriod")
    CensusVintageConfig = apps.get_model("sw_geo", "CensusVintageConfig")
    CensusDecadalVintage = apps.get_model("sw_geo", "CensusDecadalVintage")

    # Build decade -> new Vintage.id lookup.
    decade_to_new_pk = {
        cdv.decade: cdv.pk
        for cdv in CensusDecadalVintage.objects.all()
    }

    # Build old-CVC-pk -> decade lookup.
    cvc_to_decade = {
        cvc.pk: cvc.decade
        for cvc in CensusVintageConfig.objects.all()
    }

    for abp in AddressBoundaryPeriod.objects.all():
        decade = cvc_to_decade.get(abp.vintage_id)
        if decade is None:
            # Orphan; leave alone — RemoveModel below will likely fail
            # but we surface the issue rather than silently rewriting
            # to a wrong value.
            continue
        new_pk = decade_to_new_pk.get(decade)
        if new_pk is None:
            continue
        if abp.vintage_id != new_pk:
            abp.vintage_id = new_pk
            abp.save(update_fields=["vintage_id"])


def _reverse_repoint(apps, schema_editor):
    """Reverse: map ABP.vintage_id back to the original CensusVintageConfig.pk
    by decade. Best-effort; if CensusVintageConfig was deleted by a
    subsequent migration, this reverse cannot reconstruct it.
    """
    AddressBoundaryPeriod = apps.get_model("sw_geo", "AddressBoundaryPeriod")
    CensusVintageConfig = apps.get_model("sw_geo", "CensusVintageConfig")
    CensusDecadalVintage = apps.get_model("sw_geo", "CensusDecadalVintage")

    new_pk_to_decade = {
        cdv.pk: cdv.decade for cdv in CensusDecadalVintage.objects.all()
    }
    decade_to_cvc_pk = {
        cvc.decade: cvc.pk for cvc in CensusVintageConfig.objects.all()
    }
    for abp in AddressBoundaryPeriod.objects.all():
        decade = new_pk_to_decade.get(abp.vintage_id)
        if decade is None:
            continue
        old_pk = decade_to_cvc_pk.get(decade)
        if old_pk is None:
            continue
        if abp.vintage_id != old_pk:
            abp.vintage_id = old_pk
            abp.save(update_fields=["vintage_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("sw_geo", "0004_polymorphic_vintage_models"),
    ]

    operations = [
        migrations.RunPython(_repoint_abp_vintages, _reverse_repoint),
        migrations.AlterField(
            model_name="addressboundaryperiod",
            name="vintage",
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                related_name="boundary_assignments",
                to="sw_geo.vintage",
            ),
        ),
        migrations.DeleteModel(name="CensusVintageConfig"),
    ]

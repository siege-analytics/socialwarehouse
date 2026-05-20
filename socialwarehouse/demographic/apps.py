from django.apps import AppConfig


class DemographicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.demographic"
    label = "sw_demographic"
    verbose_name = "Demographic Warehouse"

from django.apps import AppConfig


class CivicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.civic"
    label = "sw_civic"
    verbose_name = "Civic Warehouse"

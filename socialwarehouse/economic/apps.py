from django.apps import AppConfig


class EconomicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.economic"
    label = "sw_economic"
    verbose_name = "Economic Warehouse"

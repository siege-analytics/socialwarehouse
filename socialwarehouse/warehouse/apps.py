from django.apps import AppConfig


class WarehouseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.warehouse"
    label = "sw_warehouse"
    verbose_name = "Census Data Warehouse"

from django.apps import AppConfig


class GeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.geo"
    label = "sw_geo"
    verbose_name = "Geographic Warehouse"

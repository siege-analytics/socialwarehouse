from django.apps import AppConfig


class GeoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.geo"
    label = "sw_geo"
    verbose_name = "Geographic Warehouse"

    def ready(self):
        # F11 step 2b: wire up the Address-cache-refresh signal.
        from socialwarehouse.geo import signals as _signals
        _signals._connect()

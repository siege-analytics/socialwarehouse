from django.apps import AppConfig


class PoliticalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.political"
    label = "sw_political"
    verbose_name = "Political Structure"

from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.events"
    label = "sw_events"
    verbose_name = "Events"

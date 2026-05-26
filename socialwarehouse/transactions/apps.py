from django.apps import AppConfig


class TransactionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "socialwarehouse.transactions"
    label = "sw_transactions"
    verbose_name = "Transaction Types"

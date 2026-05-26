from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("contributions", views.ContributionViewSet, basename="contribution")
router.register("expenditures", views.ExpenditureViewSet, basename="expenditure")
router.register("transfers", views.TransferViewSet, basename="transfer")
router.register("obligations", views.ObligationViewSet, basename="obligation")

app_name = "transactions"

urlpatterns = [
    path("", include(router.urls)),
]

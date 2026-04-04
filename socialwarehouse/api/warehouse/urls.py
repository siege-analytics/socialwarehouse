from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("geographies", views.DimGeographyViewSet, basename="geography")
router.register("election-results", views.FactElectionResultViewSet, basename="election-result")
router.register("acs-estimates", views.FactACSEstimateViewSet, basename="acs-estimate")

app_name = "warehouse"

urlpatterns = [
    path("", include(router.urls)),
]

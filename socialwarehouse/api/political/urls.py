from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("offices", views.OfficeViewSet, basename="office")
router.register("seats", views.SeatViewSet, basename="seat")
router.register("elections", views.ElectionViewSet, basename="election")
router.register("contests", views.ElectoralContestViewSet, basename="contest")
router.register("terms", views.OfficeTermViewSet, basename="term")

app_name = "political"

urlpatterns = [
    path("", include(router.urls)),
]

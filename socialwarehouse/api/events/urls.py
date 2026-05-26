from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("", views.EventViewSet, basename="event")

app_name = "events"

urlpatterns = [
    path("", include(router.urls)),
]

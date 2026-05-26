from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("persons", views.PersonViewSet, basename="person")
router.register("committees", views.CommitteeViewSet, basename="committee")
router.register("organizations", views.OrganizationViewSet, basename="organization")
router.register("classifications", views.ClassificationViewSet, basename="classification")
router.register("roles", views.RoleViewSet, basename="role")

app_name = "agents"

urlpatterns = [
    path("", include(router.urls)),
]

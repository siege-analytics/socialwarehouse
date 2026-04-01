from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/geo/", include("socialwarehouse.api.geo.urls")),
]

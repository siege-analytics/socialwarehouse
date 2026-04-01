from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # API endpoints will be wired in SW-3.4
    # path("api/geo/", include("socialwarehouse.api.geo.urls")),
    # path("api/warehouse/", include("socialwarehouse.api.warehouse.urls")),
]

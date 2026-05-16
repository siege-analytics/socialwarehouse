from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # SW warehouse + DSTK API
    path("api/geo/", include("socialwarehouse.api.geo.urls")),
    path("api/warehouse/", include("socialwarehouse.api.warehouse.urls")),
    # GST web-app surface (via vendor/geodjango_simple_template/ submodule, P1B-B #68)
    path("webapp/grappelli/", include("grappelli.urls")),
    path("webapp/accounts/", include("django.contrib.auth.urls")),
    path("webapp/api-auth/", include("rest_framework.urls")),
    path("webapp/locations/", include("locations.urls")),
]

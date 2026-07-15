from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # SW warehouse + DSTK API
    path("api/geo/", include("socialwarehouse.api.geo.urls")),
    path("api/warehouse/", include("socialwarehouse.api.warehouse.urls")),
    path("api/agents/", include("socialwarehouse.api.agents.urls")),
    path("api/political/", include("socialwarehouse.api.political.urls")),
    path("api/transactions/", include("socialwarehouse.api.transactions.urls")),
    path("api/events/", include("socialwarehouse.api.events.urls")),
    path("webapp/grappelli/", include("grappelli.urls")),
    path("webapp/accounts/", include("django.contrib.auth.urls")),
    path("webapp/api-auth/", include("rest_framework.urls")),
]

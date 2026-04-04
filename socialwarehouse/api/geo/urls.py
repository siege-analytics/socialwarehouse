from django.urls import path

from . import views

app_name = "geo"

urlpatterns = [
    path("geocode/", views.geocode, name="geocode"),
    path("reverse_geocode/", views.reverse_geocode, name="reverse_geocode"),
    path("standardize_address/", views.standardize_address, name="standardize_address"),
    path("boundaries/<str:boundary_type>/", views.boundary_list, name="boundary_list"),
    path("boundaries/<str:boundary_type>/<str:geoid>/", views.boundary_detail, name="boundary_detail"),
    path("proximity/", views.proximity, name="proximity"),
    path("intersections/", views.intersections, name="intersections"),
]

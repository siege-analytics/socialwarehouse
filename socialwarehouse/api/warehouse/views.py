"""Warehouse analytical API views."""

from rest_framework import filters, viewsets

from socialwarehouse.api.pagination import StandardPagination
from socialwarehouse.warehouse.models import (
    DimGeography,
    FactACSEstimate,
    FactElectionResult,
)
from .serializers import (
    DimGeographySerializer,
    FactACSEstimateSerializer,
    FactElectionResultSerializer,
)


class DimGeographyViewSet(viewsets.ReadOnlyModelViewSet):
    """Geographic dimension — all geographies with hierarchy."""

    queryset = DimGeography.objects.all()
    serializer_class = DimGeographySerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "geoid"]
    ordering = ["geoid"]


class FactElectionResultViewSet(viewsets.ReadOnlyModelViewSet):
    """Election results by geography."""

    queryset = FactElectionResult.objects.select_related("geography").all()
    serializer_class = FactElectionResultSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["votes", "vote_share"]
    ordering = ["-votes"]


class FactACSEstimateViewSet(viewsets.ReadOnlyModelViewSet):
    """Census ACS estimates by geography."""

    queryset = FactACSEstimate.objects.select_related("geography", "variable", "survey").all()
    serializer_class = FactACSEstimateSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["estimate"]
    ordering = ["-estimate"]

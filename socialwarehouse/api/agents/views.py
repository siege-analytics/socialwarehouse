from rest_framework import filters, viewsets

from socialwarehouse.agents.models import (
    Classification,
    Committee,
    Organization,
    Role,
)
from socialwarehouse.api.pagination import StandardPagination
from socialwarehouse.warehouse.models import DimPerson

from .serializers import (
    ClassificationSerializer,
    CommitteeSerializer,
    DimPersonSerializer,
    OrganizationSerializer,
    RoleSerializer,
)


class PersonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DimPerson.objects.all()
    serializer_class = DimPersonSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "entity_uuid"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self):
        qs = super().get_queryset()
        state = self.request.query_params.get("jurisdiction_state")
        if state:
            qs = qs.filter(jurisdiction_state=state)
        source = self.request.query_params.get("data_source")
        if source:
            qs = qs.filter(data_source=source)
        return qs


class CommitteeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Committee.objects.all()
    serializer_class = CommitteeSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "entity_uuid"]
    ordering = ["name"]


class OrganizationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "entity_uuid"]
    ordering = ["name"]


class ClassificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Classification.objects.all()
    serializer_class = ClassificationSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-effective_from"]

    def get_queryset(self):
        qs = super().get_queryset()
        agent_uuid = self.request.query_params.get("agent_uuid")
        if agent_uuid:
            qs = qs.filter(agent_uuid=agent_uuid)
        as_of = self.request.query_params.get("as_of")
        if as_of:
            from django.db.models import Q
            qs = qs.filter(
                Q(effective_from__lte=as_of),
                Q(effective_to__gte=as_of) | Q(effective_to__isnull=True),
            )
        return qs


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-effective_from"]

    def get_queryset(self):
        qs = super().get_queryset()
        agent_uuid = self.request.query_params.get("agent_uuid")
        if agent_uuid:
            qs = qs.filter(agent_uuid=agent_uuid)
        as_of = self.request.query_params.get("as_of")
        if as_of:
            from django.db.models import Q
            qs = qs.filter(
                Q(effective_from__lte=as_of),
                Q(effective_to__gte=as_of) | Q(effective_to__isnull=True),
            )
        return qs

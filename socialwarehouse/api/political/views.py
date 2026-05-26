from rest_framework import filters, viewsets

from socialwarehouse.api.pagination import StandardPagination
from socialwarehouse.political.models import (
    Election,
    ElectoralContest,
    Office,
    OfficeTerm,
    Seat,
)

from .serializers import (
    ElectionSerializer,
    ElectoralContestSerializer,
    OfficeSerializer,
    OfficeTermSerializer,
    SeatSerializer,
)


class OfficeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Office.objects.all()
    serializer_class = OfficeSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]

    def get_queryset(self):
        qs = super().get_queryset()
        chamber = self.request.query_params.get("chamber")
        if chamber:
            qs = qs.filter(chamber=chamber)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(jurisdiction_state=state)
        return qs


class SeatViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Seat.objects.select_related("office").all()
    serializer_class = SeatSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-effective_from"]


class ElectionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Election.objects.all()
    serializer_class = ElectionSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-election_date"]

    def get_queryset(self):
        qs = super().get_queryset()
        year = self.request.query_params.get("year")
        if year:
            qs = qs.filter(year=year)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(jurisdiction_state=state)
        election_type = self.request.query_params.get("election_type")
        if election_type:
            qs = qs.filter(election_type=election_type)
        return qs


class ElectoralContestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ElectoralContest.objects.select_related("election", "office").all()
    serializer_class = ElectoralContestSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-election__election_date"]


class OfficeTermViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OfficeTerm.objects.select_related("office").all()
    serializer_class = OfficeTermSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-start_date"]

    def get_queryset(self):
        qs = super().get_queryset()
        person_uuid = self.request.query_params.get("person_uuid")
        if person_uuid:
            qs = qs.filter(person_uuid=person_uuid)
        current = self.request.query_params.get("current")
        if current == "true":
            qs = qs.filter(end_date__isnull=True)
        return qs

from django.db.models import Count
from rest_framework import filters, viewsets

from socialwarehouse.api.pagination import StandardPagination
from socialwarehouse.events.models import Event

from .serializers import EventListSerializer, EventSerializer


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-event_date"]

    def get_serializer_class(self):
        if self.action == "list":
            return EventListSerializer
        return EventSerializer

    def get_queryset(self):
        qs = Event.objects.all()

        if self.action == "list":
            qs = qs.annotate(participant_count=Count("participants"))
        else:
            qs = qs.prefetch_related(
                "participants",
                "corporate_detail",
                "spatiotemporal_detail",
                "electoral_detail",
            )

        event_type = self.request.query_params.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(jurisdiction_state=state)

        year = self.request.query_params.get("year")
        if year:
            qs = qs.filter(year=year)

        agent_uuid = self.request.query_params.get("agent_uuid")
        if agent_uuid:
            qs = qs.filter(participants__agent_uuid=agent_uuid).distinct()

        return qs

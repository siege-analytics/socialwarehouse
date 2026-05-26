from rest_framework import filters, viewsets

from socialwarehouse.api.pagination import StandardPagination
from socialwarehouse.transactions.models import (
    Contribution,
    Expenditure,
    Obligation,
    Transfer,
)

from .serializers import (
    ContributionSerializer,
    ExpenditureSerializer,
    ObligationSerializer,
    TransferSerializer,
)


class _TransactionViewSetMixin:
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-transaction_date"]

    def get_queryset(self):
        qs = super().get_queryset()
        from_agent = self.request.query_params.get("from_agent_uuid")
        if from_agent:
            qs = qs.filter(from_agent_uuid=from_agent)
        to_agent = self.request.query_params.get("to_agent_uuid")
        if to_agent:
            qs = qs.filter(to_agent_uuid=to_agent)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(jurisdiction_state=state)
        year = self.request.query_params.get("year")
        if year:
            qs = qs.filter(transaction_date__year=year)
        return qs


class ContributionViewSet(_TransactionViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Contribution.objects.all()
    serializer_class = ContributionSerializer


class ExpenditureViewSet(_TransactionViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Expenditure.objects.all()
    serializer_class = ExpenditureSerializer


class TransferViewSet(_TransactionViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Transfer.objects.all()
    serializer_class = TransferSerializer


class ObligationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Obligation.objects.all()
    serializer_class = ObligationSerializer
    pagination_class = StandardPagination
    filter_backends = [filters.OrderingFilter]
    ordering = ["-original_amount"]

    def get_queryset(self):
        qs = super().get_queryset()
        agent_uuid = self.request.query_params.get("agent_uuid")
        if agent_uuid:
            qs = qs.filter(agent_uuid=agent_uuid)
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

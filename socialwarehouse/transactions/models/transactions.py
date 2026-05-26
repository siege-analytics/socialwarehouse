from decimal import Decimal

from django.db import models

from socialwarehouse.core.mixins import (
    SourceAwareModel,
    generate_entity_uuid4,
)


AGENT_TYPE_CHOICES = [
    ("person", "Person"),
    ("committee", "Committee"),
    ("organization", "Organization"),
]

TRANSACTION_TYPE_CHOICES = [
    ("contribution", "Contribution"),
    ("expenditure", "Expenditure"),
    ("transfer", "Transfer"),
    ("obligation_event", "Obligation Event"),
]

OBLIGATION_TYPE_CHOICES = [
    ("loan", "Loan"),
    ("account_payable", "Account Payable"),
    ("refund_payable", "Refund Payable"),
]

OBLIGATION_STATUS_CHOICES = [
    ("active", "Active"),
    ("paid", "Paid in Full"),
    ("forgiven", "Forgiven"),
    ("defaulted", "Defaulted"),
    ("written_off", "Written Off"),
]

OBLIGATION_EVENT_TYPE_CHOICES = [
    ("drawdown", "Drawdown / Incurrence"),
    ("repayment", "Repayment"),
    ("forgiveness", "Forgiveness"),
    ("adjustment", "Adjustment"),
]

GROUP_TYPE_CHOICES = [
    ("jfc_distribution", "Joint Fundraising Committee Distribution"),
    ("bundled_contribution", "Bundled Contribution"),
    ("split_disbursement", "Split Disbursement"),
    ("other", "Other"),
]


class _TransactionBase(SourceAwareModel):
    """Shared fields for all transaction types.

    Directed edge: from_agent -> to_agent. Agent linkage by UUID (no FK
    to agent tables — warehouse-first constraint).
    """

    transaction_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE_CHOICES,
        db_index=True,
    )
    from_agent_uuid = models.UUIDField(db_index=True)
    from_agent_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
    )
    to_agent_uuid = models.UUIDField(db_index=True)
    to_agent_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_date = models.DateField(db_index=True)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def __str__(self):
        return (
            f"{self.transaction_type}: ${self.amount} "
            f"{self.from_agent_uuid} -> {self.to_agent_uuid} "
            f"on {self.transaction_date}"
        )


class Contribution(_TransactionBase):
    """Person/Org -> Committee contribution."""

    class Meta:
        verbose_name = "Contribution"
        verbose_name_plural = "Contributions"
        db_table = "sw_contribution"
        indexes = [
            models.Index(
                fields=["from_agent_uuid", "transaction_date"],
                name="idx_contrib_from_date",
            ),
            models.Index(
                fields=["to_agent_uuid", "transaction_date"],
                name="idx_contrib_to_date",
            ),
            models.Index(
                fields=["jurisdiction_state", "transaction_date"],
                name="idx_contrib_state_date",
            ),
        ]

    def save(self, *args, **kwargs):
        self.transaction_type = "contribution"
        super().save(*args, **kwargs)


class Expenditure(_TransactionBase):
    """Committee -> Vendor/Organization expenditure."""

    class Meta:
        verbose_name = "Expenditure"
        verbose_name_plural = "Expenditures"
        db_table = "sw_expenditure"
        indexes = [
            models.Index(
                fields=["from_agent_uuid", "transaction_date"],
                name="idx_expend_from_date",
            ),
            models.Index(
                fields=["to_agent_uuid", "transaction_date"],
                name="idx_expend_to_date",
            ),
            models.Index(
                fields=["jurisdiction_state", "transaction_date"],
                name="idx_expend_state_date",
            ),
        ]

    def save(self, *args, **kwargs):
        self.transaction_type = "expenditure"
        super().save(*args, **kwargs)


class Transfer(_TransactionBase):
    """Committee -> Committee transfer (party->candidate, JFC->PAC, PAC->PAC)."""

    class Meta:
        verbose_name = "Transfer"
        verbose_name_plural = "Transfers"
        db_table = "sw_transfer"
        indexes = [
            models.Index(
                fields=["from_agent_uuid", "transaction_date"],
                name="idx_xfer_from_date",
            ),
            models.Index(
                fields=["to_agent_uuid", "transaction_date"],
                name="idx_xfer_to_date",
            ),
            models.Index(
                fields=["jurisdiction_state", "transaction_date"],
                name="idx_xfer_state_date",
            ),
        ]

    def save(self, *args, **kwargs):
        self.transaction_type = "transfer"
        super().save(*args, **kwargs)


class Obligation(SourceAwareModel):
    """Stateful balance tracking: Loan, AccountPayable, RefundPayable.

    Balance updated via ObligationEvent transactions. SCD2 in the Delta
    layer for balance history.
    """

    obligation_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    obligation_type = models.CharField(
        max_length=20,
        choices=OBLIGATION_TYPE_CHOICES,
        db_index=True,
    )
    original_amount = models.DecimalField(max_digits=14, decimal_places=2)
    current_balance = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=OBLIGATION_STATUS_CHOICES,
        default="active",
        db_index=True,
    )
    counterparty_uuid = models.UUIDField(
        db_index=True,
        help_text="entity_uuid of the counterparty (lender, payee, etc.)",
    )
    counterparty_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
    )
    agent_uuid = models.UUIDField(
        db_index=True,
        help_text="entity_uuid of the agent owing the obligation",
    )
    agent_type = models.CharField(
        max_length=20,
        choices=AGENT_TYPE_CHOICES,
    )
    incurred_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Obligation"
        verbose_name_plural = "Obligations"
        db_table = "sw_obligation"
        indexes = [
            models.Index(
                fields=["agent_uuid", "obligation_type"],
                name="idx_oblig_agent_type",
            ),
            models.Index(
                fields=["counterparty_uuid"],
                name="idx_oblig_counterparty",
            ),
            models.Index(
                fields=["status"],
                name="idx_oblig_status",
            ),
        ]

    def apply_event(self, event_type, amount):
        """Update balance based on an obligation event."""
        if event_type == "repayment":
            self.current_balance -= amount
        elif event_type == "drawdown":
            self.current_balance += amount
        elif event_type == "forgiveness":
            self.current_balance -= amount
        elif event_type == "adjustment":
            self.current_balance += amount

        if self.current_balance <= Decimal("0.00"):
            self.current_balance = Decimal("0.00")
            if event_type == "forgiveness":
                self.status = "forgiven"
            else:
                self.status = "paid"

    def __str__(self):
        return (
            f"{self.obligation_type}: ${self.current_balance} "
            f"(of ${self.original_amount}) — {self.status}"
        )


class ObligationEvent(_TransactionBase):
    """Loan drawdown, repayment, debt incurrence/forgiveness."""

    obligation = models.ForeignKey(
        Obligation,
        on_delete=models.CASCADE,
        related_name="events",
    )
    obligation_event_type = models.CharField(
        max_length=20,
        choices=OBLIGATION_EVENT_TYPE_CHOICES,
        db_index=True,
    )

    class Meta:
        verbose_name = "Obligation Event"
        verbose_name_plural = "Obligation Events"
        db_table = "sw_obligation_event"
        indexes = [
            models.Index(
                fields=["obligation", "transaction_date"],
                name="idx_oblev_oblig_date",
            ),
            models.Index(
                fields=["obligation_event_type"],
                name="idx_oblev_type",
            ),
        ]

    def save(self, *args, **kwargs):
        self.transaction_type = "obligation_event"
        super().save(*args, **kwargs)


class TransactionGroup(models.Model):
    """Links multiple transactions into a single logical event.

    Example: JFC receives $100K, distributes to 5 committees = 6
    transactions in one group.
    """

    group_uuid = models.UUIDField(
        unique=True,
        editable=False,
        default=generate_entity_uuid4,
    )
    group_type = models.CharField(
        max_length=30,
        choices=GROUP_TYPE_CHOICES,
        db_index=True,
    )
    description = models.TextField(blank=True, default="")
    contributions = models.ManyToManyField(
        Contribution,
        blank=True,
        related_name="groups",
    )
    expenditures = models.ManyToManyField(
        Expenditure,
        blank=True,
        related_name="groups",
    )
    transfers = models.ManyToManyField(
        Transfer,
        blank=True,
        related_name="groups",
    )
    obligation_events = models.ManyToManyField(
        ObligationEvent,
        blank=True,
        related_name="groups",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transaction Group"
        verbose_name_plural = "Transaction Groups"
        db_table = "sw_transaction_group"

    def __str__(self):
        return f"{self.group_type}: {self.description[:50]}" if self.description else f"{self.group_type}"

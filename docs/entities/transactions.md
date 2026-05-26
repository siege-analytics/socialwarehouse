# Transactions

**App**: `socialwarehouse.transactions`

## Transaction types

All transaction types share the `_TransactionBase` abstract model (`SourceAwareModel`) with directed edges: `from_agent_uuid` → `to_agent_uuid`.

| Model | Table | Flow |
|---|---|---|
| `Contribution` | `sw_contribution` | Person/Org → Committee |
| `Expenditure` | `sw_expenditure` | Committee → Vendor/Org |
| `Transfer` | `sw_transfer` | Committee → Committee |
| `ObligationEvent` | `sw_obligation_event` | Drawdown, repayment, forgiveness |

Each subclass auto-sets `transaction_type` on save.

## Obligation (`sw_obligation`)

Stateful balance tracking for loans, accounts payable, and refund payables. Balance updated via `apply_event()`:

- `drawdown` → increases balance
- `repayment` → decreases balance
- `forgiveness` → decreases balance, sets status to "forgiven" if zeroed
- `adjustment` → increases balance

Balance floors at zero. Status transitions: active → paid/forgiven.

## TransactionGroup (`sw_transaction_group`)

Links multiple transactions into a single logical event (e.g., JFC receives $100K, distributes to 5 committees = 6 transactions in one group). Uses M2M relationships to all transaction types.

"""Reconciliation gate.

Every extracted statement must satisfy:
    opening + Σcredits − Σdebits == closing ± tolerance

If it doesn't, the statement is unreliable and no decision is rendered.
This is what would have caught Jorge's LA-Finance sign bug before Layer 2.
"""

from dataclasses import dataclass


@dataclass
class ReconciliationResult:
    ok: bool
    expected_closing: float
    actual_closing: float
    error: float
    tolerance: float
    message: str


def reconcile(
    transactions: list[dict],
    opening_balance: float,
    closing_balance: float,
    tolerance: float = 100.0,
) -> ReconciliationResult:
    credits = sum(t["amount"] for t in transactions if t.get("is_credit"))
    debits = sum(t["amount"] for t in transactions if not t.get("is_credit"))
    expected = opening_balance + credits - debits
    error = abs(expected - closing_balance)
    ok = error <= tolerance
    return ReconciliationResult(
        ok=ok,
        expected_closing=round(expected, 2),
        actual_closing=round(closing_balance, 2),
        error=round(error, 2),
        tolerance=tolerance,
        message=(
            "ok"
            if ok
            else f"reconciliation failed: expected ${expected:.2f}, got ${closing_balance:.2f}, "
            f"diff ${error:.2f} > tolerance ${tolerance:.2f}"
        ),
    )

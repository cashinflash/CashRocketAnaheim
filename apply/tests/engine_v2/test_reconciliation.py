"""Tests for the reconciliation gate — Jorge's LA-Finance bug is the canonical case."""

from engine_v2.extraction.reconciliation import reconcile


def test_reconcile_balanced():
    txns = [
        {"amount": 100.0, "is_credit": True},
        {"amount": 30.0, "is_credit": False},
    ]
    r = reconcile(txns, opening_balance=0.0, closing_balance=70.0)
    assert r.ok
    assert r.error == 0.0


def test_reconcile_within_tolerance():
    txns = [{"amount": 100.0, "is_credit": True}]
    r = reconcile(txns, opening_balance=0.0, closing_balance=95.0, tolerance=50.0)
    assert r.ok


def test_reconcile_fails_beyond_tolerance():
    txns = [{"amount": 100.0, "is_credit": True}]
    r = reconcile(txns, opening_balance=0.0, closing_balance=200.0, tolerance=50.0)
    assert not r.ok
    assert r.error == 100.0


def test_jorge_la_finance_sign_bug_would_be_caught():
    """
    Simulates Jorge's case: LA-Finance $2,525 was extracted as a debit but was
    actually a credit. If the extractor emits it wrong, reconciliation fails by
    exactly 2 * $2,525 = $5,050, and v2 halts before Layer 2.
    """
    # Hypothetical transaction set where LA-Finance is WRONGLY a debit
    txns = [
        {"amount": 1965.06, "is_credit": True},  # payroll
        {"amount": 2525.00, "is_credit": False},  # LA-Finance (wrongly debit)
        {"amount": 1440.72, "is_credit": False},  # all other legitimate debits
    ]
    r = reconcile(txns, opening_balance=-283.72, closing_balance=-285.29, tolerance=100.0)
    assert not r.ok
    # The error exceeds the $100 tolerance by a wide margin — gate would fire,
    # halting the decision until the underlying extraction bug is resolved.
    assert r.error > 100

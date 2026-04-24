"""Regression tests for cif-apply/decision_engine.py Plaid extraction.

Jairo Canas case: applicant connected a traditional bank AND Chime. Payroll
landed on Chime but the old code grabbed the first account with transactions
and dropped every other account — so the engine saw only "Chime transfer"
inflows and declined for "no payroll." Fix aggregates across all connected
accounts; these tests lock that in.
"""

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from decision_engine import convert_plaid_to_extracted


def _plaid_response(accounts):
    """Build a minimal Plaid asset report response with N accounts."""
    return {
        "report": {
            "items": [{"accounts": accounts}],
        },
    }


def _account(account_id, subtype, txns, balance=100.0, historical=None):
    return {
        "account_id": account_id,
        "official_name": f"Acct {account_id}",
        "subtype": subtype,
        "balances": {"current": balance, "available": balance},
        "historical_balances": historical or [],
        "transactions": txns,
        "owners": [{"names": ["Jairo Canas"]}],
    }


def test_aggregates_transactions_across_all_connected_accounts():
    """The regression test for the Jairo bug. Primary bank has only Chime
    transfers in; Chime has the actual payroll. Must aggregate both."""
    bank_txns = [
        {"date": "2026-03-20", "amount": -418.82, "name": "Chime transfer",
         "personal_finance_category": {"primary": "TRANSFER_IN", "detailed": ""}},
        {"date": "2026-03-22", "amount": 45.00, "name": "Walmart",
         "personal_finance_category": {"primary": "GENERAL_MERCHANDISE", "detailed": ""}},
    ]
    chime_txns = [
        {"date": "2026-03-20", "amount": -850.00, "name": "MULHOLLAND HILLS PAYROLL",
         "personal_finance_category": {"primary": "INCOME", "detailed": "INCOME_WAGES"}},
        {"date": "2026-03-20", "amount": 418.82, "name": "Transfer to bank",
         "personal_finance_category": {"primary": "TRANSFER_OUT", "detailed": ""}},
    ]
    resp = _plaid_response([
        _account("bank1", "checking", bank_txns, balance=29.33),
        _account("chime1", "checking", chime_txns, balance=431.18),
    ])
    result = convert_plaid_to_extracted(resp)
    assert result is not None

    # All four transactions must be present — the old code would return only 2.
    assert len(result["transactions"]) == 4, \
        f"Expected 4 aggregated txns, got {len(result['transactions'])}"

    # Each txn must carry its source account id
    account_ids = {t["account_id"] for t in result["transactions"]}
    assert account_ids == {"bank1", "chime1"}

    # The payroll must be in the aggregated list
    payroll = next(t for t in result["transactions"]
                   if "MULHOLLAND" in (t.get("description") or "").upper())
    assert payroll["is_credit"] is True
    assert payroll["account_id"] == "chime1"

    # Ending balance = sum across accounts
    assert result["ending_balance"] == 29.33 + 431.18
    # Applicant connected 2 accounts
    assert result["connected_account_count"] == 2
    assert len(result["connected_accounts"]) == 2


def test_single_account_still_works():
    """Sanity: the pre-existing single-account flow must still produce the
    same shape so nothing downstream breaks."""
    resp = _plaid_response([
        _account("only1", "checking", [
            {"date": "2026-03-20", "amount": -1500.00, "name": "PAYROLL",
             "personal_finance_category": {"primary": "INCOME", "detailed": "INCOME_WAGES"}},
        ], balance=1500.0),
    ])
    result = convert_plaid_to_extracted(resp)
    assert result is not None
    assert len(result["transactions"]) == 1
    assert result["connected_account_count"] == 1


def test_no_accounts_returns_none():
    resp = _plaid_response([])
    assert convert_plaid_to_extracted(resp) is None


def test_accounts_without_transactions_still_counted():
    """An account that has balances but no transactions shouldn't block
    extraction — other accounts' transactions should still come through."""
    resp = _plaid_response([
        _account("savings1", "savings", [], balance=100.0),
        _account("checking1", "checking", [
            {"date": "2026-03-20", "amount": -500.00, "name": "ACH DEPOSIT",
             "personal_finance_category": {"primary": "INCOME", "detailed": ""}},
        ], balance=500.0),
    ])
    result = convert_plaid_to_extracted(resp)
    assert result is not None
    assert len(result["transactions"]) == 1
    assert result["connected_account_count"] == 2
    assert result["ending_balance"] == 600.0

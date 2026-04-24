"""Tests for sign-guarded categorization — Jorge's bug as a regression test."""

from engine_v2.categorization.rules import classify_credit, classify_debit
from engine_v2.categorization.registry import category_for


def test_la_finance_credit_goes_to_loan_proceeds_not_loan_payment():
    """The Jorge bug, structurally."""
    cat, _ = classify_credit("LA-Finance LLC Vendor", 2525.00)
    assert cat == "loan_proceeds"


def test_la_finance_debit_goes_to_loan_payment():
    cat, _ = classify_debit("LA-Finance LLC Vendor", 2525.00)
    assert cat == "loan_payment"


def test_atlas_financial_credit_is_not_loan_payment():
    cat, _ = classify_credit("Atlas Financial Smartpay", 1.40)
    assert cat != "loan_payment"


def test_upstart_credit_is_loan_proceeds():
    """The Michelle case."""
    cat, _ = classify_credit("Transfer Cross River Bank from Upstart ; Loan", 1100.00)
    # Either Upstart or Cross River Bank should match first.
    assert cat == "loan_proceeds"


def test_earnin_credit_is_fintech_advance():
    """The Danitza/Sherrie case — credit-side fintech blind spot is now fixed."""
    cat, _ = classify_credit("RTP CREDIT EARNIN BF", 150.00)
    assert cat == "fintech_advance"


def test_earnin_debit_is_fintech_repayment():
    cat, _ = classify_debit("WEB Earnin REPAYMENT", 155.99)
    assert cat == "fintech_repayment"


def test_atm_cash_deposit_is_cash_deposit_not_other_credit():
    """The Sherrie case — 7 cash deposits were all bucketed as other_credit."""
    cat, _ = classify_credit("ATM CASH DEPOSIT 03/21 6085 COFFEE RD", 400.00)
    assert cat == "cash_deposit"


def test_keepthechange_both_directions_are_internal_transfer():
    """The Michelle case — auto-savings round-ups."""
    cat_cr, _ = classify_credit("KEEPTHECHANGE CREDIT FROM ACCT2257", 0.57)
    cat_db, _ = classify_debit("KEEPTHECHANGE DEBIT TO ACCT2257", 0.57)
    assert cat_cr == "internal_transfer"
    assert cat_db == "internal_transfer"


def test_bright_money_pennies_are_account_verification_not_income():
    cat, _ = classify_credit("Bright Money ACCTCHECK0 084106761138224 WEB ID:", 0.01)
    assert cat == "account_verification"


def test_unmatched_merchant_is_unclassified_not_silent_default():
    """No merchant should ever silent-default into other_credit/other_expense."""
    cat, rule = classify_credit("SOME TOTALLY UNKNOWN MERCHANT XYZ", 50.00)
    assert cat == "unclassified"
    assert rule == "no_rule_matched"


def test_registry_null_direction_returns_no_match():
    """Westlake is null on credit side — Westlake only makes sense as a debit."""
    assert category_for("Westlake Financial", is_credit=True) is None
    assert category_for("Westlake Financial", is_credit=False) == "loan_payment"


def test_atm_withdrawal_at_grocery_store_is_atm_not_groceries():
    """The 'withdrawal at atm 7eleven' bug — ATM must fire before
    merchant keywords. Was classified as groceries pre-fix."""
    cat, _ = classify_debit("ATM WITHDRAWAL 7-ELEVEN CULVER CITY", 100.0)
    assert cat == "atm"


def test_atm_cash_with_no_registry_match_still_hits_keyword():
    """Force the keyword path by using a description not in the registry."""
    cat, rule = classify_debit("CASH WITHDRAWAL AT LUCKY MARKET LA", 60.0)
    assert cat == "atm"
    assert rule.startswith("keyword:atm")


def test_cash_withdrawal_at_shell_is_atm_not_gas():
    cat, rule = classify_debit("CASH WITHDRAWAL SHELL OIL VAN NUYS", 60.0)
    assert cat == "atm"


def test_overdraft_fee_is_fee_not_subscription_or_loan():
    cat, rule = classify_debit("Overdraft Fee T-Mobile Postpaid", 35.0)
    assert cat == "fee"
    # Even though T-Mobile keyword exists, FEE fires first.


def test_online_transfer_is_internal_not_p2p():
    cat, rule = classify_debit("Online Transfer to Way2Save", 500.0)
    assert cat == "internal_transfer"


def test_description_preprocessor_strips_ach_prefix():
    from engine_v2.categorization.rules import normalize_description
    assert normalize_description("PPD LA COUNTY PAYROLL") == "LA COUNTY PAYROLL"
    assert normalize_description("WEB Earnin REPAYMENT") == "Earnin REPAYMENT"
    assert normalize_description("RTP CREDIT EARNIN BF") == "EARNIN BF"


def test_description_preprocessor_strips_trailing_confirmation_ids():
    from engine_v2.categorization.rules import normalize_description
    # PPD Tilt 1004694740 -> "Tilt"
    result = normalize_description("PPD Tilt 1004694740")
    assert "Tilt" in result
    assert "1004694740" not in result


def test_description_preprocessor_strips_trailing_dates():
    from engine_v2.categorization.rules import normalize_description
    assert normalize_description("7-Eleven Culver City 03/23") == "7-Eleven Culver City"


def test_sign_guard_prevents_claude_hint_flipping_direction():
    """If Claude mis-labeled a credit as `loan_payment`, the hint fallback
    must refuse the hint because loan_payment is a DEBIT category.
    This is the Jorge-bug regression test for the hint-fallback path."""
    txn = {
        "description": "SOME UNKNOWN MERCHANT",
        "amount": 500.0,
        "is_credit": True,
        "category": "loan_payment",  # WRONG sign — Claude got confused
    }
    cat, _ = classify_credit(txn["description"], txn["amount"], txn)
    # Must NOT accept the loan_payment hint on a credit — refuses, falls through
    assert cat == "unclassified"


def test_sign_guard_accepts_same_direction_hint():
    """If Claude labels a debit as groceries, fallback accepts (sign matches)."""
    txn = {
        "description": "SOME UNKNOWN GROCERY MERCHANT",
        "amount": 50.0,
        "is_credit": False,
        "category": "groceries",
    }
    cat, rule = classify_debit(txn["description"], txn["amount"], txn)
    assert cat == "groceries"
    assert rule.startswith("hint:")


def test_mypay_advance_credit_is_fintech_advance():
    """MyPay is an earned-wage-access fintech. Jairo Canas regression —
    6 'MyPay advance' credits were landing in other_credit, silently
    under-counting his fintech stacking."""
    cat, _ = classify_credit("MyPay advance", 108.00)
    assert cat == "fintech_advance"


def test_mypay_repayment_debit_is_fintech_repayment():
    cat, _ = classify_debit("MyPay repayment", 300.00)
    assert cat == "fintech_repayment"
    cat2, _ = classify_debit("MyPay instant advance fees", 10.13)
    assert cat2 == "fintech_repayment"


def test_chime_secured_account_card_payment_is_internal_transfer():
    """Chime Credit Builder moves money between the applicant's own
    checking/deposit and the secured card. Must be internal_transfer, not
    counted as income or expense. Jairo Canas regression — a $2,208.92
    'Card Payment from Secured Account' was sitting in other_credit and
    also tripping the cherry-pick timing flag."""
    cat_cr, _ = classify_credit("Card Payment from Secured Account", 2208.92)
    assert cat_cr == "internal_transfer"
    cat_db, _ = classify_debit("Credit Builder payment", 150.00)
    assert cat_db == "internal_transfer"


def test_chime_transfer_credit_is_internal_transfer():
    """Jairo Canas regression. His traditional bank account only had
    'Chime transfer' / 'Moved from Chime' credits (all self-shuffling from
    his Chime account where payroll actually lands). Must not count toward
    verified income."""
    cat_credit, _ = classify_credit("Chime transfer", 418.82)
    assert cat_credit == "internal_transfer"
    cat_debit, _ = classify_debit("Chime transfer", 50.00)
    assert cat_debit == "internal_transfer"
    cat_moved, _ = classify_credit("Moved from Chime", 315.36)
    assert cat_moved == "internal_transfer"


def test_federal_benefit_credit_is_govt_benefits():
    """US Bank labels Social Security as 'Federal Benefit Credit'. Janine Pierce
    regression — was previously unclassified."""
    cat, _ = classify_credit("Federal Benefit Credit", 1779.00)
    assert cat == "govt_benefits"


def test_truncated_zelle_debit_is_p2p_sent_not_atm():
    """Chase/BoA truncate Zelle to "ZEL*". Must not be classified as ATM
    just because the description starts with "WITHDRAWAL"."""
    cat, rule = classify_debit("Withdrawal Faster Payments ZEL* Jakyoung Kim", 35.00)
    assert cat == "p2p_sent"


def test_truncated_zelle_credit_is_p2p_received():
    cat, _ = classify_credit("Deposit Faster Payments ZEL* Angel Aponte", 50.00)
    assert cat == "p2p_received"


def test_plaid_pfc_hint_loan_payments_maps_to_loan_payment():
    txn = {
        "description": "UNKNOWN SERVICER PAYMENT",
        "amount": 100.0,
        "is_credit": False,
        "personal_finance_category": {"primary": "LOAN_PAYMENTS", "detailed": "..."},
    }
    cat, rule = classify_debit(txn["description"], txn["amount"], txn)
    assert cat == "loan_payment"
    assert rule.startswith("plaid_pfc:")


def test_registry_overrides_take_precedence_over_base(tmp_path, monkeypatch):
    """Adding an override via the Review Queue should classify that merchant
    on the next lookup — no code deploy needed."""
    import engine_v2.categorization.registry as reg
    # A merchant not in the base registry
    assert category_for("TOTALLY NEW MERCHANT XYZ", is_credit=False) is None
    # Add an override
    reg.add_override("TOTALLY NEW MERCHANT XYZ", credit=None, debit="groceries", added_by="test")
    try:
        # Now resolves
        assert category_for("TOTALLY NEW MERCHANT XYZ", is_credit=False) == "groceries"
        assert category_for("TOTALLY NEW MERCHANT XYZ", is_credit=True) is None
    finally:
        # Clean up the overrides file to avoid polluting repo
        import json
        overrides_path = reg._OVERRIDES_PATH
        data = json.loads(overrides_path.read_text())
        data.pop("TOTALLY NEW MERCHANT XYZ", None)
        overrides_path.write_text(json.dumps(data, indent=2))
        reg.reload()

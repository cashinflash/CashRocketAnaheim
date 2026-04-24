"""End-to-end pipeline tests — exercises run_v2 from inputs to decision."""

from engine_v2 import run_v2


def test_pipeline_produces_decline_on_zero_payroll_for_stated_employment():
    """Michelle-class case: stated Employment but no payroll in statement."""
    extracted = {
        "transactions": [
            {"date": "2026-03-20", "description": "KEEPTHECHANGE CREDIT FROM ACCT2257", "amount": 0.19, "is_credit": True},
            {"date": "2026-04-01", "description": "KEEPTHECHANGE CREDIT FROM ACCT2257", "amount": 0.02, "is_credit": True},
            {"date": "2026-04-14", "description": "Transfer Cross River Bank from Upstart ; Loan", "amount": 1100.00, "is_credit": True},
            {"date": "2026-04-15", "description": "Monthly Maintenance Fee", "amount": 12.00, "is_credit": False},
        ],
        "beginning_balance": 1.92,
        "ending_balance": 1090.13,
        "statement_days": 30,
        "nsf_count": 0,
        "negative_days": 0,
        "avg_daily_balance": 50,
    }
    application = {
        "firstName": "Michelle",
        "lastName": "Anderson",
        "payFrequency": "Monthly",
        "grossPay": "6883",
        "sourceOfIncome": "Employment",
        "accountType": "Personal Checking",
        "submittedAt": "2026-04-16T14:00:00",
    }
    result = run_v2(extracted, application)
    assert result.decision.outcome == "decline"
    reason_text = " ".join(result.decision.reasons).lower()
    assert "no verified payroll" in reason_text or "competing loan" in reason_text


def test_pipeline_catches_upstart_loan_as_loan_proceeds_not_income():
    """The Michelle case — Upstart $1,100 must NOT inflate verified income."""
    extracted = {
        "transactions": [
            {"date": "2026-04-14", "description": "Transfer Cross River Bank from Upstart ; Loan", "amount": 1100.00, "is_credit": True},
            {"date": "2026-03-27", "description": "PPD LA COUNTY PAYROLL", "amount": 850.05, "is_credit": True},
        ],
        "beginning_balance": 0, "ending_balance": 1950.05,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    application = {"payFrequency": "Semi-Monthly", "grossPay": "1363", "sourceOfIncome": "Employment", "accountType": "Personal Checking", "submittedAt": "2026-04-16"}
    result = run_v2(extracted, application)

    # Verified income should be ONLY the payroll, NOT the Upstart disbursement
    assert result.affordability.verified_income_monthly < 900  # just the payroll, not +$1100
    # The Upstart transaction should be categorized as loan_proceeds
    upstart_txn = next(t for t in result.categorized_transactions if "upstart" in t["description"].lower())
    assert upstart_txn["v2_category"] == "loan_proceeds"


def test_pipeline_detects_rollover_pattern():
    """Danitza-class case: CIF repayment + fresh Sunshine advance."""
    extracted = {
        "transactions": [
            {"date": "2026-03-27", "description": "PPD LA COUNTY PAYROLL", "amount": 850.05, "is_credit": True},
            {"date": "2026-04-15", "description": "PPD LA COUNTY PAYROLL", "amount": 1339.34, "is_credit": True},
            {"date": "2026-04-15", "description": "CASH IN FLASH ARLETA CA", "amount": 176.47, "is_credit": False},
            {"date": "2026-04-16", "description": "PPD SUNSHINELOAN UTC", "amount": 200.00, "is_credit": True},
        ],
        "beginning_balance": 0, "ending_balance": 2212.92,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    application = {"payFrequency": "Semi-Monthly", "grossPay": "1363", "sourceOfIncome": "Employment", "accountType": "Personal Checking", "submittedAt": "2026-04-16"}
    result = run_v2(extracted, application)

    # Rollover pattern should be flagged
    assert result.features.cif_prior_repay_30d
    assert result.features.fresh_advance_within_7d
    # And the decision should decline for rollover
    reason_text = " ".join(result.decision.reasons).lower()
    assert "rollover" in reason_text or "competing loan" in reason_text


def test_pipeline_produces_html_report():
    """HTML renderer runs cleanly on a complete pipeline result."""
    from engine_v2.report_html import render
    extracted = {
        "transactions": [{"date": "2026-03-27", "description": "PPD LA COUNTY PAYROLL", "amount": 850.05, "is_credit": True}],
        "beginning_balance": 0, "ending_balance": 850.05,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Semi-Monthly"})
    html = render(result, {"firstName": "Test", "lastName": "Applicant"})
    assert "Engine v2" in html or "engine v2" in html
    assert "Affordability" in html
    assert "classification audit" in html.lower()


def test_pipeline_auto_decide_candidate_false_when_review_flags_present():
    """Michelle-class report has review_flags → not auto-decide."""
    extracted = {
        "transactions": [
            {"date": "2026-04-14", "description": "Transfer Cross River Bank from Upstart ; Loan", "amount": 1100.00, "is_credit": True},
            {"date": "2026-04-15", "description": "Monthly Maintenance Fee", "amount": 12.00, "is_credit": False},
        ],
        "beginning_balance": 1.92, "ending_balance": 1089.92,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 50,
    }
    application = {
        "payFrequency": "Monthly", "grossPay": "6883", "sourceOfIncome": "Employment",
        "accountType": "Personal Checking", "submittedAt": "2026-04-16T14:00:00",
    }
    result = run_v2(extracted, application)
    assert result.summary["auto_decide_candidate"] is False


def test_pipeline_auto_decide_candidate_false_on_reconciliation_failure():
    extracted = {
        "transactions": [{"date": "2026-04-01", "description": "PAYROLL", "amount": 1000.00, "is_credit": True}],
        "beginning_balance": 0, "ending_balance": 5000.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Monthly"})
    assert result.summary["auto_decide_candidate"] is False


def test_pipeline_auto_decide_threshold_exposed_in_summary():
    extracted = {
        "transactions": [{"date": "2026-04-01", "description": "PAYROLL", "amount": 1000.00, "is_credit": True}],
        "beginning_balance": 0, "ending_balance": 1000.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Monthly"})
    assert "auto_decide_candidate" in result.summary
    assert "auto_decide_threshold" in result.summary
    assert result.summary["auto_decide_threshold"] == 0.80


def test_pipeline_self_zelle_is_internal_transfer_not_p2p_sent():
    """Zelle to yourself (description contains applicant's own name) is
    an internal transfer, not a P2P sent. Surfaced by the Jakyoung Kim
    Review Queue case where 'WITHDRAWAL FASTER PAYMENTS ZEL* JAKYOUNG KIM'
    was being suggested as ATM."""
    extracted = {
        "transactions": [
            {"date": "2026-04-01", "description": "PPD LA COUNTY PAYROLL", "amount": 1000.00, "is_credit": True},
            {"date": "2026-04-02", "description": "Withdrawal Faster Payments ZEL* Jakyoung Kim", "amount": 322.00, "is_credit": False},
        ],
        "beginning_balance": 0, "ending_balance": 678.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    application = {
        "firstName": "Jakyoung", "lastName": "Kim",
        "payFrequency": "Monthly", "grossPay": "2000", "sourceOfIncome": "Employment",
    }
    result = run_v2(extracted, application)
    zelle_txn = next(t for t in result.categorized_transactions if "ZEL*" in (t["description"] or ""))
    assert zelle_txn["v2_category"] == "internal_transfer"
    assert "self_name_match" in zelle_txn["v2_rule"]


def test_pipeline_third_party_zelle_stays_p2p_sent():
    """A Zelle to someone OTHER than the applicant must stay p2p_sent —
    the self-match must not over-fire on any name in the description."""
    extracted = {
        "transactions": [
            {"date": "2026-04-01", "description": "PPD LA COUNTY PAYROLL", "amount": 1000.00, "is_credit": True},
            {"date": "2026-04-02", "description": "Withdrawal Faster Payments ZEL* Jose Martinez", "amount": 100.00, "is_credit": False},
        ],
        "beginning_balance": 0, "ending_balance": 900.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    application = {"firstName": "Jakyoung", "lastName": "Kim", "payFrequency": "Monthly"}
    result = run_v2(extracted, application)
    zelle_txn = next(t for t in result.categorized_transactions if "Jose Martinez" in (t["description"] or ""))
    assert zelle_txn["v2_category"] == "p2p_sent"


def test_pipeline_cherry_pick_ignores_payroll_and_internal_transfers():
    """Jairo Canas regression. His regular bi-weekly payroll landed 3 days
    before apply, and his Chime secured-card payment of $2,208.92 landed 6
    days before. Neither is cherry-picked — payroll is his normal cadence,
    secured-card payment is self-shuffling. The flag must NOT fire."""
    extracted = {
        "transactions": [
            {"date": "2026-04-14", "description": "Modern B&B La, Payroll", "amount": 811.00, "is_credit": True},
            {"date": "2026-04-11", "description": "Card Payment from Secured Account", "amount": 2208.92, "is_credit": True},
            {"date": "2026-04-05", "description": "Debit Purchase Walmart", "amount": 50.00, "is_credit": False},
        ],
        "beginning_balance": 0, "ending_balance": 3019.92,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    application = {
        "sourceOfIncome": "Employment", "payFrequency": "Bi-Weekly",
        "submittedAt": "2026-04-17T14:00:00",
    }
    result = run_v2(extracted, application)
    assert result.features.funds_deposited_within_7d_of_apply is False, \
        "Cherry-pick should NOT fire on payroll or on a Chime Credit Builder internal payment"


def test_pipeline_cherry_pick_fires_on_suspicious_other_credit():
    """Sanity: a genuinely suspicious $1,500 'other_credit' right before
    apply still trips the flag."""
    extracted = {
        "transactions": [
            {"date": "2026-04-01", "description": "MULHOLLAND HILLS PAYROLL", "amount": 850.00, "is_credit": True},
            {"date": "2026-04-15", "description": "SOME WEIRD UNKNOWN DEPOSIT XYZ", "amount": 1500.00, "is_credit": True},
        ],
        "beginning_balance": 0, "ending_balance": 2350.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    application = {"sourceOfIncome": "Employment", "submittedAt": "2026-04-17T14:00:00"}
    result = run_v2(extracted, application)
    assert result.features.funds_deposited_within_7d_of_apply is True


def test_pipeline_wrong_account_only_chime_transfers_declines_clearly():
    """Jairo Canas regression. Applicant connected a traditional bank account
    as their primary, but their actual payroll lands on Chime (which wasn't
    linked, or was linked but previously dropped by the single-account
    extraction bug). Every credit on the connected account is a Chime
    transfer. Must decline with the specific 'wrong account' reason — not the
    generic 'no verified payroll' reason — so the applicant knows to
    reconnect the right bank."""
    extracted = {
        "transactions": [
            {"date": "2026-03-20", "description": "Chime transfer", "amount": 73.91, "is_credit": True},
            {"date": "2026-03-20", "description": "Moved from Chime", "amount": 418.82, "is_credit": True},
            {"date": "2026-03-23", "description": "Chime transfer", "amount": 16.53, "is_credit": True},
            {"date": "2026-03-27", "description": "Chime transfer", "amount": 315.36, "is_credit": True},
            {"date": "2026-03-25", "description": "Chime transfer", "amount": 32.00, "is_credit": False},
            {"date": "2026-03-28", "description": "Debit Purchase Walmart", "amount": 45.00, "is_credit": False},
        ],
        "beginning_balance": 29.33, "ending_balance": 0,
        "statement_days": 29, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 19.33,
    }
    application = {
        "firstName": "Jairo", "lastName": "Canas",
        "sourceOfIncome": "Employment",
        "employer": "Mulholland Hills Country Club",
        "payFrequency": "Bi-Weekly",
    }
    result = run_v2(extracted, application)
    assert result.features.income_only_self_transfers is True
    assert result.decision.outcome == "decline"
    reasons = " ".join(result.decision.reasons)
    assert "Connected account only receives transfers" in reasons, \
        f"Expected the specific wrong-account reason. Got: {reasons}"


def test_pipeline_normal_payroll_does_not_trigger_wrong_account_rule():
    """Sanity: a legit payroll deposit alongside some Chime transfers must
    NOT trip the wrong-account rule — it's valid income."""
    extracted = {
        "transactions": [
            {"date": "2026-03-27", "description": "ACH MULHOLLAND HILLS PAYROLL", "amount": 850.00, "is_credit": True},
            {"date": "2026-03-28", "description": "Chime transfer", "amount": 200.00, "is_credit": True},
        ],
        "beginning_balance": 0, "ending_balance": 1050.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Bi-Weekly", "sourceOfIncome": "Employment"})
    assert result.features.income_only_self_transfers is False


def test_pipeline_shelly_romo_zelle_not_detected_as_b9_fintech():
    """Janine Pierce regression: Zelle to 'Shelly Romo Usb9cwhrvdcy' was
    detected as B9 fintech because the transaction id suffix 'usb9' contains
    'b9' as a substring. Word-boundary matching fixes it."""
    extracted = {
        "transactions": [
            {"date": "2026-04-01", "description": "PAYROLL COMPANY", "amount": 1500.00, "is_credit": True},
            {"date": "2026-04-08", "description": "Zelle Instant Pmt To Shelly Romo Usb9cwhrvdcy", "amount": 50.00, "is_credit": False},
        ],
        "beginning_balance": 0, "ending_balance": 1450.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Monthly"})
    assert "B9" not in result.features.fintech_apps_list, \
        f"B9 falsely detected in {result.features.fintech_apps_list}"


def test_pipeline_real_b9_still_detected():
    """Sanity: a genuine B9 mention (with word boundaries) must still match."""
    extracted = {
        "transactions": [
            {"date": "2026-04-01", "description": "PAYROLL COMPANY", "amount": 1500.00, "is_credit": True},
            {"date": "2026-04-08", "description": "ACH B9 Cash Advance Repayment", "amount": 50.00, "is_credit": False},
        ],
        "beginning_balance": 0, "ending_balance": 1450.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Monthly"})
    assert "B9" in result.features.fintech_apps_list, \
        f"B9 missing from {result.features.fintech_apps_list}"


def test_pipeline_same_day_cashout_flags_review():
    """Janine Pierce regression: $1,779 govt benefits deposit + $1,185 cash
    withdrawn the same day = 67% cashout ratio. Should flag for review."""
    extracted = {
        "transactions": [
            {"date": "2026-04-03", "description": "Federal Benefit Credit", "amount": 1779.00, "is_credit": True},
            {"date": "2026-04-03", "description": "Customer Withdrawal #3137798650", "amount": 1035.00, "is_credit": False},
            {"date": "2026-04-03", "description": "Atm Withdrawal Us Bank", "amount": 150.00, "is_credit": False},
        ],
        "beginning_balance": 0, "ending_balance": 594.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    application = {"payFrequency": "Monthly", "sourceOfIncome": "Government Benefits"}
    result = run_v2(extracted, application)
    assert result.features.same_day_cashout_ratio >= 0.5
    assert "same_day_cashout_high" in result.decision.review_flags


def test_pipeline_normal_cashout_does_not_flag():
    """A modest ATM pull on the same day as payday is normal — don't flag."""
    extracted = {
        "transactions": [
            {"date": "2026-04-03", "description": "PPD LA COUNTY PAYROLL", "amount": 1500.00, "is_credit": True},
            {"date": "2026-04-03", "description": "Atm Withdrawal", "amount": 60.00, "is_credit": False},
        ],
        "beginning_balance": 0, "ending_balance": 1440.00,
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Monthly", "sourceOfIncome": "Employment"})
    assert result.features.same_day_cashout_ratio < 0.5
    assert "same_day_cashout_high" not in result.decision.review_flags


def test_pipeline_reconciliation_failure_is_primary_reason():
    """When math doesn't balance, that's the first thing the engine says."""
    extracted = {
        "transactions": [{"date": "2026-04-01", "description": "PAYROLL", "amount": 1000.00, "is_credit": True}],
        "beginning_balance": 0, "ending_balance": 5000.00,  # huge mismatch
        "statement_days": 30, "nsf_count": 0, "negative_days": 0, "avg_daily_balance": 500,
    }
    result = run_v2(extracted, {"payFrequency": "Monthly"})
    assert not result.reconciliation.ok
    # First decline reason is reconciliation
    assert "reconciliation" in result.decision.reasons[0].lower() or "unreliable" in result.decision.reasons[0].lower()

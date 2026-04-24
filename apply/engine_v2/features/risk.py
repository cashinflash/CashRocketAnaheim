"""Risk-pattern features — behavioural signals that separate default from repay."""

from datetime import datetime, timedelta


def populate(fv, categorized_txns, extracted_meta, application):
    # ── same-day CIF rollover pattern ──
    # Detected when: a prior CIF loan repayment is visible in the statement
    # AND a fresh fintech/loan advance lands within 7 days of that repayment.
    cif_repayments = [
        t for t in categorized_txns
        if t.get("v2_category") == "loan_payment_cif"
        or "cash in flash" in t.get("description", "").lower()
    ]
    fv.cif_prior_repay_30d = len(cif_repayments) > 0

    fresh_advances = [
        t for t in categorized_txns
        if t.get("v2_category") in ("loan_proceeds", "loan_proceeds_cif", "fintech_advance")
    ]

    same_day = False
    fresh_advance_within_7d = False
    for repay in cif_repayments:
        repay_date = _parse_date(repay.get("date", ""))
        if not repay_date:
            continue
        for adv in fresh_advances:
            adv_date = _parse_date(adv.get("date", ""))
            if not adv_date:
                continue
            gap_days = abs((adv_date - repay_date).days)
            if gap_days <= 7:
                fresh_advance_within_7d = True
            if gap_days == 0:
                same_day = True
    fv.same_day_cif_rollover = same_day
    fv.fresh_advance_within_7d = fresh_advance_within_7d

    # ── P2P self-transfer ratio ──
    # How much money moves as P2P (includes both sent and received).
    # High ratio suggests account is being used as a pass-through.
    p2p_sent = sum(t["amount"] for t in categorized_txns if t.get("v2_category") == "p2p_sent")
    p2p_received = sum(t["amount"] for t in categorized_txns if t.get("v2_category") == "p2p_received")
    total_activity = sum(t["amount"] for t in categorized_txns)
    if total_activity > 0:
        fv.p2p_self_transfer_ratio = round((p2p_sent + p2p_received) / total_activity, 3)
    else:
        fv.p2p_self_transfer_ratio = 0.0

    # ── wrong-account-type detection ──
    # Savings accounts typically lack: regular debit-card merchant activity,
    # recurring bill pays, payroll direct deposits.
    # If the application claims "Personal Checking" but transactions look like
    # savings (mostly internal transfers + verification pings), flag.
    stated_type = (application or {}).get("accountType", "").lower()
    fv.wrong_account_type_detected = _detect_wrong_account_type(
        stated_type, categorized_txns
    )

    # ── cash velocity ──
    # Ratio of (cash deposits + ATM withdrawals) to total activity.
    # High ratio suggests cash-heavy behaviour, often correlated with unstable
    # employment or informal income.
    cash_in = sum(t["amount"] for t in categorized_txns if t.get("v2_category") == "cash_deposit")
    cash_out = sum(t["amount"] for t in categorized_txns if t.get("v2_category") == "atm")
    if total_activity > 0:
        fv.cash_velocity_ratio = round((cash_in + cash_out) / total_activity, 3)
    else:
        fv.cash_velocity_ratio = 0.0

    # ── income-is-only-self-transfers ──
    # Catches the "applicant connected the wrong account" pattern. If every
    # credit on the statement is an internal transfer (e.g., every single
    # deposit is a "Chime transfer" from the applicant's own Chime account)
    # AND the applicant claims Employment, the primary account where payroll
    # lands wasn't linked. Different failure mode from "no income at all" —
    # needs a clearer decline reason so the applicant knows to reconnect.
    credit_txns = [t for t in categorized_txns if t.get("is_credit")]
    if credit_txns:
        internal_credits = sum(
            1 for t in credit_txns if t.get("v2_category") == "internal_transfer"
        )
        fv.income_only_self_transfers = (
            internal_credits == len(credit_txns) and len(credit_txns) >= 3
        )

    # ── same-day cash-out of verified income ──
    # For each verified-income deposit (payroll / govt_benefits / gig / pension /
    # child_support), sum ATM withdrawals and large "customer withdrawal" cash
    # outflows posted on the SAME calendar day. Compute the ratio per deposit
    # and keep the max. High values (>50%) signal cash-dependent spending or
    # an attempt to deflate the observed balance before application review.
    INCOME_CATEGORIES = ("payroll", "gig_income", "govt_benefits", "pension", "child_support")
    income_by_date = {}
    for t in categorized_txns:
        if t.get("v2_category") in INCOME_CATEGORIES and t.get("is_credit"):
            d = _parse_date(t.get("date", ""))
            if d:
                income_by_date[d] = income_by_date.get(d, 0.0) + float(t.get("amount") or 0)

    def _is_cash_out(t):
        if t.get("is_credit"):
            return False
        if t.get("v2_category") == "atm":
            return True
        desc = (t.get("description") or "").lower()
        return "customer withdrawal" in desc and float(t.get("amount") or 0) >= 200

    cashout_by_date = {}
    for t in categorized_txns:
        if _is_cash_out(t):
            d = _parse_date(t.get("date", ""))
            if d:
                cashout_by_date[d] = cashout_by_date.get(d, 0.0) + float(t.get("amount") or 0)

    max_ratio = 0.0
    for d, income_amt in income_by_date.items():
        if income_amt <= 0:
            continue
        same_day_cash = cashout_by_date.get(d, 0.0)
        ratio = same_day_cash / income_amt
        if ratio > max_ratio:
            max_ratio = ratio
    fv.same_day_cashout_ratio = round(max_ratio, 3)

    # ── funds deposited within 7 days of apply ──
    # Cherry-picked timing detection. The legitimate signal: a large credit
    # from an unknown/suspicious source landing just before application,
    # potentially staged to make the balance look healthy. Previous version
    # fired on Jairo Canas's regular bi-weekly payroll timing (false positive)
    # and on his Chime Credit Builder "Card Payment from Secured Account"
    # $2,208.92 (categorized as other_credit because the secured-card keyword
    # wasn't there). Tightened the exclusion list so only genuinely suspicious
    # categories can trip it.
    _EXCLUDED_FROM_CHERRY_PICK = (
        "payroll", "gig_income", "govt_benefits", "pension", "child_support",
        "internal_transfer",           # self-shuffling, not staged
        "fintech_advance",              # tracked separately via stacking rules
        "account_verification",         # $0.01 pings
        "bnpl_refund", "mobile_deposit",
        "loan_proceeds", "loan_proceeds_cif",  # flagged by competing-loan rule
    )
    submitted_at = (application or {}).get("submittedAt", "")
    apply_date = _parse_date(submitted_at)
    if apply_date:
        cutoff = apply_date - timedelta(days=7)
        large_recent = [
            t for t in categorized_txns
            if t.get("is_credit")
            and t.get("amount", 0) >= 500
            and _parse_date(t.get("date", "")) is not None
            and cutoff <= _parse_date(t.get("date", "")) <= apply_date
            and t.get("v2_category") not in _EXCLUDED_FROM_CHERRY_PICK
        ]
        fv.funds_deposited_within_7d_of_apply = len(large_recent) > 0


def _parse_date(s: str):
    if not s:
        return None
    try:
        s = str(s).split("T")[0].split(" ")[0]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _detect_wrong_account_type(stated_type: str, txns: list) -> bool:
    """Heuristic: checking accounts usually have >=3 debit-card merchant transactions.
    If stated is checking but we see near-zero merchant debits and many internal
    transfers / verification pings, flag as wrong-account.
    """
    if "checking" not in stated_type:
        return False

    merchant_debits = sum(
        1 for t in txns
        if not t.get("is_credit")
        and t.get("v2_category") not in (
            "internal_transfer", "account_verification", "fee", "atm",
            "p2p_sent", "fintech_repayment", "loan_payment", "bnpl_payment",
            "unclassified",
        )
    )
    verification_noise = sum(
        1 for t in txns if t.get("v2_category") == "account_verification"
    )
    internal_transfers = sum(
        1 for t in txns if t.get("v2_category") == "internal_transfer"
    )

    # Checking account with <3 real merchant debits AND >= 3x that in
    # internal-transfer/verification noise → probably a savings account.
    if merchant_debits < 3 and (internal_transfers + verification_noise) >= 10:
        return True
    return False

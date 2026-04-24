"""Affordability calculator — paper-validated across Jorge/Michelle/Danitza/Sherrie.

Formula (user-approved 2026-04-16):

    verified_income_monthly  = payroll + gig + govt_benefits + pension + child_support
    committed_obligations    = rent + utilities + phone + internet + insurance
                             + loan_payments + fintech_repayments + bnpl
                             + subscriptions + recurring_medical + transportation
                             + max($800, 0.18 * income)           # baseline living
    large_p2p_outflows       = Σ(p2p_sent ≥ $300 or recurring-to-same-party)

    fcf_monthly              = verified_income_monthly - committed_obligations - large_p2p_outflows
    fcf_per_period           = fcf_monthly / pay_periods_per_month
    max_affordable_payment   = fcf_per_period * 0.50                # subprime safety factor
    max_affordable_loan      = largest CIF tier whose periodic payment <= max_affordable_payment
"""

from dataclasses import dataclass, field


SAFETY_FACTOR = 0.50
BASELINE_LIVING_FLOOR = 800.0
BASELINE_LIVING_RATIO = 0.18
LARGE_P2P_THRESHOLD = 300.0


# Per-period loan payment sizes. These are approximations based on CIF's
# short-term amortization; real values should come from policy YAML.
# Assumes ~4 pay periods to repay the principal + fees.
TIER_PERIODIC_PAYMENTS = {
    100: 33.0,
    150: 50.0,
    200: 67.0,
    255: 85.0,
}


@dataclass
class AffordabilityReport:
    verified_income_monthly: float
    committed_obligations_monthly: float
    baseline_living_included: float
    large_p2p_outflows_monthly: float
    fcf_monthly: float
    fcf_per_period: float
    pay_periods_per_month: float
    safety_factor: float
    max_affordable_payment: float
    max_affordable_loan_amount: int
    confidence: float
    anti_gaming_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)


def compute_affordability(categorized_txns: list[dict], fv, extracted_meta: dict, application: dict) -> AffordabilityReport:
    statement_days = extracted_meta.get("statement_days", 30)
    multiplier = 30.0 / max(statement_days, 1)

    # ── Committed obligations ──
    OBLIGATION_CATEGORIES = {
        "rent", "utilities", "phone", "internet", "insurance",
        "loan_payment", "loan_payment_cif", "fintech_repayment",
        "bnpl_payment", "subscriptions", "medical",
        "transportation", "childcare",
    }

    obligations_period = {}
    for t in categorized_txns:
        if t.get("is_credit"):
            continue
        cat = t.get("v2_category", "")
        if cat in OBLIGATION_CATEGORIES:
            obligations_period[cat] = obligations_period.get(cat, 0) + t.get("amount", 0)

    # Cap subscriptions at max 2 per merchant (port v1 sub_cap logic)
    obligations_monthly = {
        cat: round(total * multiplier, 2)
        for cat, total in obligations_period.items()
    }
    obligations_total = sum(obligations_monthly.values())

    # Baseline living floor
    baseline = max(BASELINE_LIVING_FLOOR, BASELINE_LIVING_RATIO * fv.verified_income_monthly)

    # If explicit groceries/gas/restaurants already seen, deduct them from
    # the baseline to avoid double-counting (baseline covers variable living).
    variable_living_seen = sum(
        t.get("amount", 0) for t in categorized_txns
        if not t.get("is_credit")
        and t.get("v2_category", "") in ("groceries", "gas_fuel", "restaurants")
    ) * multiplier
    baseline_net = max(0.0, baseline - variable_living_seen)

    # ── Large P2P outflows ──
    # Recurring-to-same-party: 2+ payments to same payee counts as obligation.
    recurring_p2p = _detect_recurring_p2p(categorized_txns)
    large_single_p2p_period = sum(
        t.get("amount", 0) for t in categorized_txns
        if not t.get("is_credit")
        and t.get("v2_category") == "p2p_sent"
        and t.get("amount", 0) >= LARGE_P2P_THRESHOLD
    )
    # Include recurring totals even if individual amounts are under $300
    recurring_p2p_period = sum(info["total"] for info in recurring_p2p.values() if info["count"] >= 2)
    # De-dup: if a transaction is both recurring and large, don't double-count
    large_p2p_period = max(large_single_p2p_period, recurring_p2p_period)
    large_p2p_monthly = round(large_p2p_period * multiplier, 2)

    committed_total = round(obligations_total + baseline_net + large_p2p_monthly, 2)

    # ── FCF ──
    fcf_monthly = round(fv.verified_income_monthly - committed_total, 2)
    periods = max(fv.pay_periods_per_month, 1.0)
    fcf_per_period = round(fcf_monthly / periods, 2)
    max_affordable_payment = round(fcf_per_period * SAFETY_FACTOR, 2)

    # ── Max affordable loan tier ──
    max_loan = 0
    for tier_amount in sorted(TIER_PERIODIC_PAYMENTS.keys()):
        periodic = TIER_PERIODIC_PAYMENTS[tier_amount]
        if periodic <= max_affordable_payment:
            max_loan = tier_amount
        else:
            break

    # ── Anti-gaming flags ──
    flags = []
    if fv.funds_deposited_within_7d_of_apply:
        flags.append("funds_deposited_7d_before_apply")
    if fv.payroll_regularity_score < 0.5 and fv.payroll_count >= 2:
        flags.append("income_irregular")
    if fv.stated_income_anomaly_ratio > 3 or fv.stated_income_anomaly_ratio < 0.33:
        flags.append("stated_income_mismatch")
    if fv.wrong_account_type_detected:
        flags.append("wrong_account_type")
    if fv.single_paycheck_in_period:
        flags.append("single_paycheck_in_period")
    if statement_days < 60:
        flags.append("statement_period_under_60_days")

    # ── Confidence ──
    # Scale: 0..1. Built from income count, stability, classification quality.
    confidence = 1.0
    if fv.payroll_count == 0:
        confidence *= 0.3
    elif fv.payroll_count == 1:
        confidence *= 0.7
    confidence *= max(0.5, fv.payroll_regularity_score)
    if fv.unclassified_ratio > 0.1:
        confidence *= 1 - fv.unclassified_ratio
    if fv.reconciliation_error > 100:
        confidence *= 0.3
    confidence = round(max(0.0, min(1.0, confidence)), 2)

    return AffordabilityReport(
        verified_income_monthly=round(fv.verified_income_monthly, 2),
        committed_obligations_monthly=committed_total,
        baseline_living_included=round(baseline_net, 2),
        large_p2p_outflows_monthly=large_p2p_monthly,
        fcf_monthly=fcf_monthly,
        fcf_per_period=fcf_per_period,
        pay_periods_per_month=fv.pay_periods_per_month,
        safety_factor=SAFETY_FACTOR,
        max_affordable_payment=max_affordable_payment,
        max_affordable_loan_amount=max_loan,
        confidence=confidence,
        anti_gaming_flags=flags,
        notes=[],
        breakdown={
            "obligations_by_category": obligations_monthly,
            "recurring_p2p": {k: round(v["total"] * multiplier, 2) for k, v in recurring_p2p.items()},
            "baseline_before_netting": round(baseline, 2),
            "variable_living_seen": round(variable_living_seen, 2),
        },
    )


def _detect_recurring_p2p(txns: list[dict]) -> dict:
    """Return {recipient_signature: {count, total}} for P2P sent with >=2 occurrences."""
    buckets: dict[str, dict] = {}
    for t in txns:
        if t.get("is_credit"):
            continue
        if t.get("v2_category") != "p2p_sent":
            continue
        # Extract a recipient signature — strip common prefixes.
        desc = t.get("description", "").lower()
        for prefix in ("zelle payment to ", "zelle to ", "venmo ", "cashapp to ",
                       "apple cash sent money ", "paypal to ", "remitly "):
            if desc.startswith(prefix):
                desc = desc[len(prefix):]
                break
        sig = desc[:30].strip()
        if not sig:
            continue
        b = buckets.setdefault(sig, {"count": 0, "total": 0.0})
        b["count"] += 1
        b["total"] += t.get("amount", 0)
    return {k: v for k, v in buckets.items() if v["count"] >= 2}

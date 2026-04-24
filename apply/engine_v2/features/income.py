"""Income-side features."""

from statistics import mean, pstdev


PAY_FREQ_MAP = {
    "Weekly": 4.33,
    "Bi-Weekly": 2.17,
    "Biweekly": 2.17,
    "Semi-Monthly": 2.0,
    "Monthly": 1.0,
    "Twice Monthly": 2.0,
}


def populate(fv, categorized_txns, extracted_meta, application):
    payroll_txns = [t for t in categorized_txns if t.get("v2_category") == "payroll"]
    gig_txns = [t for t in categorized_txns if t.get("v2_category") == "gig_income"]
    govt_txns = [t for t in categorized_txns if t.get("v2_category") == "govt_benefits"]
    child_txns = [t for t in categorized_txns if t.get("v2_category") == "child_support"]
    pension_txns = [t for t in categorized_txns if t.get("v2_category") == "pension"]

    fv.payroll_count = len(payroll_txns)
    fv.payroll_total_period = sum(t["amount"] for t in payroll_txns)
    fv.gig_income_total_period = sum(t["amount"] for t in gig_txns)
    fv.govt_benefits_total_period = sum(t["amount"] for t in govt_txns)
    fv.verified_income_period = (
        fv.payroll_total_period
        + fv.gig_income_total_period
        + fv.govt_benefits_total_period
        + sum(t["amount"] for t in child_txns)
        + sum(t["amount"] for t in pension_txns)
    )

    statement_days = extracted_meta.get("statement_days", 30)
    multiplier = 30.0 / max(statement_days, 1)
    fv.verified_income_monthly = fv.verified_income_period * multiplier

    # Pay periods per month from application.
    pay_freq = (application or {}).get("payFrequency", "Bi-Weekly")
    fv.pay_periods_per_month = PAY_FREQ_MAP.get(pay_freq, 2.17)

    fv.single_paycheck_in_period = fv.payroll_count == 1

    # Payroll regularity — coefficient of variation of paycheck amounts.
    # 1.0 = perfectly stable; 0.0 = wildly variable.
    if fv.payroll_count >= 2:
        amts = [t["amount"] for t in payroll_txns]
        m = mean(amts)
        sd = pstdev(amts)
        cv = (sd / m) if m > 0 else 1.0
        fv.payroll_regularity_score = max(0.0, min(1.0, 1.0 - cv))
    else:
        fv.payroll_regularity_score = 0.5  # unknown with 0-1 paychecks

    # Stated income anomaly ratio.
    # Application.grossPay is typically per-period (semi-monthly/biweekly);
    # convert to monthly using stated pay frequency, then compare to observed.
    stated = (application or {}).get("grossPay", "0")
    try:
        stated_val = float(str(stated).replace(",", "").replace("$", ""))
    except (ValueError, TypeError):
        stated_val = 0.0
    stated_monthly = stated_val * fv.pay_periods_per_month
    if fv.verified_income_monthly > 0 and stated_monthly > 0:
        fv.stated_income_anomaly_ratio = stated_monthly / fv.verified_income_monthly
    else:
        fv.stated_income_anomaly_ratio = 1.0

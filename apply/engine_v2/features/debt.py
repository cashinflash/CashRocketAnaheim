"""Debt and stacking features."""

import re
from datetime import datetime


# Merchants considered "fintech" for unique-app counting purposes.
# Derived from patterns in categorization/entities.json fintech_advance_apps
# plus rules.py FINTECH_REPAYMENT_KEYWORDS.
_FINTECH_NAMES = {
    "earnin": "Earnin", "brigit": "Brigit", "dave": "Dave", "cleo": "Cleo",
    "empower": "Empower/Tilt", "tilt": "Empower/Tilt",
    "moneylion": "MoneyLion", "ml plus": "MoneyLion", "instacash": "MoneyLion",
    "klover": "Klover", "albert": "Albert", "floatme": "FloatMe",
    "b9": "B9", "spotme": "SpotMe", "payactiv": "PayActiv",
    "mypay": "MyPay", "my pay": "MyPay",
    "dailypay": "DailyPay", "gerald": "Gerald", "joingerald": "Gerald",
    "possible": "Possible Finance", "opp loans": "OppLoans", "oppfi": "OppLoans",
    "netcredit": "NetCredit", "net credit": "NetCredit",
    "credit genie": "Credit Genie", "creditgenie": "Credit Genie",
    "cg connect": "Credit Genie", "cg auth": "Credit Genie",
    "atm.com": "ATM.com", "atm_com": "ATM.com", "atm-com": "ATM.com",
    "grant": "Grant", "oasiscre": "Grant",
    "advance america": "Advance America",
    "sunshine loan": "Sunshine Loans", "sunshineloan": "Sunshine Loans",
    "klarna": "Klarna", "afterpay": "Afterpay", "affirm": "Affirm",
    "upstart": "Upstart", "cross river bank": "Upstart",
    "bright money": "Bright Money",
    "varo": "Varo",
    "la-finance": "LA-Finance", "atlasfinancial": "Atlas Financial",
    "atlas financial": "Atlas Financial",
    "together loans": "Together Loans", "snap finance": "Snap Finance",
    "snaploan": "Snap Finance",
}


# Pre-compile word-boundary patterns once. Naive substring matching caused
# false positives like "b9" matching the transaction-id suffix "usb9cwhrvdcy"
# on a Zelle to a person named Shelly Romo. Requiring \b on both sides means
# "b9" only matches when it stands alone as a token.
_FINTECH_REGEX = [
    (re.compile(r"\b" + re.escape(pat) + r"\b", re.IGNORECASE), canonical)
    for pat, canonical in _FINTECH_NAMES.items()
]


def _detected_fintech_names(txns):
    seen = set()
    for t in txns:
        desc = t.get("description", "")
        for rx, canonical in _FINTECH_REGEX:
            if rx.search(desc):
                seen.add(canonical)
                break
    return seen


def populate(fv, categorized_txns, extracted_meta, application):
    fintech_names = _detected_fintech_names(categorized_txns)
    fv.fintech_unique_count = len(fintech_names)
    fv.fintech_apps_list = sorted(fintech_names)

    fv.fintech_advance_total_period = sum(
        t["amount"] for t in categorized_txns if t.get("v2_category") == "fintech_advance"
    )
    fv.fintech_repayment_total_period = sum(
        t["amount"] for t in categorized_txns if t.get("v2_category") == "fintech_repayment"
    )
    fv.loan_payment_total_period = sum(
        t["amount"] for t in categorized_txns if t.get("v2_category") in ("loan_payment", "loan_payment_cif")
    )
    fv.bnpl_payment_total_period = sum(
        t["amount"] for t in categorized_txns if t.get("v2_category") == "bnpl_payment"
    )

    # Active loan count: unique "lender-like" patterns seen on the debit side
    loan_sigs = set()
    for t in categorized_txns:
        if t.get("v2_category") in ("loan_payment", "fintech_repayment", "bnpl_payment"):
            desc = t.get("description", "")
            matched = False
            for rx, canonical in _FINTECH_REGEX:
                if rx.search(desc):
                    loan_sigs.add(canonical)
                    matched = True
                    break
            if not matched:
                # Not in fintech map; treat first 20 chars as a signature
                loan_sigs.add(desc.lower()[:20])
    fv.active_loan_count = len(loan_sigs)

    # Fresh loan within 14 days of application submission
    submitted_at = (application or {}).get("submittedAt", "")
    apply_date = _parse_iso_date(submitted_at)
    if apply_date:
        fresh = 0
        for t in categorized_txns:
            if t.get("v2_category") == "loan_proceeds":
                txn_date = _parse_iso_date(t.get("date", ""))
                if txn_date and 0 <= (apply_date - txn_date).days <= 14:
                    fresh += 1
        fv.fresh_loan_within_14d = fresh

    # DTI: monthly debt obligations / monthly income
    statement_days = extracted_meta.get("statement_days", 30)
    multiplier = 30.0 / max(statement_days, 1)
    monthly_debt = (
        fv.loan_payment_total_period
        + fv.fintech_repayment_total_period
        + fv.bnpl_payment_total_period
    ) * multiplier
    if fv.verified_income_monthly > 0:
        fv.dti = round(monthly_debt / fv.verified_income_monthly * 100, 2)
    else:
        fv.dti = 999.0


def _parse_iso_date(s: str):
    if not s:
        return None
    try:
        s = s.split("T")[0].split(" ")[0]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None

"""Balance and stability features — the floor of 'can they absorb a small shock'."""


def populate(fv, categorized_txns, extracted_meta, application):
    fv.ending_balance = float(extracted_meta.get("ending_balance", 0) or 0)
    fv.avg_daily_balance = float(extracted_meta.get("avg_daily_balance", 0) or 0)
    fv.negative_days = int(extracted_meta.get("negative_days", 0) or 0)
    fv.nsf_count = int(extracted_meta.get("nsf_count", 0) or 0)

    # Trough balance: if not directly provided, approximate as
    # min(avg_daily, ending). Real extractor should provide it.
    trough = extracted_meta.get("trough_balance")
    if trough is not None:
        fv.trough_balance = float(trough)
    else:
        fv.trough_balance = min(fv.avg_daily_balance, fv.ending_balance)

    # Bounced/returned payments detection: fee transactions with 'overdraft'
    # or 'returned' description count as bounced events.
    fv.bounced_payment_count = sum(
        1 for t in categorized_txns
        if t.get("v2_category") == "fee"
        and any(k in t.get("description", "").lower()
                for k in ("overdraft", "returned", "nsf"))
    )

    # Account velocity: real outflows / real inflows (excluding transfers).
    # Matches v1 logic so the feature is comparable in shadow mode.
    VELOCITY_EXCLUDE_CREDITS = {
        "internal_transfer", "p2p_received", "fintech_advance",
        "loan_proceeds", "loan_proceeds_cif", "account_verification",
        "cash_deposit", "unclassified",
    }
    VELOCITY_EXCLUDE_DEBITS = {
        "internal_transfer", "p2p_sent", "fintech_repayment", "fee",
        "account_verification", "unclassified",
    }
    real_inflows = sum(
        t["amount"] for t in categorized_txns
        if t.get("is_credit") and t.get("v2_category", "") not in VELOCITY_EXCLUDE_CREDITS
    )
    real_outflows = sum(
        t["amount"] for t in categorized_txns
        if not t.get("is_credit") and t.get("v2_category", "") not in VELOCITY_EXCLUDE_DEBITS
    )
    if real_inflows > 0:
        fv.account_velocity = round(real_outflows / real_inflows * 100, 1)
    else:
        fv.account_velocity = 0.0

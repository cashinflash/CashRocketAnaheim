"""Layer 3 — feature computation. Pure functions over categorized transactions.

Public API:
    compute_features(categorized_txns, extracted_meta, application) -> FeatureVector

Each sub-module (income.py, debt.py, risk.py, stability.py) owns a slice
of the feature set and is testable in isolation.
"""

from dataclasses import dataclass, field

from . import income as _income
from . import debt as _debt
from . import risk as _risk
from . import stability as _stability


@dataclass
class FeatureVector:
    # Income
    payroll_count: int = 0
    payroll_total_period: float = 0.0
    gig_income_total_period: float = 0.0
    govt_benefits_total_period: float = 0.0
    verified_income_period: float = 0.0
    verified_income_monthly: float = 0.0
    pay_periods_per_month: float = 2.0
    single_paycheck_in_period: bool = False
    payroll_regularity_score: float = 1.0  # 0..1, higher = more stable
    stated_income_anomaly_ratio: float = 1.0  # observed monthly / stated monthly

    # Debt & stacking
    fintech_unique_count: int = 0
    fintech_apps_list: list[str] = field(default_factory=list)
    fintech_advance_total_period: float = 0.0
    fintech_repayment_total_period: float = 0.0
    loan_payment_total_period: float = 0.0
    bnpl_payment_total_period: float = 0.0
    active_loan_count: int = 0
    fresh_loan_within_14d: int = 0    # number of loan_proceeds events <= 14 days before apply
    dti: float = 0.0                   # debt obligations as % of income

    # Risk signals
    same_day_cif_rollover: bool = False
    cif_prior_repay_30d: bool = False
    fresh_advance_within_7d: bool = False
    p2p_self_transfer_ratio: float = 0.0
    wrong_account_type_detected: bool = False
    cash_velocity_ratio: float = 0.0
    funds_deposited_within_7d_of_apply: bool = False
    # Max ratio (over all verified-income deposits) of cash withdrawn on the
    # same calendar day as the deposit. Janine-Pierce pattern: $1,779 SS
    # deposit → $1,185 ATM/cash withdrawn same day = 0.67. High values flag
    # cash-dependent or gaming behaviour.
    same_day_cashout_ratio: float = 0.0
    # True when every credit on the connected account(s) was classified as
    # internal_transfer (e.g., "Chime transfer", "Moved from Chime"). Signals
    # the applicant connected a secondary account that only receives money
    # from their primary — the primary (where payroll lands) wasn't linked.
    # Janine-Pierce-adjacent pattern; Jairo-Canas exact pattern.
    income_only_self_transfers: bool = False

    # Stability
    ending_balance: float = 0.0
    avg_daily_balance: float = 0.0
    trough_balance: float = 0.0
    negative_days: int = 0
    nsf_count: int = 0
    bounced_payment_count: int = 0
    account_velocity: float = 0.0      # outflows/inflows excluding transfers

    # Data quality
    reconciliation_error: float = 0.0
    unclassified_count: int = 0
    unclassified_ratio: float = 0.0
    statement_days: int = 30


def compute_features(categorized_txns: list[dict], extracted_meta: dict, application: dict) -> FeatureVector:
    """Compute all features. Pure function — same inputs, same output, always."""
    fv = FeatureVector()

    _income.populate(fv, categorized_txns, extracted_meta, application)
    _debt.populate(fv, categorized_txns, extracted_meta, application)
    _risk.populate(fv, categorized_txns, extracted_meta, application)
    _stability.populate(fv, categorized_txns, extracted_meta, application)

    # Data quality
    fv.statement_days = extracted_meta.get("statement_days", 30)
    total = len(categorized_txns)
    unclassified = sum(1 for t in categorized_txns if t.get("v2_category") == "unclassified")
    fv.unclassified_count = unclassified
    fv.unclassified_ratio = (unclassified / total) if total > 0 else 0.0

    return fv

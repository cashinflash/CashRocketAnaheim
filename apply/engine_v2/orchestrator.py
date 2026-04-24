"""engine_v2.run_v2 — the top-level entry point.

Takes the same inputs as the v1 engine (extracted_data + application_data)
and produces a v2 decision matching v1's output shape closely enough that
the existing dashboard can render it.

Pipeline:
    Layer 1  reconcile(txns, opening, closing)
    Layer 2  classify_credit / classify_debit (pure, sign-guarded)
    Layer 3  compute_features(txns, meta, application)
    Layer 3.5 compute_affordability(txns, features, meta, application)
    Layer 4  policy.evaluate(features, affordability)

Output: V2Result dataclass with every intermediate step available for audit.
"""

from dataclasses import dataclass, asdict, field

from .extraction.reconciliation import reconcile, ReconciliationResult
from .categorization.rules import classify_credit, classify_debit
from .features import compute_features, FeatureVector
from .affordability.calculator import compute_affordability, AffordabilityReport
from .policy.engine import evaluate, Decision


def _reclassify_self_p2p(categorized: list[dict], application: dict) -> None:
    """Flip p2p_sent / p2p_received to internal_transfer when the description
    contains the applicant's own name. Mutates categorized list in place."""
    first = (application.get("firstName") or "").strip().upper()
    last = (application.get("lastName") or "").strip().upper()
    if not first or not last or len(first) < 2 or len(last) < 2:
        return
    for t in categorized:
        if t.get("v2_category") not in ("p2p_sent", "p2p_received"):
            continue
        desc_upper = (t.get("description") or "").upper()
        if first in desc_upper and last in desc_upper:
            t["v2_category"] = "internal_transfer"
            t["v2_rule"] = (t.get("v2_rule") or "") + "+self_name_match"


@dataclass
class V2Result:
    engine_version: str
    reconciliation: ReconciliationResult
    categorized_transactions: list[dict]
    features: FeatureVector
    affordability: AffordabilityReport
    decision: Decision
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "engine_version": self.engine_version,
            "reconciliation": asdict(self.reconciliation),
            "categorized_transactions": self.categorized_transactions,
            "features": self.features.__dict__,
            "affordability": asdict(self.affordability),
            "decision": asdict(self.decision),
            "summary": self.summary,
        }


def run_v2(extracted_data: dict, application: dict | None = None) -> V2Result:
    application = application or {}
    transactions = list(extracted_data.get("transactions") or [])

    # ── Layer 1 — reconciliation gate ──
    opening = float(extracted_data.get("beginning_balance") or 0)
    closing = float(extracted_data.get("ending_balance") or 0)
    recon = reconcile(transactions, opening, closing, tolerance=100.0)

    # ── Layer 2 — categorization (sign-guarded, no AI) ──
    categorized = []
    for t in transactions:
        t2 = dict(t)  # shallow copy; don't mutate caller data
        desc = t2.get("description", "")
        amt = float(t2.get("amount", 0) or 0)
        if t2.get("is_credit"):
            cat, rule = classify_credit(desc, amt, t2)
        else:
            cat, rule = classify_debit(desc, amt, t2)
        t2["v2_category"] = cat
        t2["v2_rule"] = rule
        categorized.append(t2)

    # ── Layer 2.5 — self-P2P detection ──
    # A P2P transfer whose description contains the applicant's own name is
    # an internal transfer (Zelle to self, Venmo to self, etc.), not a
    # true P2P to another party. Underwriters kept confirming these manually.
    _reclassify_self_p2p(categorized, application)

    # ── Layer 3 — features ──
    features = compute_features(categorized, extracted_data, application)
    features.reconciliation_error = recon.error

    # ── Layer 3.5 — affordability ──
    affordability = compute_affordability(categorized, features, extracted_data, application)

    # ── Layer 4 — policy ──
    decision = evaluate(features, affordability, application=application)

    # Auto-decide candidate: the engine is confident enough to one-click approve.
    # Informational today; gating comes later once Vergent outcome data confirms.
    AUTO_DECIDE_THRESHOLD = 0.80
    auto_decide_candidate = (
        decision.outcome == "approve"
        and affordability.confidence >= AUTO_DECIDE_THRESHOLD
        and not decision.review_flags
        and recon.ok
    )

    # ── Summary (flat view matching v1's core fields) ──
    summary = {
        "decision": "APPROVED" if decision.outcome == "approve" else decision.outcome.upper(),
        "tier_amount": decision.tier_amount,
        "auto_decide_candidate": auto_decide_candidate,
        "auto_decide_threshold": AUTO_DECIDE_THRESHOLD,
        "max_affordable_loan": affordability.max_affordable_loan_amount,
        "verified_income_monthly": affordability.verified_income_monthly,
        "committed_obligations_monthly": affordability.committed_obligations_monthly,
        "fcf_monthly": affordability.fcf_monthly,
        "fcf_per_period": affordability.fcf_per_period,
        "pay_periods_per_month": affordability.pay_periods_per_month,
        "confidence": affordability.confidence,
        "reasons": decision.reasons,
        "review_flags": decision.review_flags,
        "applied_adjustments": decision.applied_adjustments,
        "anti_gaming_flags": affordability.anti_gaming_flags,
        "reconciliation_ok": recon.ok,
        "reconciliation_error": recon.error,
        "fintech_unique_count": features.fintech_unique_count,
        "fintech_apps_list": features.fintech_apps_list,
        "nsf_count": features.nsf_count,
        "negative_days": features.negative_days,
        "ending_balance": features.ending_balance,
        "avg_daily_balance": features.avg_daily_balance,
        "dti": features.dti,
        "statement_days": features.statement_days,
        "unclassified_count": features.unclassified_count,
    }

    return V2Result(
        engine_version="v2-0.1.0",
        reconciliation=recon,
        categorized_transactions=categorized,
        features=features,
        affordability=affordability,
        decision=decision,
        summary=summary,
    )

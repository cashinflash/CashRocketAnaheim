"""HTML report renderer for v2.

Produces an HTML fragment that fits the existing dashboard modal styling
(`.report-card`, `.mrhtml`). Not a full page — just the report body.

Focus: affordability-first presentation. The engine output is a number
(max affordable loan) plus supporting evidence. Reasons are actionable.
"""

from html import escape


_DECISION_COLORS = {
    "approve": "#1a6b3c",
    "decline": "#c0392b",
    "review_required": "#f39c12",
}


def render(v2_result, applicant_info: dict | None = None) -> str:
    """Return an HTML string for embedding in the dashboard modal."""
    applicant_info = applicant_info or {}
    d = v2_result.decision
    a = v2_result.affordability
    f = v2_result.features
    r = v2_result.reconciliation
    summary = v2_result.summary

    color = _DECISION_COLORS.get(d.outcome, "#333")
    outcome_label = {
        "approve": "APPROVED",
        "decline": "DECLINED",
        "review_required": "REVIEW REQUIRED",
    }.get(d.outcome, d.outcome.upper())

    parts = [_header(outcome_label, color, d, a, applicant_info, summary)]
    parts.append(_reconciliation_card(r))
    parts.append(_affordability_card(a, f))
    parts.append(_decision_card(d, a))
    parts.append(_risk_signals_card(f, a))
    parts.append(_debt_stacking_card(f))
    parts.append(_stability_card(f))
    parts.append(_transaction_audit_card(v2_result.categorized_transactions))
    parts.append(_footer())

    return "\n".join(parts)


def _header(label: str, color: str, d, a, applicant: dict, summary: dict) -> str:
    name = escape(applicant.get("firstName", "") + " " + applicant.get("lastName", "")).strip()
    name = name or "—"
    if summary.get("auto_decide_candidate"):
        badge = (
            '<div style="display:inline-block;margin-top:6px;padding:3px 10px;'
            'border-radius:12px;background:#e6f4ea;color:#1a6b3c;'
            'font-size:11px;font-weight:600;letter-spacing:0.3px">'
            '✅ AUTO-DECIDE CANDIDATE</div>'
        )
    else:
        badge = (
            '<div style="display:inline-block;margin-top:6px;padding:3px 10px;'
            'border-radius:12px;background:#fff4e0;color:#a15c00;'
            'font-size:11px;font-weight:600;letter-spacing:0.3px">'
            '👀 REVIEW REQUIRED</div>'
        )
    return f"""
<div class="report-card" style="border-left:4px solid {color};padding-left:16px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div>
      <div style="font-size:13px;color:#888;text-transform:uppercase;letter-spacing:1px">engine v2 decision</div>
      <div style="font-size:28px;font-weight:700;color:{color}">{label}</div>
      <div style="font-size:14px;color:#555;margin-top:4px">{name}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:12px;color:#888">max affordable loan</div>
      <div style="font-size:32px;font-weight:700;color:#1a6b3c">${d.tier_amount}</div>
      <div style="font-size:11px;color:#888">engine would offer (confidence {a.confidence:.0%})</div>
      {badge}
    </div>
  </div>
</div>
"""


def _reconciliation_card(r) -> str:
    if r.ok:
        return f"""
<div class="report-card">
  <h3 style="margin:0 0 4px">✓ Reconciliation passed</h3>
  <div style="font-size:12px;color:#666">
    Expected closing ${r.expected_closing:,.2f} vs actual ${r.actual_closing:,.2f} — within ${r.tolerance:,.2f} tolerance.
  </div>
</div>
"""
    return f"""
<div class="report-card" style="background:#fff4e6;border-left:4px solid #e74c3c">
  <h3 style="margin:0 0 4px;color:#c0392b">⚠ Reconciliation failed — data may be unreliable</h3>
  <div style="font-size:13px;color:#333">
    Expected closing ${r.expected_closing:,.2f} vs actual ${r.actual_closing:,.2f}.
    Mismatch: <b>${r.error:,.2f}</b> (tolerance ${r.tolerance:,.2f}).
  </div>
  <div style="font-size:12px;color:#666;margin-top:6px">
    Likely cause: one or more transactions extracted with wrong is_credit flag,
    or transactions missing from the statement. Decision is provisional until resolved.
  </div>
</div>
"""


def _affordability_card(a, f) -> str:
    rows = []
    for cat, amt in sorted(a.breakdown.get("obligations_by_category", {}).items(), key=lambda x: -x[1]):
        if amt <= 0:
            continue
        rows.append(
            f"<tr><td style='padding:2px 8px'>{escape(cat)}</td>"
            f"<td style='text-align:right;padding:2px 8px'>${amt:,.2f}</td></tr>"
        )
    recurring_p2p = a.breakdown.get("recurring_p2p", {})
    for sig, amt in sorted(recurring_p2p.items(), key=lambda x: -x[1])[:5]:
        rows.append(
            f"<tr><td style='padding:2px 8px;color:#888'>└ recurring to {escape(sig)}</td>"
            f"<td style='text-align:right;padding:2px 8px;color:#888'>${amt:,.2f}</td></tr>"
        )
    rows.append(
        f"<tr><td style='padding:2px 8px;font-style:italic;color:#666'>+ baseline living (floor)</td>"
        f"<td style='text-align:right;padding:2px 8px;color:#666'>${a.baseline_living_included:,.2f}</td></tr>"
    )

    return f"""
<div class="report-card">
  <h3 style="margin:0 0 8px">Affordability</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="border-bottom:1px solid #eee">
      <td style="padding:6px 8px;font-weight:600">Verified monthly income</td>
      <td style="text-align:right;padding:6px 8px;font-weight:600;color:#1a6b3c">${a.verified_income_monthly:,.2f}</td>
    </tr>
    <tr><td colspan="2" style="padding:6px 8px;color:#888;font-size:11px;text-transform:uppercase">committed obligations</td></tr>
    {''.join(rows)}
    <tr style="border-top:1px solid #eee">
      <td style="padding:6px 8px;font-weight:600">Total obligations</td>
      <td style="text-align:right;padding:6px 8px;font-weight:600;color:#c0392b">−${a.committed_obligations_monthly:,.2f}</td>
    </tr>
    <tr style="background:#f8f8f8">
      <td style="padding:6px 8px;font-weight:700">Free cash flow (monthly)</td>
      <td style="text-align:right;padding:6px 8px;font-weight:700">${a.fcf_monthly:,.2f}</td>
    </tr>
    <tr>
      <td style="padding:6px 8px">÷ pay periods per month ({a.pay_periods_per_month})</td>
      <td style="text-align:right;padding:6px 8px">${a.fcf_per_period:,.2f}/period</td>
    </tr>
    <tr>
      <td style="padding:6px 8px">× safety factor {a.safety_factor}</td>
      <td style="text-align:right;padding:6px 8px;font-weight:600">${a.max_affordable_payment:,.2f}/period</td>
    </tr>
    <tr style="background:#eef9f1">
      <td style="padding:6px 8px;font-weight:700">Max affordable loan</td>
      <td style="text-align:right;padding:6px 8px;font-weight:700;color:#1a6b3c">${a.max_affordable_loan_amount}</td>
    </tr>
  </table>
</div>
"""


def _decision_card(d, a) -> str:
    reasons_html = ""
    if d.reasons:
        items = "".join(f"<li style='margin-bottom:4px'>{escape(r)}</li>" for r in d.reasons)
        reasons_html = f"""
<div style="background:#fff4f0;padding:8px 12px;border-left:3px solid #c0392b;margin-top:8px">
  <div style="font-size:11px;color:#c0392b;text-transform:uppercase;font-weight:600">decline reasons</div>
  <ul style="margin:4px 0 0 16px;padding:0">{items}</ul>
</div>
"""

    adj_html = ""
    if d.applied_adjustments:
        items = "".join(f"<li style='margin-bottom:4px'>{escape(a)}</li>" for a in d.applied_adjustments)
        adj_html = f"""
<div style="background:#fffbea;padding:8px 12px;border-left:3px solid #f39c12;margin-top:8px">
  <div style="font-size:11px;color:#b07500;text-transform:uppercase;font-weight:600">applied adjustments</div>
  <ul style="margin:4px 0 0 16px;padding:0">{items}</ul>
</div>
"""

    flags_html = ""
    if d.review_flags:
        items = "".join(f"<span style='display:inline-block;background:#eef;padding:2px 8px;border-radius:12px;margin:2px;font-size:11px'>{escape(f)}</span>" for f in d.review_flags)
        flags_html = f"""
<div style="margin-top:8px">
  <div style="font-size:11px;color:#666;text-transform:uppercase;font-weight:600">review flags</div>
  <div style="margin-top:4px">{items}</div>
</div>
"""

    return f"""
<div class="report-card">
  <h3 style="margin:0 0 8px">Decision</h3>
  <div style="display:flex;gap:16px;font-size:13px">
    <div><span style="color:#888">base tier</span> <b>${d.base_tier_amount}</b></div>
    <div><span style="color:#888">final tier</span> <b>${d.tier_amount}</b></div>
    <div><span style="color:#888">confidence</span> <b>{a.confidence:.0%}</b></div>
  </div>
  {reasons_html}
  {adj_html}
  {flags_html}
</div>
"""


def _risk_signals_card(f, a) -> str:
    lines = []
    if f.same_day_cif_rollover:
        lines.append("⚠ <b>Same-day CIF rollover</b>: prior CIF repayment + fresh advance within 7 days")
    if f.wrong_account_type_detected:
        lines.append("⚠ <b>Account type mismatch</b>: stated checking but transaction shape suggests savings")
    if f.fresh_loan_within_14d:
        lines.append(f"⚠ <b>Fresh loan disbursement(s)</b>: {f.fresh_loan_within_14d} within 14 days of apply")
    if f.fintech_unique_count >= 5:
        lines.append(f"⚠ <b>Severe fintech stacking</b>: {f.fintech_unique_count} unique apps")
    elif f.fintech_unique_count >= 3:
        lines.append(f"⚠ <b>Moderate fintech stacking</b>: {f.fintech_unique_count} unique apps")
    if f.funds_deposited_within_7d_of_apply:
        lines.append("⚠ <b>Funds deposited &lt;7 days before apply</b>: possible cherry-picked timing")
    if f.stated_income_anomaly_ratio > 3:
        lines.append(f"⚠ <b>Stated income anomaly</b>: stated is {f.stated_income_anomaly_ratio:.1f}× observed")
    if not lines:
        lines.append("<span style='color:#888'>No risk signals detected.</span>")
    return f"""
<div class="report-card">
  <h3 style="margin:0 0 8px">Risk signals</h3>
  <ul style="margin:0;padding-left:16px;font-size:13px">
    {''.join(f'<li style="margin-bottom:4px">{line}</li>' for line in lines)}
  </ul>
</div>
"""


def _debt_stacking_card(f) -> str:
    apps = ", ".join(escape(a) for a in f.fintech_apps_list) if f.fintech_apps_list else "—"
    return f"""
<div class="report-card">
  <h3 style="margin:0 0 8px">Debt & stacking</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr><td style="padding:3px 8px">Fintech apps (unique)</td><td style="text-align:right;padding:3px 8px"><b>{f.fintech_unique_count}</b></td></tr>
    <tr><td style="padding:3px 8px;color:#888;font-size:11px" colspan="2">{apps}</td></tr>
    <tr><td style="padding:3px 8px">DTI</td><td style="text-align:right;padding:3px 8px"><b>{f.dti:.1f}%</b></td></tr>
    <tr><td style="padding:3px 8px">Active loan count</td><td style="text-align:right;padding:3px 8px"><b>{f.active_loan_count}</b></td></tr>
    <tr><td style="padding:3px 8px">Fresh loans within 14d</td><td style="text-align:right;padding:3px 8px"><b>{f.fresh_loan_within_14d}</b></td></tr>
  </table>
</div>
"""


def _stability_card(f) -> str:
    neg_color = "#c0392b" if f.negative_days >= 3 else "#333"
    bal_color = "#c0392b" if f.ending_balance < 50 else "#333"
    return f"""
<div class="report-card">
  <h3 style="margin:0 0 8px">Stability</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr><td style="padding:3px 8px">NSF count</td><td style="text-align:right;padding:3px 8px;color:{'#c0392b' if f.nsf_count > 0 else '#333'}"><b>{f.nsf_count}</b></td></tr>
    <tr><td style="padding:3px 8px">Negative days</td><td style="text-align:right;padding:3px 8px;color:{neg_color}"><b>{f.negative_days}</b> of {f.statement_days}</td></tr>
    <tr><td style="padding:3px 8px">Ending balance</td><td style="text-align:right;padding:3px 8px;color:{bal_color}"><b>${f.ending_balance:,.2f}</b></td></tr>
    <tr><td style="padding:3px 8px">Avg daily balance</td><td style="text-align:right;padding:3px 8px"><b>${f.avg_daily_balance:,.2f}</b></td></tr>
    <tr><td style="padding:3px 8px">Account velocity</td><td style="text-align:right;padding:3px 8px"><b>{f.account_velocity:.0f}%</b></td></tr>
    <tr><td style="padding:3px 8px">Bounced payments</td><td style="text-align:right;padding:3px 8px"><b>{f.bounced_payment_count}</b></td></tr>
  </table>
</div>
"""


def _transaction_audit_card(categorized_txns: list[dict]) -> str:
    # Group by v2_category, count & sum
    groups: dict[str, dict] = {}
    for t in categorized_txns:
        cat = t.get("v2_category", "unclassified")
        g = groups.setdefault(cat, {"count": 0, "credits": 0.0, "debits": 0.0, "rules": set()})
        g["count"] += 1
        g["rules"].add(t.get("v2_rule", ""))
        if t.get("is_credit"):
            g["credits"] += t.get("amount", 0)
        else:
            g["debits"] += t.get("amount", 0)

    rows = []
    for cat, g in sorted(groups.items()):
        net = g["credits"] - g["debits"]
        net_str = f"+${net:,.2f}" if net > 0 else f"−${abs(net):,.2f}"
        rows.append(
            f"<tr>"
            f"<td style='padding:3px 8px'>{escape(cat)}</td>"
            f"<td style='text-align:right;padding:3px 8px'>{g['count']}</td>"
            f"<td style='text-align:right;padding:3px 8px'>{net_str}</td>"
            f"<td style='padding:3px 8px;color:#888;font-size:11px'>{', '.join(sorted(g['rules']))[:60]}</td>"
            f"</tr>"
        )

    return f"""
<div class="report-card">
  <h3 style="margin:0 0 8px">Classification audit</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr style="background:#f8f8f8">
      <th style="text-align:left;padding:4px 8px">category</th>
      <th style="text-align:right;padding:4px 8px">count</th>
      <th style="text-align:right;padding:4px 8px">net</th>
      <th style="text-align:left;padding:4px 8px">rule(s)</th>
    </tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""


def _footer() -> str:
    return """
<p style="font-size:11px;color:#aaa;margin-top:12px;text-align:center">
  Engine v2 — deterministic, 4-layer pipeline. Running in shadow mode. No AI in the decision path.
</p>
"""

"""Plaid-sourced extraction. Preferred path; bypasses AI entirely.

Converts Plaid asset report JSON into NormalizedTransaction[]. Plaid already
provides merchant names, categories, and pending flags — we pass those through
as hints for Layer 2 but do not treat them as authoritative.
"""

# TODO: implement extract_from_plaid_asset_report(plaid_json) -> list[dict]

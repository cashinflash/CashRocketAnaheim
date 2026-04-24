"""PDF-sourced extraction using Claude (fallback for applicants without Plaid).

This is the ONLY place in v2 where the AI runs. Output is ALWAYS passed
through reconciliation.reconcile() before Layer 2 consumes it. Jorge's
LA-Finance sign bug happened here (is_credit flipped); reconciliation would
have caught it.
"""

# TODO: port the Claude prompt from server.py, add sign-direction cross-checks
# using opening/closing balance math as a proof gate.

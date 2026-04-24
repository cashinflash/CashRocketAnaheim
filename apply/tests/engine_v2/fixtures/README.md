# Case fixtures

Per-case ground truth for regression testing. Each fixture is:

```
<case_id>/
  input.json      # normalized transactions + applicant metadata (redacted)
  expected.json   # per-transaction category, per-category totals,
                  # affordability numbers, decision outcome
```

## Rules

1. **PII redaction required before commit**. Strip SSN, DOB, full name,
   email, phone, address, routing/account numbers. Keep transaction
   descriptions (they're needed for categorization).
2. **Ground truth**: `expected.json` is hand-validated, not engine output.
3. **Invariants**: every fixture must satisfy
   - all `loan_payment` items are debits
   - all `payroll` items are credits
   - `opening + Σcredits − Σdebits == closing ± $50`

## Cases to populate (Phase 4)

- `jorge_monroy/`    — sign bug + overdraft pattern. Decline.
- `michelle_anderson/` — wrong account + fresh Upstart loan. Decline.
- `danitza_olmedo/`  — CIF rollover + 9-app stacking. Decline.
- `sherrie_craig/`   — wrong account + 9-app stacking + near-zero balance. Decline.

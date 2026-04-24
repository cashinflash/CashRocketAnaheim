# engine_v2 — CashInFlash deterministic underwriting engine

See `/root/.claude/plans/look-over-my-project-frolicking-tower.md` for the full
plan, case audits, and formula derivations.

## Four deterministic layers + a feedback loop

```
NormalizedTransaction[]          <-- Layer 1  extraction/
        |
        v
CategorizedTransaction[]         <-- Layer 2  categorization/
        |
        v
FeatureVector                    <-- Layer 3  features/
        |
        v
AffordabilityReport              <-- Layer 3.5  affordability/
        |
        v
Decision                         <-- Layer 4  policy/  (YAML rules)
```

Principles:
- AI appears only in `extraction/pdf_claude.py` and its output must pass
  `extraction/reconciliation.py` before Layer 2 consumes it.
- Categorization is pure rules via merchant registry + sign-guarded regex.
  No silent defaults; unmatched items surface to the underwriter.
- Features are pure functions with snapshot tests.
- Policy is data (YAML), not code.

## Running in parallel with v1

`harness/parallel_runner.py` runs both engines on the same input and diffs the
outputs for shadow-mode validation. Cut over once v2 matches all fixtures and
beats v1 on the Jorge / Michelle / Danitza / Sherrie flagged issues.

## Status

Scaffold only. Layers 2, 3, 3.5, 4 have stub interfaces. Layer 1 reconciliation
gate is the next module to flesh out.

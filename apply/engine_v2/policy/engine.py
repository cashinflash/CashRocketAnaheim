"""YAML-driven policy evaluator.

Takes a FeatureVector + AffordabilityReport and emits a Decision.

The YAML policy file uses a tiny expression grammar:
    feature_name OPERATOR number
    feature_name == "string"
    expr AND expr
    expr OR expr

Supported operators: == != < <= > >=
Supported keywords: AND OR (case-insensitive)

We sandboxed-eval against a whitelisted dict — no arbitrary Python.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Decision:
    outcome: str  # "approve" | "decline" | "review_required"
    tier_amount: int
    base_tier_amount: int
    reasons: list[str] = field(default_factory=list)
    applied_adjustments: list[str] = field(default_factory=list)
    review_flags: list[str] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)


def evaluate(
    features,
    affordability,
    policy_path: str | Path | None = None,
    application: dict | None = None,
) -> Decision:
    if policy_path is None:
        policy_path = Path(__file__).parent / "standard.yaml"
    policy = _load_yaml(Path(policy_path))

    # Build context dict for expression evaluation
    ctx = _build_context(features, affordability, application or {})

    # Start with max_affordable as base, clamped to CIF tiers.
    base_tier = affordability.max_affordable_loan_amount
    current_tier = base_tier
    applied_adjustments = []
    review_flags = []
    audit = []

    # ── Hard declines first ──
    decline_reasons = []
    for rule in policy.get("hard_declines", []):
        try:
            matches = _eval_expr(rule["when"], ctx)
        except Exception as e:
            matches = False
            audit.append({"rule": rule["id"], "error": str(e)})
        audit.append({"rule": rule["id"], "kind": "hard_decline", "matched": matches})
        if matches:
            decline_reasons.append(rule["reason"])

    if decline_reasons:
        return Decision(
            outcome="decline",
            tier_amount=0,
            base_tier_amount=base_tier,
            reasons=decline_reasons,
            applied_adjustments=applied_adjustments,
            review_flags=review_flags,
            audit=audit,
        )

    # ── Soft adjustments ──
    for rule in policy.get("soft_adjustments", []):
        try:
            matches = _eval_expr(rule["when"], ctx)
        except Exception:
            matches = False
        audit.append({"rule": rule["id"], "kind": "soft_adjustment", "matched": matches})
        if not matches:
            continue
        effect = rule.get("effect", "")
        if effect == "drop_1_tier":
            current_tier = _drop_tier(current_tier, 1)
            applied_adjustments.append(f"{rule['id']}: drop 1 tier -> ${current_tier}")
        elif effect == "drop_2_tiers":
            current_tier = _drop_tier(current_tier, 2)
            applied_adjustments.append(f"{rule['id']}: drop 2 tiers -> ${current_tier}")
        elif effect == "flag_for_review":
            review_flags.append(rule["id"])
        elif effect.startswith("cap_at_"):
            cap = int(effect.replace("cap_at_", ""))
            if current_tier > cap:
                current_tier = cap
                applied_adjustments.append(f"{rule['id']}: cap at ${cap}")

    # Carry affordability confidence into review_flags if low
    if affordability.confidence < 0.6:
        review_flags.append("low_confidence")

    # Carry anti-gaming flags forward
    for flag in affordability.anti_gaming_flags:
        review_flags.append(flag)

    outcome = "approve" if current_tier > 0 else "decline"
    if outcome == "decline" and not decline_reasons:
        decline_reasons.append(
            f"Max affordable loan is $0 given current cashflow "
            f"(FCF/period ${affordability.fcf_per_period:.2f} × {affordability.safety_factor} safety)"
        )

    return Decision(
        outcome=outcome,
        tier_amount=current_tier,
        base_tier_amount=base_tier,
        reasons=decline_reasons,
        applied_adjustments=applied_adjustments,
        review_flags=review_flags,
        audit=audit,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_TIER_LADDER = [255, 200, 150, 100, 0]


def _drop_tier(current: int, steps: int) -> int:
    if current not in _TIER_LADDER:
        # Snap up to the nearest tier in the ladder
        for t in _TIER_LADDER:
            if t <= current:
                current = t
                break
        else:
            current = 0
    idx = _TIER_LADDER.index(current)
    new_idx = min(len(_TIER_LADDER) - 1, idx + steps)
    return _TIER_LADDER[new_idx]


def _build_context(features, affordability, application: dict) -> dict:
    """Whitelisted context for expression eval."""
    ctx = {}
    # Feature vector fields
    for k, v in features.__dict__.items():
        ctx[k] = v
    # Affordability fields
    for k, v in affordability.__dict__.items():
        if not isinstance(v, (list, dict)):
            ctx[k] = v
    # Application extras
    ctx["stated_employment"] = application.get("sourceOfIncome", "")
    ctx["loan_amount_requested"] = float(application.get("loanAmount", 0) or 0)
    return ctx


def _load_yaml(path: Path) -> dict:
    """Minimal YAML loader — avoids adding a dependency for the subset we use.
    Supports: top-level lists of dicts with simple scalar values, nested dicts,
    quoted strings. Falls back to PyYAML if available (more tolerant).
    """
    text = path.read_text()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return _parse_minimal_yaml(text)


def _parse_minimal_yaml(text: str) -> dict:
    """Handle the specific shape of standard.yaml without pyyaml."""
    import re as _re
    # This is narrow on purpose — standard.yaml is hand-authored.
    lines = text.splitlines()
    root: dict = {}
    stack = [(0, root)]  # (indent, container)
    current_list_parent = None

    def current_container():
        return stack[-1][1]

    i = 0
    while i < len(lines):
        raw = lines[i]
        # Strip comments
        line = _re.sub(r"(^|\s)#.*$", "", raw).rstrip()
        if not line.strip():
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        # Pop the stack until we find a parent with less indent
        while stack and indent < stack[-1][0]:
            stack.pop()

        stripped = line.strip()

        if stripped.startswith("- "):
            # List item — under the current container (must be a list)
            parent_container = current_container()
            # If the parent is a dict, need to convert its last key to a list
            if isinstance(parent_container, dict) and current_list_parent:
                parent_container = current_list_parent
            item_body = stripped[2:].strip()
            if ":" in item_body and not item_body.startswith("{"):
                k, v = item_body.split(":", 1)
                k = k.strip()
                v = v.strip()
                item = {k: _coerce(v) if v else {}}
                parent_container.append(item)
                # Subsequent keys at higher indent belong to this item
                stack.append((indent + 2, item))
            else:
                parent_container.append(_coerce(item_body))
            i += 1
            continue

        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            container = current_container()
            if value == "":
                # Could be a dict or list; look ahead
                look_ahead = i + 1
                while look_ahead < len(lines):
                    la = lines[look_ahead]
                    la_stripped = _re.sub(r"(^|\s)#.*$", "", la).rstrip()
                    if not la_stripped.strip():
                        look_ahead += 1
                        continue
                    la_indent = len(la_stripped) - len(la_stripped.lstrip())
                    if la_indent <= indent:
                        # Empty container
                        container[key] = {}
                        break
                    if la_stripped.strip().startswith("- "):
                        container[key] = []
                    else:
                        container[key] = {}
                    break
                else:
                    container[key] = {}
                stack.append((indent + 2, container[key]))
                current_list_parent = container[key]
            else:
                container[key] = _coerce(value)
        i += 1

    return root


def _coerce(value: str):
    value = value.strip()
    if value == "":
        return None
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _eval_expr(expr: str, ctx: dict) -> bool:
    """Evaluate a policy condition against a whitelisted context dict.

    Grammar:
        term    := name op value
        value   := number | "string" | 'string' | true | false | name
        expr    := term ( (AND|OR) term )*
        op      := == | != | < | <= | > | >=

    We intentionally do NOT use eval/exec.
    """
    # Split on AND/OR while preserving tokens
    tokens = re.split(r"\s+(AND|OR|and|or)\s+", expr)
    # tokens is [term, 'AND', term, 'OR', term, ...]
    result = _eval_term(tokens[0], ctx)
    for i in range(1, len(tokens), 2):
        op = tokens[i].upper()
        rhs = _eval_term(tokens[i + 1], ctx)
        if op == "AND":
            result = result and rhs
        elif op == "OR":
            result = result or rhs
    return bool(result)


_TERM_RE = re.compile(r"^(?P<name>\w+)\s*(?P<op>==|!=|<=|>=|<|>)\s*(?P<value>.+)$")


def _eval_term(term: str, ctx: dict) -> bool:
    term = term.strip()
    m = _TERM_RE.match(term)
    if not m:
        # Bare boolean feature
        return bool(ctx.get(term, False))
    name = m.group("name")
    op = m.group("op")
    raw_val = m.group("value").strip()
    lhs = ctx.get(name, 0)
    rhs = _coerce(raw_val)
    if isinstance(rhs, str) and rhs in ctx:
        rhs = ctx[rhs]
    try:
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        if op == "<":
            return lhs < rhs
        if op == "<=":
            return lhs <= rhs
        if op == ">":
            return lhs > rhs
        if op == ">=":
            return lhs >= rhs
    except TypeError:
        return False
    return False

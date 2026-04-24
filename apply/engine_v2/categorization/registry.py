"""Merchant registry lookup.

Every merchant has a (credit_category, debit_category) pair. This is what
makes Jorge-style sign bugs structurally impossible: the same description
cannot resolve to a debit category when is_credit=True, because we look up
by direction.

Two-layer registry:
    1. entities.json            — base registry, committed + versioned
    2. entities_overrides.json  — mutable, edited live via the dashboard
                                   "Review Queue". Takes precedence over
                                   the base. Analysts can promote entries
                                   back to entities.json periodically.
"""

import json
import threading
from pathlib import Path
from dataclasses import dataclass

_DIR = Path(__file__).parent
_BASE_PATH = _DIR / "entities.json"
_OVERRIDES_PATH = _DIR / "entities_overrides.json"
_LOCK = threading.Lock()


@dataclass(frozen=True)
class RegistryHit:
    pattern: str
    group: str
    credit_category: str | None
    debit_category: str | None


def _load_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        return {}


def _build_registry() -> list[RegistryHit]:
    """Combine base + overrides. Overrides with the same pattern win."""
    base = _load_file(_BASE_PATH)
    overrides = _load_file(_OVERRIDES_PATH)

    merged: dict[str, tuple[str, dict]] = {}
    for group_name, group in base.items():
        if group_name.startswith("_") or not isinstance(group, dict):
            continue
        for pattern, mapping in group.items():
            if not isinstance(mapping, dict):
                continue
            merged[pattern.upper()] = (group_name, mapping)

    # Overrides shape (flat): { "_meta": {...}, "<pattern>": {"credit": "...", "debit": "...", "added_at": ..., "added_by": ...} }
    if isinstance(overrides, dict):
        for pattern, mapping in overrides.items():
            if pattern.startswith("_") or not isinstance(mapping, dict):
                continue
            merged[pattern.upper()] = ("overrides", mapping)

    hits = [
        RegistryHit(
            pattern=pattern_upper,
            group=group_name,
            credit_category=mapping.get("credit"),
            debit_category=mapping.get("debit"),
        )
        for pattern_upper, (group_name, mapping) in merged.items()
    ]
    # Longest pattern first — specific wins over generic.
    return sorted(hits, key=lambda h: -len(h.pattern))


# Cached registry; reload() invalidates.
_REGISTRY: list[RegistryHit] = _build_registry()


def reload():
    """Rebuild registry after entities_overrides.json changes on disk."""
    global _REGISTRY
    with _LOCK:
        _REGISTRY = _build_registry()


def lookup(description: str, is_credit: bool) -> RegistryHit | None:
    """Find the first registry hit for this description+direction.

    Returns None if no pattern matches, OR if the matched pattern has a null
    category for this direction (meaning: this merchant doesn't legitimately
    send in this direction; caller should treat as unclassified for review).
    """
    desc_upper = description.upper()
    for hit in _REGISTRY:
        if hit.pattern in desc_upper:
            category = hit.credit_category if is_credit else hit.debit_category
            if category is None:
                return None
            return hit
    return None


def category_for(description: str, is_credit: bool) -> str | None:
    hit = lookup(description, is_credit)
    if hit is None:
        return None
    return hit.credit_category if is_credit else hit.debit_category


def add_override(pattern: str, credit: str | None, debit: str | None, added_by: str = "dashboard") -> None:
    """Persist a new mapping to entities_overrides.json and reload."""
    import time
    with _LOCK:
        data = _load_file(_OVERRIDES_PATH)
        if not isinstance(data, dict):
            data = {}
        if "_meta" not in data:
            data["_meta"] = {
                "description": "Live-editable overrides from the Review Queue. Promoted back to entities.json periodically.",
                "created": int(time.time()),
            }
        data[pattern] = {
            "credit": credit,
            "debit": debit,
            "added_at": int(time.time()),
            "added_by": added_by,
        }
        _OVERRIDES_PATH.write_text(json.dumps(data, indent=2))
    reload()


def size() -> int:
    """Total number of patterns in the combined registry."""
    return len(_REGISTRY)

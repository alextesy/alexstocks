"""Utilities for handling ticker alias and equivalence groups."""

from __future__ import annotations

from collections.abc import Iterable

# Canonical ticker symbol -> set of additional symbols that should be treated
# as the same company for analytics purposes. Include only deliberate mergers
# (e.g., Alphabet's GOOG/GOOGL share classes) to avoid accidental grouping.
_MERGED_TICKERS: dict[str, set[str]] = {
    "GOOG": {"GOOGL"},
}

# Precompute lookup tables so canonicalization and expansion are O(1).
_EQUIVALENT_GROUPS: dict[str, set[str]] = {
    canonical: {canonical, *aliases} for canonical, aliases in _MERGED_TICKERS.items()
}
_ALIAS_TO_CANONICAL: dict[str, str] = {
    alias: canonical
    for canonical, aliases in _EQUIVALENT_GROUPS.items()
    for alias in aliases
}


def canonicalize_symbol(symbol: str) -> str:
    """Return the canonical ticker symbol for the provided symbol."""

    clean = symbol.upper().strip()
    if not clean:
        return clean
    return _ALIAS_TO_CANONICAL.get(clean, clean)


def expand_equivalent_symbols(symbol: str) -> set[str]:
    """Return the set of symbols equivalent to the canonical symbol."""

    canonical = canonicalize_symbol(symbol)
    return set(_EQUIVALENT_GROUPS.get(canonical, {canonical}))


def deduplicate_by_canonical(symbols: Iterable[str]) -> list[str]:
    """Deduplicate symbols by their canonical representation preserving order."""

    seen: set[str] = set()
    result: list[str] = []
    for sym in symbols:
        canonical = canonicalize_symbol(sym)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result

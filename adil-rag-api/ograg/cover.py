"""Greedy approximation of the OG-RAG paper's Algorithm 1 (hyperedge cover).

Given ANN candidates (each a hyperedge with similarity score + node-id set),
pick a subset that maximises unique entity coverage within a token budget.

Implementation: re-rank by ``similarity * (1 + new_entity_count)`` against the
running covered-entity set; take in order until the budget is exhausted.
Oversized hyperedges that exceed the remaining budget are skipped, not
truncated.

The full ILP version (paper) is deferred to v2.
"""

from __future__ import annotations

from typing import Any


# Token estimate — cheap heuristic: ~4 chars per English token. Matches the
# rule-of-thumb both Gemini and tiktoken-style tokenisers approximate to
# within ±20% on prose. Tightening this requires a real tokeniser dep, which
# is overkill for budget-bounded retrieval.
def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def algo1_cover(
    candidates: list[dict[str, Any]],
    *,
    k_target_tokens: int = 6000,
) -> list[dict[str, Any]]:
    """Greedy entity-cover selection over `candidates`.

    Each candidate must have:
      - ``similarity`` : float in [0, 1] (cosine similarity, higher = better)
      - ``node_ids``   : iterable of entity ids
      - ``paragraph_text`` : str

    Returns the selected hyperedges in pick order. Annotates each returned
    dict with ``cover_score`` (the re-ranked greedy score at pick time) and
    ``new_entity_count`` (entities this hyperedge contributed at pick time).
    """
    if k_target_tokens <= 0:
        return []

    remaining = [{**c, "_node_set": set(c.get("node_ids") or [])} for c in candidates]
    selected: list[dict[str, Any]] = []
    covered: set[Any] = set()
    tokens_used = 0

    while remaining:
        best_idx = -1
        best_score = -1.0
        best_new = 0
        for i, c in enumerate(remaining):
            new_entities = len(c["_node_set"] - covered)
            score = float(c.get("similarity") or 0.0) * (1 + new_entities)
            if score > best_score:
                best_score = score
                best_idx = i
                best_new = new_entities

        if best_idx < 0:
            break

        cand = remaining.pop(best_idx)
        token_cost = estimate_tokens(cand.get("paragraph_text") or "")
        if tokens_used + token_cost > k_target_tokens:
            # Skip this oversized hyperedge; smaller ones below may still fit.
            continue

        node_set = cand.pop("_node_set")
        cand["cover_score"] = best_score
        cand["new_entity_count"] = best_new
        selected.append(cand)
        covered.update(node_set)
        tokens_used += token_cost

    return selected

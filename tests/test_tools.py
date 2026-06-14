"""
Tests for the three FitFindr tools, with at least one test per failure mode.

Run from the project root with:
    pytest tests/

The search_listings tests are offline and deterministic. The LLM-backed tests
skip automatically when GROQ_API_KEY is not set so the suite still runs offline.
"""

import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Nothing matches this; should return an empty list, not raise.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


# ── create_fit_card failure mode (offline) ──────────────────────────────────

def test_create_fit_card_empty_outfit():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert result.strip() != ""  # descriptive message, not a crash or empty string


# ── suggest_outfit failure mode (needs LLM) ─────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set; skipping live LLM test",
)
def test_suggest_outfit_empty_wardrobe():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""

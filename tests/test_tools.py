"""
Tests for the three FitFindr tools, with at least one test per failure mode.

Run from the project root with:
    pytest tests/

The search_listings tests are offline and deterministic. The LLM-backed tests
skip automatically when GROQ_API_KEY is not set so the suite still runs offline.
"""

import os

import pytest

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_price,
    check_trends,
)
from agent import _search_with_fallback
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe, load_listings
from utils.profile import load_profile, save_profile, update_profile_from_run


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


# ── stretch: compare_price ───────────────────────────────────────────────────

def test_compare_price_deal():
    # A very cheap top should read as a great deal versus comparable tops.
    cheap = {"id": "synthetic", "category": "tops", "price": 1.0,
             "style_tags": ["vintage"]}
    result = compare_price(cheap)
    assert result["verdict"] == "great deal"
    assert "$" in result["message"]


def test_compare_price_returns_reasoning():
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = compare_price(item)
    assert result["verdict"] in {"great deal", "fair", "above average", "unknown"}
    assert isinstance(result["message"], str) and result["message"]


def test_compare_price_unknown_when_no_comparables():
    # A category with no other listings cannot be judged.
    odd = {"id": "synthetic", "category": "costume", "price": 50.0, "style_tags": []}
    result = compare_price(odd)
    assert result["verdict"] == "unknown"
    assert result["comparable_median"] is None


# ── stretch: check_trends ────────────────────────────────────────────────────

def test_check_trends_top_tag():
    result = check_trends(None)
    assert "vintage" in result["tags"]
    assert result["message"]


# ── stretch: retry with fallback ─────────────────────────────────────────────

def test_retry_fallback_drops_size():
    # Size "ZZ" matches nothing; the fallback should drop it and still find items.
    parsed = {"description": "track jacket", "size": "ZZ", "max_price": 80.0}
    session = {"search_adjustments": []}
    results = _search_with_fallback(parsed, session)
    assert len(results) > 0
    assert any("size" in note for note in session["search_adjustments"])


# ── stretch: style profile memory ────────────────────────────────────────────

def test_profile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FITFINDR_PROFILE", str(tmp_path / "profile.json"))
    profile = load_profile()
    update_profile_from_run(profile, {"description": "vintage tee", "size": "M"})
    save_profile(profile)

    reloaded = load_profile()
    assert reloaded["preferred_size"] == "M"
    assert reloaded["favorite_tags"].get("vintage") == 1
    assert reloaded["runs"] == 1

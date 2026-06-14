"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re
import statistics
from collections import Counter

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(prompt: str, temperature: float, max_tokens: int = 400) -> str:
    """Send a single-message prompt to Groq and return the response text."""
    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# Common words to ignore when scoring keyword overlap.
_STOPWORDS = {"the", "and", "for", "with", "an", "of", "in", "to", "my", "i", "a"}


def _size_matches(query_size: str, listing_size: str) -> bool:
    """
    Case-insensitive size match. Splits the listing size on whitespace and "/"
    so "M" matches "S/M", and falls back to a substring check for formats like
    "XL (oversized)". Returns False when the query size isn't found.
    """
    wanted = query_size.strip().lower()
    listing_size = listing_size.lower()
    tokens = re.split(r"[\s/]+", listing_size)
    return wanted in tokens or wanted in listing_size


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # 1. Filter by price ceiling (inclusive) if provided.
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    # 2. Filter by size (case-insensitive) if provided.
    if size is not None:
        listings = [item for item in listings if _size_matches(size, item["size"])]

    # 3. Score remaining listings by keyword overlap with the description.
    query_tokens = {
        tok
        for tok in re.findall(r"[a-z0-9]+", description.lower())
        if len(tok) >= 2 and tok not in _STOPWORDS
    }

    scored = []
    for item in listings:
        blob = " ".join(
            [
                item["title"],
                item["description"],
                " ".join(item["style_tags"]),
                item["category"],
                " ".join(item["colors"]),
                item["brand"] or "",
            ]
        ).lower()
        score = sum(1 for tok in query_tokens if tok in blob)
        if score > 0:
            scored.append((score, item))

    # 4. Sort by score, highest first (stable sort keeps dataset order on ties).
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict, trends: dict | None = None) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.
        trends:   Optional dict from check_trends() with a 'tags' list. When
                  given, the suggestion leans into those currently-popular
                  styles and names the trend it followed.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = (
        f"{new_item['title']} (category: {new_item['category']}, "
        f"colors: {', '.join(new_item['colors'])}, "
        f"style: {', '.join(new_item['style_tags'])})"
    )

    # Optional trend nudge: ask the model to lean into popular styles and say so.
    trend_tags = (trends or {}).get("tags") or []
    if trend_tags:
        trend_line = (
            "\n\nCurrently trending styles: "
            + ", ".join(trend_tags)
            + ". Lean the look into the trending styles that fit this piece, and "
            "name the trend you leaned on in one short phrase."
        )
    else:
        trend_line = ""

    items = wardrobe.get("items", []) if wardrobe else []

    if not items:
        # Empty wardrobe: fall back to general styling advice for the item.
        prompt = (
            "You are a thoughtful personal stylist. The shopper has no wardrobe "
            "saved yet, so give general styling advice for this thrifted piece.\n\n"
            f"Item: {item_desc}\n\n"
            "In 3 to 5 sentences, describe what kinds of pieces pair well with it, "
            "the vibe it suits, and one specific way to wear it. Be concrete and warm."
            + trend_line
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {it['name']} ({it['category']}; {', '.join(it['style_tags'])})"
            + (f"; note: {it['notes']}" if it.get("notes") else "")
            for it in items
        )
        prompt = (
            "You are a thoughtful personal stylist. Build outfits for the shopper "
            "using their new thrifted item plus pieces they already own.\n\n"
            f"New item: {item_desc}\n\n"
            f"Their wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1 or 2 complete outfits that pair the new item with specific "
            "named pieces from their wardrobe. For each, add one quick styling tip "
            "(how to tuck, layer, roll, etc.). Keep it concise and concrete."
            + trend_line
        )

    try:
        return _call_llm(prompt, temperature=0.7)
    except Exception:
        return (
            f"I couldn't reach the styling model just now, but {new_item['title']} "
            "is versatile. Pair it with simple, neutral basics and a shoe that "
            "matches its vibe, then build around the colors you already wear most."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # Guard against missing/empty outfit input — no LLM call needed.
    if not outfit or not outfit.strip():
        return (
            "I can't write a fit card without an outfit yet. "
            "Run suggest_outfit first, then try again."
        )

    prompt = (
        "Write a short, shareable outfit caption for a thrifted find, the kind of "
        "thing someone posts with an OOTD photo. Make it sound casual and real, not "
        "like a product description.\n\n"
        f"Item: {new_item['title']}\n"
        f"Price: ${new_item['price']}\n"
        f"Platform: {new_item['platform']}\n"
        f"Outfit: {outfit}\n\n"
        "Write 2 to 4 sentences. Mention the item name, price, and platform once "
        "each, naturally. Capture the vibe in specific terms. Emojis are welcome."
    )

    try:
        return _call_llm(prompt, temperature=1.0)
    except Exception:
        return (
            f"thrifted this {new_item['title']} off {new_item['platform']} for "
            f"${new_item['price']} and it fits the vibe perfectly. full look soon ✨"
        )


# ── Stretch Tool: compare_price ───────────────────────────────────────────────

def compare_price(item: dict, listings: list[dict] | None = None) -> dict:
    """
    Estimate whether an item's price is fair, based on comparable listings in
    the dataset (same category, ideally sharing a style tag).

    Args:
        item:     A listing dict to assess.
        listings: Optional list of listings to compare against. Defaults to the
                  full dataset via load_listings().

    Returns:
        A dict with the assessment and the reasoning behind it:
        - verdict (str): "great deal", "fair", "above average", or "unknown"
        - item_price (float)
        - comparable_median (float | None)
        - comparable_count (int)
        - message (str): a human-readable explanation

    Never raises. If there are too few comparable listings, returns the
    "unknown" verdict with an explanatory message.
    """
    if listings is None:
        listings = load_listings()

    same_category = [
        x for x in listings
        if x["category"] == item["category"] and x["id"] != item["id"]
    ]
    # Prefer comparables that also share a style tag; fall back if too few.
    item_tags = set(item.get("style_tags", []))
    sharing = [x for x in same_category if item_tags & set(x.get("style_tags", []))]
    comparables = sharing if len(sharing) >= 3 else same_category

    price = item["price"]

    if len(comparables) < 2:
        return {
            "verdict": "unknown",
            "item_price": price,
            "comparable_median": None,
            "comparable_count": len(comparables),
            "message": (
                f"Not enough comparable listings to judge the ${price} price "
                f"on this {item['category']} piece."
            ),
        }

    median = round(statistics.median([x["price"] for x in comparables]), 2)
    if price <= median * 0.85:
        verdict = "great deal"
    elif price <= median * 1.05:
        verdict = "fair"
    else:
        verdict = "above average"

    message = (
        f"${price} vs a typical ${median} across {len(comparables)} similar "
        f"{item['category']}, so this price looks {verdict}."
    )
    return {
        "verdict": verdict,
        "item_price": price,
        "comparable_median": median,
        "comparable_count": len(comparables),
        "message": message,
    }


# ── Stretch Tool: check_trends ────────────────────────────────────────────────

def check_trends(
    size: str | None = None,
    listings: list[dict] | None = None,
    top_n: int = 5,
) -> dict:
    """
    Surface what styles are currently popular, based on the live secondhand
    listings feed (the dataset is sourced from public platforms: depop,
    poshmark, thredUp). Optionally narrows to the user's size range.

    Args:
        size:     Optional size to narrow the feed to (matched like search).
        listings: Optional listings to analyze. Defaults to load_listings().
        top_n:    How many trending tags to return.

    Returns:
        A dict:
        - size (str | None): the size scope requested
        - scope (str): "size X" or "all listings"
        - trending (list[tuple[str, int]]): (tag, count) pairs, most popular first
        - tags (list[str]): just the trending tag names
        - message (str): a human-readable summary

    Never raises. Falls back to all listings if a size filter leaves nothing.
    """
    if listings is None:
        listings = load_listings()

    scope = "all listings"
    pool = listings
    if size is not None:
        sized = [x for x in listings if _size_matches(size, x["size"])]
        if sized:
            pool = sized
            scope = f"size {size}"

    if not pool:
        return {
            "size": size,
            "scope": scope,
            "trending": [],
            "tags": [],
            "message": "No trend data available right now.",
        }

    counts = Counter(tag for x in pool for tag in x["style_tags"])
    trending = counts.most_common(top_n)
    tags = [tag for tag, _ in trending]
    message = f"Trending right now in {scope}: {', '.join(tags)}."

    return {
        "size": size,
        "scope": scope,
        "trending": trending,
        "tags": tags,
        "message": message,
    }

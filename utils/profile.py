"""
utils/profile.py

Cross-session style memory for FitFindr. The profile is a small JSON file that
remembers the shopper's preferred size and favorite style keywords, so a later
session can reuse those preferences without the user re-entering them.

Storage: a single JSON file at the repo root (style_profile.json by default).
Override the path with the FITFINDR_PROFILE environment variable (used by tests).
"""

import json
import os

from utils.data_loader import load_listings

# Default location: repo root, one level up from this utils/ folder.
_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "style_profile.json")

# Lazily-built set of real style tags from the dataset, so we only remember
# meaningful style preferences (e.g. "vintage", "graphic tee") and not filler
# words from the query.
_KNOWN_TAGS: set[str] | None = None


def _known_tags() -> set[str]:
    global _KNOWN_TAGS
    if _KNOWN_TAGS is None:
        _KNOWN_TAGS = {
            tag.lower() for item in load_listings() for tag in item["style_tags"]
        }
    return _KNOWN_TAGS


def _profile_path() -> str:
    """Return the profile file path, honoring the FITFINDR_PROFILE override."""
    return os.environ.get("FITFINDR_PROFILE", _DEFAULT_PATH)


def _defaults() -> dict:
    return {"preferred_size": None, "favorite_tags": {}, "runs": 0}


def load_profile() -> dict:
    """
    Load the saved style profile, or return a fresh default profile if the file
    is missing or unreadable. Never raises.
    """
    path = _profile_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge onto defaults so missing keys are always present.
        profile = _defaults()
        profile.update({k: data[k] for k in profile if k in data})
        return profile
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _defaults()


def save_profile(profile: dict) -> None:
    """Write the profile to disk as JSON."""
    with open(_profile_path(), "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


def update_profile_from_run(profile: dict, parsed: dict) -> dict:
    """
    Update the profile in place from one run's parsed query.

    - Remembers the most recent explicit size as the preferred size.
    - Counts description keywords as favorite style tags.
    - Increments the run counter.

    Returns the same (mutated) profile dict.
    """
    if parsed.get("size"):
        profile["preferred_size"] = parsed["size"]

    # Only remember keywords that are real style tags in the dataset, so the
    # profile captures meaningful preferences rather than filler query words.
    favorites = profile.setdefault("favorite_tags", {})
    description = (parsed.get("description") or "").lower()
    for tag in _known_tags():
        if tag in description:
            favorites[tag] = favorites.get(tag, 0) + 1

    profile["runs"] = profile.get("runs", 0) + 1
    return profile


def top_favorite_tags(profile: dict, n: int = 3) -> list[str]:
    """Return the n most frequent favorite tags, most frequent first."""
    favorites = profile.get("favorite_tags", {})
    return [tag for tag, _ in sorted(favorites.items(), key=lambda kv: kv[1], reverse=True)[:n]]

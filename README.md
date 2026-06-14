# FitFindr

FitFindr is a multi-tool AI agent that helps me find secondhand pieces and figure out how to wear them. I describe what I want in plain language, and the agent searches a mock listings dataset, styles the top find against my wardrobe, and writes a shareable caption for it. It runs a real planning loop, so its behavior changes based on what each tool returns instead of firing every tool no matter what.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add your free Groq API key to a `.env` file in the repo root (get one at console.groq.com):

```
GROQ_API_KEY=your_key_here
```

## Run

```bash
python app.py          # launch the Gradio UI, then open the local URL it prints
python agent.py        # run the planning loop from the terminal (happy path + no-results path)
pytest tests/          # run the tool tests
```

The Gradio app shows three panels: the top listing found, an outfit idea, and a fit card caption. There's a wardrobe toggle for "Example wardrobe" vs "Empty wardrobe (new user)" so you can see the empty-wardrobe path too.

## Tool Inventory

### search_listings

- **Signature:** `search_listings(description: str, size: str | None = None, max_price: float | None = None) -> list[dict]`
- **Inputs:**
  - `description` (str): keywords for what I'm after, like "vintage graphic tee". Drives the relevance scoring.
  - `size` (str | None): size to filter on, matched case-insensitively. None skips the size filter.
  - `max_price` (float | None): inclusive price ceiling in dollars. None skips the price filter.
- **Output:** a `list[dict]` of listing dicts sorted by relevance (most keyword overlap first). Each dict has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Empty list when nothing matches.
- **Purpose:** find candidate listings in the dataset that fit my request. Pure Python, no LLM.

### suggest_outfit

- **Signature:** `suggest_outfit(new_item: dict, wardrobe: dict, trends: dict | None = None) -> str`
- **Inputs:**
  - `new_item` (dict): the listing I picked, straight from search_listings.
  - `wardrobe` (dict): a dict with an `items` list of wardrobe pieces (`id`, `name`, `category`, `colors`, `style_tags`, `notes`). Can be empty.
  - `trends` (dict | None): optional output from check_trends; when given, the suggestion leans into the trending styles and names the one it followed. None skips it.
- **Output:** a non-empty `str` describing one or two outfits, naming specific wardrobe pieces when I have them.
- **Purpose:** style the found item against what I already own, leaning into current trends when trend data is passed in. Calls Groq (llama-3.3-70b-versatile).

### create_fit_card

- **Signature:** `create_fit_card(outfit: str, new_item: dict) -> str`
- **Inputs:**
  - `outfit` (str): the outfit suggestion string from suggest_outfit.
  - `new_item` (dict): the listing dict, used to mention name, price, and platform.
- **Output:** a 2 to 4 sentence `str` caption, casual and shareable, that varies each run.
- **Purpose:** turn the outfit into something I'd actually post. Calls Groq at a higher temperature so it reads different each time.

### compare_price (stretch)

- **Signature:** `compare_price(item: dict, listings: list[dict] | None = None) -> dict`
- **Inputs:**
  - `item` (dict): the listing to assess.
  - `listings` (list[dict] | None): comparison pool, defaults to the full dataset.
- **Output:** a dict with `verdict` ("great deal" / "fair" / "above average" / "unknown"), `item_price`, `comparable_median`, `comparable_count`, and a `message` explaining the call.
- **Purpose:** judge whether a price is fair against comparable same-category listings. Pure Python, no LLM.

### check_trends (stretch)

- **Signature:** `check_trends(size: str | None = None, listings: list[dict] | None = None, top_n: int = 5) -> dict`
- **Inputs:**
  - `size` (str | None): narrows the feed to a size range.
  - `listings` (list[dict] | None): pool to analyze, defaults to the full dataset.
  - `top_n` (int): how many trending tags to return.
- **Output:** a dict with `scope`, `trending` (tag, count pairs), `tags`, and a `message`.
- **Purpose:** surface currently popular styles from the listings feed; its tags feed into suggest_outfit. Pure Python, no LLM.

## How the Planning Loop Works

The loop lives in `run_agent(query, wardrobe)` and works off a single session dict, branching on what each tool returns:

1. Build a fresh session.
2. Parse the query with regex into a description, an optional size, and an optional max_price (price from `$N` / "under N", size from a "size X" pattern, leftover words become the description). Store it in `session["parsed"]`.
3. Call `search_listings` with the parsed parameters and store the list in `session["search_results"]`.
4. If the results are empty, set `session["error"]` to a helpful message and return right away. This is the branch that matters: the agent does not call suggest_outfit on empty input.
5. If there are results, set `session["selected_item"]` to the top one.
6. Call `suggest_outfit(selected_item, wardrobe)` and store the string.
7. If the suggestion came back empty, set an error and skip the card.
8. Call `create_fit_card(outfit_suggestion, selected_item)` and store the caption.
9. Return the session.

So the path forks on the search result: a real query runs all three tools, while an impossible query stops at step 4 with just an error. That difference in behavior is the whole point of the loop.

## State Management

Everything for one interaction lives in a single session dict created by `_new_session()`. Each tool reads what it needs from the session and writes its result back, so nothing gets re-entered by the user and nothing is hardcoded between steps. It tracks:

- `query`: the original text.
- `parsed`: the description / size / max_price from the query.
- `search_results`: the matching listings.
- `selected_item`: the top listing, which is exactly the dict handed to suggest_outfit.
- `wardrobe`: my wardrobe dict.
- `outfit_suggestion`: the string from suggest_outfit, which is exactly what goes into create_fit_card.
- `fit_card`: the final caption.
- `error`: set only when the run stops early, None otherwise.

The chain is: search_listings fills `selected_item`, that flows into suggest_outfit, its output fills `outfit_suggestion`, that flows into create_fit_card. The UI reads `error` first to decide whether the other fields are valid.

## Error Handling

Each tool owns its own failure mode, and I triggered each one deliberately to confirm it recovers instead of crashing.

- **search_listings, no matches:** returns `[]` instead of raising. The loop reads the empty list and sets a helpful error, then stops before the other tools. Tested: `search_listings("designer ballgown", "XXS", 5)` returned `[]`, and the full agent on that query set the error "I couldn't find anything matching that. Try raising your max price, dropping the size filter, or using simpler keywords," with `outfit_suggestion` and `fit_card` left as None (suggest_outfit was never called).
- **suggest_outfit, empty wardrobe:** instead of crashing on an empty `items` list, it asks the model for general styling advice. Tested: `suggest_outfit(tee, get_empty_wardrobe())` returned a real paragraph of advice about what pairs well with the piece rather than an empty string.
- **create_fit_card, missing outfit:** guards an empty or whitespace outfit before any LLM call and returns a descriptive message. Tested: `create_fit_card("", item)` returned "I can't write a fit card without an outfit yet. Run suggest_outfit first, then try again." with no exception.
- **LLM call failures:** both Groq-backed tools wrap the API call in try/except and return a short fallback string, so a network or key error degrades gracefully instead of taking down the agent.

## Spec Reflection

One way the spec helped: locking the tool signatures and the session dict shape in planning.md before writing code meant the tools dropped straight into the planning loop with no rework. Because `selected_item` and `outfit_suggestion` were defined as the exact hand-off points up front, wiring search to suggest to card was mechanical.

One way the implementation diverged: my walkthrough named lst_006 as the top result for "vintage graphic tee," but the actual keyword scoring surfaces lst_002 (the Y2K Baby Tee), because several tees tie on score and the first one in the dataset wins. I kept it as is since the walkthrough was illustrative and the ranking is still correct. I also added one branch the original loop didn't have, a guard in step 7 that stops before the fit card if the outfit suggestion ever comes back empty, just to be safe.

## AI Usage

**Implementing the three tools:** I gave Claude each tool's spec block from planning.md plus the matching stub from tools.py, one tool at a time, and told it to use `load_listings()` for search and the existing `_get_groq_client()` helper for the LLM tools. It produced the keyword-overlap search and the two Groq-backed tools. I reviewed each against the spec and made changes: I had it use token-based size matching (splitting "S/M" into tokens) instead of a plain substring check so a query for "L" wouldn't match "XL," and I had it factor the repeated Groq call into a shared `_call_llm` helper.

**Wiring the planning loop:** I gave Claude the Planning Loop and State Management sections plus the Mermaid diagram and the agent.py stub, and asked it to implement `run_agent` and a regex query parser. Before trusting it I checked that it branches on an empty search result with an early return and does not call all three tools unconditionally, and I confirmed the state actually flows through the session dict by printing `selected_item` and `outfit_suggestion` mid-run. I chose regex parsing over an LLM parse for the query, and I decided to leave the walkthrough example as illustrative rather than reworking the scoring to force it to match.

## Stretch Features

All four stretch features are implemented.

**Price comparison (compare_price).** Given an item, it finds comparable listings in the same category (preferring ones that share a style tag), takes the median price, and returns a verdict with the reasoning, for example "$18 vs a typical $21.5 across 14 similar tops, so this price looks great deal." A great deal is at or below 85% of the median, fair is within 5% above it, and anything higher is above average. If there are fewer than two comparables it returns an "unknown" verdict instead of guessing. The result shows up in the listing panel.

**Style profile memory.** The agent remembers my preferences across sessions in a small JSON file (`style_profile.json`, gitignored, path overridable with the `FITFINDR_PROFILE` env var). It stores my most recent explicit size as `preferred_size` and counts the style tags I search for in `favorite_tags`. On a later run, if I don't give a size, the agent reuses my remembered size and tells me so, so I don't have to re-enter it. Storage is plain JSON loaded at the start of a run and saved at the end via `utils/profile.py`.

**Trend awareness (check_trends).** This surfaces what's currently popular by reading the secondhand listings feed itself. The dataset comes from real public platforms (depop, poshmark, thredUp), so I treat the current listings as the platform feed and count the most common style tags, optionally within my size range. There's no free reliable public fashion-trends API, so the listings feed is the documented data source. The trending tags are passed into suggest_outfit, so the outfit visibly leans into them (the suggestion names the trend it followed, like "vintage revival").

**Retry with fallback.** If search_listings returns nothing, the agent automatically retries with loosened constraints, first dropping the size filter, then dropping the price cap, and it tells me exactly what it adjusted (for example "Loosened search: ignored the size filter (ZZ)"). Only if everything still comes back empty does it give up with an error.

### Stretch error handling

- **compare_price:** too few comparables returns the "unknown" verdict with a clear message, never an exception.
- **check_trends:** an over-narrow size falls back to all listings; no data returns an empty trend list with a message.
- **style memory:** a missing or corrupt profile file returns sensible defaults instead of crashing.
- **retry:** if even the fully loosened search finds nothing, the agent stops with a helpful error rather than calling the later tools.

## Demo

A 3 to 5 minute demo video walks through a full interaction (search to outfit to fit card), points out the state passing between tools, and shows a triggered failure with the agent's graceful response.

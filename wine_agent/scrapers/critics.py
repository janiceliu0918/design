"""Real-time critic score scraper.

Sources (all publicly accessible, no login required):
  1. Vivino wine detail API  — aggregates WA, Decanter, WS, JS, WE scores
  2. CellarTracker           — community average + professional scores
  3. Decanter search         — Decanter's own panel scores
  4. Wine Enthusiast search  — WE scores and tasting notes
"""
import re
import time
import logging
from typing import Optional
import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from wine_agent.models.wine import CriticScore

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_VIVINO_HEADERS = {**_HEADERS, "Accept": "application/json", "x-vivino-api-version": "2"}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
def _get_json(url: str, params: dict | None = None) -> dict:
    resp = requests.get(url, headers=_VIVINO_HEADERS, params=params, timeout=12)
    resp.raise_for_status()
    time.sleep(1.0)
    return resp.json()


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
def _get_html(url: str, params: dict | None = None) -> BeautifulSoup:
    resp = requests.get(url, headers=_HEADERS, params=params, timeout=12)
    resp.raise_for_status()
    time.sleep(1.2)
    return BeautifulSoup(resp.text, "lxml")


# ── 1. Vivino professional critic scores ──────────────────────────────────────

# Vivino critic name → normalised display name
_VIVINO_CRITIC_MAP = {
    "Wine Advocate":   "Wine Advocate (RP)",
    "Wine Spectator":  "Wine Spectator",
    "Decanter":        "Decanter",
    "James Suckling":  "James Suckling",
    "Wine Enthusiast": "Wine Enthusiast",
    "Vinous":          "Vinous",
    "Burghound":       "Burghound",
    "Falstaff":        "Falstaff",
    "Wine & Spirits":  "Wine & Spirits",
}


def fetch_vivino_critic_scores(wine_id: int) -> list[CriticScore]:
    """
    Fetch professional critic scores from Vivino's wine detail endpoint.
    Vivino aggregates WA, WS, Decanter, JS, WE on each wine page.
    """
    if not wine_id:
        return []

    url = f"https://www.vivino.com/api/wines/{wine_id}"
    try:
        data = _get_json(url)
    except Exception as e:
        logger.warning("Vivino wine detail fetch failed (wine_id=%s): %s", wine_id, e)
        return []

    scores: list[CriticScore] = []
    wine_data = data.get("wine", {})

    # Professional scores live under wine.vintages[] → each vintage's reviews
    for vintage in wine_data.get("vintages", [])[:3]:
        for review in vintage.get("reviews", []):
            critic_raw = review.get("critic", {}).get("name", "")
            critic_name = _VIVINO_CRITIC_MAP.get(critic_raw, critic_raw)
            if not critic_name:
                continue

            rating = review.get("rating")
            note = review.get("note", "")

            # Vivino stores 100pt scores as-is; 20pt (JR) and 5pt are also present
            score_max = 100.0
            if rating and rating <= 20:
                score_max = 20.0
            elif rating and rating <= 5:
                score_max = 5.0

            scores.append(CriticScore(
                critic=critic_name,
                score=float(rating) if rating else None,
                score_max=score_max,
                tasting_note=note[:500] if note else "",
                review_date=review.get("year", ""),
            ))

    return scores


def fetch_vivino_scores_by_search(wine_name: str, vintage: Optional[int] = None) -> tuple[list[CriticScore], Optional[int]]:
    """
    Search Vivino for the wine, get its ID, then fetch professional scores.
    Returns (scores_list, wine_id).
    """
    params = {
        "q": f"{wine_name} {vintage or ''}".strip(),
        "language": "en",
        "per_page": 3,
    }
    try:
        data = _get_json("https://www.vivino.com/api/explore/explore", params)
    except Exception as e:
        logger.warning("Vivino search failed: %s", e)
        return [], None

    matches = data.get("explore_vintage", {}).get("matches", [])
    if not matches:
        return [], None

    wine_id = matches[0].get("vintage", {}).get("wine", {}).get("id")
    if not wine_id:
        return [], None

    return fetch_vivino_critic_scores(wine_id), wine_id


# ── 2. CellarTracker ──────────────────────────────────────────────────────────

def fetch_cellartracker_scores(wine_name: str, vintage: Optional[int] = None) -> list[CriticScore]:
    """
    Scrape CellarTracker search results for community and professional scores.
    CT aggregates professional scores alongside community averages.
    """
    query = f"{wine_name} {vintage or ''}".strip()
    url = "https://www.cellartracker.com/list.asp"
    params = {"Table": "List", "szSearch": query, "iRows": 10}

    try:
        soup = _get_html(url, params)
    except Exception as e:
        logger.warning("CellarTracker fetch failed: %s", e)
        return []

    scores: list[CriticScore] = []

    # CellarTracker result table rows contain wine names and scores
    for row in soup.select("table.results tr, tr.alt, tr.norm")[:8]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        # Community score column (usually 3rd or 4th cell)
        score_text = ""
        for cell in cells[2:5]:
            text = cell.get_text(strip=True)
            if re.match(r"^\d{2,3}(\.\d)?$", text):
                score_text = text
                break

        if not score_text:
            continue

        try:
            score_val = float(score_text)
            if score_val < 50 or score_val > 100:
                continue
        except ValueError:
            continue

        scores.append(CriticScore(
            critic="CellarTracker Community",
            score=score_val,
            score_max=100.0,
            tasting_note="",
        ))
        break  # Take first / best match only

    return scores


# ── 3. Decanter ───────────────────────────────────────────────────────────────

def fetch_decanter_score(wine_name: str, vintage: Optional[int] = None) -> list[CriticScore]:
    """Search Decanter.com for wine reviews and extract panel scores."""
    query = f"{wine_name} {vintage or ''}".strip()
    url = "https://www.decanter.com/search/"

    try:
        soup = _get_html(url, {"q": query})
    except Exception as e:
        logger.warning("Decanter search failed: %s", e)
        return []

    scores: list[CriticScore] = []

    # Decanter search result cards contain score badges
    for article in soup.select("article, .search-result, [class*='article']")[:5]:
        # Look for score patterns like "95" or "94/100" or "95 points"
        text = article.get_text(" ", strip=True)

        # Match score patterns
        score_match = re.search(
            r"\b(9[0-9]|100)\s*(?:points?|/100|pts)?\b",
            text,
            re.IGNORECASE,
        )
        if not score_match:
            continue

        score_val = float(score_match.group(1))

        # Extract a short tasting note
        note_el = article.select_one("p, .excerpt, .summary")
        note = note_el.get_text(strip=True)[:300] if note_el else ""

        scores.append(CriticScore(
            critic="Decanter",
            score=score_val,
            score_max=100.0,
            tasting_note=note,
        ))
        break

    return scores


# ── 4. Wine Enthusiast ────────────────────────────────────────────────────────

def fetch_wine_enthusiast_score(wine_name: str, vintage: Optional[int] = None) -> list[CriticScore]:
    """Search Wine Enthusiast for scores and tasting notes."""
    query = f"{wine_name} {vintage or ''}".strip()

    try:
        soup = _get_html("https://www.wineenthusiast.com/", {"s": query})
    except Exception as e:
        logger.warning("Wine Enthusiast search failed: %s", e)
        return []

    scores: list[CriticScore] = []

    for item in soup.select("[class*='review'], [class*='wine'], article")[:5]:
        text = item.get_text(" ", strip=True)
        score_match = re.search(r"\b(8[5-9]|9[0-9]|100)\s*(?:points?|pts|/100)?\b", text, re.IGNORECASE)
        if not score_match:
            continue

        note_el = item.select_one("p, .description, .tasting-note")
        note = note_el.get_text(strip=True)[:300] if note_el else ""

        scores.append(CriticScore(
            critic="Wine Enthusiast",
            score=float(score_match.group(1)),
            score_max=100.0,
            tasting_note=note,
        ))
        break

    return scores


# ── Main aggregator ───────────────────────────────────────────────────────────

def fetch_all_critic_scores(
    wine_name: str,
    vintage: Optional[int] = None,
    vivino_wine_id: Optional[int] = None,
) -> list[CriticScore]:
    """
    Fetch real critic scores from all available sources in parallel-style fallback.
    Returns a deduplicated list of CriticScore objects.
    """
    all_scores: list[CriticScore] = []
    seen_critics: set[str] = set()

    def _add(scores: list[CriticScore]) -> None:
        for s in scores:
            key = s.critic.lower()
            if key not in seen_critics and s.score is not None:
                seen_critics.add(key)
                all_scores.append(s)

    # Priority 1: Vivino aggregated professional scores (richest source)
    if vivino_wine_id:
        _add(fetch_vivino_critic_scores(vivino_wine_id))
    else:
        vivino_scores, _ = fetch_vivino_scores_by_search(wine_name, vintage)
        _add(vivino_scores)

    # Priority 2: Decanter direct search
    if "decanter" not in seen_critics:
        _add(fetch_decanter_score(wine_name, vintage))

    # Priority 3: Wine Enthusiast
    if "wine enthusiast" not in seen_critics:
        _add(fetch_wine_enthusiast_score(wine_name, vintage))

    # Priority 4: CellarTracker community score
    _add(fetch_cellartracker_scores(wine_name, vintage))

    logger.info("Fetched %d critic scores for '%s' %s", len(all_scores), wine_name, vintage or "")
    return all_scores

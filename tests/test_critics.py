"""Unit tests for the critic score scraper (offline / mock-based)."""
from unittest.mock import patch, MagicMock
import pytest
from wine_agent.scrapers.critics import (
    fetch_vivino_critic_scores,
    fetch_all_critic_scores,
    _VIVINO_CRITIC_MAP,
)
from wine_agent.models.wine import CriticScore


# ── fetch_vivino_critic_scores ────────────────────────────────────────────────

def _mock_vivino_wine_response():
    return {
        "wine": {
            "vintages": [
                {
                    "reviews": [
                        {
                            "critic": {"name": "Wine Advocate"},
                            "rating": 93,
                            "note": "Elegant and concentrated with fine tannins.",
                            "year": "2022",
                        },
                        {
                            "critic": {"name": "Wine Spectator"},
                            "rating": 91,
                            "note": "Rich dark fruit with a long finish.",
                            "year": "2022",
                        },
                        {
                            "critic": {"name": "Decanter"},
                            "rating": 95,
                            "note": "Outstanding vintage.",
                            "year": "2022",
                        },
                    ]
                }
            ]
        }
    }


@patch("wine_agent.scrapers.critics._get_json")
def test_vivino_critic_scores_parsed(mock_get):
    mock_get.return_value = _mock_vivino_wine_response()
    scores = fetch_vivino_critic_scores(wine_id=12345)
    assert len(scores) == 3
    critics = {s.critic for s in scores}
    assert "Wine Advocate (RP)" in critics
    assert "Wine Spectator" in critics
    assert "Decanter" in critics


@patch("wine_agent.scrapers.critics._get_json")
def test_vivino_scores_range(mock_get):
    mock_get.return_value = _mock_vivino_wine_response()
    scores = fetch_vivino_critic_scores(wine_id=12345)
    for s in scores:
        assert s.score is not None
        assert 80 <= s.score <= 100


@patch("wine_agent.scrapers.critics._get_json")
def test_vivino_empty_wine_id_returns_empty(mock_get):
    scores = fetch_vivino_critic_scores(wine_id=0)
    assert scores == []
    mock_get.assert_not_called()


@patch("wine_agent.scrapers.critics._get_json")
def test_vivino_api_failure_returns_empty(mock_get):
    mock_get.side_effect = Exception("Network error")
    scores = fetch_vivino_critic_scores(wine_id=99999)
    assert scores == []


# ── fetch_all_critic_scores (deduplication) ───────────────────────────────────

@patch("wine_agent.scrapers.critics.fetch_vivino_critic_scores")
@patch("wine_agent.scrapers.critics.fetch_decanter_score")
@patch("wine_agent.scrapers.critics.fetch_wine_enthusiast_score")
@patch("wine_agent.scrapers.critics.fetch_cellartracker_scores")
def test_deduplication(mock_ct, mock_we, mock_decanter, mock_vivino):
    """Scores from the same critic should not be duplicated."""
    mock_vivino.return_value = [
        CriticScore(critic="Decanter", score=95, score_max=100),
        CriticScore(critic="Wine Advocate (RP)", score=93, score_max=100),
    ]
    # Decanter direct also returns a Decanter score — should be deduped
    mock_decanter.return_value = [CriticScore(critic="Decanter", score=94, score_max=100)]
    mock_we.return_value = [CriticScore(critic="Wine Enthusiast", score=90, score_max=100)]
    mock_ct.return_value = [CriticScore(critic="CellarTracker Community", score=92, score_max=100)]

    scores = fetch_all_critic_scores("Château Test", 2019, vivino_wine_id=1)
    critic_names = [s.critic for s in scores]

    # Decanter should appear only once
    assert critic_names.count("Decanter") == 1
    # All unique critics should be present
    assert len(scores) == 4


@patch("wine_agent.scrapers.critics.fetch_vivino_scores_by_search")
@patch("wine_agent.scrapers.critics.fetch_decanter_score")
@patch("wine_agent.scrapers.critics.fetch_wine_enthusiast_score")
@patch("wine_agent.scrapers.critics.fetch_cellartracker_scores")
def test_all_sources_fail_returns_empty(mock_ct, mock_we, mock_decanter, mock_search):
    mock_search.return_value = ([], None)
    mock_decanter.return_value = []
    mock_we.return_value = []
    mock_ct.return_value = []
    scores = fetch_all_critic_scores("Unknown Wine", 2019)
    assert scores == []

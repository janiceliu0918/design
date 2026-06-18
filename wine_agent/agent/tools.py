"""Anthropic tool-use definitions for the Wine Intelligence Agent.

Each function here maps to a Claude tool that the agent can call to trigger
real data lookups during its reasoning loop.
"""
from typing import Any
import logging

from wine_agent.scrapers import wine_searcher, vivino, winery, critics
from wine_agent.processors import calculator, sentiment
from wine_agent.config.settings import config
from wine_agent.models.wine import CriticScore

logger = logging.getLogger(__name__)

# ── Tool schemas (passed to Claude's `tools` parameter) ──────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "search_wine_prices",
        "description": (
            "Search Wine-Searcher for global market prices for a specific wine and vintage. "
            "Returns global average, min, max prices in CAD and a sample count."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_name": {"type": "string", "description": "Full wine name, e.g. 'Château Talbot'"},
                "vintage": {"type": "integer", "description": "Vintage year, e.g. 2019"},
            },
            "required": ["wine_name"],
        },
    },
    {
        "name": "get_vivino_sentiment",
        "description": (
            "Fetch consumer ratings, flavour tags, and sentiment data from Vivino "
            "for a specific wine and vintage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_name": {"type": "string"},
                "vintage": {"type": "integer"},
            },
            "required": ["wine_name"],
        },
    },
    {
        "name": "fetch_winery_classification",
        "description": (
            "Fetch official classification, grape blend, and technical data from the "
            "producer's website. Requires the producer name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "producer": {"type": "string", "description": "Producer/château name"},
                "wine_name": {"type": "string"},
                "vintage": {"type": "integer"},
            },
            "required": ["producer", "wine_name"],
        },
    },
    {
        "name": "calculate_bc_landed_cost",
        "description": (
            "Calculate the fully-loaded BC landed cost for one bottle, including "
            "CETA duty rates, LDB markup, federal excise, and GST. "
            "Returns a detailed cost breakdown and suggested retail price in CAD."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "supplier_price": {"type": "number", "description": "Supplier price per bottle (numeric)"},
                "currency": {"type": "string", "description": "Currency code: EUR, USD, GBP, CAD"},
                "country_of_origin": {"type": "string", "description": "Wine's country of origin"},
                "market_avg_cad": {"type": "number", "description": "Global market average price in CAD (optional)"},
            },
            "required": ["supplier_price", "currency", "country_of_origin"],
        },
    },
    {
        "name": "fetch_critic_scores",
        "description": (
            "Fetch REAL professional critic scores from Vivino (aggregates Wine Advocate, "
            "Wine Spectator, Decanter, James Suckling, Wine Enthusiast), CellarTracker, "
            "and Decanter direct search. Always call this instead of guessing scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wine_name": {"type": "string", "description": "Full wine name"},
                "vintage": {"type": "integer", "description": "Vintage year"},
                "vivino_wine_id": {"type": "integer", "description": "Vivino wine ID if already known"},
            },
            "required": ["wine_name"],
        },
    },
    {
        "name": "lookup_vintage_report",
        "description": (
            "Generate a vintage quality report for a given appellation and year, "
            "covering weather, quality assessment, and drinking window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "appellation": {"type": "string", "description": "Wine appellation, e.g. 'Saint-Julien'"},
                "vintage": {"type": "integer", "description": "Year"},
            },
            "required": ["appellation", "vintage"],
        },
    },
]


# ── Tool execution dispatcher ─────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> Any:
    """Route a Claude tool call to the appropriate handler and return the result."""
    logger.info("Executing tool: %s | input: %s", tool_name, tool_input)

    if tool_name == "search_wine_prices":
        return _tool_search_prices(tool_input)

    if tool_name == "get_vivino_sentiment":
        return _tool_vivino(tool_input)

    if tool_name == "fetch_winery_classification":
        return _tool_winery(tool_input)

    if tool_name == "calculate_bc_landed_cost":
        return _tool_landed_cost(tool_input)

    if tool_name == "fetch_critic_scores":
        return _tool_critic_scores(tool_input)

    if tool_name == "lookup_vintage_report":
        return {"status": "handled_by_llm"}

    return {"error": f"Unknown tool: {tool_name}"}


def _tool_search_prices(inp: dict) -> dict:
    result = wine_searcher.fetch_market_prices(
        wine_name=inp["wine_name"],
        vintage=inp.get("vintage"),
    )
    return {
        "global_avg_cad": result.get("global_avg_cad"),
        "min_cad": result.get("min_cad"),
        "max_cad": result.get("max_cad"),
        "sample_size": result.get("sample_size", 0),
        "note": "Prices in CAD, 750ml equivalent",
    }


def _tool_vivino(inp: dict) -> dict:
    result = vivino.fetch_vivino_data(
        wine_name=inp["wine_name"],
        vintage=inp.get("vintage"),
    )
    sent = result.get("sentiment")
    if not sent:
        return {"status": "not_found"}
    return {
        "average_rating": sent.average_rating,
        "rating_count": sent.rating_count,
        "flavour_tags": sent.flavour_tags,
        "positive_keywords": sent.positive_keywords,
        "negative_keywords": sent.negative_keywords,
        "sentiment_score": sent.sentiment_score,
    }


def _tool_winery(inp: dict) -> dict:
    cls = winery.fetch_winery_classification(
        producer=inp["producer"],
        wine_name=inp["wine_name"],
        vintage=inp.get("vintage"),
    )
    return {
        "appellation": cls.appellation,
        "country": cls.country,
        "region": cls.region,
        "classification": cls.classification,
        "grape_varieties": cls.grape_varieties,
        "oak_aging_months": cls.oak_aging_months,
        "alcohol_pct": cls.alcohol_pct,
        "vintage_rating": cls.vintage_rating,
    }


def _tool_critic_scores(inp: dict) -> dict:
    scores = critics.fetch_all_critic_scores(
        wine_name=inp["wine_name"],
        vintage=inp.get("vintage"),
        vivino_wine_id=inp.get("vivino_wine_id"),
    )
    if not scores:
        return {"status": "not_found", "scores": []}

    return {
        "scores": [
            {
                "critic": s.critic,
                "score": s.score,
                "score_max": s.score_max,
                "tasting_note": s.tasting_note[:200] if s.tasting_note else "",
                "review_date": s.review_date,
            }
            for s in scores
        ],
        "count": len(scores),
        "sources": list({s.critic for s in scores}),
    }


def _tool_landed_cost(inp: dict) -> dict:
    breakdown = calculator.calculate_landed_cost(
        supplier_price_per_bottle=float(inp["supplier_price"]),
        supplier_currency=inp.get("currency", "EUR"),
        country_of_origin=inp["country_of_origin"],
    )
    market_avg = inp.get("market_avg_cad")
    if market_avg:
        breakdown = calculator.add_market_comparison(breakdown, float(market_avg))

    return {
        "fob_cad": breakdown.fob_price_cad,
        "freight_cad": breakdown.freight_cad,
        "import_duty_cad": breakdown.import_duty_cad,
        "federal_excise_cad": breakdown.federal_excise_cad,
        "ldb_markup_cad": breakdown.ldb_markup_cad,
        "gst_cad": breakdown.gst_cad,
        "total_shelf_cad": breakdown.total_landed_cad,
        "suggested_retail_cad": breakdown.suggested_retail_cad,
        "quote_vs_market": breakdown.quote_vs_market,
        "gross_margin_pct": breakdown.gross_margin_pct,
    }

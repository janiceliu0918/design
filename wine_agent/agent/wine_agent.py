"""Core Wine Market Intelligence Agent — orchestrates the agentic loop."""
import json
import logging
import re
import uuid
from typing import Optional

from wine_agent.config.settings import config
from wine_agent.agent.prompts import SYSTEM_PROMPT, ANALYSIS_PROMPT
from wine_agent.agent.tools import TOOL_DEFINITIONS, execute_tool
from wine_agent.agent.llm_client import get_llm_client
from wine_agent.models.wine import (
    WineIntelligenceReport, WineClassification,
    LandedCostBreakdown, ConsumerSentiment, CriticScore, PricePoint,
)

logger = logging.getLogger(__name__)

MAX_AGENTIC_ROUNDS = 8   # Safety ceiling for the tool-use loop


class WineIntelligenceAgent:
    """
    Orchestrates a multi-step agentic loop to build a WineIntelligenceReport.

    Supports both Groq (free) and Anthropic (paid) as the LLM backend.
    Set LLM_PROVIDER=groq or LLM_PROVIDER=anthropic in your .env file.
    """

    def __init__(self) -> None:
        self._llm = get_llm_client()

    def analyse(
        self,
        wine_name: str,
        producer: str = "",
        vintage: Optional[int] = None,
        supplier_quote: Optional[float] = None,
        supplier_currency: str = "EUR",
    ) -> WineIntelligenceReport:
        """
        Run the full intelligence pipeline and return a structured report.

        Parameters
        ----------
        wine_name        : e.g. "Château Talbot"
        producer         : e.g. "Château Talbot" (may differ from label name)
        vintage          : e.g. 2019
        supplier_quote   : numeric price per bottle in supplier_currency
        supplier_currency: "EUR", "USD", "GBP", or "CAD"
        """
        report = WineIntelligenceReport(
            query_id=str(uuid.uuid4())[:8],
            wine_name=wine_name,
            producer=producer or wine_name,
            vintage=vintage,
            supplier_quote_eur=supplier_quote if supplier_currency == "EUR" else None,
        )

        quote_str = (
            f"{supplier_currency} {supplier_quote:.2f}/bottle"
            if supplier_quote else "Not provided"
        )

        user_content = ANALYSIS_PROMPT.format(
            wine_name=wine_name,
            producer=producer or wine_name,
            vintage=vintage or "N/A",
            supplier_quote=quote_str,
            price_data="[Agent will fetch via search_wine_prices tool]",
            critic_data="[Agent will synthesise from its knowledge + tools]",
            sentiment_data="[Agent will fetch via get_vivino_sentiment tool]",
            classification_data="[Agent will fetch via fetch_winery_classification tool]",
            landed_cost_data="[Agent will calculate via calculate_bc_landed_cost tool]",
        )

        messages: list[dict] = [{"role": "user", "content": user_content}]
        tool_results_cache: dict = {}
        last_text = ""

        # ── Agentic loop ──────────────────────────────────────────────────────
        for round_num in range(MAX_AGENTIC_ROUNDS):
            logger.info("Agent round %d/%d", round_num + 1, MAX_AGENTIC_ROUNDS)

            norm_response, raw_response = self._llm.chat_raw(
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                max_tokens=4096,
            )

            if norm_response.text:
                last_text = norm_response.text

            # Append assistant turn (provider-specific message format)
            self._llm.append_assistant_turn(messages, norm_response, raw_response)

            if norm_response.stop_reason == "end_turn":
                logger.info("Agent completed in %d round(s)", round_num + 1)
                break

            if not norm_response.has_tool_calls:
                logger.warning("Unexpected stop without tool calls or end_turn")
                break

            # Execute tool calls and collect results
            results: list[str] = []
            for tc in norm_response.tool_calls:
                tool_output = execute_tool(tc.name, tc.input)
                tool_results_cache[tc.name] = tool_output
                results.append(json.dumps(tool_output, default=str))

            self._llm.append_tool_results(messages, norm_response.tool_calls, results)

        # ── Extract structured fields from final assistant message ─────────
        _populate_report_from_text(report, last_text)
        _populate_report_from_cache(report, tool_results_cache, supplier_quote, supplier_currency)

        return report


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_section(text: str, heading: str) -> str:
    """Extract text under a markdown heading (up to the next heading)."""
    pattern = rf"(?:#+\s*{re.escape(heading)}[^\n]*\n)(.*?)(?=\n#+\s|\Z)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_score(text: str) -> Optional[int]:
    """Extract Opportunity Score integer from the report text."""
    match = re.search(r"opportunity\s+score[:\s]*(\d+)", text, re.IGNORECASE)
    if match:
        return min(10, max(1, int(match.group(1))))
    # Fallback: look for bare number near the heading
    match = re.search(r"(?:score|rating)[:\s]*(\d+)\s*/?\s*10", text, re.IGNORECASE)
    if match:
        return min(10, max(1, int(match.group(1))))
    return None


def _extract_risk_flags(text: str) -> list[str]:
    section = _extract_section(text, "Risk Flags")
    if not section:
        return []
    lines = [re.sub(r"^[-*•]\s*", "", ln).strip() for ln in section.splitlines() if ln.strip()]
    return [ln for ln in lines if len(ln) > 5]


def _populate_report_from_text(report: WineIntelligenceReport, text: str) -> None:
    report.executive_summary = _extract_section(text, "Executive Summary")
    report.vintage_assessment = _extract_section(text, "Vintage Assessment")
    report.market_positioning = _extract_section(text, "Market Positioning")
    report.buyer_recommendation = _extract_section(text, "Buyer Recommendation")
    report.risk_flags = _extract_risk_flags(text)
    report.opportunity_score = _extract_score(text)


def _populate_report_from_cache(
    report: WineIntelligenceReport,
    cache: dict,
    supplier_quote: Optional[float],
    supplier_currency: str,
) -> None:
    """Hydrate report data models from cached tool results."""
    if "search_wine_prices" in cache:
        pd = cache["search_wine_prices"]
        if pd.get("global_avg_cad"):
            report.price_benchmarks.append(PricePoint(
                source="wine_searcher",
                price_cad=pd["global_avg_cad"],
                currency="CAD",
            ))

    if "get_vivino_sentiment" in cache:
        vd = cache["get_vivino_sentiment"]
        if vd.get("average_rating"):
            report.consumer_sentiment = ConsumerSentiment(
                platform="vivino",
                average_rating=vd.get("average_rating"),
                rating_count=vd.get("rating_count", 0),
                flavour_tags=vd.get("flavour_tags", []),
                positive_keywords=vd.get("positive_keywords", []),
                negative_keywords=vd.get("negative_keywords", []),
                sentiment_score=vd.get("sentiment_score"),
            )

    if "fetch_winery_classification" in cache:
        wd = cache["fetch_winery_classification"]
        report.classification = WineClassification(
            appellation=wd.get("appellation", ""),
            country=wd.get("country", ""),
            region=wd.get("region", ""),
            classification=wd.get("classification", ""),
            grape_varieties=wd.get("grape_varieties", {}),
            oak_aging_months=wd.get("oak_aging_months"),
            alcohol_pct=wd.get("alcohol_pct"),
            vintage_rating=wd.get("vintage_rating"),
            vintage_year=report.vintage,
        )

    if "fetch_critic_scores" in cache:
        cd = cache["fetch_critic_scores"]
        for s in cd.get("scores", []):
            if s.get("score") is not None:
                report.critic_scores.append(CriticScore(
                    critic=s["critic"],
                    score=s["score"],
                    score_max=s.get("score_max", 100.0),
                    tasting_note=s.get("tasting_note", ""),
                    review_date=str(s.get("review_date", "")),
                ))

    if "calculate_bc_landed_cost" in cache:
        lc = cache["calculate_bc_landed_cost"]
        report.landed_cost = LandedCostBreakdown(
            fob_price_cad=lc.get("fob_cad", 0),
            freight_cad=lc.get("freight_cad", 0),
            import_duty_cad=lc.get("import_duty_cad", 0),
            federal_excise_cad=lc.get("federal_excise_cad", 0),
            ldb_markup_cad=lc.get("ldb_markup_cad", 0),
            gst_cad=lc.get("gst_cad", 0),
            total_landed_cad=lc.get("total_shelf_cad", 0),
            suggested_retail_cad=lc.get("suggested_retail_cad", 0),
            supplier_quote_cad=lc.get("fob_cad"),
            quote_vs_market=lc.get("quote_vs_market"),
            gross_margin_pct=lc.get("gross_margin_pct"),
        )

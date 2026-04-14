"""
Azure OpenAI GPT-4 financial analysis service.

Generates four types of analysis from 10-K content:
  1. Risk factor summarization (from MD&A / risk sections)
  2. Management sentiment scoring (bullish / neutral / cautious)
  3. Year-over-year trend narrative
  4. Key highlights (top 3-5 bullets)

Architecture note — pluggable methodology templates:
  The ANALYSIS_TEMPLATES dict maps a template name to a system prompt variant.
  Future roadmap: add "meet_kevin" and "financial_education" templates that apply
  the specific ratio weightings, growth thresholds, and scoring rubrics used by
  those popular retail investor frameworks. Each template receives the same
  FinancialMetrics + filing text and returns a comparable structured output,
  enabling side-by-side methodology comparison on the same company data.
"""
import json
import logging

import structlog

from app.config import get_settings

log = structlog.get_logger()

MOCK_ANALYSIS = {
    "risk_summary": (
        "Key risks include macroeconomic headwinds (inflation, rising rates), intense competition "
        "in cloud and enterprise software markets, and expanding data privacy regulations (GDPR, CCPA). "
        "Currency exposure from international operations adds earnings volatility."
    ),
    "mgmt_sentiment": "bullish",
    "sentiment_rationale": (
        "Management highlighted double-digit revenue growth, margin expansion, and robust free cash "
        "flow generation. Language around AI investment and product momentum was notably optimistic."
    ),
    "trend_narrative": (
        "Revenue grew 12% YoY driven by cloud segment strength. Gross margin expanded +3.3pp to 68.4%, "
        "reflecting mix shift toward higher-margin subscriptions. FCF of $4.2B supports ongoing "
        "capital returns and strategic M&A optionality."
    ),
    "key_highlights": [
        "Cloud segment revenue grew 22% YoY, now representing 45% of total revenue",
        "Gross margin expanded 330bps to 68.4% on subscription mix shift",
        "Free cash flow of $4.2B (+18% YoY) enables continued share repurchases",
        "R&D investment increased 15% as company accelerates AI product roadmap",
        "Management guided for continued double-digit revenue growth in FY2024",
    ],
}

_RISK_SYSTEM = """You are a senior equity research analyst. Given the risk factors and MD&A text from a
10-K filing, produce a concise risk summary in 3-4 sentences covering the most material business,
market, and regulatory risks. Be specific — avoid generic boilerplate. Respond with plain text only."""

_SENTIMENT_SYSTEM = """You are a financial analyst assessing management tone in 10-K filings.
Given the MD&A text, classify management sentiment as exactly one of: bullish, neutral, or cautious.
Then provide a 2-3 sentence rationale citing specific language from the filing.
Respond with valid JSON: {"sentiment": "bullish|neutral|cautious", "rationale": "..."}"""

_TREND_SYSTEM = """You are a financial analyst. Given structured financial metrics (revenue, margins,
cash flow) for a company's fiscal year alongside their MD&A text, write a 3-4 sentence trend narrative
in plain English suitable for a retail investor. Highlight revenue trajectory, margin direction,
and cash generation. Respond with plain text only."""

_HIGHLIGHTS_SYSTEM = """You are a financial analyst. Given 10-K filing content and key financial
metrics, extract exactly 5 bullet-point highlights that a retail investor should know. Each bullet
should be one concise sentence with a specific number or metric where possible.
Respond with valid JSON: {"highlights": ["bullet1", "bullet2", "bullet3", "bullet4", "bullet5"]}"""

# Roadmap: additional methodology templates
ANALYSIS_TEMPLATES = {
    "default": "Standard equity research summary",
    "meet_kevin": "TODO: Meet Kevin methodology — focus on revenue growth rate vs P/E, moat assessment, and management track record",
    "financial_education": "TODO: Financial Education (Jeremy) methodology — focus on P/E vs peers, balance sheet safety, and dividend potential",
}


async def _call_gpt4(system: str, user_content: str) -> str:
    settings = get_settings()
    from openai import AzureOpenAI
    client = AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_key,
        api_version="2024-02-01",
    )
    response = client.chat.completions.create(
        model=settings.azure_openai_deployment,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content[:8000]},
        ],
        temperature=0.2,
        max_tokens=1000,
    )
    return response.choices[0].message.content or ""


async def analyze_filing(
    raw_text: str,
    metrics: dict,
    company_name: str,
    fiscal_year: int,
) -> dict:
    """
    Run all four GPT-4 analysis tasks on a 10-K filing.
    Returns dict matching FilingAnalysis fields.
    """
    settings = get_settings()
    if settings.mock_azure:
        log.info("analyst_mock_mode", company=company_name, year=fiscal_year)
        return MOCK_ANALYSIS

    metrics_str = "\n".join(
        f"  {k}: {v:,.2f}" if isinstance(v, float) else f"  {k}: {v}"
        for k, v in metrics.items()
        if v is not None
    )
    context = (
        f"Company: {company_name}\nFiscal Year: {fiscal_year}\n\n"
        f"Financial Metrics:\n{metrics_str}\n\n"
        f"Filing Text (truncated):\n{raw_text[:6000]}"
    )

    try:
        risk_summary = await _call_gpt4(_RISK_SYSTEM, context)
    except Exception as e:
        log.warning("risk_summary_failed", error=str(e))
        risk_summary = None

    try:
        raw_sentiment = await _call_gpt4(_SENTIMENT_SYSTEM, context)
        parsed = json.loads(raw_sentiment)
        mgmt_sentiment = parsed.get("sentiment", "neutral")
        sentiment_rationale = parsed.get("rationale", "")
    except Exception as e:
        log.warning("sentiment_failed", error=str(e))
        mgmt_sentiment, sentiment_rationale = "neutral", None

    try:
        trend_narrative = await _call_gpt4(_TREND_SYSTEM, context)
    except Exception as e:
        log.warning("trend_narrative_failed", error=str(e))
        trend_narrative = None

    try:
        raw_highlights = await _call_gpt4(_HIGHLIGHTS_SYSTEM, context)
        key_highlights = json.loads(raw_highlights).get("highlights", [])
    except Exception as e:
        log.warning("highlights_failed", error=str(e))
        key_highlights = []

    return {
        "risk_summary": risk_summary,
        "mgmt_sentiment": mgmt_sentiment,
        "sentiment_rationale": sentiment_rationale,
        "trend_narrative": trend_narrative,
        "key_highlights": key_highlights,
        "model_used": settings.azure_openai_deployment,
    }

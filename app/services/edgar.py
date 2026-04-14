"""
SEC EDGAR API client.

Provides two data paths for 10-K filings:
  1. XBRL structured facts  → reliable numeric financial metrics
  2. Filing document URL    → PDF/HTML for Azure Doc Intelligence OCR

EDGAR rate limit: 10 requests/second max. We use edgar_rate_limit_delay (default 0.12s).
No auth required — public API. User-Agent header is mandatory per EDGAR policy.
"""
import asyncio
import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

# XBRL concept names to try in priority order for each metric.
# EDGAR companies use varying concept names depending on filing era.
XBRL_REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
]
XBRL_NET_INCOME_CONCEPTS = ["NetIncomeLoss", "ProfitLoss"]
XBRL_GROSS_PROFIT_CONCEPTS = ["GrossProfit"]
XBRL_OPERATING_INCOME_CONCEPTS = ["OperatingIncomeLoss"]
XBRL_EPS_BASIC_CONCEPTS = ["EarningsPerShareBasic"]
XBRL_EPS_DILUTED_CONCEPTS = ["EarningsPerShareDiluted"]
XBRL_ASSETS_CONCEPTS = ["Assets"]
XBRL_LIABILITIES_CONCEPTS = ["Liabilities"]
XBRL_EQUITY_CONCEPTS = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
XBRL_DEBT_CONCEPTS = ["LongTermDebt", "LongTermDebtNoncurrent"]
XBRL_CASH_CONCEPTS = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments"]
XBRL_OCF_CONCEPTS = ["NetCashProvidedByUsedInOperatingActivities"]
XBRL_CAPEX_CONCEPTS = ["PaymentsToAcquirePropertyPlantAndEquipment"]
XBRL_SHARES_CONCEPTS = ["CommonStockSharesOutstanding"]
XBRL_RD_CONCEPTS = ["ResearchAndDevelopmentExpense"]


def _build_headers() -> dict[str, str]:
    return {"User-Agent": get_settings().edgar_user_agent, "Accept": "application/json"}


async def _get(client: httpx.AsyncClient, url: str) -> dict:
    settings = get_settings()
    await asyncio.sleep(settings.edgar_rate_limit_delay)
    resp = await client.get(url, headers=_build_headers(), timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def resolve_cik(ticker: str) -> str:
    """Resolve a ticker symbol to a zero-padded 10-digit CIK."""
    async with httpx.AsyncClient() as client:
        data = await _get(client, "https://www.sec.gov/files/company_tickers.json")
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker not found in EDGAR: {ticker!r}")


async def get_company_info(cik10: str) -> dict:
    """Fetch company name, SIC code, and industry from EDGAR submissions."""
    async with httpx.AsyncClient() as client:
        data = await _get(client, f"https://data.sec.gov/submissions/CIK{cik10}.json")
    return {
        "name": data.get("name", ""),
        "sic_code": str(data.get("sic", "")),
        "industry": data.get("sicDescription", ""),
    }


async def get_latest_10k_accession(cik10: str) -> dict | None:
    """
    Find the most recent 10-K filing accession number and document URL.
    Returns {"accession_number": "...", "filing_url": "...", "period_of_report": "..."} or None.
    """
    async with httpx.AsyncClient() as client:
        data = await _get(client, f"https://data.sec.gov/submissions/CIK{cik10}.json")

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    periods = filings.get("reportDate", [])
    primary_docs = filings.get("primaryDocument", [])

    for i, form in enumerate(forms):
        if form == "10-K":
            acc = accessions[i].replace("-", "")
            period = periods[i] if i < len(periods) else ""
            doc = primary_docs[i] if i < len(primary_docs) else ""
            base_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{acc}"
            filing_url = f"{base_url}/{doc}" if doc else base_url
            return {
                "accession_number": accessions[i],
                "filing_url": filing_url,
                "period_of_report": period,
                "fiscal_year": int(period[:4]) if period else 0,
            }
    return None


def _extract_annual_value(facts: dict, concepts: list[str], fiscal_year: int) -> float | None:
    """
    Pull the annual (10-K) value for a given fiscal year from XBRL company facts.
    Tries each concept name in order until one is found.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        concept_data = us_gaap.get(concept)
        if not concept_data:
            continue
        units = concept_data.get("units", {})
        # USD values under "USD", shares under "shares"
        for unit_vals in units.values():
            for entry in unit_vals:
                if (
                    entry.get("form") == "10-K"
                    and entry.get("fp") == "FY"
                    and entry.get("fy") == fiscal_year
                ):
                    return float(entry["val"])
    return None


async def get_xbrl_metrics(cik10: str, fiscal_year: int) -> dict[str, float | None]:
    """
    Fetch structured financial metrics from EDGAR XBRL company facts API.
    Returns a dict of metric_name → value (in USD, not thousands).
    """
    async with httpx.AsyncClient() as client:
        facts = await _get(client, f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json")

    def extract(concepts: list[str]) -> float | None:
        return _extract_annual_value(facts, concepts, fiscal_year)

    revenue = extract(XBRL_REVENUE_CONCEPTS)
    gross_profit = extract(XBRL_GROSS_PROFIT_CONCEPTS)
    operating_income = extract(XBRL_OPERATING_INCOME_CONCEPTS)
    net_income = extract(XBRL_NET_INCOME_CONCEPTS)
    total_assets = extract(XBRL_ASSETS_CONCEPTS)
    total_liabilities = extract(XBRL_LIABILITIES_CONCEPTS)
    total_equity = extract(XBRL_EQUITY_CONCEPTS)
    long_term_debt = extract(XBRL_DEBT_CONCEPTS)
    cash = extract(XBRL_CASH_CONCEPTS)
    operating_cash_flow = extract(XBRL_OCF_CONCEPTS)
    capex = extract(XBRL_CAPEX_CONCEPTS)
    shares = extract(XBRL_SHARES_CONCEPTS)
    rd = extract(XBRL_RD_CONCEPTS)
    eps_basic = extract(XBRL_EPS_BASIC_CONCEPTS)
    eps_diluted = extract(XBRL_EPS_DILUTED_CONCEPTS)

    free_cash_flow = (
        operating_cash_flow - abs(capex)
        if operating_cash_flow is not None and capex is not None
        else None
    )

    # Computed ratios
    gross_margin = (gross_profit / revenue * 100) if gross_profit and revenue else None
    net_margin = (net_income / revenue * 100) if net_income and revenue else None
    op_margin = (operating_income / revenue * 100) if operating_income and revenue else None
    dte = (long_term_debt / total_equity) if long_term_debt and total_equity else None
    roe = (net_income / total_equity * 100) if net_income and total_equity else None

    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "eps_basic": eps_basic,
        "eps_diluted": eps_diluted,
        "rd_expense": rd,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "long_term_debt": long_term_debt,
        "cash": cash,
        "operating_cash_flow": operating_cash_flow,
        "capital_expenditures": capex,
        "free_cash_flow": free_cash_flow,
        "shares_outstanding": shares,
        "gross_margin_pct": gross_margin,
        "net_margin_pct": net_margin,
        "operating_margin_pct": op_margin,
        "debt_to_equity": dte,
        "roe": roe,
    }


async def fetch_filing_text(filing_url: str) -> str:
    """Download the raw HTML/text content of a 10-K filing document."""
    async with httpx.AsyncClient() as client:
        await asyncio.sleep(get_settings().edgar_rate_limit_delay)
        resp = await client.get(
            filing_url,
            headers={"User-Agent": get_settings().edgar_user_agent},
            timeout=60.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text

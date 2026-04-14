"""
Analysis router — structured financial metrics, trend history, and peer comparison.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.filing import Company, Filing, FinancialMetrics, FilingAnalysis

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def _metrics_dict(m: FinancialMetrics | None) -> dict:
    if not m:
        return {}
    return {
        "revenue": m.revenue,
        "gross_profit": m.gross_profit,
        "operating_income": m.operating_income,
        "net_income": m.net_income,
        "ebitda": m.ebitda,
        "eps_basic": m.eps_basic,
        "eps_diluted": m.eps_diluted,
        "rd_expense": m.rd_expense,
        "total_assets": m.total_assets,
        "total_liabilities": m.total_liabilities,
        "total_equity": m.total_equity,
        "long_term_debt": m.long_term_debt,
        "cash": m.cash,
        "operating_cash_flow": m.operating_cash_flow,
        "capital_expenditures": m.capital_expenditures,
        "free_cash_flow": m.free_cash_flow,
        "shares_outstanding": m.shares_outstanding,
        "gross_margin_pct": m.gross_margin_pct,
        "net_margin_pct": m.net_margin_pct,
        "operating_margin_pct": m.operating_margin_pct,
        "debt_to_equity": m.debt_to_equity,
        "roe": m.roe,
    }


def _analysis_dict(a: FilingAnalysis | None) -> dict:
    if not a:
        return {}
    return {
        "risk_summary": a.risk_summary,
        "mgmt_sentiment": a.mgmt_sentiment,
        "sentiment_rationale": a.sentiment_rationale,
        "trend_narrative": a.trend_narrative,
        "key_highlights": a.key_highlights,
        "model_used": a.model_used,
        "generated_at": a.generated_at.isoformat() if a.generated_at else None,
    }


async def _get_company_or_404(ticker: str, db: AsyncSession) -> Company:
    result = await db.execute(select(Company).where(Company.ticker == ticker.upper()))
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company not found: {ticker}. Run POST /api/v1/ingest/{ticker} first.")
    return company


@router.get("/compare")
async def compare_tickers(
    tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT,GOOG"),
    db: AsyncSession = Depends(get_db),
):
    """Compare latest financial metrics across multiple companies."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=422, detail="At least one ticker required")
    if len(ticker_list) > 10:
        raise HTTPException(status_code=422, detail="Maximum 10 tickers per comparison")

    rows = []
    for ticker in ticker_list:
        result = await db.execute(select(Company).where(Company.ticker == ticker))
        company = result.scalar_one_or_none()
        if not company:
            rows.append({"ticker": ticker, "error": "not ingested"})
            continue

        filing_result = await db.execute(
            select(Filing)
            .options(selectinload(Filing.metrics), selectinload(Filing.analysis))
            .where(Filing.company_id == company.id, Filing.status == "completed")
            .order_by(Filing.fiscal_year.desc())
            .limit(1)
        )
        filing = filing_result.scalar_one_or_none()
        if not filing or not filing.metrics:
            rows.append({"ticker": ticker, "error": "no completed filing"})
            continue

        m = filing.metrics
        rows.append({
            "ticker": company.ticker,
            "company_name": company.name,
            "fiscal_year": filing.fiscal_year,
            "revenue": m.revenue,
            "gross_margin_pct": m.gross_margin_pct,
            "net_margin_pct": m.net_margin_pct,
            "operating_margin_pct": m.operating_margin_pct,
            "free_cash_flow": m.free_cash_flow,
            "debt_to_equity": m.debt_to_equity,
            "roe": m.roe,
            "eps_diluted": m.eps_diluted,
            "mgmt_sentiment": filing.analysis.mgmt_sentiment if filing.analysis else None,
        })

    return {"comparison": rows}


@router.get("/{ticker}")
async def get_analysis(ticker: str, db: AsyncSession = Depends(get_db)):
    """Return the latest available 10-K analysis for a ticker."""
    company = await _get_company_or_404(ticker, db)
    result = await db.execute(
        select(Filing)
        .options(selectinload(Filing.metrics), selectinload(Filing.analysis))
        .where(Filing.company_id == company.id, Filing.status == "completed")
        .order_by(Filing.fiscal_year.desc())
        .limit(1)
    )
    filing = result.scalar_one_or_none()
    if not filing:
        raise HTTPException(status_code=404, detail=f"No completed filing found for {ticker}")

    return {
        "ticker": company.ticker,
        "company_name": company.name,
        "fiscal_year": filing.fiscal_year,
        "period_of_report": filing.period_of_report,
        "filing_id": str(filing.id),
        "metrics": _metrics_dict(filing.metrics),
        "analysis": _analysis_dict(filing.analysis),
    }


@router.get("/{ticker}/trends")
async def get_trends(ticker: str, db: AsyncSession = Depends(get_db)):
    """Return multi-year revenue, margin, and FCF trends for a ticker."""
    company = await _get_company_or_404(ticker, db)
    result = await db.execute(
        select(Filing)
        .options(selectinload(Filing.metrics))
        .where(Filing.company_id == company.id, Filing.status == "completed")
        .order_by(Filing.fiscal_year.asc())
    )
    filings = result.scalars().all()

    years = []
    for f in filings:
        m = f.metrics
        years.append({
            "fiscal_year": f.fiscal_year,
            "revenue": m.revenue if m else None,
            "gross_margin_pct": m.gross_margin_pct if m else None,
            "net_margin_pct": m.net_margin_pct if m else None,
            "operating_margin_pct": m.operating_margin_pct if m else None,
            "free_cash_flow": m.free_cash_flow if m else None,
            "net_income": m.net_income if m else None,
            "eps_diluted": m.eps_diluted if m else None,
        })

    # Compute YoY revenue growth
    for i in range(1, len(years)):
        prev_rev = years[i - 1]["revenue"]
        curr_rev = years[i]["revenue"]
        if prev_rev and curr_rev and prev_rev != 0:
            years[i]["revenue_growth_pct"] = round((curr_rev - prev_rev) / abs(prev_rev) * 100, 2)
        else:
            years[i]["revenue_growth_pct"] = None
    if years:
        years[0]["revenue_growth_pct"] = None

    return {"ticker": company.ticker, "company_name": company.name, "trends": years}

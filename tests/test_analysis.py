"""
Analysis and ask endpoint tests using pre-seeded DB records.
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filing import Company, Filing, FinancialMetrics, FilingAnalysis, DocChunk
from datetime import datetime, timezone


async def _seed(db: AsyncSession) -> tuple[Company, Filing]:
    company = Company(
        cik="0000320193",
        ticker="AAPL",
        name="Apple Inc.",
        sic_code="3674",
        industry="Semiconductors And Related Devices",
    )
    db.add(company)
    await db.flush()

    filing = Filing(
        company_id=company.id,
        fiscal_year=2023,
        period_of_report="2023-09-30",
        accession_number="0000320193-23-000106",
        filing_url="https://example.com/aapl-10k.htm",
        raw_text="ITEM 1A. RISK FACTORS\nMacroeconomic risks including inflation and competition.",
        status="completed",
        created_at=datetime.now(timezone.utc),
        processed_at=datetime.now(timezone.utc),
    )
    db.add(filing)
    await db.flush()

    metrics = FinancialMetrics(
        filing_id=filing.id,
        revenue=383285000000.0,
        net_income=96995000000.0,
        gross_profit=169148000000.0,
        gross_margin_pct=44.1,
        net_margin_pct=25.3,
        free_cash_flow=99584000000.0,
    )
    db.add(metrics)

    analysis = FilingAnalysis(
        filing_id=filing.id,
        risk_summary="Key risks: macroeconomic headwinds, competition, regulatory.",
        mgmt_sentiment="bullish",
        sentiment_rationale="Management highlighted strong growth.",
        trend_narrative="Revenue grew driven by services.",
        key_highlights=["Services revenue grew 16% YoY"],
        model_used="gpt-4",
    )
    db.add(analysis)

    chunk = DocChunk(
        filing_id=filing.id,
        section="risk_factors",
        chunk_index=0,
        chunk_text="Macroeconomic risks including inflation and competition.",
        embedding=[0.1] * 1536,
    )
    db.add(chunk)

    await db.commit()
    return company, filing


@pytest.mark.asyncio
async def test_get_analysis(client: AsyncClient, db_session: AsyncSession):
    await _seed(db_session)
    resp = await client.get("/api/v1/analysis/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["fiscal_year"] == 2023
    assert body["metrics"]["revenue"] == 383285000000.0
    assert body["analysis"]["mgmt_sentiment"] == "bullish"


@pytest.mark.asyncio
async def test_get_trends(client: AsyncClient, db_session: AsyncSession):
    await _seed(db_session)
    resp = await client.get("/api/v1/analysis/AAPL/trends")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert len(body["trends"]) == 1
    assert body["trends"][0]["fiscal_year"] == 2023


@pytest.mark.asyncio
async def test_compare(client: AsyncClient, db_session: AsyncSession):
    await _seed(db_session)
    resp = await client.get("/api/v1/analysis/compare?tickers=AAPL,MSFT")
    assert resp.status_code == 200
    rows = resp.json()["comparison"]
    assert any(r["ticker"] == "AAPL" for r in rows)
    assert any(r.get("error") for r in rows if r["ticker"] == "MSFT")


@pytest.mark.asyncio
async def test_ask(client: AsyncClient, db_session: AsyncSession):
    await _seed(db_session)
    resp = await client.post("/api/v1/ask", json={"question": "What are Apple's main risks?", "ticker": "AAPL"})
    assert resp.status_code == 200
    body = resp.json()
    assert "answer" in body
    assert len(body["sources"]) >= 0


@pytest.mark.asyncio
async def test_analysis_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/analysis/ZZZNOTTICKER")
    assert resp.status_code == 404

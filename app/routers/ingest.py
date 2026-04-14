"""
Ingest router — triggers the full 10-K ingestion pipeline for a ticker.

Pipeline:
  1. Resolve ticker → CIK via EDGAR company_tickers.json
  2. Fetch company metadata (name, SIC, industry)
  3. Find latest 10-K accession number and filing URL
  4. Download filing text (Azure Doc Intelligence OCR on the document)
  5. Fetch structured XBRL financial metrics
  6. Run GPT-4 analysis (risk summary, sentiment, trend narrative, highlights)
  7. Chunk filing text and generate embeddings for RAG
  8. Persist everything to PostgreSQL
"""
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.filing import Company, DocChunk, Filing, FilingAnalysis, FinancialMetrics
from app.services import edgar, ocr, analyst, embedder

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
log = structlog.get_logger()


async def _run_pipeline(ticker: str, db: AsyncSession) -> Filing:
    """Execute the full ingestion pipeline and persist results."""
    ticker = ticker.upper()

    # --- Step 1-2: Resolve CIK and company info ---
    try:
        cik10 = await edgar.resolve_cik(ticker)
        company_info = await edgar.get_company_info(cik10)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Upsert company record
    result = await db.execute(select(Company).where(Company.ticker == ticker))
    company = result.scalar_one_or_none()
    if company is None:
        company = Company(
            cik=cik10,
            ticker=ticker,
            name=company_info["name"],
            sic_code=company_info.get("sic_code"),
            industry=company_info.get("industry"),
        )
        db.add(company)
        await db.flush()
    log.info("company_resolved", ticker=ticker, cik=cik10, name=company.name)

    # --- Step 3: Find latest 10-K filing ---
    filing_meta = await edgar.get_latest_10k_accession(cik10)
    if not filing_meta:
        raise HTTPException(status_code=404, detail=f"No 10-K filing found for {ticker}")

    fiscal_year = filing_meta["fiscal_year"]

    # Check if already ingested
    existing = await db.execute(
        select(Filing).where(
            Filing.company_id == company.id,
            Filing.fiscal_year == fiscal_year,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"{ticker} FY{fiscal_year} already ingested. Use DELETE first to re-ingest.",
        )

    # Create filing record
    filing = Filing(
        company_id=company.id,
        fiscal_year=fiscal_year,
        period_of_report=filing_meta["period_of_report"],
        accession_number=filing_meta["accession_number"],
        filing_url=filing_meta["filing_url"],
        status="processing",
        created_at=datetime.now(timezone.utc),
    )
    db.add(filing)
    await db.flush()
    log.info("filing_created", ticker=ticker, fiscal_year=fiscal_year, filing_id=str(filing.id))

    try:
        # --- Step 4: OCR / text extraction ---
        raw_text = await ocr.extract_text_from_url(filing_meta["filing_url"])
        filing.raw_text = raw_text
        log.info("ocr_complete", chars=len(raw_text))

        # --- Step 5: XBRL structured financial metrics ---
        metrics_data = await edgar.get_xbrl_metrics(cik10, fiscal_year)
        metrics = FinancialMetrics(filing_id=filing.id, **metrics_data)
        db.add(metrics)
        log.info("xbrl_metrics_extracted", revenue=metrics_data.get("revenue"))

        # --- Step 6: GPT-4 analysis ---
        analysis_data = await analyst.analyze_filing(
            raw_text=raw_text,
            metrics=metrics_data,
            company_name=company.name,
            fiscal_year=fiscal_year,
        )
        model_used = analysis_data.pop("model_used", None)
        filing_analysis = FilingAnalysis(
            filing_id=filing.id,
            model_used=model_used,
            **analysis_data,
        )
        db.add(filing_analysis)
        log.info("analysis_complete", sentiment=analysis_data.get("mgmt_sentiment"))

        # --- Step 7: Chunking + embedding ---
        chunks = embedder.chunk_text(raw_text)
        chunk_texts = [c["chunk_text"] for c in chunks]
        embeddings = await embedder.embed_texts(chunk_texts)
        for chunk_meta, emb in zip(chunks, embeddings):
            db.add(DocChunk(
                filing_id=filing.id,
                section=chunk_meta["section"],
                chunk_index=chunk_meta["chunk_index"],
                chunk_text=chunk_meta["chunk_text"],
                embedding=emb,
            ))
        log.info("chunks_embedded", count=len(chunks))

        filing.status = "completed"
        filing.processed_at = datetime.now(timezone.utc)

    except Exception as exc:
        log.error("ingestion_failed", ticker=ticker, error=str(exc))
        filing.status = "failed"
        filing.error_message = str(exc)

    await db.commit()
    await db.refresh(filing)
    return filing


@router.post("/{ticker}", status_code=status.HTTP_202_ACCEPTED)
async def ingest_ticker(
    ticker: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger 10-K ingestion for a ticker symbol.
    Runs synchronously (waits for completion) — suitable for demo; add Celery for production scale.
    """
    filing = await _run_pipeline(ticker.upper(), db)
    return {
        "ticker": ticker.upper(),
        "fiscal_year": filing.fiscal_year,
        "filing_id": str(filing.id),
        "status": filing.status,
        "error": filing.error_message,
    }


@router.delete("/{ticker}/{fiscal_year}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_filing(ticker: str, fiscal_year: int, db: AsyncSession = Depends(get_db)):
    """Remove a filing to allow re-ingestion."""
    result = await db.execute(
        select(Filing)
        .join(Company, Filing.company_id == Company.id)
        .where(Company.ticker == ticker.upper(), Filing.fiscal_year == fiscal_year)
    )
    filing = result.scalar_one_or_none()
    if not filing:
        raise HTTPException(status_code=404, detail="Filing not found")
    await db.delete(filing)
    await db.commit()

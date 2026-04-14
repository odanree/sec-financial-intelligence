"""
Vector similarity retrieval for RAG Q&A over 10-K document chunks.

Uses cosine similarity over stored embeddings in PostgreSQL (ARRAY(Float)).
No external vector store required — consistent with the existing portfolio
pattern (beacon job-search-pipeline stores embeddings as ARRAY(Float) too).
"""
import math
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filing import DocChunk, Filing, Company
from app.services.embedder import embed_texts

log = structlog.get_logger()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


async def semantic_search(
    query: str,
    db: AsyncSession,
    ticker: str | None = None,
    section: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Embed the query and retrieve the top-k most similar 10-K chunks.

    Args:
        query: Natural language question about a company's financials.
        db: Async SQLAlchemy session.
        ticker: If provided, restrict search to this company's filings.
        section: If provided, filter to chunks from this section (e.g. "risk_factors").
        top_k: Number of results to return.

    Returns:
        List of dicts with chunk_text, section, similarity, ticker, fiscal_year.
    """
    embeddings = await embed_texts([query])
    query_vec = embeddings[0]

    # Build query — join through filings → companies for ticker filter
    stmt = (
        select(DocChunk, Filing.fiscal_year, Company.ticker, Company.name)
        .join(Filing, DocChunk.filing_id == Filing.id)
        .join(Company, Filing.company_id == Company.id)
        .where(DocChunk.embedding.is_not(None))
    )
    if ticker:
        stmt = stmt.where(Company.ticker == ticker.upper())
    if section:
        stmt = stmt.where(DocChunk.section == section)

    result = await db.execute(stmt)
    rows = result.all()

    scored = []
    for chunk, fiscal_year, ticker_val, company_name in rows:
        if not chunk.embedding:
            continue
        sim = _cosine_similarity(query_vec, chunk.embedding)
        scored.append({
            "chunk_text": chunk.chunk_text,
            "section": chunk.section,
            "similarity": round(sim, 4),
            "ticker": ticker_val,
            "company_name": company_name,
            "fiscal_year": fiscal_year,
            "filing_id": str(chunk.filing_id),
        })

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:top_k]

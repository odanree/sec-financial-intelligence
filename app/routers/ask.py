"""
RAG Q&A router — answers questions grounded in 10-K filing corpus.

Retrieval → Context assembly → Azure OpenAI GPT-4 generation.
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.services.retriever import semantic_search

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])
log = structlog.get_logger()

MOCK_ANSWER = (
    "Based on the 10-K filing, the company faces three primary risks: macroeconomic headwinds "
    "from inflation and rising interest rates, intensifying competition in cloud and enterprise "
    "software markets, and expanding data privacy regulations. The management team has highlighted "
    "these risks in their risk factor disclosures but expressed confidence in their competitive "
    "moat and recurring revenue model to navigate the environment."
)


class AskRequest(BaseModel):
    question: str
    ticker: str | None = None       # restrict to a specific company
    section: str | None = None      # restrict to a filing section (risk_factors, mda, etc.)
    top_k: int = 5


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[dict]


@router.post("", response_model=AskResponse)
async def ask(payload: AskRequest, db: AsyncSession = Depends(get_db)):
    """
    Answer a question about a company's 10-K filing using RAG.
    Retrieves the most relevant text chunks, then generates a grounded answer.
    """
    settings = get_settings()

    chunks = await semantic_search(
        query=payload.question,
        db=db,
        ticker=payload.ticker,
        section=payload.section,
        top_k=payload.top_k,
    )

    if not chunks and not settings.mock_azure:
        raise HTTPException(
            status_code=404,
            detail="No relevant content found. Ingest at least one filing first.",
        )

    if settings.mock_azure:
        return AskResponse(
            question=payload.question,
            answer=MOCK_ANSWER,
            sources=[{"ticker": "MOCK", "fiscal_year": 2023, "section": "risk_factors", "similarity": 0.91}],
        )

    # Build grounded context from retrieved chunks
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[{i}] {chunk['ticker']} FY{chunk['fiscal_year']} ({chunk['section']}):\n{chunk['chunk_text']}"
        )
    context = "\n\n".join(context_parts)

    system_prompt = (
        "You are a financial analyst assistant with access to SEC 10-K filing excerpts. "
        "Answer the question based ONLY on the provided filing context. "
        "Cite the company and fiscal year when referencing specific data. "
        "If the context does not contain enough information, say so clearly. "
        "Do not fabricate financial figures."
    )
    user_prompt = f"Filing context:\n{context}\n\nQuestion: {payload.question}"

    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_key,
            api_version="2024-02-01",
        )
        response = client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=1000,
        )
        answer = response.choices[0].message.content or "Unable to generate answer."
    except Exception as exc:
        log.error("rag_generation_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="LLM generation failed")

    sources = [
        {
            "ticker": c["ticker"],
            "fiscal_year": c["fiscal_year"],
            "section": c["section"],
            "similarity": c["similarity"],
        }
        for c in chunks
    ]
    return AskResponse(question=payload.question, answer=answer, sources=sources)

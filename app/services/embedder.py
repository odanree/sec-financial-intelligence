"""
Text chunking and embedding service using Azure OpenAI embeddings.

Splits 10-K filing text into overlapping chunks by section, then generates
embeddings for each chunk for RAG retrieval.
"""
import re
import structlog
from app.config import get_settings

log = structlog.get_logger()

CHUNK_SIZE = 800       # tokens (approximate — we use character proxy)
CHUNK_OVERLAP = 150
CHARS_PER_TOKEN = 4   # rough proxy for splitting

# Section header patterns — used to tag chunks with their source section
SECTION_PATTERNS = {
    "risk_factors": re.compile(r"ITEM\s+1A[\.\s].*?RISK\s+FACTOR", re.IGNORECASE),
    "mda": re.compile(r"ITEM\s+7[\.\s].*?MANAGEMENT'?S?\s+DISCUSSION", re.IGNORECASE),
    "business": re.compile(r"ITEM\s+1[\.\s].*?BUSINESS", re.IGNORECASE),
    "financials": re.compile(r"ITEM\s+8[\.\s].*?FINANCIAL\s+STATEMENT", re.IGNORECASE),
}

MOCK_EMBEDDING = [0.01] * 1536  # text-embedding-3-small dimension


def _detect_section(text: str) -> str:
    for section, pattern in SECTION_PATTERNS.items():
        if pattern.search(text[:200]):
            return section
    return "general"


def chunk_text(text: str) -> list[dict]:
    """
    Split filing text into overlapping chunks with section tags.
    Returns list of {"chunk_index": int, "section": str, "chunk_text": str}.
    """
    chunk_chars = CHUNK_SIZE * CHARS_PER_TOKEN
    overlap_chars = CHUNK_OVERLAP * CHARS_PER_TOKEN
    chunks = []
    i = 0
    idx = 0
    while i < len(text):
        chunk = text[i : i + chunk_chars]
        chunks.append({
            "chunk_index": idx,
            "section": _detect_section(chunk),
            "chunk_text": chunk.strip(),
        })
        i += chunk_chars - overlap_chars
        idx += 1
    return [c for c in chunks if len(c["chunk_text"]) > 50]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of text strings.
    Returns list of float vectors (one per input text).
    """
    settings = get_settings()
    if settings.mock_azure or not texts:
        return [MOCK_EMBEDDING[:] for _ in texts]

    from openai import AzureOpenAI
    client = AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_key,
        api_version="2024-02-01",
    )
    # Batch in groups of 100 (Azure OpenAI limit)
    all_embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        response = client.embeddings.create(
            model=settings.azure_openai_embedding_deployment,
            input=batch,
        )
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings

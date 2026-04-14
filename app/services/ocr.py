"""
Azure AI Document Intelligence OCR service.

Extracts structured text and table content from 10-K filing documents.
Supports both URL-based analysis (for EDGAR HTML/PDF URLs) and raw bytes.

Set MOCK_AZURE=true to skip real Azure calls and return synthetic text,
useful for local development without Azure credentials.
"""
import logging

import structlog

from app.config import get_settings

log = structlog.get_logger()

MOCK_TEXT = """
ITEM 1A. RISK FACTORS

The following risk factors may materially affect our business, financial condition, and results of operations.

Macroeconomic Risks: Global economic uncertainty, inflation, and rising interest rates may reduce consumer
and enterprise spending, adversely affecting our revenue growth. Currency fluctuations could impact our
international operations and reported results.

Competition: We operate in intensely competitive markets. Competitors may introduce superior products or
pricing strategies that reduce our market share or force us to lower prices, compressing margins.

Regulatory Risks: Increased government regulation in the areas of data privacy (GDPR, CCPA) and AI could
require significant compliance investments and limit certain business activities.

ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS

Revenue for fiscal year 2023 increased 12% year-over-year, driven by strong growth in our cloud services
segment. Gross margin improved to 68.4% from 65.1% in the prior year, reflecting operating leverage and
a favorable product mix shift toward higher-margin software subscriptions. Operating expenses increased
modestly as we continued to invest in research and development while managing general and administrative
costs. Free cash flow generation remained robust at $4.2 billion, providing flexibility for capital
allocation including share repurchases and strategic acquisitions.
"""


async def extract_text_from_url(document_url: str) -> str:
    """
    Extract full text from a document URL using Azure AI Document Intelligence.
    Falls back to MOCK_TEXT when MOCK_AZURE=true.
    """
    settings = get_settings()
    if settings.mock_azure:
        log.info("ocr_mock_mode", url=document_url)
        return MOCK_TEXT

    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
    from azure.core.credentials import AzureKeyCredential

    client = DocumentIntelligenceClient(
        endpoint=settings.azure_doc_intelligence_endpoint,
        credential=AzureKeyCredential(settings.azure_doc_intelligence_key),
    )
    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(url_source=document_url),
    )
    result = poller.result()

    parts: list[str] = []
    for page in result.pages or []:
        for line in page.lines or []:
            parts.append(line.content)

    # Include table content
    for table in result.tables or []:
        rows: dict[int, list[str]] = {}
        for cell in table.cells or []:
            rows.setdefault(cell.row_index, []).append(cell.content or "")
        for row_cells in sorted(rows.values()):
            parts.append(" | ".join(row_cells))

    return "\n".join(parts)

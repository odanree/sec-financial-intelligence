# SEC Financial Intelligence Pipeline

An end-to-end financial analysis pipeline that ingests SEC 10-K filings via EDGAR, extracts structured XBRL financial metrics, runs Azure AI Document Intelligence OCR on the filing text, and generates AI-powered analysis using GPT-4. Includes a RAG-based Q&A endpoint for grounded document queries.

## Features

- **EDGAR Integration** — Resolves tickers to CIK, fetches latest 10-K filings and XBRL structured financial data
- **Azure Document Intelligence** — OCR extraction from SEC filing documents using `prebuilt-layout` model
- **GPT-4 Analysis** — Risk summary, management sentiment classification, trend narrative, and key highlights
- **RAG Q&A** — Chunk + embed filing text (Azure OpenAI `text-embedding-3-small`), retrieve by cosine similarity, answer grounded questions
- **Financial Metrics** — Revenue, net income, gross profit, FCF, margins, ROE, debt-to-equity and more
- **Multi-year Trends** — Compare metrics across fiscal years with YoY growth calculations
- **Peer Comparison** — Side-by-side metric comparison across multiple tickers

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/ingest/{ticker}` | Trigger full ingest pipeline for a ticker |
| `DELETE` | `/api/v1/ingest/{ticker}/{year}` | Remove a filing for re-ingestion |
| `GET` | `/api/v1/analysis/{ticker}` | Latest analysis + metrics for a ticker |
| `GET` | `/api/v1/analysis/{ticker}/trends` | Multi-year trend data |
| `GET` | `/api/v1/analysis/compare` | Peer comparison (`?tickers=AAPL,MSFT,NVDA`) |
| `POST` | `/api/v1/ask` | RAG Q&A against filing documents |
| `GET` | `/health` | Liveness check |
| `GET` | `/health/db` | Database connectivity check |

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Set: AZURE_DOC_INTELLIGENCE_ENDPOINT, AZURE_DOC_INTELLIGENCE_KEY,
#      AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, DATABASE_URL

# Run with Docker Compose (from portfolio-infra)
docker compose up -d sec-finint-api

# Seed demo data (AAPL, MSFT, NVDA)
python scripts/seed_demo.py

# Query analysis
curl http://localhost:8001/api/v1/analysis/AAPL | jq .
curl http://localhost:8001/api/v1/analysis/compare?tickers=AAPL,MSFT,NVDA | jq .

# Ask a question
curl -X POST http://localhost:8001/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What are Apple main risk factors?", "ticker": "AAPL"}'
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests (SQLite in-memory, MOCK_AZURE=true)
pytest tests/ -v --cov=app --cov-report=term-missing

# Lint
ruff check . --select=E,F,W --ignore=E501,E402,F401

# Run locally (mock Azure mode)
MOCK_AZURE=true DATABASE_URL="sqlite+aiosqlite:///./dev.db" uvicorn app.main:app --reload
```

## Architecture

```
POST /api/v1/ingest/{ticker}
    │
    ├─ 1. Resolve CIK from EDGAR company_tickers.json
    ├─ 2. Fetch company info from submissions API
    ├─ 3. Find latest 10-K accession number
    ├─ 4. Azure Doc Intelligence OCR on filing URL
    ├─ 5. XBRL structured metrics from companyfacts API
    ├─ 6. GPT-4 analysis (risk, sentiment, trends, highlights)
    ├─ 7. Chunk text → embed with text-embedding-3-small
    └─ 8. Persist all to PostgreSQL
```

## Roadmap

### YouTube Financial Methodology Analysis Templates

The pipeline is designed to support pluggable analysis templates that mirror popular financial YouTube methodologies. The `ANALYSIS_TEMPLATES` dict in `app/services/analyst.py` serves as the extensibility point.

#### Meet Kevin (Kevin Paffrath) Methodology
- **Revenue growth rate vs. P/E multiple** — prioritizes companies where revenue CAGR > P/E (similar to PEG ratio logic)
- **Moat assessment** — qualitative scoring of brand loyalty, switching costs, regulatory moats
- **Management credibility signals** — scan MD&A for forward guidance language vs. analyst consensus alignment
- **Macro sensitivity** — flag interest rate / inflation mentions and correlate to revenue guidance
- **Bull/Bear case framing** — generate explicit bull case (best case) and bear case (risk scenario) summaries

**Implementation plan**: Add `meet_kevin` template key → custom system prompt focusing on growth-vs-multiple framing, moat keywords, guidance language extraction.

#### Financial Education (Jeremy) Methodology
- **P/E vs. sector peers** — compare P/E to sector average, flag over/undervaluation
- **FCF yield** — free cash flow / market cap as primary valuation metric
- **Dividend sustainability** — payout ratio, FCF coverage of dividends, growth history
- **Debt analysis** — long-term debt trend, interest coverage ratio, net debt/EBITDA
- **Insider ownership** — flag significant insider buying/selling from proxy filings
- **10-year DCF sketch** — simple DCF narrative using stated growth rates from management guidance

**Implementation plan**: Add `financial_education` template key → system prompt emphasizing FCF yield, P/E peer comparison, debt safety metrics, and dividend sustainability signals.

#### Other Planned Templates
- **Aswath Damodaran / Academic** — intrinsic value DCF, WACC calculation, terminal growth rate sensitivity
- **Cathie Wood / ARK** — total addressable market (TAM) expansion narrative, disruption scoring
- **Charlie Munger / Value** — owner earnings, competitive advantage period (CAP), moat durability

### Additional Planned Features
- Batch ingest for S&P 500 universe
- Scheduled re-ingestion on new 10-K filings
- Historical multi-year XBRL trend extraction (beyond latest year)
- Sector/industry aggregate benchmarks
- PDF rendering + page-level citation in RAG answers

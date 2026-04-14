import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# BigInteger renders as INTEGER in SQLite (supports autoincrement) but BIGINT in PostgreSQL
_BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class Company(Base):
    """A publicly traded company tracked by CIK."""
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cik: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    sic_code: Mapped[str | None] = mapped_column(String(10))
    industry: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    filings: Mapped[list["Filing"]] = relationship(back_populates="company", cascade="all, delete-orphan")


class Filing(Base):
    """A single 10-K annual filing for a company."""
    __tablename__ = "filings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_of_report: Mapped[str | None] = mapped_column(String(20))   # e.g. "2023-12-31"
    accession_number: Mapped[str | None] = mapped_column(String(50))    # EDGAR accession
    filing_url: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)                  # full OCR text
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|processing|completed|failed
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(back_populates="filings")
    metrics: Mapped["FinancialMetrics | None"] = relationship(back_populates="filing", uselist=False, cascade="all, delete-orphan")
    analysis: Mapped["FilingAnalysis | None"] = relationship(back_populates="filing", uselist=False, cascade="all, delete-orphan")
    chunks: Mapped[list["DocChunk"]] = relationship(back_populates="filing", cascade="all, delete-orphan")


class FinancialMetrics(Base):
    """Structured financial metrics extracted from XBRL data + OCR tables."""
    __tablename__ = "financial_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Income statement
    revenue: Mapped[float | None] = mapped_column(Float)
    gross_profit: Mapped[float | None] = mapped_column(Float)
    operating_income: Mapped[float | None] = mapped_column(Float)
    net_income: Mapped[float | None] = mapped_column(Float)
    ebitda: Mapped[float | None] = mapped_column(Float)
    eps_basic: Mapped[float | None] = mapped_column(Float)
    eps_diluted: Mapped[float | None] = mapped_column(Float)
    rd_expense: Mapped[float | None] = mapped_column(Float)
    # Balance sheet
    total_assets: Mapped[float | None] = mapped_column(Float)
    total_liabilities: Mapped[float | None] = mapped_column(Float)
    total_equity: Mapped[float | None] = mapped_column(Float)
    long_term_debt: Mapped[float | None] = mapped_column(Float)
    cash: Mapped[float | None] = mapped_column(Float)
    # Cash flow
    operating_cash_flow: Mapped[float | None] = mapped_column(Float)
    capital_expenditures: Mapped[float | None] = mapped_column(Float)
    free_cash_flow: Mapped[float | None] = mapped_column(Float)
    # Share data
    shares_outstanding: Mapped[float | None] = mapped_column(Float)
    # Computed ratios (stored for fast retrieval)
    gross_margin_pct: Mapped[float | None] = mapped_column(Float)
    net_margin_pct: Mapped[float | None] = mapped_column(Float)
    operating_margin_pct: Mapped[float | None] = mapped_column(Float)
    debt_to_equity: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)

    filing: Mapped["Filing"] = relationship(back_populates="metrics")


class FilingAnalysis(Base):
    """GPT-4 generated analysis of the 10-K filing."""
    __tablename__ = "filing_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    risk_summary: Mapped[str | None] = mapped_column(Text)           # summarized risk factors
    mgmt_sentiment: Mapped[str | None] = mapped_column(String(20))   # bullish|neutral|cautious
    sentiment_rationale: Mapped[str | None] = mapped_column(Text)
    trend_narrative: Mapped[str | None] = mapped_column(Text)        # YoY trend in plain English
    key_highlights: Mapped[list | None] = mapped_column(JSON)        # top 3-5 bullet highlights
    model_used: Mapped[str | None] = mapped_column(String(100))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    filing: Mapped["Filing"] = relationship(back_populates="analysis")


class DocChunk(Base):
    """A text chunk from a 10-K filing, embedded for RAG retrieval."""
    __tablename__ = "doc_chunks"

    id: Mapped[int] = mapped_column(_BigIntPK, primary_key=True, autoincrement=True)
    filing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    section: Mapped[str | None] = mapped_column(String(100))   # risk_factors|mda|business|financials
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)      # ARRAY(Float) on Postgres, JSON elsewhere

    filing: Mapped["Filing"] = relationship(back_populates="chunks")

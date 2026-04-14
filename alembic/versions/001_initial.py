"""Initial schema: companies, filings, financial_metrics, filing_analyses, doc_chunks

Revision ID: c1d2e3f4a5b6
Revises:
Create Date: 2026-04-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1d2e3f4a5b6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cik", sa.String(20), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("sic_code", sa.String(10), nullable=True),
        sa.Column("industry", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cik"),
        sa.UniqueConstraint("ticker"),
    )
    op.create_index("ix_companies_cik", "companies", ["cik"])
    op.create_index("ix_companies_ticker", "companies", ["ticker"])

    op.create_table(
        "filings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("period_of_report", sa.String(20), nullable=True),
        sa.Column("accession_number", sa.String(50), nullable=True),
        sa.Column("filing_url", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_filings_company_id", "filings", ["company_id"])

    op.create_table(
        "financial_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("gross_profit", sa.Float(), nullable=True),
        sa.Column("operating_income", sa.Float(), nullable=True),
        sa.Column("net_income", sa.Float(), nullable=True),
        sa.Column("ebitda", sa.Float(), nullable=True),
        sa.Column("eps_basic", sa.Float(), nullable=True),
        sa.Column("eps_diluted", sa.Float(), nullable=True),
        sa.Column("rd_expense", sa.Float(), nullable=True),
        sa.Column("total_assets", sa.Float(), nullable=True),
        sa.Column("total_liabilities", sa.Float(), nullable=True),
        sa.Column("total_equity", sa.Float(), nullable=True),
        sa.Column("long_term_debt", sa.Float(), nullable=True),
        sa.Column("cash", sa.Float(), nullable=True),
        sa.Column("operating_cash_flow", sa.Float(), nullable=True),
        sa.Column("capital_expenditures", sa.Float(), nullable=True),
        sa.Column("free_cash_flow", sa.Float(), nullable=True),
        sa.Column("shares_outstanding", sa.Float(), nullable=True),
        sa.Column("gross_margin_pct", sa.Float(), nullable=True),
        sa.Column("net_margin_pct", sa.Float(), nullable=True),
        sa.Column("operating_margin_pct", sa.Float(), nullable=True),
        sa.Column("debt_to_equity", sa.Float(), nullable=True),
        sa.Column("roe", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filing_id"),
    )

    op.create_table(
        "filing_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_summary", sa.Text(), nullable=True),
        sa.Column("mgmt_sentiment", sa.String(20), nullable=True),
        sa.Column("sentiment_rationale", sa.Text(), nullable=True),
        sa.Column("trend_narrative", sa.Text(), nullable=True),
        sa.Column("key_highlights", postgresql.JSONB(), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filing_id"),
    )

    op.create_table(
        "doc_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("filing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section", sa.String(100), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_doc_chunks_filing_id", "doc_chunks", ["filing_id"])


def downgrade() -> None:
    op.drop_index("ix_doc_chunks_filing_id", table_name="doc_chunks")
    op.drop_table("doc_chunks")
    op.drop_table("filing_analyses")
    op.drop_table("financial_metrics")
    op.drop_index("ix_filings_company_id", table_name="filings")
    op.drop_table("filings")
    op.drop_index("ix_companies_ticker", table_name="companies")
    op.drop_index("ix_companies_cik", table_name="companies")
    op.drop_table("companies")

import uuid
from datetime import datetime
from pydantic import BaseModel


class CompanyOut(BaseModel):
    id: uuid.UUID
    cik: str
    ticker: str
    name: str
    sic_code: str | None
    industry: str | None
    model_config = {"from_attributes": True}


class FinancialMetricsOut(BaseModel):
    revenue: float | None
    gross_profit: float | None
    operating_income: float | None
    net_income: float | None
    ebitda: float | None
    eps_basic: float | None
    eps_diluted: float | None
    rd_expense: float | None
    total_assets: float | None
    total_liabilities: float | None
    total_equity: float | None
    long_term_debt: float | None
    cash: float | None
    operating_cash_flow: float | None
    capital_expenditures: float | None
    free_cash_flow: float | None
    shares_outstanding: float | None
    gross_margin_pct: float | None
    net_margin_pct: float | None
    operating_margin_pct: float | None
    debt_to_equity: float | None
    roe: float | None
    model_config = {"from_attributes": True}


class FilingAnalysisOut(BaseModel):
    risk_summary: str | None
    mgmt_sentiment: str | None
    sentiment_rationale: str | None
    trend_narrative: str | None
    key_highlights: list | None
    model_used: str | None
    generated_at: datetime | None
    model_config = {"from_attributes": True}


class FilingOut(BaseModel):
    id: uuid.UUID
    ticker: str
    company_name: str
    fiscal_year: int
    period_of_report: str | None
    status: str
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None
    model_config = {"from_attributes": True}

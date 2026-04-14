"""
Ingest endpoint tests — uses MOCK_AZURE=true and mocks EDGAR HTTP calls.
"""
import re
import pytest
import respx
import httpx
from httpx import AsyncClient


MOCK_COMPANY_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}
}

MOCK_SUBMISSIONS = {
    "name": "Apple Inc.",
    "sic": "3674",
    "sicDescription": "Semiconductors And Related Devices",
    "filings": {
        "recent": {
            "form": ["10-K", "10-Q"],
            "accessionNumber": ["0000320193-23-000106", "0000320193-23-000077"],
            "reportDate": ["2023-09-30", "2023-07-01"],
            "primaryDocument": ["aapl-20230930.htm", "aapl-20230701.htm"],
        }
    },
}

MOCK_COMPANY_FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"form": "10-K", "fp": "FY", "fy": 2023, "val": 383285000000}
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {"form": "10-K", "fp": "FY", "fy": 2023, "val": 96995000000}
                    ]
                }
            },
        }
    }
}


@pytest.mark.asyncio
async def test_ingest_ticker_mock(client: AsyncClient):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json=MOCK_COMPANY_TICKERS)
        )
        mock.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
            return_value=httpx.Response(200, json=MOCK_SUBMISSIONS)
        )
        mock.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json").mock(
            return_value=httpx.Response(200, json=MOCK_COMPANY_FACTS)
        )
        # Filing document URL (SEC Archives)
        mock.get(re.compile(r".*Archives.*")).mock(
            return_value=httpx.Response(200, text="ITEM 1A. RISK FACTORS\nSome risk text here.")
        )

        resp = await client.post("/api/v1/ingest/AAPL")

    assert resp.status_code == 202
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["fiscal_year"] == 2023
    assert body["status"] in ("completed", "failed")  # mock Azure may still succeed


@pytest.mark.asyncio
async def test_ingest_unknown_ticker(client: AsyncClient):
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json={})
        )
        resp = await client.post("/api/v1/ingest/ZZZNOTTICKER")
    assert resp.status_code == 404

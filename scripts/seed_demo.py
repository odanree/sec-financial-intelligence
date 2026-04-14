"""
Seed demo data for sec-financial-intelligence.

Ingests real 10-K data for AAPL, MSFT, NVDA via the live ingest pipeline.
Requires a running API server and valid Azure credentials.

Usage:
    python scripts/seed_demo.py [--base-url http://localhost:8000]
"""
import asyncio
import argparse
import httpx
import sys


DEMO_TICKERS = ["AAPL", "MSFT", "NVDA"]


async def ingest_ticker(client: httpx.AsyncClient, ticker: str, base_url: str) -> None:
    print(f"[{ticker}] Starting ingest...")
    resp = await client.post(
        f"{base_url}/api/v1/ingest/{ticker}",
        timeout=120.0,
    )
    if resp.status_code == 202:
        body = resp.json()
        print(f"[{ticker}] status={body['status']} fiscal_year={body['fiscal_year']}")
    elif resp.status_code == 409:
        print(f"[{ticker}] Already ingested (409 conflict) — skipping.")
    else:
        print(f"[{ticker}] ERROR {resp.status_code}: {resp.text}", file=sys.stderr)


async def main(base_url: str) -> None:
    async with httpx.AsyncClient() as client:
        # Check health first
        health = await client.get(f"{base_url}/health", timeout=5.0)
        if health.status_code != 200:
            print(f"API not healthy: {health.status_code}", file=sys.stderr)
            sys.exit(1)
        print(f"API healthy at {base_url}")

        for ticker in DEMO_TICKERS:
            await ingest_ticker(client, ticker, base_url)
            await asyncio.sleep(1.0)  # polite spacing

    print("\nSeed complete. Query with:")
    for ticker in DEMO_TICKERS:
        print(f"  curl {base_url}/api/v1/analysis/{ticker}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo tickers into sec-financial-intelligence")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()
    asyncio.run(main(args.base_url))

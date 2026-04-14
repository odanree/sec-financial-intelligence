import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if settings.app_env == "development"
            else structlog.processors.JSONRenderer(),
        ]
    )
    await init_db()
    logger.info("startup_complete", env=settings.app_env, mock_azure=settings.mock_azure)
    yield
    logger.info("shutdown_complete")


app = FastAPI(
    title="SEC Financial Intelligence API",
    version="0.1.0",
    description="10-K document ingestion, financial analysis, and RAG Q&A over SEC EDGAR filings.",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=str(request.url.path), error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


from app.routers import health, ingest, analysis, ask  # noqa: E402

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(analysis.router)
app.include_router(ask.router)

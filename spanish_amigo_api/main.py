import logging
import time
import uuid

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.logging_setup import configure_logging
from app.routers import adaptive, chat, progress
from app.services.health import check_database_health

settings = get_settings()
configure_logging()
logger = logging.getLogger("spanish-amigo-api")

app = FastAPI(
    title="SpanishAmigo API",
    description="Python API with LangGraph, Neon Postgres, and Gemini.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(progress.router)
app.include_router(chat.router)
app.include_router(adaptive.router)


@app.middleware("http")
async def add_request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.exception(
            "request_id=%s method=%s path=%s status=%s latency_ms=%s",
            request_id,
            request.method,
            request.url.path,
            500,
            elapsed_ms,
        )
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s latency_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get("/")
async def root():
    return {"message": "Hola! Welcome to the SpanishAmigo API.", "status": "online"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_ok, db_error = check_database_health(db)
    app_status = "healthy" if db_ok else "unhealthy"
    payload = {
        "status": app_status,
        "database": "connected" if db_ok else "disconnected",
        "ai_engine": f"{settings.GEMINI_PRIMARY_MODEL} ready",
    }
    if db_error:
        payload["database_error"] = db_error
    if db_ok:
        return payload
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)


@app.get("/status")
def status_alias(db: Session = Depends(get_db)):
    # Backward-compatible alias for existing clients.
    return health_check(db)

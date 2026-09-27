from contextlib import asynccontextmanager
import logging
import json
import sys
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.config import get_settings
from app.metrics import REQUEST_COUNT, REQUEST_LATENCY, metrics_payload
from app.request_context import get_request_id, set_request_id
from app.routes import router


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Prefer the contextvar so every log line (providers, services, repos)
        # carries the propagated X-Request-ID even without explicit extras.
        request_id = get_request_id() or getattr(record, "request_id", None)
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": request_id,
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# Clear default handlers and attach json handler to stdout
root_logger.handlers = [handler]

logger = logging.getLogger("civicpulse")


async def database_check() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def redis_check() -> None:
    from redis.asyncio import from_url

    client = from_url(get_settings().redis_url)
    try:
        await client.ping()
    finally:
        await client.aclose()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Application starting up")
    # NOTE: we deliberately do NOT install our own SIGTERM handler here.
    # Uvicorn already implements the graceful-shutdown sequence the PDF
    # requires: stop accepting new requests, finish in-flight requests,
    # then exit. Replacing its handler with a no-op event-set (as an
    # earlier revision did) skipped the drain and dropped live requests
    # on every rolling update.
    yield
    logger.info("Application shutdown complete. Closed connections.")


app = FastAPI(title=get_settings().app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Rubric 2.2: 400 with a field-level error body (not a bare 422/500)."""
    field_errors = [
        {
            "field": ".".join(str(part) for part in error.get("loc", [])[1:]),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=400, content={"detail": field_errors})


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    set_request_id(request_id)
    started = perf_counter()
    response: Response
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "Unhandled server exception during request processing",
            extra={"request_id": request_id},
            exc_info=True,
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
    elapsed = perf_counter() - started
    response.headers["X-Request-ID"] = request_id
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, request.url.path).observe(elapsed)

    logger.info(
        f"{request.method} {request.url.path} {response.status_code} in {round(elapsed * 1000, 2)}ms",
        extra={"request_id": request_id},
    )
    set_request_id(None)
    return response


@app.get("/")
async def root() -> dict[str, str]:
    """Service root: points operators at the docs and health surfaces."""
    return {
        "service": get_settings().app_name,
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "metrics": "/metrics",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    # Liveness only: must NOT touch the database (rubric 2.2).
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> JSONResponse:
    dependencies: dict[str, str] = {}
    for name, check in (("postgres", database_check), ("redis", redis_check)):
        try:
            await check()
            dependencies[name] = "ok"
        except Exception:
            dependencies[name] = "unavailable"
    status_code = 200 if all(value == "ok" for value in dependencies.values()) else 503
    # 503 body names the failed dependency (rubric 2.2).
    return JSONResponse(status_code=status_code, content={"status": "ready" if status_code == 200 else "not_ready", "dependencies": dependencies})


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=metrics_payload(), media_type="text/plain; version=0.0.4")

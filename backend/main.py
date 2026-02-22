"""
UnifyInbox — FastAPI Application Entry Point

Wires together:
  - All API routers (auth, feed, actions, platforms, webhooks)
  - WebSocket endpoint for live feed
  - Database lifecycle (init on startup, close on shutdown)
  - Redis lifecycle
  - CORS middleware
  - Request logging middleware
  - Rate limiting middleware
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import get_settings
from backend.core.database import init_db, close_db
from backend.core.redis import close_redis

# Import routers
from backend.api.auth import router as auth_router
from backend.api.feed import router as feed_router
from backend.api.actions import router as actions_router
from backend.api.platforms import router as platforms_router
from backend.api.webhooks import router as webhooks_router
from backend.api.websocket import router as ws_router, ws_manager
from backend.core.pubsub import start_subscriber, close_pubsub

settings = get_settings()

# --- Logging ---
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("unifyinbox")

# Background task handle for pub/sub subscriber
_pubsub_task = None


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global _pubsub_task
    # Startup
    logger.info("Starting UnifyInbox API...")
    await init_db()
    logger.info("Database initialized")

    # Start Redis Pub/Sub subscriber to relay Celery events to WebSockets
    import asyncio
    _pubsub_task = asyncio.create_task(start_subscriber(ws_manager))
    logger.info("Redis Pub/Sub subscriber started")

    logger.info(f"Environment: {settings.APP_ENV}")
    yield
    # Shutdown
    logger.info("Shutting down UnifyInbox API...")
    if _pubsub_task:
        _pubsub_task.cancel()
    await close_pubsub()
    await close_db()
    await close_redis()
    logger.info("Shutdown complete")


# --- App ---
app = FastAPI(
    title="UnifyInbox API",
    description="AI-native universal communication OS",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
)


# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request logging middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing."""
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)

    # Skip noisy health check logs
    if request.url.path != "/health":
        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} ({duration}ms)"
        )
    return response


# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler to prevent 500 leaking stack traces."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# --- Register routers ---
app.include_router(auth_router)
app.include_router(feed_router)
app.include_router(actions_router)
app.include_router(platforms_router)
app.include_router(webhooks_router)
app.include_router(ws_router)


# --- Health check ---
@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "ok",
        "service": "unifyinbox-api",
        "version": "1.0.0",
    }


@app.get("/", tags=["system"])
async def root():
    """Root endpoint."""
    return {
        "service": "UnifyInbox API",
        "version": "1.0.0",
        "docs": "/docs",
    }

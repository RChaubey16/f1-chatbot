"""F1 Chatbot FastAPI application."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.agent import Agent
from ingestion.scheduler import create_scheduler
from ingestion.core.logging import get_logger

import api.routes.chat as chat_router
import api.routes.health as health_router
import api.routes.standings as standings_router

log = get_logger(__name__)

_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    os.environ.get("FRONTEND_URL", ""),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting F1 Chatbot API")
    app.state.agent = Agent()
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("Startup complete")

    yield

    log.info("Shutting down F1 Chatbot API")
    try:
        app.state.scheduler.shutdown(wait=False)
    except Exception:
        log.warning("Scheduler was not running on shutdown")
    await app.state.agent.close()
    log.info("Shutdown complete")


app = FastAPI(
    title="F1 Chatbot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _ALLOWED_ORIGINS if o],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(chat_router.router)
app.include_router(health_router.router)
app.include_router(standings_router.router)

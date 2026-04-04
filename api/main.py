"""F1 Chatbot FastAPI application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from agent.agent import Agent
from ingestion.scheduler import create_scheduler
from ingestion.core.logging import get_logger

import api.routes.chat as chat_router
import api.routes.health as health_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("Starting F1 Chatbot API")
    app.state.agent = Agent()
    scheduler = create_scheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    log.info("Startup complete")

    yield

    # Shutdown
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

app.include_router(chat_router.router)
app.include_router(health_router.router)

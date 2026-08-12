from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import async_session_maker, engine
from app.routers import (
    agent,
    auth,
    coldstart,
    discussions,
    judge,
    knowledge,
    learning,
    notifications,
    problems,
    progress,
    recommendations,
    review,
    solutions,
    submissions,
    wrongbook,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize singletons required by the agent layer.
    import app.services.openai_service as openai_module

    # late import to set module-level singleton
    import app.services.rag as rag_module
    from app.services.openai_service import OpenAIService
    from app.services.rag import RAGService

    openai_module.openai_service = OpenAIService()
    rag_module.rag_service = RAGService(async_session_maker, openai_module.openai_service)

    logger.info("app lifespan started: openai_service + rag_service ready")
    yield
    await engine.dispose()
    logger.info("app lifespan stopped: engine disposed")


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(knowledge.router, prefix=settings.API_V1_STR)
app.include_router(problems.router, prefix=settings.API_V1_STR)
app.include_router(agent.router, prefix=settings.API_V1_STR)
app.include_router(learning.path_router, prefix=settings.API_V1_STR)
app.include_router(learning.daily_router, prefix=settings.API_V1_STR)
app.include_router(progress.router, prefix=settings.API_V1_STR)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(discussions.router, prefix=settings.API_V1_STR)
app.include_router(solutions.router, prefix=settings.API_V1_STR)
app.include_router(wrongbook.router, prefix=settings.API_V1_STR)
app.include_router(submissions.router, prefix=settings.API_V1_STR)
app.include_router(coldstart.router, prefix=settings.API_V1_STR)
app.include_router(review.router, prefix=settings.API_V1_STR)
app.include_router(judge.router, prefix=settings.API_V1_STR)
app.include_router(notifications.router, prefix=settings.API_V1_STR)
app.include_router(recommendations.router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {"message": "算法教练平台 API", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}

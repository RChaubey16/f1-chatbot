"""Pydantic request/response models for the F1 Chatbot API."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    max_chunks: int = 6


class Source(BaseModel):
    content_type: str
    source: str
    metadata: dict


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
    intent: str
    latency_ms: float


class DriverStanding(BaseModel):
    position: int
    driver: str
    team: str
    points: float


class ConstructorStanding(BaseModel):
    position: int
    team: str
    points: float

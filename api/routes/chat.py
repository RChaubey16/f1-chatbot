import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.schemas import ChatRequest, ChatResponse, Source
from ingestion.core.logging import get_logger

log = get_logger(__name__)
router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    agent = request.app.state.agent
    try:
        result = await agent.run_sync(body.query, max_chunks=body.max_chunks)
    except Exception as exc:
        log.error("chat endpoint error", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(
        answer=result["answer"],
        sources=[Source(**s) for s in result["sources"]],
        intent=result["intent"],
        latency_ms=result["latency_ms"],
    )


@router.get("/chat/stream")
async def chat_stream(request: Request, query: str) -> StreamingResponse:
    agent = request.app.state.agent

    async def event_generator():
        async for token in agent.run(query):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

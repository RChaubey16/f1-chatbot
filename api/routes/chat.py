from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from api.schemas import ChatRequest, ChatResponse, Source
import json

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    agent = request.app.state.agent
    result = await agent.run_sync(body.query, max_chunks=body.max_chunks)
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

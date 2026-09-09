"""
HTTP Streaming implementation for FastAPI:
Uses StreamingResponse with text/event-stream, asyncio.Queue, and asyncio.to_thread
to deliver real-time structured progress updates while keeping Agent Core execution synchronous.
"""
import asyncio
import logging
import re
import time
import uuid
from typing import AsyncGenerator, Optional, List
from fastapi import Request
from fastapi.responses import StreamingResponse

from src.identity import resolve_principal
from src.agent_core.events import (
    StreamEvent,
    AgentEventEmitter,
    AgentPhase,
)
from src.api.schemas import ChatRequest, ChatResponse
from src.api.chat_service import get_chat_execution_service

logger = logging.getLogger(__name__)

_QUEUE_DONE = object()


def chunk_answer_text(text: str, target_chunk_len: int = 35) -> List[str]:
    """
    Split final verified answer into natural word-bounded typing chunks.
    Strict invariant: "".join(chunks) == text.
    """
    if not text:
        return []
    tokens = re.findall(r"\S+\s*", text)
    if not tokens:
        return [text]

    chunks = []
    current_chunk = []
    current_len = 0
    for tok in tokens:
        current_chunk.append(tok)
        current_len += len(tok)
        if current_len >= target_chunk_len:
            chunks.append("".join(current_chunk))
            current_chunk = []
            current_len = 0
    if current_chunk:
        chunks.append("".join(current_chunk))
    return chunks


async def chat_stream_generator(
    request: ChatRequest,
    client_request: Request,
    chunk_delay: float = 0.015,
    heartbeat_interval: float = 10.0,
) -> AsyncGenerator[str, None]:
    """
    Async generator that consumes structured events from the Agent execution thread
    and yields SSE formatted strings (text/event-stream).
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    principal = resolve_principal()
    user_id = principal.user_id
    conv_id = request.conversation_id or str(uuid.uuid4())
    request.conversation_id = conv_id

    # 1. Immediate TTFE feedback: Emit initial meta and UNDERSTAND
    meta_event = StreamEvent(
        type="meta",
        conversation_id=conv_id,
        data={"conversation_id": conv_id, "user_id": user_id},
    )
    yield meta_event.to_sse()

    understand_event = StreamEvent(
        type="phase",
        conversation_id=conv_id,
        phase=AgentPhase.UNDERSTAND,
        label="Đang hiểu yêu cầu của bạn...",
    )
    yield understand_event.to_sse()

    # Callback bridging sync worker thread to async queue
    def on_event(event: StreamEvent):
        loop.call_soon_threadsafe(queue.put_nowait, (event, None, None))

    event_emitter = AgentEventEmitter(
        callback=on_event,
        conversation_id=conv_id,
    )

    # Worker thread execution
    def worker():
        try:
            service = get_chat_execution_service()
            # Suppress re-emitting duplicate initial understand in chat service
            resp = service.process(request, event_sink=event_emitter)
            loop.call_soon_threadsafe(queue.put_nowait, (_QUEUE_DONE, resp, None))
        except Exception as e:
            logger.error(f"Error in chat stream worker: {e}", exc_info=True)
            loop.call_soon_threadsafe(queue.put_nowait, (_QUEUE_DONE, None, e))

    worker_task = asyncio.to_thread(worker)
    asyncio.create_task(worker_task)

    chat_response: Optional[ChatResponse] = None
    already_streamed: bool = False

    try:
        while True:
            # Check client disconnect
            if await client_request.is_disconnected():
                logger.info("Client disconnected from stream.")
                return

            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                if await client_request.is_disconnected():
                    logger.info("Client disconnected during heartbeat wait.")
                    return
                # Emit ping heartbeat
                yield StreamEvent(type="ping", timestamp=time.time()).to_sse()
                continue

            event, result, exc = item
            if event is _QUEUE_DONE:
                if exc:
                    yield StreamEvent(
                        type="error",
                        conversation_id=conv_id,
                        data={
                            "code": "INTERNAL_ERROR",
                            "message": "Đã xảy ra lỗi khi xử lý yêu cầu. Vui lòng thử lại sau.",
                        },
                    ).to_sse()
                    return
                chat_response = result
                break
            else:
                # Do not re-emit redundant duplicate meta or understand from beginning
                if event.type == "phase" and event.phase == AgentPhase.UNDERSTAND:
                    continue
                if event.type == "answer_delta":
                    already_streamed = True
                yield event.to_sse()

    except asyncio.CancelledError:
        logger.info("Chat stream generator cancelled.")
        return

    # Post-execution streaming: evidence truth invariant enforced
    if not chat_response:
        return

    # If needs user clarification
    if chat_response.status == "NEEDS_USER_INPUT" and chat_response.clarification_question:
        yield StreamEvent(
            type="clarification",
            conversation_id=conv_id,
            goal_id=chat_response.goal_id,
            data={
                "goal_id": chat_response.goal_id,
                "question": chat_response.clarification_question,
                "options": chat_response.clarification_options or [],
            },
        ).to_sse()

        if not already_streamed:
            yield StreamEvent(
                type="answer_start",
                conversation_id=conv_id,
                goal_id=chat_response.goal_id,
                data={},
            ).to_sse()

            chunks = chunk_answer_text(chat_response.answer)
            for chunk in chunks:
                if await client_request.is_disconnected():
                    return
                yield StreamEvent(
                    type="answer_delta",
                    conversation_id=conv_id,
                    goal_id=chat_response.goal_id,
                    data={"delta": chunk},
                ).to_sse()
                if chunk_delay > 0:
                    await asyncio.sleep(chunk_delay)

        yield StreamEvent(
            type="done",
            conversation_id=conv_id,
            goal_id=chat_response.goal_id,
            data={
                "status": "NEEDS_USER_INPUT",
                "conversation_id": conv_id,
                "goal_id": chat_response.goal_id,
                "category": chat_response.category,
            },
        ).to_sse()
        return

    # Final verified answer streaming
    if not already_streamed:
        yield StreamEvent(
            type="answer_start",
            conversation_id=conv_id,
            goal_id=chat_response.goal_id,
            data={},
        ).to_sse()

        chunks = chunk_answer_text(chat_response.answer)
        for chunk in chunks:
            if await client_request.is_disconnected():
                return
            yield StreamEvent(
                type="answer_delta",
                conversation_id=conv_id,
                goal_id=chat_response.goal_id,
                data={"delta": chunk},
            ).to_sse()
            if chunk_delay > 0:
                await asyncio.sleep(chunk_delay)

    # Emit sources only after answer verification and completion
    if chat_response.sources:
        yield StreamEvent(
            type="sources",
            conversation_id=conv_id,
            goal_id=chat_response.goal_id,
            data={"items": [s.model_dump() for s in chat_response.sources]},
        ).to_sse()

    # Emit done event
    yield StreamEvent(
        type="done",
        conversation_id=conv_id,
        goal_id=chat_response.goal_id,
        data={
            "status": chat_response.status or "COMPLETED",
            "conversation_id": conv_id,
            "goal_id": chat_response.goal_id,
            "category": chat_response.category,
        },
    ).to_sse()


async def create_chat_stream_response(
    request: ChatRequest,
    raw_request: Request,
    chunk_delay: float = 0.015,
) -> StreamingResponse:
    """Create a FastAPI StreamingResponse for HTTP text/event-stream."""
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        chat_stream_generator(
            request=request,
            client_request=raw_request,
            chunk_delay=chunk_delay,
        ),
        media_type="text/event-stream",
        headers=headers,
    )

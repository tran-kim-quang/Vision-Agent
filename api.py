import json
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage
from pydantic import BaseModel

from agents.supervisor_agent import build_supervisor

_REDIS_URL   = os.getenv("REDIS_URL", "")
_UPLOAD_DIR  = Path("assets/uploads")
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


# ── Startup / shutdown ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    checkpointer = None

    if _REDIS_URL:
        try:
            from langgraph.checkpoint.redis.aio import AsyncRedisSaver
            checkpointer = AsyncRedisSaver.from_conn_string(_REDIS_URL)
            await checkpointer.setup()
            print(f"[memory] Redis checkpointer connected → {_REDIS_URL}")
        except Exception as exc:
            print(f"[memory] Redis unavailable ({exc}), falling back to MemorySaver")
            checkpointer = None

    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
        print("[memory] Using in-memory checkpointer (sessions lost on restart)")

    app.state.supervisor = build_supervisor(checkpointer=checkpointer)
    app.state.checkpointer = checkpointer
    yield

    if hasattr(checkpointer, "aclose"):
        await checkpointer.aclose()


app = FastAPI(title="Visual Agent API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request model ──────────────────────────────────────────────────────────────
class InferenceRequest(BaseModel):
    message: str
    session_id: str = "default"


# ── Helpers ────────────────────────────────────────────────────────────────────
def _effective_agent(metadata: dict) -> str:
    checkpoint_ns: str = metadata.get("langgraph_checkpoint_ns", "")
    if checkpoint_ns:
        return checkpoint_ns.split("|")[0].split(":")[0]
    return metadata.get("langgraph_node", "supervisor")


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return ""


# ── SSE stream ─────────────────────────────────────────────────────────────────
async def event_stream(message: str, session_id: str, supervisor):
    config = {
        "recursion_limit": 50,
        "configurable": {"thread_id": session_id},
    }
    seen_agents: set[str] = set()
    supervisor_text_sent = False

    def _start(agent: str) -> str | None:
        if agent not in seen_agents:
            seen_agents.add(agent)
            return f"data: {json.dumps({'type': 'agent_start', 'agent': agent})}\n\n"
        return None

    try:
        async for raw in supervisor.astream(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], str):
                mode, payload = raw
            elif isinstance(raw, tuple) and len(raw) == 2:
                mode, payload = "messages", raw
            elif isinstance(raw, dict):
                mode, payload = "updates", raw
            else:
                continue

            if mode == "messages":
                chunk, metadata = payload
                agent = _effective_agent(metadata)
                start = _start(agent)
                if start:
                    yield start

                if isinstance(chunk, ToolMessage):
                    tool_name = chunk.name or ""
                    if "transfer" in tool_name.lower():
                        yield f"data: {json.dumps({'type': 'handoff', 'agent': agent, 'tool': tool_name})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'tool_result', 'agent': agent, 'tool': tool_name, 'content': str(chunk.content)[:1000]})}\n\n"

                elif isinstance(chunk, AIMessageChunk):
                    text = _extract_text(chunk.content)
                    if text:
                        if agent == "supervisor":
                            supervisor_text_sent = True
                        yield f"data: {json.dumps({'type': 'token', 'agent': agent, 'content': text})}\n\n"
                    for tc in (chunk.tool_call_chunks or []):
                        if tc.get("name") and "transfer" not in tc["name"].lower():
                            yield f"data: {json.dumps({'type': 'tool_call', 'agent': agent, 'tool': tc['name'], 'args': str(tc.get('args', ''))})}\n\n"

            elif mode == "updates" and not supervisor_text_sent:
                for node, state in (payload or {}).items():
                    if node != "supervisor" or not isinstance(state, dict):
                        continue
                    for msg in reversed(state.get("messages", [])):
                        text = _extract_text(getattr(msg, "content", ""))
                        has_tool_calls = bool(getattr(msg, "tool_calls", None))
                        if text and not has_tool_calls:
                            supervisor_text_sent = True
                            start = _start("supervisor")
                            if start:
                                yield start
                            yield f"data: {json.dumps({'type': 'token', 'agent': 'supervisor', 'content': text})}\n\n"
                            break

    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    yield f"data: {json.dumps({'type': 'done', 'supervisor_responded': supervisor_text_sent})}\n\n"


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.post("/api/stream")
async def stream_inference(request: InferenceRequest, req: Request):
    return StreamingResponse(
        event_stream(request.message, request.session_id, req.app.state.supervisor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "image.jpg").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        ext = ".jpg"
    dest = _UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"path": str(dest.resolve())}


@app.get("/health")
async def health(req: Request):
    checkpointer_type = type(req.app.state.checkpointer).__name__
    return {"status": "ok", "memory": checkpointer_type}

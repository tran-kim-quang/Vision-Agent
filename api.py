import json
import os
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, ToolMessage
from pydantic import BaseModel

_UPLOAD_DIR = Path("assets/uploads")
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

from agents.supervisor_agent import supervisor

app = FastAPI(title="Visual Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class InferenceRequest(BaseModel):
    message: str


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


async def event_stream(message: str):
    config = {"recursion_limit": 50}
    seen_agents: set[str] = set()
    supervisor_text_sent = False

    def _start(agent: str) -> str | None:
        if agent not in seen_agents:
            seen_agents.add(agent)
            return f"data: {json.dumps({'type': 'agent_start', 'agent': agent})}\n\n"
        return None

    try:
        # Use both modes: messages for token streaming, updates to capture
        # supervisor's final text when it doesn't stream tokens itself.
        async for raw in supervisor.astream(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            stream_mode=["messages", "updates"],
        ):
            # LangGraph wraps multi-mode events as (mode_name, payload).
            # Be defensive: handle both wrapped and unwrapped formats.
            if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[0], str):
                mode, payload = raw
            elif isinstance(raw, tuple) and len(raw) == 2:
                # Plain (chunk, metadata) — messages mode without wrapper
                mode, payload = "messages", raw
            elif isinstance(raw, dict):
                # Plain update dict
                mode, payload = "updates", raw
            else:
                continue

            # ── Token streaming ────────────────────────────────────────
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

            # ── State updates — supervisor fallback ────────────────────
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

    # Tell the frontend whether supervisor produced its own text so it can
    # decide whether to use the last agent's response as a fallback.
    yield f"data: {json.dumps({'type': 'done', 'supervisor_responded': supervisor_text_sent})}\n\n"


@app.post("/api/stream")
async def stream_inference(request: InferenceRequest):
    return StreamingResponse(
        event_stream(request.message),
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
async def health():
    return {"status": "ok"}

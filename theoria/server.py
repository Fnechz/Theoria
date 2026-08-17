"""FastAPI local web server for Theoria."""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from theoria import chats as chat_store
from theoria.config import rag_db_path, static_dir
from theoria.i18n.shona import localize_ui
from theoria.inference import InferenceConfig, stream_chat, warm_up
from theoria.pipeline import CHITCHAT_MAX_TOKENS, ask, check_proof, prepare
from theoria.rag.embed import build_index
from theoria.router import Intent


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Load the model up front so the first user query is not the one that waits.
    with contextlib.suppress(Exception):
        warm_up()
    yield


app = FastAPI(
    title="Theoria",
    description="Offline math & science assistant",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    query: str
    use_rag: bool = True
    lang: str = "en"
    chat_id: str | None = None
    think: bool = False
    # Filled by the UI after a photo attachment is OCR'd; merged into the
    # prompt server-side so the chat behaves like a multimodal assistant.
    attachment_text: str | None = None
    attachment_name: str | None = None


def _effective_query(req: QueryRequest) -> str:
    if not req.attachment_text:
        return req.query
    prefix = req.query.strip() or "Please solve the problem in the attached photo."
    return (
        f"{prefix}\n\n[Attached photo"
        f"{f' {req.attachment_name}' if req.attachment_name else ''}"
        f" — transcribed text]:\n{req.attachment_text.strip()}"
    )


def _inference_config(req: QueryRequest, intent: Intent) -> InferenceConfig:
    cfg = InferenceConfig()
    if req.think:
        # Reasoning tokens are hidden from the answer budget, so widen both.
        cfg.enable_thinking = True
        cfg.max_tokens = 2048
        cfg.timeout_s = 360
    if intent == Intent.CHITCHAT and not req.think:
        cfg.max_tokens = CHITCHAT_MAX_TOKENS
    return cfg


class QueryResponse(BaseModel):
    answer: str
    intent: str = "math"
    sympy_result: str | None = None
    sympy_error: str | None = None
    counterexample: dict | None = None
    lean: dict | None = None
    sources: list[dict]
    tokens_per_second: float | None = None
    elapsed_s: float | None = None
    backend: str = ""


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir() / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "rag_indexed": rag_db_path().is_file(),
    }


@app.get("/api/i18n/{lang}")
def i18n_strings(lang: str) -> dict:
    return localize_ui("sn" if lang == "sn" else "en")


@app.post("/api/ask", response_model=QueryResponse)
def api_ask(req: QueryRequest) -> QueryResponse:
    cfg = _inference_config(req, Intent.GENERAL) if req.think else None
    result = ask(_effective_query(req), use_rag=req.use_rag, lang=req.lang, config=cfg)
    return QueryResponse(
        answer=result.answer,
        intent=result.intent,
        sympy_result=result.sympy_result,
        sympy_error=result.sympy_error,
        counterexample=result.counterexample,
        lean=result.lean,
        sources=result.sources,
        tokens_per_second=result.tokens_per_second,
        elapsed_s=result.elapsed_s,
        backend=result.backend,
    )


@app.post("/api/ask/stream")
def api_ask_stream(req: QueryRequest) -> StreamingResponse:
    """Server-sent events: meta first (intent, SymPy, sources), then token
    deltas, then a done event with throughput."""

    def event(payload: dict) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    def generate():
        query = _effective_query(req)
        history = chat_store.recent_history(req.chat_id) if req.chat_id else None
        ctx = prepare(query, use_rag=req.use_rag, lang=req.lang, history=history)

        if req.chat_id:
            user_meta = (
                {"attachment": req.attachment_name} if req.attachment_name else None
            )
            chat_store.append_message(req.chat_id, "user", req.query, meta=user_meta)

        meta_payload = {
            "type": "meta",
            "intent": ctx["intent"].value,
            "sympy_result": ctx["sympy_result"],
            "sympy_error": ctx["sympy_error"],
            "counterexample": ctx["counterexample"],
            "sources": ctx["sources"],
        }
        yield event(meta_payload)

        def persist_answer(answer: str, lean_info: dict | None = None) -> None:
            if not req.chat_id or not answer:
                return
            meta = {k: v for k, v in meta_payload.items() if k != "type" and v}
            if lean_info:
                meta["lean"] = lean_info
            chat_store.append_message(req.chat_id, "assistant", answer, meta=meta or None)

        if ctx["canned_answer"]:
            yield event({"type": "delta", "text": ctx["canned_answer"]})
            yield event({"type": "done", "tokens_per_second": None})
            persist_answer(ctx["canned_answer"])
            return

        cfg = _inference_config(req, ctx["intent"])

        try:
            answer_parts: list[str] = []
            for chunk in stream_chat(ctx["messages"], config=cfg):
                if chunk["type"] == "think":
                    yield event({"type": "think", "text": chunk["text"]})
                elif chunk["type"] == "delta":
                    answer_parts.append(chunk["text"])
                    yield event({"type": "delta", "text": chunk["text"]})
                else:
                    answer = "".join(answer_parts)
                    lean_info = None
                    # Lean check runs after decoding finished (never during),
                    # so its RAM spike doesn't stack on the KV cache.
                    if ctx["intent"] == Intent.PROVE:
                        yield event({"type": "verifying", "what": "lean"})
                        lean_info = check_proof(answer)
                        if lean_info is not None:
                            yield event({"type": "lean", **lean_info})
                    timings = chunk.get("timings", {})
                    yield event(
                        {
                            "type": "done",
                            "tokens_per_second": timings.get("predicted_per_second"),
                        }
                    )
                    persist_answer(answer, lean_info)
        except Exception as exc:  # noqa: BLE001 — surface errors to the UI
            fallback = (
                f"Exact result (SymPy): {ctx['sympy_result']}"
                if ctx["sympy_result"]
                else f"Inference failed: {exc}"
            )
            yield event({"type": "error", "message": fallback})

    return StreamingResponse(generate(), media_type="text/event-stream")


class ChatCreate(BaseModel):
    title: str = "New chat"


class ChatRename(BaseModel):
    title: str


@app.get("/api/chats")
def api_list_chats() -> dict:
    return {"chats": chat_store.list_chats()}


@app.post("/api/chats")
def api_create_chat(req: ChatCreate) -> dict:
    return chat_store.create_chat(req.title)


@app.get("/api/chats/{chat_id}")
def api_get_chat(chat_id: str) -> dict:
    chat = chat_store.get_chat(chat_id)
    return chat if chat else {"error": "not found"}


@app.patch("/api/chats/{chat_id}")
def api_rename_chat(chat_id: str, req: ChatRename) -> dict:
    chat_store.rename_chat(chat_id, req.title)
    return {"ok": True}


@app.delete("/api/chats/{chat_id}")
def api_delete_chat(chat_id: str) -> dict:
    return {"ok": chat_store.delete_chat(chat_id)}


class ExportRequest(BaseModel):
    filename: str
    content: str
    kind: str = "tex"  # tex | html


@app.post("/api/export")
def api_export(req: ExportRequest) -> Response:
    """Crash-safe file download for Cursor/Electron: no window.print(), no
    client-side blob URLs. Returns Content-Disposition: attachment."""
    name = (req.filename or "theoria-document").replace("/", "_").replace("\\", "_")
    if req.kind == "html":
        if not name.endswith(".html"):
            name += ".html"
        body = req.content.encode("utf-8")
        media = "text/html; charset=utf-8"
    else:
        if not name.endswith(".tex"):
            name += ".tex"
        body = req.content.encode("utf-8")
        media = "application/x-tex; charset=utf-8"
    return Response(
        content=body,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Content-Length": str(len(body)),
        },
    )


@app.post("/api/export/form")
def api_export_form(
    filename: str = Form(...),
    content: str = Form(...),
    kind: str = Form("tex"),
) -> Response:
    """Same as /api/export but accepts multipart/form — useful as a plain
    HTML form target when fetch downloads misbehave in embedded browsers."""
    return api_export(ExportRequest(filename=filename, content=content, kind=kind))


@app.post("/api/upload-pdf")
async def api_upload_pdf(file: UploadFile) -> dict:
    from theoria.rag.pdf import ingest_pdf

    content = await file.read()
    result = ingest_pdf(file.filename or "document.pdf", content)
    return result


@app.post("/api/upload-photo")
async def api_upload_photo(file: UploadFile) -> dict:
    """OCR a homework photo in a throwaway subprocess. Returns the extracted
    text for the user to review/correct in the composer — does NOT auto-ask."""
    import tempfile
    from pathlib import Path

    from theoria.ocr import extract_text

    suffix = Path(file.filename or "photo.jpg").suffix or ".jpg"
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        result = extract_text(tmp_path)
    except Exception as exc:  # noqa: BLE001 — report to the UI, don't 500
        return {"ok": False, "error": str(exc)}
    finally:
        tmp_path.unlink(missing_ok=True)
    return {"ok": True, **result}


@app.get("/api/documents")
def api_documents() -> dict:
    from theoria.rag.pdf import list_documents

    return {"documents": list_documents()}


@app.post("/api/build-index")
def api_build_index() -> dict:
    count = build_index()
    return {"indexed": count}


static_path = static_dir()
if static_path.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run("theoria.server:app", host="127.0.0.1", port=8080, reload=False)


if __name__ == "__main__":
    main()

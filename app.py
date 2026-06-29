"""FastAPI server for the offline Lawyer Assistant."""
import os
import shutil

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import chat
import config
import llm
import memory
import rag
import telephony

app = FastAPI(title="Lexora — Offline Lawyer Assistant")

STATIC_DIR = os.path.join(config.BASE_DIR, "static")


@app.middleware("http")
async def no_cache(request, call_next):
    """Disable browser caching so updated UI assets always load (local app)."""
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ----------------------------------------------------------------- models
class ChatIn(BaseModel):
    client_id: str = "general"
    message: str


class ClientIn(BaseModel):
    name: str
    case_type: str = "General"
    case_status: str = "open"
    summary: str = ""
    email: str = ""


class ClientUpdate(BaseModel):
    name: str | None = None
    case_type: str | None = None
    case_status: str | None = None
    summary: str | None = None
    email: str | None = None


class CallIn(BaseModel):
    client_id: str = "general"
    transcript: str


class LiveIn(BaseModel):
    client_id: str | None = "general"
    text: str
    speaker: str = "client"
    pending: list[str] = []


# ----------------------------------------------------------------- API
@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.status()}


@app.post("/api/chat")
def api_chat(body: ChatIn):
    return chat.respond(body.client_id, body.message)


@app.get("/api/clients")
def api_clients():
    return {"clients": memory.list_clients()}


@app.post("/api/clients")
def api_create_client(body: ClientIn):
    return memory.create_client(body.name, body.case_type, body.case_status,
                                body.summary, body.email)


@app.patch("/api/clients/{client_id}")
def api_update_client(client_id: str, body: ClientUpdate):
    c = memory.update_client(client_id, **body.dict())
    return c or JSONResponse({"error": "not found"}, status_code=404)


@app.delete("/api/clients/{client_id}")
def api_delete_client(client_id: str):
    ok = memory.delete_client(client_id)
    return JSONResponse({"deleted": ok}, status_code=200 if ok else 404)


@app.get("/api/clients/{client_id}/messages")
def api_messages(client_id: str):
    return {"messages": memory.get_messages(client_id)}


@app.delete("/api/clients/{client_id}/messages")
def api_clear_messages(client_id: str):
    return {"cleared": memory.clear_messages(client_id)}


@app.get("/api/clients/{client_id}/graph")
def api_graph(client_id: str):
    return memory.get_graph(client_id)


@app.get("/api/clients/{client_id}/statements")
def api_statements(client_id: str):
    return {"statements": memory.get_statements(client_id)}


@app.get("/api/clients/{client_id}/calls")
def api_calls(client_id: str):
    return {"calls": memory.get_calls(client_id)}


@app.post("/api/call")
def api_process_call(body: CallIn):
    return chat.process_call(body.client_id, body.transcript)


@app.post("/api/live")
def api_live(body: LiveIn):
    return chat.live_turn(body.client_id, body.text, body.speaker, body.pending)


# ----------------------------------------------------------------- Twilio telephony
def _base_url(request: Request):
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    # derive from forwarded headers (ngrok) or the request itself
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    proto = request.headers.get("x-forwarded-proto", "https")
    return f"{proto}://{host}" if host else str(request.base_url).rstrip("/")


@app.post("/voice")
async def twilio_voice(request: Request):
    form = await request.form()
    call_sid = form.get("CallSid", "")
    telephony.on_call_start(call_sid)
    xml = telephony.voice_twiml(_base_url(request))
    return Response(content=xml, media_type="application/xml")


@app.post("/transcription")
async def twilio_transcription(request: Request):
    form = await request.form()
    event = form.get("TranscriptionEvent", "")
    if event == "transcription-content":
        telephony.enqueue_transcription(
            form.get("CallSid", ""), form.get("Track", "inbound_track"),
            form.get("TranscriptionData", ""), form.get("Final", "true"))
    elif event in ("transcription-stopped",):
        telephony.on_call_end(form.get("CallSid", ""))
    return Response(status_code=204)


@app.post("/voice/status")
async def twilio_voice_status(request: Request):
    form = await request.form()
    telephony.on_call_end(form.get("CallSid", ""))
    return Response(content=telephony.hangup_twiml(), media_type="application/xml")


@app.get("/api/telephony/live")
def api_telephony_live():
    return telephony.live_state()


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...), client_id: str = Form("general")):
    dest = os.path.join(config.UPLOAD_DIR, file.filename)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        n = rag.ingest_pdf(dest, file.filename, client_id=client_id)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=500)
    memory.log_activity(client_id, "Document uploaded", f"{file.filename} ({n} chunks)")
    return {"filename": file.filename, "chunks": n, "client_id": client_id}


@app.get("/api/documents")
def api_documents():
    return {"documents": rag.list_documents()}


@app.get("/api/dashboard")
def api_dashboard():
    return memory.dashboard()


# ----------------------------------------------------------------- static
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="localhost", port=1000, reload=False)

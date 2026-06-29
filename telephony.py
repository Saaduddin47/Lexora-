"""Twilio telephony: bridge a real two-phone call and transcribe it live into memory.

Flow:
  Lawyer dials the Twilio number  ->  /voice returns TwiML that
     (a) <Start><Transcription> streams both legs' text to /transcription, and
     (b) <Dial>s the client's phone, bridging the two real phones.
  Each finalised utterance is committed to memory + the knowledge graph in real
  time (auto-creating the client from their spoken name).  Audio rides Twilio;
  all AI (memory, graph, contradictions, summary) stays local.
"""
import json
import queue
import threading

import chat
import config

_lock = threading.RLock()
_sessions = {}        # call_sid -> session dict
_latest_sid = None
_q = queue.Queue()
_worker_started = False


def _blank_session(call_sid):
    return {"call_sid": call_sid, "client_id": None, "client_name": None,
            "pending": [], "transcript": [], "contradictions": [],
            "graph_nodes": 0, "summary": "", "action_items": [],
            "active": True, "ended": False}


def _get(call_sid):
    s = _sessions.get(call_sid)
    if s is None:
        s = _blank_session(call_sid)
        _sessions[call_sid] = s
    return s


# ----------------------------------------------------------------- TwiML
def voice_twiml(base_url):
    """TwiML for an inbound call: start live transcription, then bridge to client."""
    cb = f"{base_url}/transcription"
    action = f"{base_url}/voice/status"
    client = config.TWILIO_CLIENT_NUMBER
    caller = f' callerId="{config.TWILIO_NUMBER}"' if config.TWILIO_NUMBER else ""
    transcription = (
        f'<Start><Transcription statusCallbackUrl="{cb}" track="both_tracks" '
        f'partialResults="false" languageCode="{config.TRANSCRIBE_LANG}" '
        f'name="Lexora Live"/></Start>')
    if client:
        dial = f'<Dial{caller} action="{action}" answerOnBridge="true">{client}</Dial>'
    else:
        # no client number configured -> just listen to the caller for a while
        dial = ('<Say>No client number is configured. Please speak; the assistant is '
                'transcribing.</Say><Pause length="60"/>')
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{transcription}{dial}</Response>'


def hangup_twiml():
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


# ----------------------------------------------------------------- ingest
def on_call_start(call_sid):
    global _latest_sid
    with _lock:
        _get(call_sid)
        _latest_sid = call_sid
    _ensure_worker()


def enqueue_transcription(call_sid, track, data_json, final="true"):
    """Called by the /transcription webhook; fast + non-blocking."""
    if str(final).lower() == "false":
        return
    text = _parse_transcript(data_json)
    if not text:
        return
    _ensure_worker()
    _q.put((call_sid, track, text))


def _parse_transcript(data_json):
    if not data_json:
        return ""
    try:
        d = json.loads(data_json)
        if isinstance(d, dict):
            return (d.get("transcript") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return str(data_json).strip()


def _ensure_worker():
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
    threading.Thread(target=_worker, daemon=True).start()


def _worker():
    while True:
        call_sid, track, text = _q.get()
        try:
            _process(call_sid, track, text)
        except Exception as e:  # noqa: BLE001
            print(f"[telephony] process error: {e}")
        finally:
            _q.task_done()


def _process(call_sid, track, text):
    global _latest_sid
    speaker = "Lawyer" if track == "inbound_track" else "Client"
    with _lock:
        s = _get(call_sid)
        _latest_sid = call_sid
        s["transcript"].append({"speaker": speaker, "text": text})
        cid = s["client_id"]
        pending = list(s["pending"])

    r = chat.live_turn(cid or "general", text, speaker, [] if cid else pending)

    with _lock:
        s = _get(call_sid)
        if not cid:
            if r.get("client_id"):
                s["client_id"] = r["client_id"]
                s["client_name"] = r["client_name"]
                s["pending"] = []
            else:
                s["pending"].append(text)
        if r.get("contradictions"):
            s["contradictions"].extend(r["contradictions"])
        if r.get("graph"):
            s["graph_nodes"] = len(r["graph"]["nodes"])


# ----------------------------------------------------------------- end of call
def on_call_end(call_sid):
    """Generate the meeting summary + action items in the background."""
    threading.Thread(target=_summarise, args=(call_sid,), daemon=True).start()


def _summarise(call_sid):
    with _lock:
        s = _sessions.get(call_sid)
        if not s:
            return
        s["active"] = False
        cid = s["client_id"]
        transcript = "\n".join(f"{u['speaker']}: {u['text']}" for u in s["transcript"])
    if not cid or not transcript.strip():
        with _lock:
            if call_sid in _sessions:
                _sessions[call_sid]["ended"] = True
        return
    try:
        res = chat.process_call(cid, transcript)
    except Exception as e:  # noqa: BLE001
        print(f"[telephony] summary failed: {e}")
        res = {"summary": "", "action_items": []}
    with _lock:
        s = _sessions.get(call_sid)
        if s:
            s["summary"] = res.get("summary", "")
            s["action_items"] = res.get("action_items", [])
            s["ended"] = True


# ----------------------------------------------------------------- UI state
def live_state():
    with _lock:
        s = _sessions.get(_latest_sid)
        if not s:
            return {"active": False, "configured": bool(config.TWILIO_CLIENT_NUMBER),
                    "transcript": [], "client_name": None, "contradictions": [],
                    "summary": "", "action_items": [], "ended": False}
        return {
            "active": s["active"], "configured": bool(config.TWILIO_CLIENT_NUMBER),
            "call_sid": s["call_sid"], "client_id": s["client_id"],
            "client_name": s["client_name"], "transcript": s["transcript"][-40:],
            "contradictions": s["contradictions"][-3:], "graph_nodes": s["graph_nodes"],
            "summary": s["summary"], "action_items": s["action_items"], "ended": s["ended"],
        }

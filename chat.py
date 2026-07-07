"""Chat orchestration: memory + RAG + contradiction-aware response generation."""
import config
import llm
import memory
import rag
import calendarx
import mailer

CHAT_SYS = (
    "You are Lexora, an offline AI assistant for a lawyer. Write a short, direct reply "
    "(2-5 sentences) in your own words. Rules: do NOT repeat or quote the context back; do "
    "NOT output any URLs, links or headings; do NOT invent facts, documents or citations. "
    "If a CONTRADICTION is reported in the context, your FIRST sentence must clearly warn the "
    "lawyer that the statements contradict each other and name the conflict."
)


import re

_URL = re.compile(r"https?://\S+|www\.\S+|\(?https?:[^\s)]+\)?")
_ECHO = re.compile(r"^(client|relevant case memory|relevant documents|recent conversation|"
                   r"reply|context|case|status|end context)\b.*", re.I)


def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _clean(text, context=""):
    """Remove URL hallucinations and context-echo lines from the small model output."""
    text = _URL.sub("", text)
    text = re.sub(r"\[END CONTEXT\]|\[CONTEXT[^\]]*\]", "", text, flags=re.I)
    ctx_lines = {_norm(re.sub(r"^[-*\s]+", "", l)) for l in context.splitlines() if len(l.strip()) > 12}
    kept = []
    for ln in text.splitlines():
        s = ln.strip()
        if _ECHO.match(s):
            continue
        if s.startswith("- [") or re.fullmatch(r"[-*\s]*\[.*\]", s):  # echoed doc links
            continue
        n = _norm(re.sub(r"^[-*\s]+", "", s))
        if n and n in ctx_lines:                                       # verbatim context echo
            continue
        kept.append(ln)
    out = "\n".join(kept).strip()
    out = re.sub(r"^(as lexora[,:]?\s*)", "", out, flags=re.I).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out or text.strip()


def _is_factual(text):
    return len(text.split()) >= 4


# ----------------------------------------------------------------- intents
def _email_intent(text):
    low = text.lower()
    return (("send" in low or "mail" in low or "email" in low)
            and ("mail" in low or "email" in low)
            and ("client" in low or "case" in low or "him" in low or "her" in low
                 or "summary" in low or "details" in low or "@" in low))


def _find_client_by_name(text):
    low = text.lower()
    for c in memory.list_clients():
        if c["name"].lower() in low:
            return c
    return None


CASE_SUM_SYS = ("You are a legal assistant. Write a concise, professional case-summary email "
                "body (4-7 sentences) for the client, covering the key facts, status and next "
                "steps. Plain text, no placeholders, no markdown.")


def _build_case_summary(client):
    cid = client["id"]
    stmts = memory.get_statements(cid)
    facts = "\n".join(f"- {s['text']}" for s in stmts[:20]) or "- (no recorded statements yet)"
    events = memory.get_events(cid)
    ev = "\n".join(f"- {e['title']} on {e['when']}" for e in events) or "- (none)"
    prompt = (f"Client: {client['name']}\nCase type: {client['case_type']}\n"
              f"Status: {client['case_status']}\nKey facts:\n{facts}\n"
              f"Upcoming dates:\n{ev}\n\nWrite the email body.")
    body = llm.generate(prompt, system=CASE_SUM_SYS, max_new_tokens=300).strip()
    body = _clean(body)
    if events:
        body += "\n\nUpcoming dates:\n" + "\n".join(f"  • {e['title']} — {e['when']}" for e in events)
    body += f"\n\nRegards,\nYour legal team"
    return body


def _handle_email(client_id, message):
    target = memory.get_client(client_id) if (client_id and client_id != "general") else None
    if not target:
        target = _find_client_by_name(message)
    if not target:
        ans = ("Which client should I email? Open the client (or say their name), then ask "
               "again, e.g. \"send a mail to the client with the case summary\".")
        memory.add_message(client_id, "assistant", ans)
        return {"answer": ans, "contradictions": [], "memory_used": [], "documents_used": []}

    to_addr = (target.get("email") or config.DEFAULT_CLIENT_EMAIL or config.GMAIL_ADDRESS)
    body = _build_case_summary(target)
    subject = f"Case update — {target['name']} ({target['case_type']})"
    ok, err = mailer.send_email(to_addr, subject, body)
    if ok:
        memory.log_activity(target["id"], "Email sent", f"Case summary → {to_addr}")
        # reflect the email in the client's knowledge base (memory + graph)
        memory.record_email(target["id"], target["name"], to_addr)
        ans = f"📧 Sent {target['name']} a case-summary email to {to_addr}."
    else:
        ans = f"⚠ Couldn't send the email: {err}"
    memory.add_message(client_id, "assistant", ans)
    return {"answer": ans, "email": {"sent": ok, "to": to_addr, "error": err,
            "subject": subject, "preview": body[:400]},
            "contradictions": [], "memory_used": [], "documents_used": []}


def _handle_calendar(client_id, message, event):
    start, end = event["start"], event["end"]
    when = calendarx.human(start)
    conflicts = memory.find_conflicts(start, end)
    is_client = client_id and client_id != "general"
    rec = memory.add_event(event["title"], start, end, when,
                           client_id=client_id if is_client else None)
    link = calendarx.gcal_link(event["title"], start, end,
                               details=f"Added by Lexora for {memory.get_client(client_id)['name']}"
                               if is_client else "Added by Lexora")
    if conflicts:
        c = conflicts[0]
        ans = (f"⚠ Heads up — you already have \"{c['title']}\" on {c['when']}, which clashes "
               f"with this. I've still noted \"{event['title']}\" for {when}. "
               f"You can add it to Google Calendar from the link below.")
    else:
        ans = (f"📅 Noted \"{event['title']}\" for {when}. "
               f"Add it to Google Calendar from the link below.")
    memory.add_message(client_id, "assistant", ans)
    return {"answer": ans,
            "calendar": {"title": event["title"], "when": when, "gcal_link": link,
                         "conflicts": [{"title": x["title"], "when": x["when"]} for x in conflicts]},
            "contradictions": [], "memory_used": [], "documents_used": []}


def respond(client_id, message):
    is_client = client_id and client_id != "general"

    # ---- action intents (calendar / email) handled before normal chat ----
    if _email_intent(message):
        memory.add_message(client_id, "user", message)
        return _handle_email(client_id, message)
    cal_event = calendarx.parse_event(message)
    if cal_event:
        memory.add_message(client_id, "user", message)
        return _handle_calendar(client_id, message, cal_event)

    memory.add_message(client_id, "user", message)

    contradictions = []
    stmt = None
    if is_client and _is_factual(message):
        stmt = memory.add_statement(client_id, message, speaker="from lawyer/client", source="chat")
        contradictions = memory.check_contradictions(client_id, message, new_id=stmt["id"])

    # ---- gather context
    mem_hits = []
    if is_client:
        try:
            mem_hits = rag.query_memory(message, client_id,
                                        exclude_id=stmt["id"] if stmt else None)
        except Exception:  # noqa: BLE001
            pass
    doc_hits = []
    try:
        doc_hits = rag.query_docs(message, client_id=client_id if is_client else None)
        if not doc_hits and is_client:
            doc_hits = rag.query_docs(message)  # fall back to global docs
    except Exception:  # noqa: BLE001
        pass

    history = memory.get_messages(client_id, limit=7)[:-1]  # exclude the just-added msg

    parts = []
    client = memory.get_client(client_id) if is_client else None
    if client:
        parts.append(f"CLIENT: {client['name']} | case: {client['case_type']} "
                     f"| status: {client['case_status']}")
    if mem_hits:
        parts.append("RELEVANT CASE MEMORY:\n" +
                     "\n".join(f"- {h['text']}" for h in mem_hits[:config.MEMORY_TOP_K]))
    if doc_hits:
        parts.append("RELEVANT DOCUMENTS (RAG):\n" +
                     "\n".join(f"- [{h['source']}] {h['text'][:400]}" for h in doc_hits))
    if history:
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])
        parts.append("RECENT CONVERSATION:\n" + convo)
    if contradictions:
        c = contradictions[0]
        parts.append("⚠ CONTRADICTION DETECTED by the memory system:\n"
                     f'  New statement: "{message}"\n'
                     f'  Conflicts with earlier: "{c["prior_text"]}"\n'
                     f'  Why: {c["reason"]}\n'
                     "You MUST warn the lawyer about this contradiction in your answer.")

    context = "\n\n".join(parts)
    prompt = (f"[CONTEXT — reference only, do not repeat]\n{context}\n[END CONTEXT]\n\n"
              f"The lawyer says: \"{message}\"\n\n"
              "Write your concise reply now (your own words, no links, no headings):")
    answer = llm.generate(prompt, system=CHAT_SYS).strip()
    # strip common echo artifacts + verbatim context echoes from the small model
    answer = _clean(answer, context)

    # safety net: ensure the contradiction is surfaced even if the small model omits it
    if contradictions and "contradict" not in answer.lower():
        c = contradictions[0]
        answer = (f"⚠ **Possible contradiction detected.** The new statement conflicts "
                  f"with an earlier one — {c['reason']} "
                  f'(earlier: "{c["prior_text"]}").\n\n' + answer)

    # update knowledge graph from this turn
    if is_client and _is_factual(message):
        try:
            memory.extract_graph(client_id, message, source="chat")
        except Exception as e:  # noqa: BLE001
            print(f"[chat] graph extract failed: {e}")

    memory.add_message(client_id, "assistant", answer)
    return {
        "answer": answer,
        "contradictions": contradictions,
        "memory_used": [h["text"] for h in mem_hits[:config.MEMORY_TOP_K]],
        "documents_used": [{"source": h["source"], "text": h["text"][:200]} for h in doc_hits],
    }


CALL_SUM_SYS = (
    "You are a legal call-notes assistant. Given a transcript of a phone call between a "
    "lawyer and a client, write a concise professional meeting summary (3-5 sentences)."
)
CALL_AI_SYS = (
    "You extract concrete action items / follow-up tasks for the lawyer from a call "
    "transcript. Return ONLY JSON: {\"action_items\":[\"...\",\"...\"]}. "
    "Each item is a short imperative task. If none, return an empty list."
)


_ACTION_CUES = ("will ", "i'll", "we'll", "need to", "needs to", "have to", "has to",
                "should ", "must ", "going to", "gonna", "follow up", "follow-up",
                "make sure", "remember to", "don't forget", "by friday", "by monday",
                "by tomorrow", "next week", "this week", "send ", "submit ", "file ",
                "obtain ", "gather ", "collect ", "prepare ", "draft ", "schedule ",
                "confirm ", "get the", "ask ", "request ", "provide ", "bring ")


def _fallback_action_items(transcript):
    """Pull task-like utterances from the transcript when JSON extraction fails."""
    items = []
    for raw in re.split(r"[\n.!?]+", transcript):
        line = re.sub(r"^\s*(lawyer|client)\s*:\s*", "", raw.strip(), flags=re.I)
        low = " " + line.lower() + " "
        if len(line.split()) < 3:
            continue
        if any(c in low for c in _ACTION_CUES):
            # strip conversational filler openings ("Okay,", "Yes I", "Not yet,", ...)
            line = re.sub(r"^(okay|ok|yeah|yes|yep|sure|well|alright|right|no|not yet)[,\s]+",
                          "", line, flags=re.I).strip()
            line = re.sub(r"^(i['’]?ll|i will|we['’]?ll|we will)\s+", "", line, flags=re.I).strip()
            if not line:
                continue
            task = line[0].upper() + line[1:]
            if task not in items:
                items.append(task)
    return items[:8]


def process_call(client_id, transcript):
    """Summarise a recorded call, extract action items, update client memory + graph."""
    transcript = (transcript or "").strip()
    if not transcript:
        return {"summary": "", "action_items": [], "contradictions": []}

    summary = llm.generate(f"Transcript:\n{transcript}\n\nWrite the meeting summary.",
                           system=CALL_SUM_SYS, max_new_tokens=220)
    ai_data = llm.generate_json(f"Transcript:\n{transcript}\n\nExtract the action items.",
                                system=CALL_AI_SYS, max_new_tokens=220) or {}
    items = ai_data.get("action_items", []) if isinstance(ai_data, dict) else []
    items = [str(i).strip() for i in items if str(i).strip()][:10]
    if not items:                       # reliable fallback when the small model skips JSON
        items = _fallback_action_items(transcript)

    # update memory: store the call as a statement, run contradiction check, grow graph
    contradictions = []
    if client_id and client_id != "general":
        stmt = memory.add_statement(client_id, transcript[:1500],
                                    speaker="call", source="voice_call")
        try:
            contradictions = memory.check_contradictions(client_id, transcript[:1500],
                                                         new_id=stmt["id"])
        except Exception:  # noqa: BLE001
            pass
        try:
            memory.extract_graph(client_id, transcript[:1500], source="voice_call")
        except Exception:  # noqa: BLE001
            pass

    memory.add_call(client_id, transcript, summary, items)
    return {"summary": summary, "action_items": items, "contradictions": contradictions}


# ===================================================================== LIVE CALL
# Real-time transcription of an actual phone conversation. Each finalised utterance
# is committed to memory + knowledge graph as it is spoken. If no client is selected,
# the caller's name is auto-detected from speech and a new client chat is created.

_NAME_TRIGGERS = re.compile(
    r"(?:my name is|i am|i'm|this is|you[''`]?re speaking (?:to|with)|"
    r"speaking (?:to|with)|new client(?:[, ]+(?:named|called))?|"
    r"client(?: named| called)|calling is|caller is|it[''`]?s)\s+"
    r"([a-z][a-z]+(?:\s+[a-z][a-z]+){0,2})", re.I)

_NAME_STOP = {"calling", "here", "speaking", "not", "a", "an", "the", "your", "very",
              "just", "now", "about", "regarding", "from", "with", "to", "and", "but",
              "really", "actually", "sorry", "hello", "hi", "good", "morning", "afternoon",
              "evening", "sir", "madam", "ma", "mr", "mrs", "ms", "today", "going", "trying",
              "looking", "wondering", "afraid", "sure", "okay", "fine", "well", "still",
              "new", "client", "clients", "caller", "case", "matter", "person", "someone",
              "calling", "this", "that", "my", "i", "we", "you", "they", "name"}

_CASE_KEYWORDS = [
    (("theft", "stole", "stolen", "robbery", "assault", "murder", "criminal", "fir", "police", "accused", "bail"), "Criminal"),
    (("property", "land", "plot", "boundary", "tenant", "rent", "encroach", "deed"), "Property Dispute"),
    (("divorce", "custody", "alimony", "marriage", "spouse", "maintenance"), "Divorce"),
    (("fraud", "cheat", "scam", "invest", "chit", "money", "embezzle", "loan"), "Financial Fraud"),
    (("contract", "breach", "vendor", "agreement", "deliver", "supply", "payment"), "Contract Breach"),
]


def _detect_client_name(text):
    m = _NAME_TRIGGERS.search(text or "")
    if not m:
        return None
    words = [w for w in m.group(1).split() if w.lower() not in _NAME_STOP]
    words = words[:2]
    if not words:
        return None
    return " ".join(w.capitalize() for w in words)


def _detect_case_type(text):
    low = (text or "").lower()
    for keys, label in _CASE_KEYWORDS:
        if any(k in low for k in keys):
            return label
    return "General"


def _commit_utterance(client_id, text, speaker):
    """Add one spoken line to memory + graph, return any contradictions."""
    contradictions = []
    if not _is_factual(text):
        return contradictions
    stmt = memory.add_statement(client_id, text, speaker=speaker or "call", source="live_call")
    try:
        contradictions = memory.check_contradictions(client_id, text, new_id=stmt["id"])
    except Exception:  # noqa: BLE001
        pass
    try:
        memory.extract_graph(client_id, text, source="live_call")
    except Exception as e:  # noqa: BLE001
        print(f"[live] graph extract failed: {e}")
    return contradictions


def live_turn(client_id, text, speaker="client", pending=None):
    """Handle one live utterance. Auto-creates a client from the caller's name if needed."""
    text = (text or "").strip()
    pending = pending or []
    is_real = client_id and client_id not in ("", "general", None)
    created = False
    name = None

    if not is_real:
        # try to identify the caller from this line, then from earlier buffered lines
        name = _detect_client_name(text)
        if not name:
            for p in reversed(pending):
                name = _detect_client_name(p)
                if name:
                    break
        if not name:
            # still unknown — keep transcribing, nothing committed yet
            return {"client_id": None, "client_name": None, "created": False,
                    "committed": 0, "contradictions": [], "graph": None}
        ctype = _detect_case_type(" ".join(pending + [text]))
        client = memory.create_client(name, ctype, "open")
        client_id = client["id"]
        created = True
        to_commit = list(pending)
        if text and text not in to_commit:
            to_commit.append(text)
    else:
        to_commit = [text]

    contradictions = []
    committed = 0
    for t in to_commit:
        if _is_factual(t):
            contradictions += _commit_utterance(client_id, t, speaker)
            committed += 1

    cname = name or (memory.get_client(client_id) or {}).get("name")
    return {"client_id": client_id, "client_name": cname, "created": created,
            "committed": committed, "contradictions": contradictions,
            "graph": memory.get_graph(client_id)}

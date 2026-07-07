"""Persistent client memory, per-client knowledge graph, and contradiction logic."""
import json
import os
import threading
import time
import uuid

import config
import llm
import rag

_lock = threading.RLock()
_STORE = None

_EMPTY = {
    "clients": {},      # id -> profile
    "messages": {},     # client_id -> [ {role, content, ts} ]
    "statements": {},   # client_id -> [ {id, text, speaker, ts, source, contradictions} ]
    "graphs": {},       # client_id -> {nodes, edges}
    "activity": [],     # [ {ts, client_id, client_name, action, detail} ]
    "calls": {},        # client_id -> [ {ts, transcript, summary, action_items} ]
    "events": [],       # [ {id, title, start, end, when, client_id, source, created} ]
}


# ---------------------------------------------------------------- persistence
def _load():
    global _STORE
    if _STORE is not None:
        return _STORE
    if os.path.exists(config.STORE_FILE):
        try:
            with open(config.STORE_FILE, "r", encoding="utf-8") as f:
                _STORE = json.load(f)
        except Exception:  # noqa: BLE001
            _STORE = json.loads(json.dumps(_EMPTY))
    else:
        _STORE = json.loads(json.dumps(_EMPTY))
    for k, v in _EMPTY.items():
        _STORE.setdefault(k, json.loads(json.dumps(v)))
    return _STORE


def _save():
    with open(config.STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(_STORE, f, indent=2, ensure_ascii=False)


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_activity(client_id, action, detail=""):
    with _lock:
        s = _load()
        name = s["clients"].get(client_id, {}).get("name", "General")
        s["activity"].insert(0, {"ts": _now(), "client_id": client_id,
                                 "client_name": name, "action": action, "detail": detail})
        s["activity"] = s["activity"][:500]
        _save()


# ---------------------------------------------------------------- clients
def list_clients():
    with _lock:
        s = _load()
        out = []
        for c in s["clients"].values():
            out.append({**c,
                        "messages": len(s["messages"].get(c["id"], [])),
                        "statements": len(s["statements"].get(c["id"], []))})
        return sorted(out, key=lambda x: x.get("created", ""), reverse=True)


def get_client(client_id):
    with _lock:
        return _load()["clients"].get(client_id)


def create_client(name, case_type="General", case_status="open", summary="", email=""):
    with _lock:
        s = _load()
        cid = "c_" + uuid.uuid4().hex[:8]
        s["clients"][cid] = {"id": cid, "name": name, "case_type": case_type,
                             "case_status": case_status, "summary": summary,
                             "email": email, "created": _now(), "tags": []}
        s["messages"].setdefault(cid, [])
        s["statements"].setdefault(cid, [])
        s["graphs"].setdefault(cid, {"nodes": [{"id": name, "label": name, "type": "client"}],
                                     "edges": []})
        _save()
        log_activity(cid, "Client created", name)
        return s["clients"][cid]


def delete_client(client_id):
    """Delete a client and all of their data (chat, statements, graph, calls, vectors)."""
    with _lock:
        s = _load()
        client = s["clients"].get(client_id)
        if not client:
            return False
        name = client["name"]
        for coll in ("clients", "messages", "statements", "graphs", "calls"):
            s[coll].pop(client_id, None)
        s["events"] = [e for e in s.get("events", []) if e.get("client_id") != client_id]
        s["activity"] = [a for a in s["activity"] if a.get("client_id") != client_id]
        s["activity"].insert(0, {"ts": _now(), "client_id": "general",
                                 "client_name": name, "action": "Client deleted",
                                 "detail": name})
        s["activity"] = s["activity"][:500]
        _save()
    try:
        rag.delete_client(client_id)
    except Exception as e:  # noqa: BLE001
        print(f"[memory] vector purge failed: {e}")
    return True


def update_client(client_id, **fields):
    with _lock:
        s = _load()
        c = s["clients"].get(client_id)
        if not c:
            return None
        for k in ("name", "case_type", "case_status", "summary", "email"):
            if k in fields and fields[k] is not None:
                c[k] = fields[k]
        _save()
        log_activity(client_id, "Case updated",
                     f"status={c['case_status']}, type={c['case_type']}")
        return c


# ---------------------------------------------------------------- messages
def get_messages(client_id, limit=None):
    with _lock:
        msgs = _load()["messages"].get(client_id, [])
        return msgs[-limit:] if limit else msgs


def add_message(client_id, role, content):
    with _lock:
        s = _load()
        s["messages"].setdefault(client_id, []).append(
            {"role": role, "content": content, "ts": _now()})
        _save()


def clear_messages(client_id):
    """Clear the visible chat thread (keeps case memory, statements & graph)."""
    with _lock:
        s = _load()
        s["messages"][client_id] = []
        _save()
    return True


# ---------------------------------------------------------------- statements
def get_statements(client_id):
    with _lock:
        return list(_load()["statements"].get(client_id, []))


def add_statement(client_id, text, speaker="client", source="chat"):
    """Store a factual statement + its embedding for later recall/contradiction."""
    with _lock:
        s = _load()
        sid = "s_" + uuid.uuid4().hex[:10]
        rec = {"id": sid, "text": text.strip(), "speaker": speaker,
               "ts": _now(), "source": source, "contradictions": []}
        s["statements"].setdefault(client_id, []).append(rec)
        _save()
    try:
        rag.add_statement_vector(sid, text, client_id,
                                 meta={"speaker": speaker, "source": source, "ts": rec["ts"]})
    except Exception as e:  # noqa: BLE001
        print(f"[memory] vector add failed: {e}")
    return rec


# ---------------------------------------------------------------- knowledge graph
GRAPH_SYS = (
    "You are an information extraction engine for a lawyer's case file. "
    "From the text, extract concrete entities and relationships. "
    "Return ONLY JSON of the form: "
    '{"entities":[{"name":"...","type":"person|place|date|event|organization|object|claim"}],'
    '"relations":[{"from":"...","to":"...","relation":"short verb phrase"}]}. '
    "Keep names short. If nothing concrete, return empty arrays."
)


def extract_graph(client_id, text, source="chat"):
    """Use the LLM to pull entities/relations and merge into the client graph."""
    client = get_client(client_id)
    cname = client["name"] if client else "Client"
    data = llm.generate_json(
        f"Client under discussion: {cname}\nText: \"{text}\"",
        system=GRAPH_SYS, max_new_tokens=300, temperature=0.1) or {}
    ents = data.get("entities", []) if isinstance(data, dict) else []
    rels = data.get("relations", []) if isinstance(data, dict) else []
    added = _merge_graph(client_id, cname, ents, rels, source_text=text, source=source)
    if added:
        log_activity(client_id, "Knowledge graph updated",
                     f"+{added['nodes']} nodes, +{added['edges']} edges")
    return added


_GENERIC_NAMES = {
    "person", "people", "name", "names", "date", "time", "place", "places", "location",
    "event", "events", "organization", "organisation", "object", "objects", "entity",
    "entities", "thing", "things", "someone", "somebody", "unknown", "none", "n/a", "na",
    "claim", "claims", "subject", "user", "client", "lawyer", "person_name", "full_name",
}


def _clean_name(name):
    """Reject hallucinated URLs / generic placeholders and keep labels short and clean."""
    name = str(name).strip().strip('"\'.,').replace("_", " ").strip()
    if not name:
        return None
    low = name.lower()
    if "http" in low or "www." in low or "://" in low or "@" in low or "/" in name:
        return None
    if low in _GENERIC_NAMES:            # generic type words the small model emits as names
        return None
    if len(name) > 45 or len(name.split()) > 7:
        return None
    return name


_MENTION_CAP = 5
_EVIDENCE_CAP = 5


def _add_mention(node, source_text, source, ts):
    """Record a capped provenance mention on a node (skipped for the synthetic client node)."""
    if node.get("type") == "client" or not source_text:
        return
    mentions = node.setdefault("mentions", [])
    mentions.append({"text": str(source_text).strip()[:160], "ts": ts, "source": source or "chat"})
    del mentions[:-_MENTION_CAP]
    node["count"] = len(mentions)


def _add_evidence(edge, source_text, source, ts):
    """Record capped provenance evidence on an edge (skipped for synthetic 'mentioned' edges)."""
    if not source_text:
        return
    evidence = edge.setdefault("evidence", [])
    evidence.append({"text": str(source_text).strip()[:160], "ts": ts, "source": source or "chat"})
    del evidence[:-_EVIDENCE_CAP]


def _merge_graph(client_id, cname, ents, rels, source_text=None, source=None, ts=None):
    ts = ts or _now()
    with _lock:
        s = _load()
        g = s["graphs"].setdefault(client_id, {"nodes": [], "edges": []})
        by_id = {n["id"].lower(): n for n in g["nodes"]}
        if cname.lower() not in by_id:
            cnode = {"id": cname, "label": cname, "type": "client"}
            g["nodes"].append(cnode)
            by_id[cname.lower()] = cnode

        new_n = new_e = 0
        for e in ents:
            if not isinstance(e, dict):
                continue
            name = _clean_name(e.get("name", ""))
            if not name:
                continue
            key = name.lower()
            node = by_id.get(key)
            if not node:
                node = {"id": name, "label": name, "type": str(e.get("type", "entity")).lower()}
                g["nodes"].append(node)
                by_id[key] = node
                new_n += 1
            _add_mention(node, source_text, source, ts)

        edge_index = {(x["source"].lower(), x["target"].lower(), x.get("label", "").lower()): x
                     for x in g["edges"]}

        def ensure_node(nm):
            key = nm.lower()
            node = by_id.get(key)
            if not node:
                node = {"id": nm, "label": nm, "type": "entity"}
                g["nodes"].append(node)
                by_id[key] = node
            return node

        for r in rels:
            if not isinstance(r, dict):
                continue
            a, b = _clean_name(r.get("from", "")), _clean_name(r.get("to", ""))
            lbl = str(r.get("relation", "related")).strip()[:40]
            if not a or not b:
                continue
            na, nb = ensure_node(a), ensure_node(b)
            _add_mention(na, source_text, source, ts)
            _add_mention(nb, source_text, source, ts)
            key = (a.lower(), b.lower(), lbl.lower())
            edge = edge_index.get(key)
            if not edge:
                edge = {"source": a, "target": b, "label": lbl}
                g["edges"].append(edge)
                edge_index[key] = edge
                new_e += 1
            _add_evidence(edge, source_text, source, ts)
        # connect orphan top-level entities to the client for a coherent graph
        connected = set()
        for x in g["edges"]:
            connected.add(x["source"].lower())
            connected.add(x["target"].lower())
        for n in g["nodes"]:
            if n["type"] != "client" and n["id"].lower() not in connected:
                g["edges"].append({"source": cname, "target": n["id"], "label": "mentioned"})
                connected.add(n["id"].lower())
        _save()
        return {"nodes": new_n, "edges": new_e}


def get_graph(client_id):
    with _lock:
        return _load()["graphs"].get(client_id, {"nodes": [], "edges": []})


# ---------------------------------------------------------------- contradictions
import re

NEG_WORDS = {"not", "no", "never", "without", "denied", "deny", "denies", "wasn't",
             "weren't", "didn't", "isn't", "wasnt", "didnt", "absent", "neither",
             "none", "cannot", "n't", "false", "untrue"}
_STOP = {"the", "a", "an", "was", "is", "are", "were", "at", "in", "on", "of", "to",
         "and", "he", "she", "they", "i", "said", "says", "say", "that", "his", "her",
         "him", "with", "for", "had", "has", "have", "be", "been", "this", "it", "as",
         "now", "first", "second", "statement", "told", "stated", "claims", "claim"}

CONTRA_SYS = (
    "You are a meticulous legal analyst. Compare the NEW statement against the PRIOR "
    "statement from the same matter. Reply with ONE short sentence explaining the factual "
    "contradiction (conflicting time, place, presence/absence, amount, or yes/no fact)."
)


def _tokens(text):
    return [w for w in re.findall(r"[a-z']+", text.lower()) if w not in _STOP and len(w) > 1]


def _has_neg(text):
    low = " " + text.lower() + " "
    if "n't" in low:
        return True
    return any(w in low.split() for w in NEG_WORDS)


def _numbers(text):
    return set(re.findall(r"\d+(?::\d+)?", text))


def _cosine(a, b):
    va, vb = rag.embed([a, b])
    return sum(x * y for x, y in zip(va, vb))


def _heuristic_conflict(new_text, prior_text, prior_speaker=""):
    """Deterministic contradiction signal. Returns reason string or None."""
    sim = _cosine(new_text, prior_text)
    if sim < 0.40:                       # clearly unrelated
        return None
    shared = set(_tokens(new_text)) & set(_tokens(prior_text))
    if len(shared) < 2:                  # need common subject matter
        return None
    # 1) negation/polarity flip on the same subject (high confidence, any source).
    #    A polarity flip + shared subject is strong, so it tolerates a lower similarity.
    if _has_neg(new_text) != _has_neg(prior_text) and sim >= 0.45:
        return ("The two statements give opposite accounts of the same fact — one affirms "
                "while the other denies it (presence/absence or yes/no conflict).")
    # 2) different times / numbers for the same subject — skip corroborating evidence,
    #    which tends to share numbers without conflicting on the client's account.
    if prior_speaker in ("evidence", "opposing"):
        return None
    n_new, n_old = _numbers(new_text), _numbers(prior_text)
    if sim >= 0.55 and n_new and n_old and n_new != n_old and len(shared) >= 3:
        return ("The statements give different details for the same fact "
                f"({', '.join(sorted(n_old))} vs {', '.join(sorted(n_new))}).")
    return None


def check_contradictions(client_id, new_text, new_id=None):
    """Return list of {prior_id, prior_text, reason} contradicting new_text.

    Reliable deterministic heuristic first; the LLM refines the wording if available.
    """
    try:
        candidates = rag.query_memory(new_text, client_id, k=5, exclude_id=new_id)
    except Exception as e:  # noqa: BLE001
        print(f"[memory] recall failed: {e}")
        candidates = []
    found = []
    for c in candidates:
        pid = c["meta"].get("stmt_id", "")
        prior = c["text"]
        reason = _heuristic_conflict(new_text, prior, c["meta"].get("speaker", ""))
        if not reason:
            continue
        found.append({"prior_id": pid, "prior_text": prior, "reason": reason})
    if found and new_id:
        _record_contradiction(client_id, new_id, found)
        log_activity(client_id, "Contradiction detected", found[0]["reason"][:120])
    return found


def _record_contradiction(client_id, new_id, found):
    with _lock:
        s = _load()
        for st in s["statements"].get(client_id, []):
            if st["id"] == new_id:
                st["contradictions"] = found
        _save()


# ---------------------------------------------------------------- calls
def add_call(client_id, transcript, summary, action_items):
    with _lock:
        s = _load()
        rec = {"ts": _now(), "transcript": transcript, "summary": summary,
               "action_items": action_items}
        s["calls"].setdefault(client_id, []).append(rec)
        _save()
        log_activity(client_id, "Call recorded",
                     f"{len(action_items)} action item(s) extracted")
        return rec


def get_calls(client_id):
    with _lock:
        return list(_load()["calls"].get(client_id, []))


# ---------------------------------------------------------------- calendar events
import calendarx  # noqa: E402  (local import to avoid cycle at top)


def add_event(title, start_dt, end_dt, when, client_id=None, source="chat"):
    with _lock:
        s = _load()
        eid = "e_" + uuid.uuid4().hex[:8]
        rec = {"id": eid, "title": title, "start": calendarx.to_iso(start_dt),
               "end": calendarx.to_iso(end_dt), "when": when,
               "client_id": client_id, "source": source, "created": _now()}
        s["events"].append(rec)
        _save()
    name = (get_client(client_id) or {}).get("name") if client_id else None
    log_activity(client_id or "general", "Event scheduled", f"{title} — {when}")
    # reflect in the client's memory + knowledge graph
    if client_id and client_id not in ("", "general", None):
        try:
            add_statement(client_id, f"Scheduled: {title} on {when}.",
                          speaker="calendar", source="calendar")
        except Exception:  # noqa: BLE001
            pass
        try:
            _merge_graph(client_id, name or "Client",
                         [{"name": title, "type": "event"},
                          {"name": when, "type": "date"}],
                         [{"from": title, "to": when, "relation": "scheduled for"}],
                         source_text=f"Scheduled: {title} on {when}.", source="calendar")
        except Exception:  # noqa: BLE001
            pass
    return rec


def record_email(client_id, client_name, to_addr):
    """Reflect a sent case-summary email in the client's memory + knowledge graph."""
    when = _now()
    try:
        add_statement(client_id, f"Case-summary email sent to {client_name} ({to_addr}) on {when}.",
                      speaker="email", source="email")
    except Exception:  # noqa: BLE001
        pass
    try:
        _merge_graph(client_id, client_name,
                     [{"name": "Case summary email", "type": "event"},
                      {"name": to_addr, "type": "object"}],
                     [{"from": "Case summary email", "to": to_addr, "relation": "sent to"}],
                     source_text=f"Case-summary email sent to {client_name} ({to_addr}) on {when}.",
                     source="email")
    except Exception:  # noqa: BLE001
        pass


def get_events(client_id=None):
    with _lock:
        evs = list(_load()["events"])
    if client_id and client_id not in ("", "general", None):
        evs = [e for e in evs if e.get("client_id") == client_id]
    return sorted(evs, key=lambda e: e.get("start", ""))


def find_conflicts(start_dt, end_dt, exclude_id=None):
    """Return stored events whose time overlaps [start_dt, end_dt)."""
    out = []
    for e in get_events():
        if e["id"] == exclude_id:
            continue
        es, ee = calendarx.from_iso(e["start"]), calendarx.from_iso(e["end"])
        if not es or not ee:
            continue
        if es < end_dt and start_dt < ee:        # intervals overlap
            out.append(e)
    return out


# ---------------------------------------------------------------- dashboard
def dashboard():
    with _lock:
        s = _load()
        clients = list(s["clients"].values())
        by_status = {}
        by_type = {}
        for c in clients:
            by_status[c["case_status"]] = by_status.get(c["case_status"], 0) + 1
            by_type[c["case_type"]] = by_type.get(c["case_type"], 0) + 1
        contradictions = 0
        for sts in s["statements"].values():
            contradictions += sum(1 for x in sts if x.get("contradictions"))
        try:
            total_docs = len(rag.list_documents())
        except Exception:  # noqa: BLE001
            total_docs = 0
        rows = []
        for c in clients:
            rows.append({
                "id": c["id"], "name": c["name"], "case_type": c["case_type"],
                "case_status": c["case_status"],
                "statements": len(s["statements"].get(c["id"], [])),
                "calls": len(s["calls"].get(c["id"], [])),
                "graph_nodes": len(s["graphs"].get(c["id"], {}).get("nodes", [])),
            })
        return {
            "total_clients": len(clients),
            "by_status": by_status,
            "by_type": by_type,
            "total_calls": sum(len(v) for v in s["calls"].values()),
            "total_statements": sum(len(v) for v in s["statements"].values()),
            "total_documents": total_docs,
            "contradictions": contradictions,
            "rows": rows,
            "activity": s["activity"][:60],
        }

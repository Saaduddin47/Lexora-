"""Offline RAG: BGE embeddings + a lightweight on-disk vector store + PDF ingest.

Uses a self-contained NumPy cosine-similarity index persisted as JSON under
CHROMA_DB_PATH. (Avoids a known compaction bug in the installed ChromaDB build;
embeddings are normalised so cosine == dot product.)
"""
import json
import os
import threading
import uuid

import config

_lock = threading.Lock()
_embedder = None
_store = None        # {"documents": [...], "memory": [...]}  each item: {id,text,emb,meta}
_np = None

_DOC_FILE = os.path.join(config.CHROMA_DB_PATH, "documents.json")
_MEM_FILE = os.path.join(config.CHROMA_DB_PATH, "memory.json")


def _load():
    global _embedder, _store, _np
    if _embedder is not None:
        return
    import numpy as np
    from sentence_transformers import SentenceTransformer
    _np = np
    _embedder = SentenceTransformer(config.EMBED_MODEL_NAME)
    os.makedirs(config.CHROMA_DB_PATH, exist_ok=True)
    _store = {"documents": _read(_DOC_FILE), "memory": _read(_MEM_FILE)}
    print(f"[rag] embedder ready; {_count('documents')} doc chunks, "
          f"{_count('memory')} memory vectors")


def _read(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return []
    return []


def _persist(coll):
    path = _DOC_FILE if coll == "documents" else _MEM_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_store[coll], f)


def _count(coll):
    return len(_store[coll]) if _store else 0


def embed(texts):
    _load()
    if isinstance(texts, str):
        texts = [texts]
    vecs = _embedder.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def _search(coll, query_vec, k, where=None, exclude_id=None):
    items = _store[coll]
    if where:
        items = [it for it in items
                 if all(it["meta"].get(kk) == vv for kk, vv in where.items())]
    if exclude_id:
        items = [it for it in items if it["meta"].get("stmt_id") != exclude_id]
    if not items:
        return []
    mat = _np.array([it["emb"] for it in items], dtype=_np.float32)
    q = _np.array(query_vec, dtype=_np.float32)
    sims = mat @ q                       # cosine (vectors are normalised)
    order = _np.argsort(-sims)[:k]
    return [(items[i], float(sims[i])) for i in order]


# ---- PDF document RAG -------------------------------------------------------
def _chunk(text, size=900, overlap=150):
    text = " ".join(text.split())
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i + size])
        i += size - overlap
    return [c for c in out if c.strip()]


def extract_pdf_text(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:  # noqa: BLE001
            pages.append("")
    return "\n".join(pages)


def ingest_pdf(path, filename, client_id="general"):
    """Extract, chunk, embed and store a PDF. Returns chunk count."""
    with _lock:
        _load()
        text = extract_pdf_text(path)
        chunks = _chunk(text)
        if not chunks:
            return 0
        embs = embed(chunks)
        for i, (c, e) in enumerate(zip(chunks, embs)):
            _store["documents"].append({
                "id": str(uuid.uuid4()), "text": c, "emb": e,
                "meta": {"source": filename, "client_id": client_id, "chunk": i}})
        _persist("documents")
        return len(chunks)


def query_docs(question, client_id=None, k=None):
    with _lock:
        _load()
        if _count("documents") == 0:
            return []
        k = k or config.RAG_TOP_K
        qv = embed(question)[0]
        where = {"client_id": client_id} if client_id else None
        hits = _search("documents", qv, k, where=where)
        return [{"text": it["text"], "source": it["meta"].get("source"),
                 "client_id": it["meta"].get("client_id")} for it, _ in hits]


# ---- Semantic memory recall -------------------------------------------------
def add_statement_vector(stmt_id, text, client_id, meta=None):
    with _lock:
        _load()
        meta = {**(meta or {}), "client_id": client_id, "stmt_id": stmt_id}
        _store["memory"].append({"id": stmt_id, "text": text,
                                 "emb": embed(text)[0], "meta": meta})
        _persist("memory")


def query_memory(text, client_id, k=None, exclude_id=None):
    with _lock:
        _load()
        if _count("memory") == 0:
            return []
        k = k or config.MEMORY_TOP_K
        qv = embed(text)[0]
        hits = _search("memory", qv, k, where={"client_id": client_id},
                       exclude_id=exclude_id)
        return [{"text": it["text"], "meta": it["meta"]} for it, _ in hits]


def reset():
    """Drop the vector store (used by the seeder's --reset)."""
    global _store
    with _lock:
        for path in (_DOC_FILE, _MEM_FILE):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:  # noqa: BLE001
                pass
        if _store is not None:
            _store = {"documents": [], "memory": []}
        print("[rag] vector store reset")


def delete_client(client_id):
    """Remove all document chunks and memory vectors belonging to a client."""
    with _lock:
        _load()
        for coll in ("documents", "memory"):
            before = len(_store[coll])
            _store[coll] = [it for it in _store[coll]
                            if it["meta"].get("client_id") != client_id]
            if len(_store[coll]) != before:
                _persist(coll)


def list_documents():
    with _lock:
        _load()
        seen = {}
        for it in _store["documents"]:
            key = (it["meta"].get("source"), it["meta"].get("client_id"))
            seen[key] = seen.get(key, 0) + 1
        return [{"source": s, "client_id": c, "chunks": n} for (s, c), n in seen.items()]

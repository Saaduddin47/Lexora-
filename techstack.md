# 🛠 Lexora — Tech Stack (per feature)

A fully **offline**, on-device AI assistant for lawyers. Everything that matters (the LLM,
the embeddings, the vector search, the knowledge graph) runs **locally** with no internet.
A remote fallback exists but is never used unless explicitly configured, and is never shown
in the UI.

---

## Global stack

| Layer | Technology | Notes |
|---|---|---|
| Language / runtime | **Python 3.11** | CUDA-enabled |
| Web framework | **FastAPI** + **Uvicorn** | REST API + static hosting |
| Request models | **Pydantic** | request validation |
| LLM (primary) | **TinyLlama-1.1B-Chat** via **HuggingFace Transformers** + **PyTorch** | local, runs on GPU (fp16) or CPU |
| LLM (silent fallback) | **Google Generative AI (Gemini)** | optional, env-gated, never referenced in the UI |
| Embeddings | **BGE-small-en-v1.5** via **sentence-transformers** | 384-dim, normalized |
| Vector store | **Custom NumPy cosine index**, persisted as JSON | replaces ChromaDB (see note below) |
| PDF parsing | **pypdf** | text extraction |
| Persistence | **JSON files** (`data/store.json`, `chroma_db/*.json`) | human-readable, portable |
| Frontend | **Vanilla HTML / CSS / JS** | dark, ChatGPT-style, no framework |
| Charts | **Chart.js** (vendored locally) | dashboard only |
| Knowledge-graph viz | **Custom HTML5 Canvas force-directed renderer** | no vis.js, no three.js, no D3 |
| Speech-to-text | **Web Speech API** (`SpeechRecognition` / `webkitSpeechRecognition`) | browser-native, Chrome/Edge |

> **Why a custom NumPy vector store instead of ChromaDB?** The installed ChromaDB build
> (1.5.9) threw a fatal `mismatched types (u64/BLOB)` error during compaction on a *fresh*
> database in this environment, silently dropping every vector. We replaced it with a small,
> dependency-light NumPy cosine index (vectors are normalized, so cosine = dot product) that
> persists to JSON under the same `CHROMA_DB_PATH`. Same retrieval quality, zero failure points.

---

## Project layout

```
app.py        FastAPI server, REST endpoints, no-cache middleware, static hosting
chat.py       Orchestration: chat replies, call processing, live-call turns, auto-client creation
llm.py        TinyLlama loader/generation + JSON extraction + silent Gemini fallback
rag.py        BGE embeddings + NumPy vector store + PDF ingest/retrieval
memory.py     Clients, statements, knowledge graph, contradiction engine, dashboard, activity
seed_data.py  Dummy data + a self-contained PDF generator (no external PDF lib)
static/       index.html, styles.css, app.js, vendor/chart.umd.min.js
data/         store.json (all case data) + uploads/
chroma_db/    documents.json + memory.json (the vector store)
```

---

## Feature-by-feature breakdown

### 1. Chat (ChatGPT-style, offline)
- **API:** `POST /api/chat` → `chat.respond()`.
- **Generation:** TinyLlama via Transformers/PyTorch using the tokenizer's chat template,
  with sampling controls (`temperature`, `top_p`, `repetition_penalty`).
- **Context assembly:** the prompt is built from (a) relevant **memory recall** (NumPy vector
  search over the client's past statements), (b) **RAG** document chunks, (c) the last few
  chat turns, and (d) any detected contradiction.
- **Output hygiene:** regex post-processing strips hallucinated URLs and context-echo lines
  that small models tend to emit.
- **Frontend:** vanilla JS chat UI, dark theme, streaming-style "typing" indicator.

### 2. Knowledge-graph memory (auto-built per client)
- **Extraction:** TinyLlama is prompted to return JSON `{entities, relations}` for each
  factual message (`llm.generate_json`).
- **Sanitisation:** a heuristic layer (`_clean_name`) drops hallucinated URLs and generic
  placeholder labels (e.g. "PERSON", "DATE") the small model sometimes emits.
- **Merge logic:** nodes/edges are merged case-insensitively into the client's graph, so the
  **same entity mentioned in different conversations connects automatically** (this is what
  links multiple matters to one client). Orphan entities are attached to the client node.
- **Storage:** a lightweight in-house graph model — `{nodes:[…], edges:[…]}` lists in
  `store.json` (no graph DB needed).
- **Rendering:** a **custom HTML5 Canvas force-directed graph** — repulsion between nodes,
  spring attraction along edges, centre gravity, drag-to-move, colour-coded by entity type.
  Zero external libraries.

### 3. Persistent memory ("like ChatGPT, always there")
- All clients, chats, statements, graphs and calls live in **`data/store.json`**; all vectors
  live in **`chroma_db/documents.json` + `memory.json`**.
- Thread-safe access via an `RLock`; every write is flushed to disk, so closing and reopening
  the app restores everything exactly.

### 4. Offline RAG (PDF upload → retrieval)
- **API:** `POST /api/upload` (multipart via **python-multipart**).
- **Pipeline:** **pypdf** extracts text → fixed-size overlapping **chunking** → **BGE**
  embeddings → stored in the NumPy `documents` index with `{source, client_id}` metadata.
- **Retrieval:** at chat time, the question is embedded and matched by cosine similarity
  (top-k), filtered to the active client (falling back to the shared library).
- Answers cite the source document; everything runs offline.

### 5. Contradiction detection
- **Recall:** the new statement is embedded and the most similar prior statements for that
  client are retrieved from the NumPy `memory` index.
- **Deterministic engine** (`memory._heuristic_conflict`) — *not* left to the 1.1B model,
  for reliability:
  - **Negation/polarity flip:** same subject (shared tokens + cosine ≥ 0.45) but one statement
    affirms while the other denies → contradiction ("was at the office" vs "was **not** at the
    office").
  - **Numeric/time conflict:** same subject but different numbers/times (e.g. 5 PM vs 9 PM),
    while skipping corroborating evidence.
- The chatbot then **explains the contradiction in natural language** (TinyLlama), with a red
  warning card in the UI as a guaranteed visual.

### 6. AI Call Assistant (demo) + 📱 Live Call (real phone call)
- **Speech-to-text:** **Web Speech API** in the browser (Chrome/Edge) — no audio leaves the
  machine; for a real two-phone call the phone is put on speaker next to the laptop.
- **Live pipeline:** `POST /api/live` → each finalised utterance is committed to memory + the
  knowledge graph **in real time**, with live contradiction checks.
- **Auto client creation:** a regex name-detector (`_detect_client_name`, e.g. "my name is …",
  "this is …") plus a keyword-based **case-type classifier** (`_detect_case_type`: theft→
  Criminal, divorce→Divorce, …) creates a new client chat on the fly when none is selected.
- **End of call:** TinyLlama writes the **meeting summary**; **action items** are extracted via
  LLM JSON with a robust regex fallback (cue words like "will", "send by Friday", "follow up").

### 7. Case Insights Dashboard
- **API:** `GET /api/dashboard` aggregates clients by **status** (solved/unsolved/…) and
  **type**, plus totals (calls, statements, documents, contradictions).
- **Charts:** **Chart.js** (doughnut + bar) rendered on a dark theme.
- **Who-did-what-when:** an in-memory **activity log** records every action (client created,
  graph updated, contradiction detected, call recorded, document uploaded, client deleted).

### 8. Client management (create / update / delete)
- `POST /api/clients`, `PATCH /api/clients/{id}`, `DELETE /api/clients/{id}`.
- **Delete** purges the client everywhere: chat, statements, graph, calls, and all of their
  vectors in both the document and memory indexes.

### 9. Silent remote fallback
- `llm.py` tries the local model first; only on a local error (and only if `GEMINI_API_KEY`
  is set) does it fall back to **Gemini** via `google-generativeai`. The frontend never
  references it — the product is offline-first.

---

## End-to-end data flow (a chat turn)

```
User message
   │
   ├─► store as a statement                (memory.add_statement)
   │        └─► embed + index               (rag → NumPy memory store)
   ├─► contradiction check                  (embed recall + heuristic)
   ├─► gather context: memory recall + RAG chunks + recent turns + contradiction
   ├─► TinyLlama generate                   (transformers / torch)
   │        └─► clean output                (regex)
   ├─► extract entities/relations → graph   (TinyLlama JSON + sanitize + merge)
   └─► persist everything                   (store.json + *.json vectors)
```

---

## Non-functional notes
- **Offline-first:** models, embeddings, vector search and graph all run locally; Chart.js is
  vendored. No network calls in the default configuration.
- **No-cache middleware** ensures the browser always loads the latest UI assets during a demo.
- **Hackathon-pragmatic choices:** deterministic heuristics back the 1.1B model on the
  "must-be-correct" tasks (contradictions, action items, graph labels), so demos are reliable
  regardless of the small model's variance.

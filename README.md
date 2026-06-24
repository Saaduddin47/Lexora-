# Lexora

Lexora is an offline‑first AI assistant for lawyers. It runs locally using an on‑device
LLM and local embeddings to provide concise legal chat replies, persistent per‑client
factual memory, an extractive knowledge graph, PDF retrieval (offline RAG), and
voice/call summarisation. Data and vector indexes are stored on disk so the app
works without internet; an optional remote LLM fallback is available if you set a key.

Quick start:

1. Install dependencies: `py -3.11 -m pip install -r requirements.txt`
2. (Optional) Seed demo data: `py -3.11 seed_data.py --reset`
3. Run the server: `py -3.11 app.py`
4. Open the UI: `http://127.0.0.1:8000`

Project layout: main app (`app.py`), chat orchestration (`chat.py`), memory (`memory.py`),
RAG (`rag.py`), LLM wrapper (`llm.py`) and static UI in `static/`.

For configuration, edit `config.py` or set environment variables (GMAIL, TWILIO, GEMINI, etc.).

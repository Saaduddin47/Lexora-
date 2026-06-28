"""Central configuration for the offline Lawyer Assistant."""
import os


def _load_dotenv():
    """Load KEY=VALUE pairs from a local .env file into the environment.
    Dependency-free; real environment variables always win over .env."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.lower().startswith("export "):
                    line = line[7:]
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:  # noqa: BLE001
        print(f"[config] .env load skipped: {e}")


_load_dotenv()

# ---- Local models (offline) -------------------------------------------------
MODEL_NAME = "C:\\Syed\\Syed\\__CODING__\\__PROJECTS__\\_______TEST______\\tinyllama_1_1b_chat"
# Use a small sentence-transformers model by default so embeddings work
# (downloads on first run if not present). Change to a local path to use a
# pre-downloaded embedder instead.
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CHROMA_DB_PATH = "./chroma_db"

# ---- Data / persistence -----------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
STORE_FILE = os.path.join(DATA_DIR, "store.json")   # clients, statements, messages, graph, calls

for _d in (DATA_DIR, UPLOAD_DIR):
    os.makedirs(_d, exist_ok=True)

# ---- LLM behaviour ----------------------------------------------------------
# "auto"  -> local primary, gemini fallback on error
# "local" -> offline only
# "gemini"-> remote only (debug)
LLM_BACKEND = os.environ.get("LLM_BACKEND", "auto")

# Optional remote fallback. Never surfaced in the UI.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODELS = ["gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-pro"]

MAX_NEW_TOKENS = 320
GEN_TEMPERATURE = 0.6

# Retrieval
RAG_TOP_K = 4
MEMORY_TOP_K = 5

# ---- Twilio telephony (real two-phone calls) -------------------------------
# All optional; only needed for the Phone Line feature. Set via environment.
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER", "").strip()            # your Twilio number, E.164 (+1...)
TWILIO_CLIENT_NUMBER = os.environ.get("TWILIO_CLIENT_NUMBER", "").strip()  # friend's phone to dial, E.164
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")      # ngrok https base, e.g. https://abc.ngrok-free.app
TRANSCRIBE_LANG = os.environ.get("TRANSCRIBE_LANG", "en-US")

# ---- Gmail (send case summaries to clients) --------------------------------
# Use a Gmail App Password (Account → Security → App passwords), NOT your login password.
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
# Fallback recipient for clients with no email on file (handy for demos).
DEFAULT_CLIENT_EMAIL = os.environ.get("DEFAULT_CLIENT_EMAIL", "").strip()

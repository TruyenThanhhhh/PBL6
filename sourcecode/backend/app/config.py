import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    for env_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        env_line = env_line.strip()
        if not env_line or env_line.startswith("#") or "=" not in env_line:
            continue
        env_key, env_value = env_line.split("=", 1)
        os.environ.setdefault(env_key.strip(), env_value.strip().strip('"').strip("'"))
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "knowledge.db"

# Cấu hình AI & LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120.0"))
VISION_MODEL = os.getenv("VISION_MODEL", "qwen3-vl:2b-instruct")
VISION_MODEL_FALLBACK = os.getenv("VISION_MODEL_FALLBACK", "qwen2.5vl:3b")

# Cấu hình RAG & Chunking
CHUNK_SIZE = 800       # ký tự mỗi chunk
CHUNK_OVERLAP = 150    # độ gối đầu giữa các chunk
TOP_K_RETRIEVAL = 4    # số chunk lấy ra đưa vào LLM

# Hybrid retrieval: lấy rộng rồi fuse bằng RRF, sau đó rerank.
RETRIEVAL_CANDIDATE_MULTIPLIER = int(os.getenv("RETRIEVAL_CANDIDATE_MULTIPLIER", "6"))
RRF_K = int(os.getenv("RRF_K", "60"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", "jinaai/jina-reranker-v2-base-multilingual")
RERANK_MAX_CANDIDATES = int(os.getenv("RERANK_MAX_CANDIDATES", "24"))
RERANK_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "16"))

# Search, embedding and network fallback
ENABLE_DENSE_RETRIEVAL = os.getenv("ENABLE_DENSE_RETRIEVAL", "true").lower() == "true"
SIMILARITY_CUTOFF = float(os.getenv("SIMILARITY_CUTOFF", "0.28"))
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "sentence_transformers")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
DUCKDUCKGO_API_URL = os.getenv("DUCKDUCKGO_API_URL", "https://api.duckduckgo.com/")
WEB_SEARCH_TIMEOUT = float(os.getenv("WEB_SEARCH_TIMEOUT", "5"))
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(25 * 1024 * 1024)))

# Authentication and Google OpenID Connect
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-only-change-this-secret-before-deploying")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback"
)
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"

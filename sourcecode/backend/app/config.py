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

# Đảm bảo các thư mục tồn tại
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Cấu hình AI & LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "qwen2.5:3b")
VISION_MODEL = os.getenv("VISION_MODEL", "qwen2.5vl:3b")

# Cấu hình RAG & Chunking
CHUNK_SIZE = 800       # ký tự mỗi chunk
CHUNK_OVERLAP = 150    # độ gối đầu giữa các chunk
TOP_K_RETRIEVAL = 4    # số chunk lấy ra đưa vào LLM

# Search, embedding and network fallback
ENABLE_DENSE_RETRIEVAL = os.getenv("ENABLE_DENSE_RETRIEVAL", "true").lower() == "true"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
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

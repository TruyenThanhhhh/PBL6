import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE_PATH = DATA_DIR / "knowledge.db"

# Đảm bảo các thư mục tồn tại
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Cấu hình AI & LLM
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "qwen2.5:3b")

# Cấu hình RAG & Chunking
CHUNK_SIZE = 800       # ký tự mỗi chunk
CHUNK_OVERLAP = 150    # độ gối đầu giữa các chunk
TOP_K_RETRIEVAL = 4    # số chunk lấy ra đưa vào LLM

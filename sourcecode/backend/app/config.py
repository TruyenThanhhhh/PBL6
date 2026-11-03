import os
from pathlib import Path

class Settings:
    # Thư mục gốc dự án
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    DATABASE_PATH: Path = DATA_DIR / "knowledge.db"

    # Cấu hình AI & LLM
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    DEFAULT_LLM_MODEL: str = os.getenv("DEFAULT_LLM_MODEL", "qwen2.5:3b")

    # Cấu hình Embedding & Reranker Models
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    RERANK_MODEL: str = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

    # Cấu hình RAG & Chunking
    CHUNK_SIZE: int = 800       # ký tự mỗi chunk
    CHUNK_OVERLAP: int = 150    # độ gối đầu giữa các chunk
    TOP_K_RETRIEVAL: int = 5    # số chunk lấy ra sau rerank để đưa vào LLM

    def __init__(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Khởi tạo instance 'settings'
settings = Settings()

# Export trực tiếp tất cả các biến cấu hình để tương thích ngược với mã nguồn cũ
BASE_DIR = settings.BASE_DIR
DATA_DIR = settings.DATA_DIR
UPLOAD_DIR = settings.UPLOAD_DIR
DATABASE_PATH = settings.DATABASE_PATH
OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
DEFAULT_LLM_MODEL = settings.DEFAULT_LLM_MODEL
EMBEDDING_MODEL = settings.EMBEDDING_MODEL
RERANK_MODEL = settings.RERANK_MODEL
CHUNK_SIZE = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP
TOP_K_RETRIEVAL = settings.TOP_K_RETRIEVAL

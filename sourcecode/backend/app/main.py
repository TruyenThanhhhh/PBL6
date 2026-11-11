from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import asyncio
import logging
from app.database import init_db
from app.api.workspaces import router as workspaces_router
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.study import router as study_router
from app.config import APP_SECRET_KEY, SESSION_HTTPS_ONLY

logger = logging.getLogger(__name__)


def _warmup_models():
    """Tải trước BGE-M3 và Reranker vào RAM để tránh cold-start lần đầu."""
    try:
        from app.services.embedding_service import embed_texts
        embed_texts(["warmup"])
        logger.info("✅ Embedding model (BGE-M3) đã sẵn sàng.")
    except Exception as e:
        logger.warning("⚠️  Embedding warm-up thất bại: %s", e)
    try:
        from app.services.reranker_service import rerank_documents
        rerank_documents("warmup", [{"content": "test"}], top_k=1, max_candidates=1)
        logger.info("✅ Reranker model đã sẵn sàng.")
    except Exception as e:
        logger.warning("⚠️  Reranker warm-up thất bại: %s", e)


# Khởi tạo CSDL SQLite khi server bắt đầu, dọn dẹp khi tắt
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Warm-up các model AI trong background thread để không block startup
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _warmup_models)
    yield

app = FastAPI(
    title="Personal AI Knowledge Platform API",
    description="Backend API cho Trợ lý tri thức cá nhân đa nguồn (Hybrid RAG + Local LLM)",
    version="0.2.0",
    lifespan=lifespan
)

# CORS Middleware cho phép kết nối từ mọi frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=APP_SECRET_KEY, same_site="lax",
                    https_only=SESSION_HTTPS_ONLY, session_cookie="pbl6_oauth_state")

# Đăng ký API Routers
app.include_router(workspaces_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(study_router)

# Phục vụ Giao diện Web tĩnh nếu có
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "message": "Personal AI Knowledge Platform Backend is Running!",
        "docs_url": "/docs",
        "api_v1": "/api/v1"
    }

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import asyncio
import logging
import os
from app.database import init_db
from app.api.workspaces import router as workspaces_router
from app.api.chat import router as chat_router
from app.api.auth import router as auth_router
from app.api.study import router as study_router
from app.api.research import router as research_router
from app.config import APP_SECRET_KEY, SESSION_HTTPS_ONLY
from app.services.embedding_service import maybe_evict_idle_embedding_model
from app.services.hardware_profile_service import (
    get_active_profile_config,
    get_memory_gb,
    should_warmup_on_startup,
    trim_process_memory,
)
from app.services.llm_service import warmup_ollama_model
from app.services.reranker_service import maybe_evict_idle_reranker_model
from app.services.retrieval_service import invalidate_workspace_vector_cache

logger = logging.getLogger(__name__)


def _warmup_models():
    """Chỉ tải trước model khi RAM trống dồi dào để tránh tràn RAM lúc khởi động."""
    if os.getenv("DISABLE_MODEL_WARMUP") == "1":
        return
    profile = get_active_profile_config()
    w_embed, w_rerank, _ = should_warmup_on_startup(profile)
    avail_ram = float((profile.get("specs") or {}).get("available_ram_gb") or 8.0)

    if w_embed:
        try:
            from app.services.embedding_service import embed_texts
            embed_texts(["warmup"])
            logger.info("✅ Embedding model (BGE-M3 BF16) đã sẵn sàng.")
        except Exception as e:
            logger.warning("⚠️  Embedding warm-up thất bại: %s", e)
    else:
        logger.info("⚡ Tiết kiệm RAM (trống %.1f GB): Chế độ nạp Embedding theo yêu cầu.", avail_ram)

    if w_rerank:
        try:
            from app.services.reranker_service import rerank_documents
            rerank_documents("warmup", [{"content": "test"}], top_k=1, max_candidates=1)
            logger.info("✅ Reranker model đã sẵn sàng.")
        except Exception as e:
            logger.warning("⚠️  Reranker warm-up thất bại: %s", e)


async def _memory_watchdog_loop():
    """Tự động thu hồi RAM từ các model AI nhàn rỗi hoặc khi bộ nhớ hệ thống xuống thấp."""
    while True:
        await asyncio.sleep(30)
        try:
            maybe_evict_idle_reranker_model()
            maybe_evict_idle_embedding_model()
            if get_memory_gb()[1] < 3.5:
                invalidate_workspace_vector_cache()
                trim_process_memory()
        except Exception:
            logger.debug("Memory watchdog iteration error", exc_info=True)


# Khởi tạo CSDL SQLite khi server bắt đầu, dọn dẹp khi tắt
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    watchdog_task = None
    if os.getenv("DISABLE_MODEL_WARMUP") != "1":
        loop = asyncio.get_event_loop()
        profile = get_active_profile_config()
        _, _, w_ollama = should_warmup_on_startup(profile)
        loop.run_in_executor(None, _warmup_models)
        if w_ollama:
            asyncio.create_task(warmup_ollama_model())
        watchdog_task = asyncio.create_task(_memory_watchdog_loop())
    try:
        yield
    finally:
        if watchdog_task is not None:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass

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
app.include_router(research_router)

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

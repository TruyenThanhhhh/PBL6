import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import init_db
from app.api.workspaces import router as workspaces_router
from app.api.chat import router as chat_router

app = FastAPI(
    title="Personal AI Knowledge Platform API",
    description="Backend API cho Trợ lý tri thức cá nhân đa nguồn (Hybrid RAG + Local LLM)",
    version="0.1.0"
)

# CORS Middleware cho phép kết nối từ mọi frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo CSDL SQLite khi server chạy
@app.on_event("startup")
def on_startup():
    init_db()

# Đăng ký API Routers
app.include_router(workspaces_router)
app.include_router(chat_router)

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

@app.get("/kanban")
def serve_kanban():
    kanban_file = STATIC_DIR / "kanban.html"
    if kanban_file.exists():
        return FileResponse(str(kanban_file))
    return {"message": "Kanban board is not available"}

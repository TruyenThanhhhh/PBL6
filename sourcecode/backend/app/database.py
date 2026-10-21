import sqlite3
from typing import Generator
from app.config import DATABASE_PATH

import json

def init_db():
    conn = sqlite3.connect("data/knowledge.db")
    cursor = conn.cursor()
    
    # Tạo bảng lưu tài liệu & vector embedding
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT,
        chunk_index INTEGER,
        content TEXT,
        embedding TEXT,  -- Lưu mảng float dưới dạng JSON string
        metadata TEXT
    )
    """)
    conn.commit()
    conn.close()

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Bảng Workspace
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Tạo workspace mặc định nếu chưa có
    cursor.execute("SELECT id FROM workspaces WHERE id = 'default'")
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO workspaces (id, name, description)
        VALUES ('default', 'Workspace Mặc Định', 'Không gian làm việc chung lưu trữ tài liệu cá nhân')
        """)

    # 2. Bảng Documents
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        total_chunks INTEGER DEFAULT 0,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    # 3. Bảng Document Chunks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        page_number INTEGER DEFAULT 1,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """)

    # 4. Bảng FTS5 (Full-Text Search) cho tìm kiếm từ khóa siêu nhanh (BM25)
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        chunk_id UNINDEXED,
        document_id UNINDEXED,
        workspace_id UNINDEXED,
        content
    );
    """)

    # 5. Bảng Chunk Embeddings (lưu Dense Vectors 1024 dims của BGE-M3 dạng JSON)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chunk_embeddings (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        embedding_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
    );
    """)

    # 6. Bảng Chat Sessions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    # 6. Bảng Chat Messages
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        sender TEXT NOT NULL,
        content TEXT NOT NULL,
        citations_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()

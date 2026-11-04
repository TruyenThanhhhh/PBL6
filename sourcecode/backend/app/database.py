import sqlite3
from typing import Dict
from app.config import DATABASE_PATH, DATA_DIR, UPLOAD_DIR


def get_db_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _ensure_columns(cursor: sqlite3.Cursor, table_name: str, columns: Dict[str, str]) -> None:
    """Bổ sung các cột mới vào bảng hiện có để tương thích ngược với dữ liệu cũ."""
    existing = {
        row["name"]
        for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for col_name, col_def in columns.items():
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")


def init_db() -> None:
    conn = get_db_connection()
    cursor = conn.cursor()

    # =========================================================================
    # 1. PHÂN HỆ NGƯỜI DÙNG & KHÔNG GIAN LÀM VIỆC (USERS, WORKSPACES, NOTEBOOKS)
    # =========================================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        organization TEXT DEFAULT '',
        role_title TEXT DEFAULT '',
        avatar_url TEXT DEFAULT '',
        password_hash TEXT,
        google_sub TEXT UNIQUE,
        last_login_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    _ensure_columns(cursor, "users", {
        "first_name": "TEXT DEFAULT ''",
        "last_name": "TEXT DEFAULT ''",
        "phone": "TEXT DEFAULT ''",
        "organization": "TEXT DEFAULT ''",
        "role_title": "TEXT DEFAULT ''",
        "avatar_url": "TEXT DEFAULT ''",
        "last_login_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    })

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        owner_user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        category TEXT DEFAULT 'Chung',
        icon TEXT DEFAULT 'folder',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    _ensure_columns(cursor, "workspaces", {
        "owner_user_id": "TEXT REFERENCES users(id) ON DELETE CASCADE",
        "category": "TEXT DEFAULT 'Chung'",
        "icon": "TEXT DEFAULT 'folder'",
        "updated_at": "TIMESTAMP",
    })

    # Tạo workspace mặc định nếu chưa có
    cursor.execute("SELECT id FROM workspaces WHERE id = 'default'")
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO workspaces (id, name, description, category, icon)
        VALUES ('default', 'Workspace Mặc Định', 'Không gian làm việc chung lưu trữ tài liệu cá nhân', 'Chung', 'folder')
        """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notebooks (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    # =========================================================================
    # 2. PHÂN HỆ TÀI LIỆU & KHO TRI THỨC RAG (DOCUMENTS, CHUNKS, FTS5, VECTORS)
    # =========================================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        notebook_id TEXT REFERENCES notebooks(id) ON DELETE SET NULL,
        file_name TEXT NOT NULL,
        file_type TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        content_hash TEXT,
        total_pages INTEGER DEFAULT 1,
        total_chunks INTEGER DEFAULT 0,
        status TEXT NOT NULL,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    _ensure_columns(cursor, "documents", {
        "notebook_id": "TEXT REFERENCES notebooks(id) ON DELETE SET NULL",
        "content_hash": "TEXT",
        "total_pages": "INTEGER DEFAULT 1",
        "error_message": "TEXT",
    })

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS document_chunks (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        page_number INTEGER DEFAULT 1,
        token_count INTEGER DEFAULT 0,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    """)

    _ensure_columns(cursor, "document_chunks", {
        "token_count": "INTEGER DEFAULT 0",
    })

    # Bảng ảo FTS5 (Full-Text Search) cho tìm kiếm từ khóa siêu nhanh (BM25)
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        chunk_id UNINDEXED,
        document_id UNINDEXED,
        workspace_id UNINDEXED,
        content
    );
    """)

    # Bảng lưu vector embeddings BGE-M3
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chunk_embeddings (
        chunk_id TEXT PRIMARY KEY,
        model TEXT NOT NULL,
        dimensions INTEGER NOT NULL,
        vector BLOB NOT NULL,
        FOREIGN KEY (chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
    );
    """)

    # =========================================================================
    # 3. PHÂN HỆ HỘI THOẠI RAG, TRÍCH DẪN & WEB CACHE (CHAT & CITATIONS)
    # =========================================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        notebook_id TEXT REFERENCES notebooks(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        mode TEXT DEFAULT 'auto',
        model_name TEXT DEFAULT 'qwen2.5:3b',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    _ensure_columns(cursor, "chat_sessions", {
        "notebook_id": "TEXT REFERENCES notebooks(id) ON DELETE SET NULL",
        "mode": "TEXT DEFAULT 'auto'",
        "model_name": "TEXT DEFAULT 'qwen2.5:3b'",
        "updated_at": "TIMESTAMP",
    })

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        sender TEXT NOT NULL,
        content TEXT NOT NULL,
        mode_used TEXT,
        citations_json TEXT,
        latency_seconds REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
    );
    """)

    _ensure_columns(cursor, "chat_messages", {
        "mode_used": "TEXT",
        "latency_seconds": "REAL",
    })

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS web_search_cache (
        query_hash TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        results_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL
    );
    """)

    # =========================================================================
    # 4. PHÂN HỆ HỌC TẬP, GHI CHÚ & NGHIÊN CỨU (STUDY & RESEARCH ARTIFACTS)
    # =========================================================================
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        notebook_id TEXT REFERENCES notebooks(id) ON DELETE SET NULL,
        document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS study_artifacts (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,
        artifact_type TEXT NOT NULL,
        title TEXT NOT NULL,
        data_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS research_projects (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        notebook_id TEXT REFERENCES notebooks(id) ON DELETE SET NULL,
        title TEXT NOT NULL,
        question TEXT NOT NULL,
        status TEXT DEFAULT 'draft',
        selected_doc_ids TEXT,
        report_markdown TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_activities (
        id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        activity_type TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
    );
    """)

    # =========================================================================
    # 5. CHỈ MỤC TĂNG TỐC TRUY VẤN (INDEXES)
    # =========================================================================
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notebooks_workspace ON notebooks(workspace_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_workspace ON documents(workspace_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_notebook ON documents(notebook_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_docs_hash ON documents(workspace_id, content_hash);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(document_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_workspace ON document_chunks(workspace_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON chat_sessions(workspace_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_workspace ON notes(workspace_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_workspace ON study_artifacts(workspace_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_research_workspace ON research_projects(workspace_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_activities_workspace ON user_activities(workspace_id);")

    conn.commit()
    conn.close()

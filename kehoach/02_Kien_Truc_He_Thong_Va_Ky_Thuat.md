# THIẾT KẾ KIẾN TRÚC HỆ THỐNG VÀ THÔNG SỐ KỸ THUẬT
## NỀN TẢNG TRỢ LÝ TRI THỨC CÁ NHÂN ĐA NGUỒN (PERSONAL AI KNOWLEDGE PLATFORM)

> **Mã tài liệu:** SPEC-ARCH-02  
> **Phiên bản:** 1.0.0  
> **Nguyên tắc cốt lõi:** Local-First, Privacy-Preserving, Hybrid Search, Low-Latency.

---

## 1. Kiến Trúc Tổng Thể (System Architecture)

Hệ thống được tổ chức theo kiến trúc phân lớp hướng dịch vụ vi mô cục bộ (Local Modular Service-Oriented Architecture), đảm bảo tính tách biệt, dễ bảo trì và có thể chạy hoàn toàn độc lập trên máy trạm của người dùng.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    GIAO DIỆN NGƯỜI DÙNG (PRESENTATION LAYER)                │
│             React 18 + Vite + Tailwind CSS + Lucide Icons + Zustand         │
│  [Workspace View]  [Document Manager]  [Chat / Citations]  [Study Tools]   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP REST / SSE Streaming / WebSocket
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    TẦNG XỬ LÝ ỨNG DỤNG (APPLICATION BACKEND)                 │
│               Python 3.11+ / FastAPI (Async ASGI Server)                     │
│  ├── Workspace & Doc Manager (CRUD, Metadata, State Management)             │
│  ├── Task Orchestrator & Background Workers (Celery / BackgroundTasks)      │
│  └── Storage Engine (SQLite for Relational Data & Configs)                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Internal In-Memory / IPC Calls
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                      LÕI TRÍ TUỆ NHÂN TẠO (AI & RAG ENGINE)                 │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ AI ROUTER & INTENT CLASSIFIER                                         │  │
│  │  - Nhận diện ý định (Query Intent: Factoid, Analytical, Time-sens)    │  │
│  │  - Định tuyến chế độ: [LOCAL] | [ONLINE WEB] | [HYBRID]               │  │
│  │  - Fallback Handler khi mất kết nối mạng                              │  │
│  └───────────────────┬───────────────────────────────┬───────────────────┘  │
│                      │                               │                      │
│         ┌────────────▼────────────┐     ┌────────────▼────────────┐         │
│         │ LOCAL RETRIEVAL PIPELINE│     │   ONLINE SEARCH ENGINE  │         │
│         │ - Dense Search (BGE-M3) │     │ - DuckDuckGo / Tavily   │         │
│         │ - Sparse BM25 Search    │     │ - Web Scraper / Cleaner │         │
│         └────────────┬────────────┘     └────────────┬────────────┘         │
│                      │                               │                      │
│                      └───────────────┬───────────────┘                      │
│                                      ▼                                      │
│                       RECIPROCAL RANK FUSION (RRF)                          │
│                                      │                                      │
│                                      ▼                                      │
│                      CROSS-ENCODER RERANKER (BGE-v2-M3)                     │
│                                      │                                      │
│                                      ▼                                      │
│                    CONTEXT BUILDER & CITATION INJECTOR                      │
│                                      │                                      │
│                                      ▼                                      │
│                LOCAL LLM INFERENCE (Ollama API - Qwen 2.5)                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Thiết Kế Chi Tiết Hybrid RAG Pipeline

### 2.1. Quy trình Xử lý và Đánh chỉ mục Tài liệu (Ingestion Pipeline)
1. **Document Loaders:**
   * `PDF`: Sử dụng `pypdf` / `pdfplumber` để trích xuất text và giữ số trang thực tế.
   * `DOCX / PPTX`: Dùng `python-docx` và `python-pptx` duyệt qua các đoạn và slide.
   * `TXT / Markdown / Code`: Parser trực tiếp với charset UTF-8 tự động phát hiện.
2. **Text Cleaning:**
   * Chuẩn hóa Unicode (NFC), loại bỏ khoảng trắng thừa, giữ lại ngắt dòng logic.
3. **Smart Chunking Strategy:**
   * **Phương pháp:** Recursive Character Splitting kết hợp Sentence-level boundary.
   * **Kích thước chunk (Chunk Size):** 512 - 800 tokens (tương đương 1200 - 1800 ký tự).
   * **Độ gối đầu (Chunk Overlap):** 100 - 150 tokens (đảm bảo không bị mất ngữ cảnh giữa các đoạn).
   * **Metadata đính kèm:** `workspace_id`, `document_id`, `document_name`, `page_number`, `chunk_index`, `content_hash`.
4. **Dual Vectorization (BGE-M3):**
   * **Dense Embedding:** Sinh vector 1024 chiều biểu diễn ngữ nghĩa trừu tượng.
   * **Sparse Weights:** Sinh từ điển trọng số từ vựng (lexical weights) tương tự BM25 để bắt chính xác từ khóa, mã số, thuật ngữ kỹ thuật, tên riêng.
5. **Storage:**
   * Nạp vector vào **Qdrant Local** (Collection có cấu hình song song `dense` và `sparse` vector).

### 2.2. Quy trình Truy xuất & Hợp nhất (Hybrid Retrieval & Fusion)

```mermaid
flowchart TD
    UserQuery([Câu hỏi người dùng]) --> QueryPreprocess[Tiền xử lý & Mở rộng truy vấn]
    
    QueryPreprocess --> DenseSearch[Dense Vector Search: Top 20]
    QueryPreprocess --> SparseSearch[BM25 / Sparse Lexical Search: Top 20]
    
    DenseSearch --> RRF[Thuật toán Reciprocal Rank Fusion - RRF]
    SparseSearch --> RRF
    
    RRF --> TopCandidates[Danh sách Top 25 ứng viên gộp]
    TopCandidates --> CrossReranker[Cross-Encoder Reranker: bge-reranker-v2-m3]
    
    CrossReranker --> Top5Chunks[Top 4 - 5 Chunks phù hợp nhất]
    Top5Chunks --> ContextAssembler[Lắp ghép Prompt & Đánh dấu Citation [1], [2]]
    ContextAssembler --> LLM[Ollama: Qwen 2.5 3B/7B]
    LLM --> StreamAnswer[Stream câu trả lời + Metadata Citation]
```

#### Công thức Reciprocal Rank Fusion (RRF):
$$RRF\_Score(d \in D) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
* Với $k = 60$ (hằng số làm mượt chuẩn công nghiệp).
* $r_m(d)$ là thứ hạng của đoạn tài liệu $d$ trong bộ kết quả tìm kiếm thứ $m$ (Dense hoặc Sparse).

---

## 3. Thiết Kế Thuật Toán AI Router & Các Chế Độ Hoạt Động

### 3.1. Các chế độ hoạt động (Operation Modes)
1. **Local Mode (Chỉ dữ liệu máy):**
   * Tắt hoàn toàn kết nối Internet.
   * Truy vấn 100% tài liệu trong Workspace hiện tại.
   * Đảm bảo tính riêng tư tuyệt đối (Zero telemetry, Zero data leak).
2. **Online Web Mode (Chỉ Internet):**
   * Dành cho các câu hỏi tra cứu thời tiết, tin tức mới hôm nay, sự kiện vừa diễn ra, kiến thức mở rộng ngoài tài liệu.
   * Thu thập kết quả từ DuckDuckGo/Tavily, bóc tách nội dung chính của các trang web và đưa vào prompt.
3. **Hybrid Mode (Kết hợp Đa nguồn):**
   * Truy xuất đồng thời tài liệu nội bộ + thông tin thực tế từ Internet.
   * Reranker sắp xếp và tổng hợp bằng chứng từ cả 2 nguồn, cho phép so sánh đối chiếu đa chiều.
4. **Auto Mode (Tự động nhận diện qua AI Router):**
   * Sử dụng rule-based kết hợp phân loại nhanh (Fast Intent Classifier):
     * Nếu câu hỏi chứa từ khóa thời gian nhạy cảm (`hôm nay`, `năm nay`, `mới nhất`, `giá hiện tại`, `tin tức`): Kích hoạt Web Search.
     * Nếu câu hỏi gắn liền với ngữ cảnh tài liệu (`trong file`, `theo tài liệu`, `trong dự án`, `tóm tắt chương`): Chuyển về Local.
     * Nếu người dùng ép buộc chế độ trên giao diện (Toggle Switch): Bỏ qua Router tự động.
5. **Cơ chế Fallback (Mất mạng):**
   * Tự động kiểm tra mạng (`ping` timeout 1s). Nếu không có Internet khi đang ở chế độ Web/Auto, hệ thống tự động fallback về Local RAG và thông báo nhẹ nhàng cho người dùng.

---

## 4. Thiết Kế Cơ Sở Dữ Liệu Quan Hệ (Database Schema - SQLite)

Hệ thống sử dụng SQLite cục bộ kết hợp với Qdrant Vector DB:

```sql
-- 1. Bảng Quản lý Không gian làm việc
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,               -- UUID v4
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bảng Quản lý Tài liệu
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,           -- pdf, docx, txt, md, pptx
    file_size INTEGER NOT NULL,        -- Bytes
    file_path TEXT NOT NULL,           -- Đường dẫn file cục bộ
    total_pages INTEGER DEFAULT 1,
    total_chunks INTEGER DEFAULT 0,
    status TEXT NOT NULL,              -- pending, processing, indexed, error
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

-- 3. Bảng Quản lý Chunks văn bản
CREATE TABLE document_chunks (
    id TEXT PRIMARY KEY,               -- UUID
    document_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    vector_point_id TEXT NOT NULL,     -- Khóa ngoại ánh xạ sang Qdrant Point ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

-- 4. Bảng Phiên Hỏi Đáp (Chat Sessions)
CREATE TABLE chat_sessions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    title TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'auto', -- local, web, hybrid, auto
    model_name TEXT NOT NULL,          -- qwen2.5:3b-instruct
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);

-- 5. Bảng Lịch sử Tin nhắn & Trích dẫn (Messages & Citations)
CREATE TABLE chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sender TEXT NOT NULL,              -- user, assistant, system
    content TEXT NOT NULL,
    mode_used TEXT,                    -- Chế độ thực tế được kích hoạt
    citations_json TEXT,               -- Mảng JSON chứa [ { title, page, chunk_id, url, snippet } ]
    latency_seconds REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
);

-- 6. Bảng Công cụ Học tập (Flashcards & Quizzes)
CREATE TABLE study_artifacts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    document_id TEXT,
    artifact_type TEXT NOT NULL,       -- quiz, flashcard, summary, mindmap
    title TEXT NOT NULL,
    data_json TEXT NOT NULL,           -- Cấu trúc câu hỏi/câu trả lời định dạng JSON
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
);
```

---

## 5. Đặc Tả Giao Diện Lập Trình Ứng Dụng (API Specification)

Toàn bộ API được xây dựng theo chuẩn RESTful JSON kết hợp SSE (Server-Sent Events) cho phản hồi sinh text thời gian thực:

### 5.1. Nhóm Quản lý Tài liệu & Workspace
* `GET /api/v1/workspaces`: Danh sách workspace.
* `POST /api/v1/workspaces`: Tạo workspace mới.
* `POST /api/v1/workspaces/{id}/documents/upload`: Tải lên và kích hoạt pipeline xử lý tài liệu.
* `GET /api/v1/workspaces/{id}/documents`: Lấy danh sách file và tiến độ indexing.
* `DELETE /api/v1/documents/{id}`: Xóa tài liệu khỏi SQLite và xóa Vector khỏi Qdrant.

### 5.2. Nhóm Hỏi Đáp Tri Thức (Chat & RAG Engine)
* `POST /api/v1/chat/completions`:
  * **Payload:**
    ```json
    {
      "workspace_id": "ws-1234",
      "session_id": "sess-5678",
      "query": "Tài liệu này nói gì về kiến trúc Hybrid RAG?",
      "mode": "auto", // "local" | "web" | "hybrid" | "auto"
      "model": "qwen2.5:3b-instruct",
      "stream": true
    }
    ```
  * **Response (SSE Stream):**
    * `event: route_decision` -> Trả về kết quả phân tích intent và chế độ được kích hoạt.
    * `event: citations` -> Trả về danh sách trích dẫn bằng chứng (Tên tài liệu, trang, đoạn trích dẫn hoặc URL).
    * `event: delta` -> Từng token văn bản sinh ra theo thời gian thực.
    * `event: done` -> Thống kê độ trễ, số token xử lý.

### 5.3. Nhóm Công cụ Học tập (Study Assistant)
* `POST /api/v1/study/generate-summary`: Tóm tắt tài liệu theo độ dài (Bullet points, Executive, Detailed).
* `POST /api/v1/study/generate-quiz`: Tự động trích xuất các ý chính và sinh bộ câu hỏi trắc nghiệm kèm đáp án giải thích.
* `POST /api/v1/study/generate-flashcards`: Tạo bộ thẻ ghi nhớ hỏi-đáp phục vụ ôn thi, ghi nhớ thuật ngữ.

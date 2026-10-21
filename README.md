# Personal AI Knowledge Platform (PBL6)

> **Xây dựng Nền tảng Trợ lý Tri thức Cá nhân Đa nguồn sử dụng Hybrid RAG và Large Language Model**  
> *Hỗ trợ hoạt động Offline và khai thác thông tin Online*

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python)](https://python.org)
[![Ollama](https://img.shields.io/badge/Local%20LLM-Ollama%20(Qwen%202.5)-black)](https://ollama.com)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20FTS5-003B57?logo=sqlite)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## 📌 1. Giới Thiệu Đề Tài
Dự án nhằm giải quyết bài toán quản lý và khai thác tri thức cá nhân theo hướng **Local-first**:
* **Bảo mật tuyệt đối & Hoạt động Offline**: Dữ liệu tài liệu cá nhân được lưu trữ và xử lý cục bộ trên máy tính. Chạy thông qua mô hình mã nguồn mở cục bộ (**Qwen 2.5 3B/7B**) bằng **Ollama**, không gửi dữ liệu ra bên ngoài khi chưa có sự đồng ý.
* **Khai thác Online khi cần**: Kết hợp công cụ tìm kiếm Web khi người dùng hỏi các thông tin thời sự, mới nhất.
* **Hybrid RAG Pipeline**: Kết hợp giữa **Dense Vector Search** (ngữ nghĩa) và **Sparse Lexical Search** (BM25 / FTS5), gộp kết quả qua **Reciprocal Rank Fusion (RRF)** và lọc lại bằng **Cross-Encoder Reranker** để loại bỏ ảo giác (hallucination).
* **Grounded Generation & Citations**: Mọi câu trả lời đều được gắn nhãn trích dẫn nguồn (tên tài liệu, trang, đoạn trích) để kiểm chứng.

---

## 📂 2. Cấu Trúc Dự Án

```
PBL6/
├── kehoach/                        # Tài liệu nghiên cứu & Kế hoạch WBS
│   ├── 01_So_Sanh_Va_Lua_Chon_Mo_Hinh_AI.md
│   ├── 02_Kien_Truc_He_Thong_Va_Ky_Thuat.md
│   ├── 03_Ke_Hoach_Trien_Khai_Va_Lo_Trinh.md
│   ├── 04_Bang_Phan_Chia_Cong_Viec_Nhom_3_Nguoi.md
│   ├── Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx   # File Excel phân chia 28 tasks
│   └── README.md
├── sourcecode/
│   └── backend/                    # Máy chủ FastAPI & Lõi RAG
│       ├── app/
│       │   ├── api/                # API Endpoints (Workspaces, Documents, Chat)
│       │   ├── services/           # Document Parser, Retrieval FTS5, LLM Service
│       │   ├── static/             # Giao diện Web UI (HTML5 + Tailwind)
│       │   ├── config.py           # Cấu hình hệ thống
│       │   ├── database.py         # CSDL SQLite & FTS5
│       │   └── main.py             # Entrypoint FastAPI
│       ├── data/                   # Thư mục chứa SQLite database & uploads
│       ├── requirements.txt
│       └── run.py
├── tailieu/                        # Tài liệu tổng quan đề tài gốc (.docx)
├── .gitignore
├── start_app.bat                   # Script khởi động 1-click
└── README.md
```

---

## 🚀 3. Hướng Dẫn Cài Đặt & Khởi Chạy

### Yêu cầu hệ thống:
* **Hệ điều hành:** Windows 10/11, Linux, macOS.
* **Python:** 3.10 trở lên.
* **Ollama:** Cài đặt từ [ollama.com](https://ollama.com/download).

### Bước 1: Clone Repository
```bash
git clone https://github.com/TruyenThanhhhh/<tên-repo>.git
cd PBL6
```

### Bước 2: Cài Đặt Thư Viện Python
```bash
cd sourcecode/backend
pip install -r requirements.txt
```

### Bước 3: Tải Mô Hình AI Cục Bộ (Ollama)
```bash
ollama run qwen2.5:3b
```

Để dán ảnh chụp màn hình vào hộp thoại chat và nhờ AI phân tích ảnh, cần tải thêm model vision:
```bash
ollama pull qwen2.5vl:3b
```
Model này được dùng riêng cho câu hỏi có ảnh; chat văn bản vẫn dùng `qwen2.5:3b`. Tên model vision có thể đổi bằng biến `VISION_MODEL` trong `sourcecode/backend/.env`.

### Bước 4: Khởi Chạy Ứng Dụng
* **Cách 1:** Nhấp đúp vào file `start_app.bat` ở thư mục gốc.
* **Cách 2:** Chạy bằng dòng lệnh:
```bash
cd sourcecode/backend
python run.py
```
* Mở trình duyệt Web tại: **http://localhost:8000**
* Xem Swagger API Docs: **http://localhost:8000/docs**

---

## 👥 4. Phân Công Trách Nhiệm Nhóm 3 Thành Viên
* **Thành viên 1 (Lead & AI Specialist):** Lõi AI, Mô hình LLM (Ollama), Dense Embedding (BGE-M3), Reranker, RRF, Prompt Engineering, Benchmark Ragas.
* **Thành viên 2 (Backend & Data Engineer):** Parser tài liệu (PDF/DOCX/PPTX), CSDL SQLite FTS5, API FastAPI, Web Search, AI Router.
* **Thành viên 3 (Frontend & Feature Dev):** Giao diện Web UI, Quản lý Workspace, Citation Viewer, Bộ công cụ học tập (Flashcards/Quiz), Slide thuyết trình.

Chi tiết phân chia 28 công việc theo dõi tại: [`kehoach/Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx`](./kehoach/Phan_Chia_Cong_Viec_Nhom_3_Nguoi_PBL6.xlsx).

---

## Backend API (đang triển khai)

Backend nằm trong `sourcecode/backend`. Cài dependencies và khởi chạy:

```bash
cd sourcecode/backend
pip install -r requirements.txt
python run.py
```

SQLite được lưu tại `sourcecode/backend/data/knowledge.db`; tệp tải lên nằm trong `data/uploads/`. Tài liệu hỗ trợ: PDF, DOCX, PPTX, TXT, MD, PY, JSON và CSV. PDF/DOCX/PPTX được chia chunk theo trang/slide để giữ thông tin hiển thị trong citations.

### API chính

| Method | Endpoint | Mục đích |
|---|---|---|
| `GET` | `/api/v1/status` | Trạng thái Ollama, FTS5, embedding và Web Search |
| `POST` | `/api/v1/auth/register` | Tạo tài khoản email/mật khẩu (mật khẩu tối thiểu 10 ký tự) |
| `POST` | `/api/v1/auth/login` | Đăng nhập và nhận bearer token |
| `GET` | `/api/v1/auth/me` | Kiểm tra phiên đăng nhập |
| `GET` | `/api/v1/auth/google` | Bắt đầu đăng nhập Google OAuth |
| `GET` / `POST` | `/api/v1/workspaces` | Liệt kê / tạo workspace |
| `GET` | `/api/v1/workspaces/{id}/documents` | Liệt kê tài liệu |
| `POST` | `/api/v1/workspaces/{id}/documents/upload` | Upload và lập chỉ mục tài liệu (multipart field `file`) |
| `DELETE` | `/api/v1/documents/{id}` | Xóa tài liệu và index liên quan |
| `POST` | `/api/v1/documents/{id}/reindex-vectors` | Tạo lại BGE-M3 vectors khi lúc upload model chưa sẵn sàng |
| `GET` | `/api/v1/documents/{id}/chunks/{chunk_index}` | Lấy nguyên văn đoạn để Citation Modal hiển thị |
| `POST` | `/api/v1/chat/query` | Hỏi đáp RAG, citations; có thể bật tìm web |
| `POST` | `/api/v1/search/web` | Tìm web trực tiếp |

Ví dụ body cho chat:

```json
{
  "workspace_id": "default",
  "query": "Tóm tắt nội dung tài liệu",
  "web_search": false,
  "top_k": 4
}
```

`citations[]` trả `source_type` (`document` hoặc `web`), `ref_id`, tên tài liệu, trang, `chunk_index`, snippet hoặc URL để frontend dựng Citation Modal. Với citation tài liệu, endpoint chunk trả lại nội dung đầy đủ.

### Cấu hình tùy chọn

Các biến môi trường: `OLLAMA_BASE_URL`, `DEFAULT_LLM_MODEL`, `VISION_MODEL`, `ENABLE_DENSE_RETRIEVAL`, `EMBEDDING_MODEL`, `WEB_SEARCH_ENABLED`, `DUCKDUCKGO_API_URL`, `WEB_SEARCH_TIMEOUT`, `UPLOAD_MAX_BYTES`. Dense retrieval dùng `fastembed` với `BAAI/bge-m3`; lần đầu chạy có thể cần tải model. Nếu embedding không khả dụng, văn bản vẫn được lập chỉ mục bằng FTS5. Chat chạy local qua Ollama; khi Ollama lỗi, API trả các đoạn nguồn trích xuất trực tiếp. Web Search chỉ chạy khi request đặt `web_search: true`; lỗi mạng sẽ được ghi vào `web_search` và pipeline vẫn dùng nguồn local.

### Tài khoản và Google Login

Email/mật khẩu hoạt động sau khi cài requirements. Mật khẩu được lưu bằng PBKDF2; mỗi tài khoản có workspace riêng và các API tài liệu/chat yêu cầu bearer token. Workspace `default` cũ được gán cho tài khoản đầu tiên đăng nhập để giữ dữ liệu prototype hiện có.

Để bật Google Login, tạo OAuth Client ID loại **Web application** trong Google Cloud Console và thêm callback URI `http://localhost:8000/api/v1/auth/google/callback`. Sau đó đặt biến môi trường trước khi chạy server:

```powershell
$env:GOOGLE_CLIENT_ID="your-client-id"
$env:GOOGLE_CLIENT_SECRET="your-client-secret"
$env:APP_SECRET_KEY="a-long-random-secret"
python run.py
```

Google Login bị vô hiệu hóa trên giao diện cho đến khi có cả Client ID và Client Secret. Callback mặc định là `http://localhost:8000/api/v1/auth/google/callback` và có thể đổi bằng `GOOGLE_REDIRECT_URI`. Giá trị `APP_SECRET_KEY` mặc định chỉ dành cho phát triển local; hãy đặt secret riêng trước khi triển khai.

Backend cũng tự đọc `sourcecode/backend/.env` khi khởi động. File này được Git bỏ qua; có thể đặt `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` và `APP_SECRET_KEY` tại đó để không phải khai báo lại trong mỗi cửa sổ PowerShell.
